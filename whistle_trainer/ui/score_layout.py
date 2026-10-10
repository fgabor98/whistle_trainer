"""Horizontal layout of a song on one continuous treble staff.

All measurements are in staff spaces; the view scales them to pixels.
Staff positions count half spaces from the bottom line (E4 = 0, top line F5 = 8).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from whistle_trainer.config import WRITTEN_OCTAVE_OFFSET
from whistle_trainer.music.model import STEPS, Pitch, Song

# Glyph widths in staff spaces, from the Bravura metadata.
NOTEHEAD_WIDTH = 1.18
WHOLE_NOTEHEAD_WIDTH = 1.688
ACCIDENTAL_WIDTH = {-1: 0.904, 0: 0.672, 1: 0.996}
CLEF_WIDTH = 2.684
TIME_SIG_WIDTH = 1.88

SHARP_ORDER = "FCGDAEB"
FLAT_ORDER = "BEADGCF"
SHARP_POSITIONS = [8, 5, 9, 6, 3, 7, 4]
FLAT_POSITIONS = [4, 7, 3, 6, 2, 5, 1]

_BOTTOM_LINE = 4 * 7 + STEPS.index("E")  # E4


def staff_position(written: Pitch) -> int:
    return written.octave * 7 + STEPS.index(written.step) - _BOTTOM_LINE


def key_alters(fifths: int) -> dict[str, int]:
    if fifths >= 0:
        return {step: 1 for step in SHARP_ORDER[:fifths]}
    return {step: -1 for step in FLAT_ORDER[:-fifths]}


def part_advance(quarters: float, has_accidental: bool) -> float:
    """Horizontal space taken by a note or rest, growing with its duration."""
    return max(3.0, 3.2 * quarters) + (1.3 if has_accidental else 0.0)


@dataclass
class PartLayout:
    event_index: int
    x: float  # left edge of the notehead or rest
    position: int | None  # staff position; None for rests
    note_type: str | None  # None for a whole-measure rest
    dots: int
    accidental: int | None  # alter to draw before the note, if any
    stem_up: bool
    tied_to_next: bool

    @property
    def head_width(self) -> float:
        return WHOLE_NOTEHEAD_WIDTH if self.note_type == "whole" else NOTEHEAD_WIDTH


@dataclass
class EventLayout:
    left: float
    right: float
    label: str  # sounding note name, empty for rests
    parts: list[PartLayout] = field(default_factory=list)

    @property
    def center(self) -> float:
        return (self.left + self.right) / 2


@dataclass
class ScoreLayout:
    key_x: float
    key_signature: list[tuple[int, int]]  # (alter, staff position)
    time_x: float
    time_signature: tuple[int, int]
    parts: list[PartLayout]
    events: list[EventLayout]
    barlines: list[float]
    width: float


def layout_song(song: Song) -> ScoreLayout:
    x = 0.8 + CLEF_WIDTH + 0.8
    alters = key_alters(song.key.fifths)
    signature = []
    positions = SHARP_POSITIONS if song.key.fifths >= 0 else FLAT_POSITIONS
    for position in positions[: abs(song.key.fifths)]:
        signature.append((1 if song.key.fifths > 0 else -1, position))
    key_x = x
    x += abs(song.key.fifths) * 1.1 + (0.6 if song.key.fifths else 0.0)
    time_x = x
    x += TIME_SIG_WIDTH + 1.5

    parts: list[PartLayout] = []
    events = [EventLayout(0.0, 0.0, e.pitch.name if e.pitch else "") for e in song.events]
    barlines: list[float] = []
    measure_index = 0
    measure_state: dict[tuple[str, int], int] = {}

    for event in song.events:
        written = event.pitch.shifted_octaves(WRITTEN_OCTAVE_OFFSET) if event.pitch else None
        for part_number, part in enumerate(event.parts):
            if part.measure_index != measure_index:
                barlines.append(x - 0.6)
                x += 0.9
                measure_index = part.measure_index
                measure_state = {}

            accidental = None
            position = None
            if written is not None:
                position = staff_position(written)
                key = (written.step, written.octave)
                expected = measure_state.get(key, alters.get(written.step, 0))
                if written.alter != expected and part_number == 0:
                    accidental = written.alter
                measure_state[key] = written.alter

            if part.note_type is None:  # whole-measure rest, centered in the measure
                measure = song.measures[part.measure_index]
                width = part_advance(float(measure.duration), False)
                layout = PartLayout(event.index, x + width / 2 - 0.6, None, None, 0, None, True, False)
                advance = width
            else:
                head_x = x + (ACCIDENTAL_WIDTH.get(accidental, 0) + 0.3 if accidental is not None else 0.0)
                layout = PartLayout(
                    event_index=event.index,
                    x=head_x,
                    position=position,
                    note_type=part.note_type,
                    dots=part.dots,
                    accidental=accidental,
                    stem_up=position is not None and position < 4,
                    tied_to_next=part_number < len(event.parts) - 1,
                )
                advance = part_advance(float(part.duration), accidental is not None)
            parts.append(layout)
            event_layout = events[event.index]
            event_layout.parts.append(layout)
            if part_number == 0:
                event_layout.left = x - 0.4
            event_layout.right = layout.x + layout.head_width + 0.4 + (0.6 if layout.dots else 0.0)
            x += advance

    barlines.append(x - 0.6)
    return ScoreLayout(key_x, signature, time_x, (song.time.beats, song.time.beat_type), parts, events, barlines, x)
