"""Parser for the MusicXML subset described in TECHNICAL_SPEC.md.

Only one melodic line is supported. Anything that changes what must be
whistled but cannot be represented (chords, voices, tuplets, repeats, ...) is
rejected with a SongFormatError naming the file and measure. Elements that
only affect appearance, such as dynamics, lyrics, and slurs, are ignored.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from whistle_trainer import config, strings
from whistle_trainer.music.model import (
    NOTE_TYPES,
    Event,
    EventKind,
    KeySignature,
    Measure,
    NotatedPart,
    Pitch,
    Song,
    TimeSignature,
    notated_length,
)
from whistle_trainer.music.transpose import diatonic_steps_for, transpose_key, transpose_pitch

# Written notes are drawn an octave below sounding pitch, so files without a
# transpose element are read as sounding one octave higher.
_DEFAULT_OCTAVE_CHANGE = -config.WRITTEN_OCTAVE_OFFSET

_REJECTED_NOTE_ELEMENTS = {
    "chord": "chords are not supported; use a single melodic line",
    "grace": "grace notes are not supported",
    "cue": "cue notes are not supported",
    "unpitched": "unpitched notes are not supported",
}
_JUMP_ATTRIBUTES = ("dacapo", "dalsegno", "tocoda", "fine", "segno", "coda")


class SongFormatError(Exception):
    def __init__(self, file: str, message: str, measure: str | None = None):
        self.file = file
        self.measure = measure
        self.message = message
        super().__init__(str(self))

    def __str__(self) -> str:
        if self.measure is None:
            return strings.SONG_ERROR.format(file=self.file, message=self.message)
        return strings.SONG_ERROR_IN_MEASURE.format(
            file=self.file, measure=self.measure, message=self.message
        )


@dataclass
class _WrittenNote:
    pitch: Pitch | None  # written pitch; None for rests
    duration: Fraction
    note_type: str | None
    dots: int
    measure_index: int
    measure_number: str
    tie_start: bool
    tie_stop: bool
    tuplet: tuple[int, int] | None = None


@dataclass
class _Transpose:
    diatonic: int
    chromatic: int

    def apply(self, pitch: Pitch) -> Pitch:
        return transpose_pitch(pitch, self.diatonic, self.chromatic)


def parse_file(path: Path) -> Song:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise SongFormatError(path.name, f"cannot be read ({error})") from error
    return parse_string(text, song_id=path.stem, file_name=path.name)


def parse_string(text: str, song_id: str, file_name: str | None = None) -> Song:
    return _Parser(file_name or song_id).parse(text, song_id)


class _Parser:
    def __init__(self, file_name: str):
        self.file = file_name
        self.measure: str | None = None
        self.divisions: int | None = None
        self.key: KeySignature | None = None
        self.time: TimeSignature | None = None
        self.transpose: _Transpose | None = None
        self.tempo: float | None = None
        self.voice: str | None = None

    def error(self, message: str) -> SongFormatError:
        return SongFormatError(self.file, message, self.measure)

    def parse(self, text: str, song_id: str) -> Song:
        try:
            root = ET.fromstring(text)
        except ET.ParseError as error:
            raise self.error(f"is not valid XML ({error})") from error
        if root.tag != "score-partwise":
            raise self.error("is not a partwise MusicXML score")
        parts = root.findall("part")
        if len(parts) != 1:
            raise self.error(f"must contain exactly one part, found {len(parts)}")

        title = (root.findtext("work/work-title") or root.findtext("movement-title") or "").strip()
        written, measures = self.read_measures(parts[0])
        self.measure = None
        if not any(n.pitch for n in written):
            raise self.error("contains no notes")

        transpose = self.transpose or _Transpose(7 * _DEFAULT_OCTAVE_CHANGE, 12 * _DEFAULT_OCTAVE_CHANGE)
        key = self.key or KeySignature(0)
        if transpose.chromatic % 12:
            key = transpose_key(key, transpose.chromatic)
        tempo = round(self.tempo or config.DEFAULT_TEMPO)
        return Song(
            id=song_id,
            title=title or song_id,
            key=key,
            time=self.time,
            tempo=min(max(tempo, config.MIN_TEMPO), config.MAX_TEMPO),
            events=self.build_events(written, transpose),
            measures=tuple(measures),
        )

    def read_measures(self, part: ET.Element) -> tuple[list[_WrittenNote], list[Measure]]:
        written: list[_WrittenNote] = []
        measures: list[Measure] = []
        position = Fraction(0)
        elements = part.findall("measure")
        for index, element in enumerate(elements):
            self.measure = element.get("number", str(index + 1))
            length = Fraction(0)
            for child in element:
                if child.tag == "attributes":
                    self.read_attributes(child, first_measure=index == 0)
                elif child.tag == "note":
                    note = self.read_note(child, index)
                    written.append(note)
                    length += note.duration
                elif child.tag in ("backup", "forward"):
                    raise self.error("multiple voices are not supported")
                elif child.tag in ("direction", "sound"):
                    self.read_direction(child)
                elif child.tag == "barline":
                    if child.find("repeat") is not None or child.find("ending") is not None:
                        raise self.error("repeats and endings are not supported; write the music out in full")
            self.check_measure_length(length, is_edge=index in (0, len(elements) - 1))
            measures.append(Measure(index, self.measure, position, length))
            position += length
        return written, measures

    def check_measure_length(self, length: Fraction, is_edge: bool) -> None:
        if self.time is None:
            raise self.error("has no time signature")
        expected = self.time.measure_length
        if length == 0:
            raise self.error("is empty")
        if length > expected or (length < expected and not is_edge):
            raise self.error(
                f"contains {_quarters(length)} quarter notes, but the time signature "
                f"requires {_quarters(expected)}"
            )

    def read_attributes(self, element: ET.Element, first_measure: bool) -> None:
        if (divisions := element.findtext("divisions")) is not None:
            self.divisions = self.parse_positive_int(divisions, "divisions")
        if (staves := element.findtext("staves")) is not None and staves.strip() != "1":
            raise self.error("only a single staff is supported")

        if (key := element.find("key")) is not None:
            if key.find("fifths") is None:
                raise self.error("only standard key signatures are supported")
            new_key = KeySignature(self.parse_int(key.findtext("fifths"), "key fifths"), key.findtext("mode", "major"))
            if not -7 <= new_key.fifths <= 7:
                raise self.error("key signature has too many accidentals")
            self.check_unchanged(self.key, new_key, first_measure, "key signature changes")
            self.key = new_key

        if (time := element.find("time")) is not None:
            beats, beat_type = time.findtext("beats"), time.findtext("beat-type")
            if beats is None or beat_type is None:
                raise self.error("only standard time signatures are supported")
            new_time = TimeSignature(self.parse_positive_int(beats, "beats"), self.parse_positive_int(beat_type, "beat type"))
            self.check_unchanged(self.time, new_time, first_measure, "time signature changes")
            self.time = new_time

        for clef in element.findall("clef"):
            octave_change = clef.findtext("clef-octave-change", "0").strip()
            if clef.findtext("sign") != "G" or clef.findtext("line", "2").strip() != "2" or octave_change != "0":
                raise self.error("only the treble clef is supported")

        if (transpose := element.find("transpose")) is not None:
            octave = self.parse_int(transpose.findtext("octave-change", "0"), "octave change")
            chromatic = self.parse_int(transpose.findtext("chromatic", "0"), "chromatic transposition")
            diatonic_text = transpose.findtext("diatonic")
            diatonic = self.parse_int(diatonic_text, "diatonic") if diatonic_text else diatonic_steps_for(chromatic)
            new_transpose = _Transpose(diatonic + 7 * octave, chromatic + 12 * octave)
            self.check_unchanged(self.transpose, new_transpose, first_measure, "transposition changes")
            self.transpose = new_transpose

    def check_unchanged(self, old, new, first_measure: bool, what: str) -> None:
        if not first_measure and old != new:
            raise self.error(f"{what} after the first measure are not supported")

    def read_direction(self, element: ET.Element) -> None:
        sounds = [element] if element.tag == "sound" else element.findall("sound")
        for sound in sounds:
            if any(sound.get(name) for name in _JUMP_ATTRIBUTES):
                raise self.error("repeats and jumps are not supported; write the music out in full")
            if self.tempo is None and sound.get("tempo"):
                self.tempo = self.parse_positive_float(sound.get("tempo"), "tempo")
        metronome = element.find("direction-type/metronome")
        if self.tempo is None and metronome is not None:
            unit, per_minute = metronome.findtext("beat-unit"), metronome.findtext("per-minute")
            if unit in NOTE_TYPES and per_minute:
                dots = len(metronome.findall("beat-unit-dot"))
                self.tempo = self.parse_positive_float(per_minute, "tempo") * float(notated_length(unit, dots))

    def read_note(self, element: ET.Element, measure_index: int) -> _WrittenNote:
        for tag, message in _REJECTED_NOTE_ELEMENTS.items():
            if element.find(tag) is not None:
                raise self.error(message)
        voice = element.findtext("voice", "1").strip()
        if self.voice is None:
            self.voice = voice
        elif voice != self.voice:
            raise self.error("multiple voices are not supported")
        if element.findtext("staff", "1").strip() != "1":
            raise self.error("only a single staff is supported")
        if self.divisions is None:
            raise self.error("note durations appear before divisions are defined")

        duration_text = element.findtext("duration")
        if duration_text is None:
            raise self.error("a note has no duration")
        duration = Fraction(self.parse_positive_int(duration_text, "duration"), self.divisions)

        rest = element.find("rest")
        note_type = element.findtext("type")
        dots = len(element.findall("dot"))
        tuplet = self.read_tuplet(element)
        if tuplet is not None and note_type is None:
            raise self.error("a tuplet note has no written type")
        if note_type is not None:
            note_type = note_type.strip()
            if note_type not in NOTE_TYPES:
                raise self.error(f"note type {note_type!r} is not supported")
            written = notated_length(note_type, dots)
            if tuplet is not None:
                written = written * tuplet[1] / tuplet[0]
            if written != duration:
                raise self.error("a note's duration does not match its written type")
        elif rest is None or rest.get("measure") != "yes":
            note_type, dots = _type_for(duration) or (None, 0)
            if note_type is None:
                raise self.error("a note has a duration that cannot be written as one note")

        ties = {tie.get("type") for tie in element.findall("tie")}
        pitch = None if rest is not None else self.read_pitch(element)
        if pitch is None and ties:
            raise self.error("rests cannot be tied")
        return _WrittenNote(
            pitch, duration, note_type, dots, measure_index, self.measure,
            tie_start="start" in ties, tie_stop="stop" in ties, tuplet=tuplet,
        )

    def read_tuplet(self, element: ET.Element) -> tuple[int, int] | None:
        modification = element.find("time-modification")
        if modification is None:
            return None
        actual = self.parse_positive_int(modification.findtext("actual-notes"), "tuplet actual notes")
        normal = self.parse_positive_int(modification.findtext("normal-notes"), "tuplet normal notes")
        if modification.find("normal-type") is not None or modification.find("normal-dot") is not None:
            raise self.error("tuplets with a different normal note type are not supported")
        return None if actual == normal else (actual, normal)

    def read_pitch(self, element: ET.Element) -> Pitch:
        pitch = element.find("pitch")
        if pitch is None:
            raise self.error("a note has no pitch")
        alter_text = pitch.findtext("alter", "0").strip()
        try:
            alter_value = float(alter_text)
        except ValueError:
            raise self.error(f"invalid alter {alter_text!r}") from None
        if not alter_value.is_integer():
            raise self.error("microtones are not supported")
        try:
            return Pitch(
                pitch.findtext("step", "").strip(),
                int(alter_value),
                self.parse_int(pitch.findtext("octave"), "octave"),
            )
        except ValueError as error:
            raise self.error(f"invalid pitch ({error})") from None

    def build_events(self, written: list[_WrittenNote], transpose: _Transpose) -> tuple[Event, ...]:
        events: list[Event] = []
        position = Fraction(0)
        chain: list[_WrittenNote] = []
        chain_pitch: Pitch | None = None

        def close_chain() -> None:
            nonlocal chain, chain_pitch
            duration = sum((n.duration for n in chain), Fraction(0))
            kind = EventKind.NOTE if chain_pitch else EventKind.REST
            parts = tuple(NotatedPart(n.duration, n.note_type, n.dots, n.measure_index, n.tuplet) for n in chain)
            events.append(Event(len(events), kind, chain_pitch, position - duration, duration, parts))
            chain, chain_pitch = [], None

        for note in written:
            self.measure = note.measure_number
            sounding = transpose.apply(note.pitch) if note.pitch else None
            if note.tie_stop:
                if not chain or chain_pitch is None or not chain[-1].tie_start:
                    raise self.error("a tie ends without starting")
                if sounding is None or sounding.midi != chain_pitch.midi:
                    raise self.error("a tie connects notes of different pitch")
            elif chain:
                if chain[-1].tie_start:
                    raise self.error("a tie starts but does not end on the next note")
                close_chain()
            if not chain:
                chain_pitch = sounding
            chain.append(note)
            position += note.duration
        if chain[-1].tie_start:
            raise self.error("a tie starts but does not end on the next note")
        close_chain()
        return tuple(events)

    def parse_int(self, text: str | None, what: str) -> int:
        try:
            return int((text or "").strip())
        except ValueError:
            raise self.error(f"invalid {what} {text!r}") from None

    def parse_positive_int(self, text: str | None, what: str) -> int:
        value = self.parse_int(text, what)
        if value <= 0:
            raise self.error(f"invalid {what} {text!r}")
        return value

    def parse_positive_float(self, text: str | None, what: str) -> float:
        try:
            value = float((text or "").strip())
        except ValueError:
            raise self.error(f"invalid {what} {text!r}") from None
        if value <= 0:
            raise self.error(f"invalid {what} {text!r}")
        return value


def _type_for(duration: Fraction) -> tuple[str, int] | None:
    for note_type in NOTE_TYPES:
        for dots in range(3):
            if notated_length(note_type, dots) == duration:
                return note_type, dots
    return None


def _quarters(value: Fraction) -> str:
    return str(value) if value.denominator != 1 else str(value.numerator)
