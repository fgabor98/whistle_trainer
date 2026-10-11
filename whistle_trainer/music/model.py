"""Song data: sounding pitches, events, and their notation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

from whistle_trainer.config import A4_HZ

STEPS = "CDEFGAB"
STEP_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
ACCIDENTALS = {-2: "𝄫", -1: "♭", 0: "", 1: "♯", 2: "𝄪"}

# Note type name -> length in quarter notes, before dots.
NOTE_TYPES = {
    "whole": Fraction(4),
    "half": Fraction(2),
    "quarter": Fraction(1),
    "eighth": Fraction(1, 2),
    "16th": Fraction(1, 4),
    "32nd": Fraction(1, 8),
}


def notated_length(note_type: str, dots: int) -> Fraction:
    """Length in quarter notes of a note type with the given number of dots."""
    base = NOTE_TYPES[note_type]
    return base * (2 - Fraction(1, 2**dots))


@dataclass(frozen=True)
class Pitch:
    """A spelled pitch. Octave numbers follow scientific notation (A4 = 440 Hz)."""

    step: str
    alter: int
    octave: int

    def __post_init__(self) -> None:
        if self.step not in STEP_SEMITONES:
            raise ValueError(f"invalid step {self.step!r}")
        if self.alter not in ACCIDENTALS:
            raise ValueError(f"invalid alter {self.alter!r}")

    @property
    def midi(self) -> int:
        return (self.octave + 1) * 12 + STEP_SEMITONES[self.step] + self.alter

    @property
    def name(self) -> str:
        """Display name with octave, such as "F♯5"."""
        return f"{self.step}{ACCIDENTALS[self.alter]}{self.octave}"

    def frequency(self, a4_hz: float = A4_HZ) -> float:
        return a4_hz * 2 ** ((self.midi - 69) / 12)

    def shifted_octaves(self, octaves: int) -> Pitch:
        return Pitch(self.step, self.alter, self.octave + octaves)


class EventKind(StrEnum):
    NOTE = "note"
    REST = "rest"


@dataclass(frozen=True)
class NotatedPart:
    """One written note or rest. A tied chain of notes has several parts."""

    duration: Fraction
    note_type: str | None  # None for a whole-measure rest
    dots: int
    measure_index: int


@dataclass(frozen=True)
class Event:
    """One assessed unit: a note (tied notes merged) or a rest."""

    index: int
    kind: EventKind
    pitch: Pitch | None  # sounding pitch; None for rests
    start: Fraction  # quarter notes from the start of the song
    duration: Fraction  # quarter notes
    parts: tuple[NotatedPart, ...]

    @property
    def is_note(self) -> bool:
        return self.kind is EventKind.NOTE

    @property
    def end(self) -> Fraction:
        return self.start + self.duration

    @property
    def is_tied(self) -> bool:
        return len(self.parts) > 1


@dataclass(frozen=True)
class KeySignature:
    fifths: int  # positive for sharps, negative for flats
    mode: str = "major"


@dataclass(frozen=True)
class TimeSignature:
    beats: int
    beat_type: int

    @property
    def measure_length(self) -> Fraction:
        return Fraction(4 * self.beats, self.beat_type)

    @property
    def beat_length(self) -> Fraction:
        return Fraction(4, self.beat_type)


@dataclass(frozen=True)
class Measure:
    index: int
    number: str  # as written in the file
    start: Fraction
    duration: Fraction


@dataclass(frozen=True)
class Song:
    id: str
    title: str
    key: KeySignature  # key of the sounding pitches
    time: TimeSignature
    tempo: int  # default tempo in quarter notes per minute
    events: tuple[Event, ...]
    measures: tuple[Measure, ...]

    @property
    def length(self) -> Fraction:
        """Length in quarter notes."""
        return self.events[-1].end if self.events else Fraction(0)

    @property
    def notes(self) -> tuple[Event, ...]:
        return tuple(e for e in self.events if e.is_note)

    @property
    def lowest(self) -> Pitch:
        return min((e.pitch for e in self.notes), key=lambda p: p.midi)

    @property
    def highest(self) -> Pitch:
        return max((e.pitch for e in self.notes), key=lambda p: p.midi)
