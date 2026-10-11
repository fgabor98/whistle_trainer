import numpy as np
import pytest
from PySide6.QtMultimedia import QAudioFormat

from whistle_trainer.audio.playback import ScheduledSound, encode, mix, output_index
from whistle_trainer.audio.synth import click


def test_mix_adds_overlapping_sounds_and_clips():
    sounds = [ScheduledSound(2, np.full(4, 0.5, np.float32)), ScheduledSound(4, np.full(4, 0.75, np.float32))]
    assert mix(sounds, 0, 10).tolist() == pytest.approx([0, 0, 0.5, 0.5, 1.0, 1.0, 0.75, 0.75, 0, 0])
    assert mix(sounds, 5, 2).tolist() == pytest.approx([1.0, 0.75])
    assert mix(sounds, 20, 3).tolist() == [0, 0, 0]


def test_output_index_maps_time_to_samples():
    # 0.5 s ahead of now, with 1000 samples already played and 1500 written.
    assert output_index(10.5, 10.0, 1000, 1500, 48000) == 1000 + 24000
    # Too late for what is already written: as soon as possible.
    assert output_index(10.0, 10.0, 1000, 1500, 48000) == 1500


def test_encode_formats_and_channels():
    samples = np.array([0.5, -1.0], dtype=np.float32)
    assert np.frombuffer(encode(samples, QAudioFormat.SampleFormat.Float, 1), np.float32).tolist() == [0.5, -1.0]
    assert np.frombuffer(encode(samples, QAudioFormat.SampleFormat.Int16, 2), np.int16).tolist() == \
        [16384, 16384, -32767, -32767]


def test_click_is_short_and_accent_is_higher():
    accent, normal = click(True, 48000), click(False, 48000)
    assert len(accent) == len(normal) == 960
    assert np.abs(accent).max() <= 0.5
    spectrum = lambda x: np.argmax(np.abs(np.fft.rfft(x, 48000)))
    assert spectrum(accent) == pytest.approx(2000, abs=60)
    assert spectrum(normal) == pytest.approx(1500, abs=60)


def test_whistle_tone_is_detected_at_its_pitch():
    from audio_helpers import analyze
    from whistle_trainer.assessment.frames import FrameClass
    from whistle_trainer.audio.synth import whistle

    signal = whistle(987.77, 1.0, 48000)
    assert np.abs(signal).max() == pytest.approx(10 ** (-12 / 20), rel=1e-3)
    assert signal[0] == pytest.approx(0.0, abs=1e-3) and signal[-1] == pytest.approx(0.0, abs=1e-3)
    frames = [f for f in analyze(signal.astype(np.float64)) if f.frame_class is FrameClass.PITCHED]
    assert len(frames) > 80
    cents = [1200 * np.log2(f.f0_hz / 987.77) for f in frames]
    assert max(abs(c) for c in cents) < 12  # vibrato of ±8 cents
