"""Turning an arbitrary MusicXML score into a whistle melody (Add song).

See TECHNICAL_SPEC.md "Song import". The steps are: read every part, staff,
and voice; write out repeats and jumps; offer one candidate line per part and
staff; take the top notes of the chosen line (skyline); move it by octaves
into the whistle range; and write it in the app's MusicXML subset.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

from whistle_trainer import config
from whistle_trainer.music.model import NOTE_TYPES, KeySignature, Pitch, Song, TimeSignature, notated_length
from whistle_trainer.music.musicxml import parse_string
from whistle_trainer.music.transpose import diatonic_steps_for, transpose_key, transpose_pitch

# Notation grid: 1/24 of a quarter note holds both thirty-second notes and sixteenth-note triplets.
GRID = 24
WHISTLE_LOW, WHISTLE_HIGH = 74, 88  # D5 to E6
MELODY_NAMES = re.compile(r"voice|vocal|vox|melod|lead|soprano|singer|chant|canto|gesang", re.IGNORECASE)
MAX_UNROLLED_FACTOR = 8  # protection against endless repeat structures

_PLAIN_TYPES = ["whole", "half", "quarter", "eighth", "16th", "32nd"]
_TRIPLET_TYPES = ["half", "quarter", "eighth", "16th", "32nd"]


class ScoreImportError(Exception):
    """The file cannot be imported; the message says why."""


@dataclass
class _Note:
    start: Fraction  # quarters from the start of the measure (when read) or of the song (when unrolled)
    duration: Fraction
    pitch: Pitch | None  # sounding; None for rests
    staff: int
    voice: str
    tie_start: bool = False
    tie_stop: bool = False
    note_type: str | None = None
    dots: int = 0
    tuplet: tuple[int, int] | None = None


@dataclass
class _SourceMeasure:
    number: str
    duration: Fraction
    key: KeySignature
    time: TimeSignature
    implicit: bool
    content: Fraction = Fraction(0)  # length of the written notes, which may not match the time signature
    fitted: str = ""  # "long" or "short" if the measure was fitted to its time signature
    notes: dict[int, list[_Note]] = field(default_factory=dict)  # by part index
    grace_notes: dict[tuple[int, int], int] = field(default_factory=dict)  # by (part index, staff)
    forward_repeat: bool = False
    backward_repeat: int = 0  # times to play; 0 if none
    endings: frozenset[int] = frozenset()
    ending_starts: bool = False
    segno: bool = False
    coda: bool = False
    to_coda: bool = False
    fine: bool = False
    da_capo: bool = False
    dal_segno: bool = False


@dataclass(frozen=True)
class Candidate:
    part_index: int
    staff: int
    label: str
    note_count: int
    low: str  # sounding range as note names, before octave placement
    high: str


@dataclass
class ImportReport:
    line: str
    notes_left_out: int
    grace_notes_removed: int
    measures_written_out: int
    notes_rounded: int
    octave_shift: int  # semitones, a multiple of 12
    measures_too_long: int = 0  # notes past the barline were cut
    measures_too_short: int = 0  # filled with rest


@dataclass
class ImportResult:
    xml: str
    song: Song
    report: ImportReport


@dataclass
class ImportedScore:
    title: str
    file_name: str
    tempo: int
    candidates: list[Candidate]
    default_candidate: int
    measures: list[_SourceMeasure]  # in playing order, repeats written out
    source_measure_count: int


# Reading


def read_score(path: Path) -> ImportedScore:
    """Read and unroll a score file (.musicxml, .xml, or compressed .mxl)."""
    try:
        if path.suffix.lower() == ".mxl":
            text = _read_mxl(path)
        else:
            text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, KeyError) as error:
        raise ScoreImportError(f"The file could not be read ({error}).") from error
    return read_score_text(text, path.name)


def _read_mxl(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = next((e for e in container.iter() if e.tag.endswith("rootfile")), None)
        if rootfile is None or not rootfile.get("full-path"):
            raise ScoreImportError("The compressed file does not say which score it contains.")
        return archive.read(rootfile.get("full-path")).decode("utf-8")


def read_score_text(text: str, file_name: str) -> ImportedScore:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ScoreImportError(f"The file is not valid MusicXML ({error}).") from error
    if root.tag == "score-timewise":
        raise ScoreImportError("Timewise MusicXML is not supported; export the score as partwise MusicXML.")
    if root.tag != "score-partwise":
        raise ScoreImportError("The file is not a MusicXML score.")
    parts = root.findall("part")
    if not parts:
        raise ScoreImportError("The score has no parts.")
    names = {p.get("id"): (p.findtext("part-name") or "").strip() for p in root.findall("part-list/score-part")}

    measure_count = len(parts[0].findall("measure"))
    measures: list[_SourceMeasure] | None = None
    tempo: float | None = None
    staff_counts: list[int] = []
    has_lyrics: list[bool] = []
    for part_index, part in enumerate(parts):
        reader = _PartReader(part_index, measures)
        measures = reader.read(part)
        tempo = tempo or reader.tempo
        staff_counts.append(reader.staves)
        has_lyrics.append(reader.has_lyrics)
    if len(measures) != measure_count or measure_count == 0:
        raise ScoreImportError("The score has no measures.")

    order = _unroll(measures)
    played = [measures[i] for i in order]
    title = (root.findtext("work/work-title") or root.findtext("movement-title") or "").strip()

    candidates = []
    for part_index, part in enumerate(parts):
        part_name = names.get(part.get("id")) or f"Part {part_index + 1}"
        for staff in range(1, staff_counts[part_index] + 1):
            pitches = [n.pitch for m in measures for n in m.notes.get(part_index, [])
                       if n.staff == staff and n.pitch is not None]
            if not pitches:
                continue
            if staff_counts[part_index] == 1:
                label = part_name
            else:
                label = f"{part_name}, {'upper' if staff == 1 else 'lower' if staff == 2 else f'staff {staff}'} staff"
            low, high = min(pitches, key=lambda p: p.midi), max(pitches, key=lambda p: p.midi)
            candidates.append(Candidate(part_index, staff, label, len(pitches), low.name, high.name))
    if not candidates:
        raise ScoreImportError("The score contains no notes.")

    default = 0
    if len(parts) > 1:
        for index, candidate in enumerate(candidates):
            part_name = names.get(parts[candidate.part_index].get("id"), "")
            if MELODY_NAMES.search(part_name) or has_lyrics[candidate.part_index]:
                default = index
                break
    return ImportedScore(
        title=title or Path(file_name).stem,
        file_name=file_name,
        tempo=round(tempo or config.DEFAULT_TEMPO),
        candidates=candidates,
        default_candidate=default,
        measures=played,
        source_measure_count=measure_count,
    )


class _PartReader:
    """Reads one part; the first part also defines measures, signatures, repeats, and jumps."""

    def __init__(self, part_index: int, measures: list[_SourceMeasure] | None):
        self.part_index = part_index
        self.first = measures is None
        self.measures = measures or []
        self.divisions = 1
        self.key = KeySignature(0)
        self.time = TimeSignature(4, 4)
        self.transpose = (0, 0)  # (diatonic, chromatic)
        self.tempo: float | None = None
        self.staves = 1
        self.has_lyrics = False
        self.measure_number = "?"

    def error(self, message: str) -> ScoreImportError:
        return ScoreImportError(f"Measure {self.measure_number}: {message}")

    def read(self, part: ET.Element) -> list[_SourceMeasure]:
        open_ending: frozenset[int] = frozenset()
        for index, element in enumerate(part.findall("measure")):
            self.measure_number = element.get("number", str(index + 1))
            notes: list[_Note] = []
            cursor = longest = Fraction(0)
            last_start = Fraction(0)
            grace: dict[int, int] = {}
            flags: dict[str, object] = {}
            for child in element:
                tag = child.tag
                if tag == "attributes":
                    self._attributes(child)
                elif tag == "backup":
                    cursor -= self._duration(child)
                elif tag == "forward":
                    cursor += self._duration(child)
                elif tag == "note":
                    if child.find("grace") is not None or child.find("cue") is not None:
                        if child.find("grace") is not None and child.find("pitch") is not None:
                            staff = int((child.findtext("staff") or "1").strip() or 1)
                            grace[staff] = grace.get(staff, 0) + 1
                        continue
                    duration = self._duration(child)
                    start = last_start if child.find("chord") is not None else cursor
                    if child.find("chord") is None:
                        last_start = cursor
                        cursor += duration
                    note = self._note(child, start, duration)
                    if note is not None:
                        notes.append(note)
                    if child.find("lyric") is not None:
                        self.has_lyrics = True
                elif tag in ("direction", "sound"):
                    self._direction(child, flags)
                elif tag == "barline" and self.first:
                    open_ending = self._barline(child, flags, open_ending)
                longest = max(longest, cursor)
            if self.first:
                if open_ending:
                    flags.setdefault("endings", open_ending)
                measure = _SourceMeasure(self.measure_number, self.time.measure_length, self.key, self.time,
                                         element.get("implicit") == "yes", content=longest)
                for name, value in flags.items():
                    setattr(measure, name, value)
                self.measures.append(measure)
            if index < len(self.measures):
                measure = self.measures[index]
                measure.notes.setdefault(self.part_index, []).extend(notes)
                for staff, count in grace.items():
                    measure.grace_notes[(self.part_index, staff)] = count
        if self.first:
            _fit_measures(self.measures)
        return self.measures

    def _duration(self, element: ET.Element) -> Fraction:
        text = (element.findtext("duration") or "0").strip()
        try:
            return Fraction(int(float(text) * 1000), 1000 * self.divisions)
        except ValueError:
            raise self.error(f"invalid duration {text!r}") from None

    def _attributes(self, element: ET.Element) -> None:
        if (divisions := element.findtext("divisions")) is not None:
            try:
                self.divisions = int(float(divisions))
            except ValueError:
                raise self.error(f"invalid divisions {divisions!r}") from None
        if (staves := element.findtext("staves")) is not None:
            self.staves = max(self.staves, int(staves))
        key = element.find("key")
        if key is not None and key.findtext("fifths") is not None:
            fifths = max(-7, min(7, int(key.findtext("fifths"))))
            chromatic = self.transpose[1]
            written = KeySignature(fifths, key.findtext("mode", "major"))
            self.key = transpose_key(written, chromatic) if chromatic % 12 else written
        time = element.find("time")
        if time is not None and time.findtext("beats") and time.findtext("beat-type"):
            beats = time.findtext("beats")
            # Compound numerators such as "3+2" add up.
            total = sum(int(b) for b in re.findall(r"\d+", beats))
            self.time = TimeSignature(max(1, total), int(time.findtext("beat-type")))
        transpose = element.find("transpose")
        if transpose is not None:
            octave = int(transpose.findtext("octave-change", "0"))
            chromatic = int(transpose.findtext("chromatic", "0"))
            diatonic_text = transpose.findtext("diatonic")
            diatonic = int(diatonic_text) if diatonic_text else diatonic_steps_for(chromatic)
            self.transpose = (diatonic + 7 * octave, chromatic + 12 * octave)

    def _note(self, element: ET.Element, start: Fraction, duration: Fraction) -> _Note | None:
        staff = int((element.findtext("staff") or "1").strip() or 1)
        voice = (element.findtext("voice") or "1").strip()
        if element.find("rest") is not None or element.find("unpitched") is not None or duration <= 0:
            return None
        pitch_element = element.find("pitch")
        if pitch_element is None:
            return None
        alter = round(float(pitch_element.findtext("alter", "0") or 0))
        try:
            written = Pitch(pitch_element.findtext("step", "C").strip(), max(-2, min(2, alter)),
                            int(pitch_element.findtext("octave", "4")))
        except ValueError:
            raise self.error("a note has an invalid pitch") from None
        diatonic, chromatic = self.transpose
        pitch = transpose_pitch(written, diatonic, chromatic) if (diatonic or chromatic) else written
        ties = {tie.get("type") for tie in element.findall("tie")}
        note_type = (element.findtext("type") or "").strip() or None
        modification = element.find("time-modification")
        tuplet = None
        if modification is not None:
            try:
                actual = int(modification.findtext("actual-notes"))
                normal = int(modification.findtext("normal-notes"))
                tuplet = (actual, normal) if actual != normal else None
            except (TypeError, ValueError):
                tuplet = None
        return _Note(start, duration, pitch, staff, voice, "start" in ties, "stop" in ties,
                     note_type if note_type in NOTE_TYPES else None, len(element.findall("dot")), tuplet)

    def _direction(self, element: ET.Element, flags: dict[str, object]) -> None:
        sounds = [element] if element.tag == "sound" else element.findall("sound")
        for sound in sounds:
            if self.tempo is None and sound.get("tempo"):
                try:
                    self.tempo = float(sound.get("tempo"))
                except ValueError:
                    pass
            if not self.first:
                continue
            if sound.get("segno"):
                flags["segno"] = True
            if sound.get("coda"):
                flags["coda"] = True
            if sound.get("tocoda"):
                flags["to_coda"] = True
            if sound.get("fine"):
                flags["fine"] = True
            if sound.get("dacapo") == "yes":
                flags["da_capo"] = True
            if sound.get("dalsegno"):
                flags["dal_segno"] = True
        if self.first and element.tag == "direction":
            if element.find("direction-type/segno") is not None:
                flags["segno"] = True
            if element.find("direction-type/coda") is not None and not flags.get("to_coda"):
                if not any(s.get("tocoda") for s in sounds):
                    flags["coda"] = True
        metronome = element.find("direction-type/metronome") if element.tag == "direction" else None
        if self.tempo is None and metronome is not None:
            unit, per_minute = metronome.findtext("beat-unit"), metronome.findtext("per-minute")
            if unit in NOTE_TYPES and per_minute:
                try:
                    dots = len(metronome.findall("beat-unit-dot"))
                    self.tempo = float(per_minute) * float(notated_length(unit, dots))
                except ValueError:
                    pass

    def _barline(self, element: ET.Element, flags: dict[str, object], open_ending: frozenset[int]) -> frozenset[int]:
        repeat = element.find("repeat")
        if repeat is not None:
            if repeat.get("direction") == "forward":
                flags["forward_repeat"] = True
            elif repeat.get("direction") == "backward":
                flags["backward_repeat"] = int(repeat.get("times", "2") or 2)
        ending = element.find("ending")
        if ending is not None:
            numbers = frozenset(_ending_numbers(ending.get("number", "")))
            if ending.get("type") == "start":
                flags["endings"] = numbers
                flags["ending_starts"] = True
                return numbers
            if ending.get("type") in ("stop", "discontinue"):
                flags["endings"] = flags.get("endings") or open_ending or numbers
                return frozenset()
        return open_ending


def _fit_measures(measures: list[_SourceMeasure]) -> None:
    """Give every measure the length of its time signature, as recognition errors often break it.

    A shorter first or last measure (a pickup and its completion) and measures marked implicit
    keep their written length. Notes past a fitted barline are cut; a short measure is filled with rest.
    """
    last = len(measures) - 1
    for index, measure in enumerate(measures):
        nominal = measure.time.measure_length
        if measure.content <= 0:
            continue
        if measure.content < nominal and (measure.implicit or index in (0, last)):
            measure.duration, measure.implicit = measure.content, True
        elif measure.content != nominal:
            measure.fitted = "long" if measure.content > nominal else "short"


def _ending_numbers(text: str) -> list[int]:
    numbers = []
    for piece in re.split(r"[,\s]+", text.strip()):
        if "-" in piece:
            first, _, last = piece.partition("-")
            if first.isdigit() and last.isdigit():
                numbers.extend(range(int(first), int(last) + 1))
        elif piece.isdigit():
            numbers.append(int(piece))
    return numbers


# Writing out repeats and jumps


def _unroll(measures: list[_SourceMeasure]) -> list[int]:
    """Measure indexes in playing order."""
    count = len(measures)
    segno = next((i for i, m in enumerate(measures) if m.segno), None)
    coda = next((i for i, m in enumerate(measures) if m.coda and not m.to_coda), None)
    groups = _ending_groups(measures)
    order: list[int] = []
    section_start = 0
    passes: dict[int, int] = {}  # backward repeat index -> passes played
    current_pass = 1
    jumped = False
    index = 0
    while index < count:
        if len(order) > MAX_UNROLLED_FACTOR * count + 64:
            raise ScoreImportError("The repeats and jumps in this score do not come to an end.")
        measure = measures[index]
        if measure.endings:
            wanted = groups[index] if jumped else current_pass
            if wanted not in measure.endings:
                index += 1
                continue
        if measure.forward_repeat and not jumped and index != section_start:
            section_start, current_pass = index, 1
        order.append(index)
        if jumped and measure.fine:
            break
        if jumped and measure.to_coda:
            if coda is None:
                raise ScoreImportError(f"Measure {measure.number}: “To Coda” has no coda to jump to.")
            index = coda
            continue
        if measure.backward_repeat and not jumped:
            played = passes.get(index, 1)
            if played < measure.backward_repeat:
                passes[index] = played + 1
                current_pass = played + 1
                index = section_start
                continue
            section_start, current_pass = index + 1, 1
        if (measure.da_capo or measure.dal_segno) and not jumped:
            if measure.dal_segno and segno is None:
                raise ScoreImportError(f"Measure {measure.number}: “D.S.” has no segno to jump to.")
            jumped = True
            index = 0 if measure.da_capo else segno
            continue
        index += 1
    return order


def _ending_groups(measures: list[_SourceMeasure]) -> dict[int, int]:
    """For every measure in a group of endings, the highest ending number of that group."""
    groups: dict[int, int] = {}
    run: list[int] = []
    for index, measure in enumerate(measures + [None]):
        if measure is not None and measure.endings:
            run.append(index)
            continue
        if run:
            highest = max(max(measures[i].endings) for i in run)
            groups.update({i: highest for i in run})
            run = []
    return groups


# Extracting the melody


def extract(score: ImportedScore, candidate_index: int) -> ImportResult:
    candidate = score.candidates[candidate_index]
    notes, starts = [], []
    position = Fraction(0)
    for measure in score.measures:
        starts.append(position)
        for note in measure.notes.get(candidate.part_index, []):
            if note.staff == candidate.staff and note.pitch is not None and note.start < measure.duration:
                duration = min(note.duration, measure.duration - note.start)
                notes.append(_copy(note, start=position + note.start, duration=duration,
                                   tie_start=note.tie_start and duration == note.duration))
        position += measure.duration
    total = position
    merged = _merge_ties(notes)
    melody = _skyline(merged)
    shift = _octave_shift([n.pitch.midi for n in melody])
    for note in melody:
        note.pitch = note.pitch.shifted_octaves(shift // 12)

    xml, rounded = _write(score, melody, starts, total)
    report = ImportReport(
        line=candidate.label,
        notes_left_out=len(merged) - len(melody),
        grace_notes_removed=sum(m.grace_notes.get((candidate.part_index, candidate.staff), 0) for m in score.measures),
        measures_written_out=len(score.measures) - score.source_measure_count,
        notes_rounded=rounded,
        octave_shift=shift,
        measures_too_long=sum(m.fitted == "long" for m in score.measures),
        measures_too_short=sum(m.fitted == "short" for m in score.measures),
    )
    song = parse_string(xml, song_id="import-preview", file_name=score.file_name)
    return ImportResult(xml, song, report)


def _copy(note: _Note, **changes) -> _Note:
    values = dict(note.__dict__)
    values.update(changes)
    return _Note(**values)


def _merge_ties(notes: list[_Note]) -> list[_Note]:
    """Tied notes of the same pitch become one note."""
    notes = sorted(notes, key=lambda n: (n.start, -n.pitch.midi))
    by_start: dict[tuple[Fraction, int], list[_Note]] = {}
    for note in notes:
        by_start.setdefault((note.start, note.pitch.midi), []).append(note)
    used: set[int] = set()
    merged = []
    for note in notes:
        if id(note) in used:
            continue
        current = _copy(note)
        tail = note
        while tail.tie_start:
            following = next((n for n in by_start.get((current.start + current.duration, note.pitch.midi), [])
                              if id(n) not in used and n.tie_stop), None)
            if following is None:
                break
            used.add(id(following))
            current.duration += following.duration
            current.note_type, current.tuplet = None, None  # the merged length is notated afresh
            tail = following
        merged.append(current)
    return merged


def _skyline(notes: list[_Note]) -> list[_Note]:
    """The highest note at each onset, unless a higher melody note is still sounding."""
    melody: list[_Note] = []
    for start in sorted({n.start for n in notes}):
        top = max((n for n in notes if n.start == start), key=lambda n: n.pitch.midi)
        if melody:
            current = melody[-1]
            if current.start + current.duration > start:
                if top.pitch.midi < current.pitch.midi:
                    continue
                current.duration = start - current.start
                current.note_type, current.tuplet = None, None
        melody.append(_copy(top))
    return melody


def _octave_shift(midis: list[int]) -> int:
    """Whole octaves that keep the melody inside the whistle range as far as possible, then center it."""
    low, high = min(midis), max(midis)
    center = (WHISTLE_LOW + WHISTLE_HIGH) / 2

    def score(shift: int) -> tuple[int, float, int]:
        overflow = max(0, WHISTLE_LOW - (low + shift)) + max(0, high + shift - WHISTLE_HIGH)
        return overflow, abs((low + high) / 2 + shift - center), abs(shift)

    return min((12 * k for k in range(-5, 6)), key=score)


# Writing the subset


@lru_cache(maxsize=None)
def _atoms() -> tuple[tuple[int, str, int, bool], ...]:
    """Notatable lengths in grid units: (units, type, dots, triplet), plain values first."""
    atoms = []
    for note_type in _PLAIN_TYPES:
        for dots in (0, 1):
            units = notated_length(note_type, dots) * GRID
            if units.denominator == 1:
                atoms.append((int(units), note_type, dots, False))
    for note_type in _TRIPLET_TYPES:
        units = notated_length(note_type, 0) * Fraction(2, 3) * GRID
        if units.denominator == 1:
            atoms.append((int(units), note_type, 0, True))
    return tuple(sorted(atoms, key=lambda a: (-a[0], a[3])))


@lru_cache(maxsize=None)
def _decompose(units: int) -> tuple[tuple[int, str, int, bool], ...] | None:
    """The fewest atoms adding up to `units`, preferring plain values; None if impossible."""
    if units == 0:
        return ()
    best = None
    for atom in _atoms():
        if atom[0] <= units:
            rest = _decompose(units - atom[0])
            if rest is not None and (best is None or len(rest) + 1 < len(best)
                                     or (len(rest) + 1 == len(best) and sum(a[3] for a in rest) + atom[3] < sum(a[3] for a in best))):
                best = (atom, *rest)
    return best


def _to_grid(value: Fraction) -> int:
    return round(value * GRID)


def _write(score: ImportedScore, melody: list[_Note], starts: list[Fraction], total: Fraction) -> tuple[str, int]:
    rounded = sum(1 for n in melody if (n.start * GRID).denominator != 1 or (n.duration * GRID).denominator != 1)
    # Events on the grid: (start, end, pitch, original notation).
    events = []
    for note in melody:
        start, end = _to_grid(note.start), _to_grid(note.start + note.duration)
        if events and start < events[-1][1]:
            start = events[-1][1]
        if end - start >= 2:
            events.append((start, end, note.pitch, note))
    boundaries = [_to_grid(s) for s in starts] + [_to_grid(total)]

    root = ET.Element("score-partwise", version="4.0")
    ET.SubElement(ET.SubElement(root, "work"), "work-title").text = score.title
    identification = ET.SubElement(root, "identification")
    ET.SubElement(identification, "source").text = f"Melody imported by Whistle Trainer from {score.file_name}"
    part_list = ET.SubElement(root, "part-list")
    ET.SubElement(ET.SubElement(part_list, "score-part", id="P1"), "part-name").text = "Whistle"
    part = ET.SubElement(root, "part", id="P1")

    previous: _SourceMeasure | None = None
    event_index = 0
    for number, measure in enumerate(score.measures):
        begin, end = boundaries[number], boundaries[number + 1]
        element = ET.SubElement(part, "measure", number=str(number + 1))
        if measure.implicit and 0 < number < len(score.measures) - 1:
            element.set("implicit", "yes")
        if previous is None or measure.key != previous.key or measure.time != previous.time or number == 0:
            attrs = ET.SubElement(element, "attributes")
            if number == 0:
                ET.SubElement(attrs, "divisions").text = str(GRID)
            if previous is None or measure.key != previous.key:
                key = ET.SubElement(attrs, "key")
                ET.SubElement(key, "fifths").text = str(measure.key.fifths)
                ET.SubElement(key, "mode").text = measure.key.mode
            if previous is None or measure.time != previous.time:
                time = ET.SubElement(attrs, "time")
                ET.SubElement(time, "beats").text = str(measure.time.beats)
                ET.SubElement(time, "beat-type").text = str(measure.time.beat_type)
            if number == 0:
                clef = ET.SubElement(attrs, "clef")
                ET.SubElement(clef, "sign").text = "G"
                ET.SubElement(clef, "line").text = "2"
                transpose = ET.SubElement(attrs, "transpose")
                ET.SubElement(transpose, "diatonic").text = "0"
                ET.SubElement(transpose, "chromatic").text = "0"
                ET.SubElement(transpose, "octave-change").text = str(-config.WRITTEN_OCTAVE_OFFSET)
        if number == 0:
            direction = ET.SubElement(element, "direction", placement="above")
            ET.SubElement(direction, "sound", tempo=str(min(max(score.tempo, config.MIN_TEMPO), config.MAX_TEMPO)))
        previous = measure

        cursor = begin
        segments: list[tuple[int, int, object]] = []  # (start, end, event or None for a rest)
        while event_index < len(events) and events[event_index][0] < end:
            event = events[event_index]
            segment_start, segment_end = max(event[0], begin), min(event[1], end)
            if segment_start > cursor:
                segments.append((cursor, segment_start, None))
            segments.append((segment_start, segment_end, event))
            cursor = segment_end
            if event[1] <= end:
                event_index += 1
            else:
                break
        if cursor < end:
            segments.append((cursor, end, None))
        segments = _absorb_slivers(segments)

        if len(segments) == 1 and segments[0][2] is None:
            note = ET.SubElement(element, "note")
            ET.SubElement(note, "rest", measure="yes")
            ET.SubElement(note, "duration").text = str(end - begin)
            continue
        for segment_start, segment_end, event in segments:
            _write_segment(element, segment_start, segment_end, event, begin, end)

    ET.indent(root)
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
    return xml, rounded


def _absorb_slivers(segments: list[tuple[int, int, object]]) -> list[tuple[int, int, object]]:
    """Segments of one grid unit cannot be written; merge each into its neighbor."""
    result: list[tuple[int, int, object]] = []
    for segment in segments:
        if segment[1] - segment[0] == 1 and result:
            start, _, event = result.pop()
            result.append((start, segment[1], event))
        elif result and result[-1][1] - result[-1][0] == 1:
            _, _, event = result.pop()
            result.append((segment[0] - 1, segment[1], segment[2] if segment[2] is not None else event))
        else:
            result.append(segment)
    return result


def _write_segment(measure: ET.Element, start: int, end: int, event, begin: int, measure_end: int) -> None:
    pitch: Pitch | None = event[2] if event else None
    original: _Note | None = event[3] if event else None
    units = end - start
    pieces = None
    if original is not None and original.note_type and event[0] == start and event[1] == end:
        length = notated_length(original.note_type, original.dots)
        if original.tuplet:
            length = length * original.tuplet[1] / original.tuplet[0]
        if length * GRID == units and (original.tuplet in (None, (3, 2))):
            pieces = ((units, original.note_type, original.dots, original.tuplet is not None),)
    if pieces is None:
        pieces = _decompose(units)
    if pieces is None:  # cannot happen after absorbing slivers, but never write an invalid file
        raise ScoreImportError("A note length could not be written.")
    tied_before = event is not None and event[0] < start
    tied_after = event is not None and event[1] > end
    for number, (piece_units, note_type, dots, triplet) in enumerate(pieces):
        note = ET.SubElement(measure, "note")
        if pitch is None:
            ET.SubElement(note, "rest")
        else:
            written = pitch.shifted_octaves(config.WRITTEN_OCTAVE_OFFSET)
            element = ET.SubElement(note, "pitch")
            ET.SubElement(element, "step").text = written.step
            if written.alter:
                ET.SubElement(element, "alter").text = str(written.alter)
            ET.SubElement(element, "octave").text = str(written.octave)
        ET.SubElement(note, "duration").text = str(piece_units)
        if pitch is not None:
            if tied_before or number > 0:
                ET.SubElement(note, "tie", type="stop")
            if tied_after or number < len(pieces) - 1:
                ET.SubElement(note, "tie", type="start")
        ET.SubElement(note, "voice").text = "1"
        ET.SubElement(note, "type").text = note_type
        for _ in range(dots):
            ET.SubElement(note, "dot")
        if triplet:
            modification = ET.SubElement(note, "time-modification")
            ET.SubElement(modification, "actual-notes").text = "3"
            ET.SubElement(modification, "normal-notes").text = "2"


# Saving


def safe_file_name(title: str, directory: Path) -> Path:
    """A free file name in `directory` made from the title."""
    stem = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "song"
    path = directory / f"{stem}.musicxml"
    number = 2
    while path.exists():
        path = directory / f"{stem}-{number}.musicxml"
        number += 1
    return path


def save(result: ImportResult, title: str, directory: Path) -> Path:
    """Write the melody with the given title into `directory`; returns the new file."""
    directory.mkdir(parents=True, exist_ok=True)
    root = ET.fromstring(result.xml)
    root.find("work/work-title").text = title.strip() or "Song"
    ET.indent(root)
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
    path = safe_file_name(title, directory)
    path.write_text(xml, encoding="utf-8")
    return path
