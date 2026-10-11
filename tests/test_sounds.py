import math

import numpy as np
import pytest

from whistle_trainer import config
from whistle_trainer.audio.sounds import piano, piano_notes, piano_sample, render
from whistle_trainer.audio.synth import whistle
from whistle_trainer.config import Sound


def frequency_of(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def measured_cents(signal: np.ndarray, rate: int, expected: float) -> float:
    """Deviation of the strongest peak within a semitone of the expected frequency."""
    segment = signal[round(0.1 * rate):round(0.9 * rate)]
    segment = segment * np.hanning(len(segment))
    size = 8 * len(segment)
    spectrum = np.abs(np.fft.rfft(segment, size))
    frequencies = np.fft.rfftfreq(size, 1 / rate)
    band = np.flatnonzero((frequencies > expected * 2 ** (-1 / 12)) & (frequencies < expected * 2 ** (1 / 12)))
    return 1200 * math.log2(frequencies[band[np.argmax(spectrum[band])]] / expected)


def test_samples_cover_every_song_at_any_transposition():
    notes = piano_notes()
    assert notes == tuple(range(60, 103, 3))
    # Each note is at most one semitone from a sample: B3 (59) to G7 (103).
    assert all(min(abs(m - n) for n in notes) <= 1 for m in range(59, 104))
    sample, rate = piano_sample(72)
    assert rate == 48000 and len(sample) == 4 * 48000
    assert np.abs(sample).max() == pytest.approx(0.5, abs=0.01)


@pytest.mark.parametrize("midi", [59, 62, 72, 74, 83, 85, 91, 100, 103])
def test_piano_notes_are_in_tune(midi):
    note = piano(frequency_of(midi), 1.0, 48000)
    assert abs(measured_cents(note, 48000, frequency_of(midi))) < 3


def test_piano_note_length_and_release():
    note = piano(frequency_of(76), 0.5, 48000)
    assert len(note) == 24000
    release = round(config.PIANO_RELEASE_S * 48000)
    assert note[-1] == 0.0
    assert np.abs(note[-release:]).max() <= np.abs(note[-2 * release:-release]).max()


def test_piano_long_note_stops_when_the_sample_ends():
    assert len(piano(frequency_of(72), 10.0, 48000)) < 4 * 48000


def test_piano_at_another_output_rate_keeps_its_pitch():
    note = piano(frequency_of(81), 1.0, 44100)
    assert len(note) == 44100
    assert abs(measured_cents(note, 44100, frequency_of(81))) < 3


def test_render_chooses_the_sound():
    assert np.array_equal(render(Sound.PIANO, 880.0, 0.3, 48000), piano(880.0, 0.3, 48000))
    assert np.array_equal(render(Sound.WHISTLE, 880.0, 0.3, 48000, seed=3), whistle(880.0, 0.3, 48000, seed=3))
