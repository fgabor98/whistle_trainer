"""Transposition of pitches, key signatures, and whole songs."""

from __future__ import annotations

from dataclasses import replace

from whistle_trainer.config import MAX_TRANSPOSITION, MIN_TRANSPOSITION
from whistle_trainer.music.model import STEP_SEMITONES, STEPS, KeySignature, Pitch, Song

_SHARP_SPELLINGS = [
    ("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0), ("F", 0),
    ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0),
]


def spell_midi(midi: int) -> Pitch:
    """Default spelling of a MIDI note, using sharps."""
    step, alter = _SHARP_SPELLINGS[midi % 12]
    return Pitch(step, alter, midi // 12 - 1)


def transpose_pitch(pitch: Pitch, diatonic: int, semitones: int) -> Pitch:
    """Move a pitch by an interval given as letter steps and semitones.

    For example a major third up is diatonic=2, semitones=4: B4 becomes D♯5.
    """
    index = STEPS.index(pitch.step) + diatonic
    step = STEPS[index % 7]
    octave = pitch.octave + index // 7
    alter = pitch.midi + semitones - ((octave + 1) * 12 + STEP_SEMITONES[step])
    if abs(alter) > 2:
        return spell_midi(pitch.midi + semitones)
    return Pitch(step, alter, octave)


def diatonic_steps_for(semitones: int) -> int:
    """Letter steps that best match a chromatic interval, e.g. -2 semitones -> -1."""
    return round(semitones * 7 / 12)


def transpose_key(key: KeySignature, semitones: int) -> KeySignature:
    """The key after transposing, choosing the spelling with fewest accidentals.

    One semitone up moves the key seven fifths around the circle, so the new
    key is fifths + 7 * semitones modulo 12. Ties (six sharps or six flats)
    prefer sharps.
    """
    shift = (7 * semitones) % 12
    candidates = [f for f in range(-7, 8) if (f - key.fifths - shift) % 12 == 0]
    fifths = min(candidates, key=lambda f: (abs(f), f < 0))
    return KeySignature(fifths, key.mode)


def _key_diatonic_shift(old: KeySignature, new: KeySignature, semitones: int) -> int:
    """Letter steps between the two keys' tonics, in the direction of the transposition."""
    # A fifth up moves the tonic letter four steps (C -> G).
    letters = (4 * (new.fifths - old.fifths)) % 7
    candidates = (letters - 14, letters - 7, letters, letters + 7, letters + 14)
    return min(candidates, key=lambda d: abs(d * 12 / 7 - semitones))


def transpose_song(song: Song, semitones: int) -> Song:
    """The song with every pitch and the key moved, spelled in the new key."""
    if not MIN_TRANSPOSITION <= semitones <= MAX_TRANSPOSITION:
        raise ValueError(f"transposition {semitones} is outside the supported range")
    if semitones == 0:
        return song
    key = transpose_key(song.key, semitones)
    diatonic = _key_diatonic_shift(song.key, key, semitones)
    events = tuple(
        replace(e, pitch=transpose_pitch(e.pitch, diatonic, semitones)) if e.pitch else e
        for e in song.events
    )
    return replace(song, key=key, events=events)


def suggest_transposition(song: Song, low_midi: int, high_midi: int) -> int:
    """The transposition that best centers the song inside the user's range.

    Shifts that fit the song entirely within the range are preferred; among
    those, or if none fit, the one with the smallest overflow and then the
    best centering wins. Ties prefer the smaller shift.
    """
    lowest, highest = song.lowest.midi, song.highest.midi
    range_center = (low_midi + high_midi) / 2

    def score(shift: int) -> tuple[int, float, int]:
        overflow = max(0, low_midi - (lowest + shift)) + max(0, highest + shift - high_midi)
        off_center = abs((lowest + highest) / 2 + shift - range_center)
        return overflow, off_center, abs(shift)

    return min(range(MIN_TRANSPOSITION, MAX_TRANSPOSITION + 1), key=score)
