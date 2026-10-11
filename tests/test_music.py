import pytest

from conftest import note, score, whole
from whistle_trainer.music.model import KeySignature, Pitch, TimeSignature
from whistle_trainer.music.timing import beat_seconds, event_times, song_seconds
from whistle_trainer.music.transpose import (
    suggest_transposition,
    transpose_key,
    transpose_pitch,
    transpose_song,
)


def test_pitch_midi_name_and_frequency():
    assert Pitch("A", 0, 4).midi == 69
    assert Pitch("A", 0, 4).frequency() == pytest.approx(440.0)
    assert Pitch("C", 0, 6).frequency() == pytest.approx(1046.50, abs=0.01)
    assert Pitch("F", 1, 5).name == "F♯5"
    assert Pitch("B", -1, 5).name == "B♭5"
    assert Pitch("B", 1, 4).midi == Pitch("C", 0, 5).midi


def test_pitch_rejects_invalid_values():
    with pytest.raises(ValueError):
        Pitch("H", 0, 4)
    with pytest.raises(ValueError):
        Pitch("C", 3, 4)


def test_time_signature_lengths():
    assert TimeSignature(4, 4).measure_length == 4
    assert TimeSignature(6, 8).measure_length == 3
    assert TimeSignature(6, 8).beat_length == pytest.approx(0.5)


@pytest.mark.parametrize("pitch, diatonic, semitones, expected", [
    (Pitch("B", 0, 4), 2, 4, "D♯5"),
    (Pitch("C", 0, 5), -1, -2, "B♭4"),
    (Pitch("G", 0, 4), 7, 12, "G5"),
    (Pitch("E", 0, 5), 0, 1, "E♯5"),
])
def test_transpose_pitch(pitch, diatonic, semitones, expected):
    assert transpose_pitch(pitch, diatonic, semitones).name == expected


@pytest.mark.parametrize("fifths, semitones, expected", [
    (1, 0, 1),     # G stays G
    (1, 1, -4),    # G -> A♭, not G♯ (8 sharps)
    (1, 5, 0),     # G -> C
    (0, 6, 6),     # C -> F♯ rather than G♭ (tie prefers sharps)
    (0, 5, -1),    # C -> F, not E♯
    (1, -12, 1),   # octave
    (0, -1, 5),    # C -> B, not C♭ (7 flats)
])
def test_transpose_key_prefers_fewest_accidentals(fifths, semitones, expected):
    assert transpose_key(KeySignature(fifths), semitones).fifths == expected


def test_transpose_song_spells_in_new_key(parse):
    attributes_g = "<attributes><divisions>2</divisions><key><fifths>1</fifths></key>" \
        "<time><beats>4</beats><beat-type>4</beat-type></time></attributes>"
    song = parse(score(note("G4") + note("F#4") + note("rest") + note("C5"), attributes=attributes_g))
    up = transpose_song(song, 1)  # G major -> A♭ major
    assert up.key == KeySignature(-4)
    assert [e.pitch.name if e.pitch else None for e in up.events] == ["A♭5", "G5", None, "D♭6"]
    down = transpose_song(song, -5)  # G major -> D major, down a fourth
    assert [e.pitch.name if e.pitch else None for e in down.events] == ["D5", "C♯5", None, "G5"]
    octave = transpose_song(song, 12)
    assert [e.pitch.name if e.pitch else None for e in octave.events] == ["G6", "F♯6", None, "C7"]
    assert transpose_song(song, 0) is song


def test_transpose_song_range_is_limited(parse):
    song = parse(score(whole()))
    with pytest.raises(ValueError):
        transpose_song(song, 13)


def test_suggest_transposition(parse):
    song = parse(score(note("C5") + note("D5") + note("E5") + note("G5")))  # sounds C6..G6
    c6, g6 = 84, 91
    assert suggest_transposition(song, c6 - 2, g6 + 2) == 0
    assert suggest_transposition(song, c6 - 7, g6 - 7) == -7
    # Range narrower than the song: smallest overflow, centered.
    assert suggest_transposition(song, c6 + 1, c6 + 4) == -1
    # Far away ranges are clamped to the supported transposition.
    assert suggest_transposition(song, 40, 50) == -12


def test_timing(parse):
    song = parse(score(note("C5", 3, "quarter", dots=1) + note("D5", 1, "eighth") + note("E5", 4, "half")))
    assert song_seconds(song, 60) == pytest.approx(4.0)
    assert song_seconds(song, 120) == pytest.approx(2.0)
    assert song_seconds(song, 60, start_index=1) == pytest.approx(2.5)
    assert song_seconds(song, 60, start_index=3) == 0
    assert event_times(song, 60) == pytest.approx([(0, 1.5), (1.5, 2.0), (2.0, 4.0)])
    assert event_times(song, 120, start_index=1) == pytest.approx([(0, 0.25), (0.25, 1.25)])
    assert beat_seconds(song.time, 60) == pytest.approx(1.0)
