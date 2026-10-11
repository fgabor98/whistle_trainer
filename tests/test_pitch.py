import math

import numpy as np
import pytest
from PySide6.QtMultimedia import QAudioFormat

from audio_helpers import SAMPLE_RATE, FrameScript, analyze, hum, noise, silence, tone
from whistle_trainer import config
from whistle_trainer.assessment.frames import FrameClass
from whistle_trainer.audio.capture import to_mono_float
from whistle_trainer.pitch.analyzer import Analyzer, level_db
from whistle_trainer.pitch.bandpass import StreamingFilter, design_bandpass
from whistle_trainer.pitch.calibration import LevelCalibration, LevelStep, Pause, RangeMeasurement, SetupProblem
from whistle_trainer.pitch.display import NoteDisplay, hz_to_midi
from whistle_trainer.pitch.yin import yin

WINDOW = 2048


def cents(a: float, b: float) -> float:
    return 1200 * math.log2(a / b)


@pytest.mark.parametrize("hz", np.geomspace(460, 4100, 25))
def test_yin_pure_tone_within_one_cent(hz):
    estimate, confidence = yin(tone(hz, 0.05)[:WINDOW], SAMPLE_RATE, 450, 4200)
    assert abs(cents(estimate, hz)) < 1
    assert confidence > 0.95


@pytest.mark.parametrize("hz", np.geomspace(460, 4100, 25))
def test_yin_noisy_tone_within_five_cents(hz):
    signal = tone(hz, 0.05)[:WINDOW] + noise(0.05, 0.01)[:WINDOW]  # 17 dB SNR
    estimate, confidence = yin(signal, SAMPLE_RATE, 450, 4200)
    assert abs(cents(estimate, hz)) < 5
    assert confidence >= config.MIN_PITCH_CONFIDENCE


@pytest.mark.parametrize("hz", [600, 900, 1500])
def test_yin_strong_second_harmonic_is_not_an_octave_error(hz):
    estimate, _ = yin(tone(hz, 0.05, harmonic=0.8)[:WINDOW], SAMPLE_RATE, 450, 4200)
    assert abs(cents(estimate, hz)) < 5


def test_yin_noise_and_silence_have_low_confidence():
    _, confidence = yin(noise(0.05, 0.1)[:WINDOW], SAMPLE_RATE, 450, 4200)
    assert confidence < 0.5
    assert yin(silence(0.05)[:WINDOW], SAMPLE_RATE, 450, 4200) == (None, 0.0)


def test_bandpass_removes_hum_and_keeps_whistle_range():
    kernel = design_bandpass(SAMPLE_RATE, 400, 4500, 1025)

    def gain_db(hz: float) -> float:
        response = np.sum(kernel * np.exp(-2j * np.pi * hz / SAMPLE_RATE * np.arange(len(kernel))))
        return 20 * math.log10(abs(response))

    assert gain_db(50) < -80 and gain_db(100) < -60 and gain_db(200) < -40
    for hz in (500, 1000, 2000, 4000):
        assert abs(gain_db(hz)) < 0.5
    assert gain_db(8000) < -60


def test_streaming_filter_matches_one_shot_filter():
    kernel = design_bandpass(SAMPLE_RATE, 400, 4500, 101)
    signal = noise(0.1, 0.1)
    streaming = StreamingFilter(kernel)
    blocks = [streaming.process(signal[i:i + 333]) for i in range(0, len(signal), 333)]
    expected = np.convolve(signal, kernel)[: len(signal)]
    assert np.allclose(np.concatenate(blocks), expected)


def test_level_db():
    assert level_db(np.full(100, 0.1)) == pytest.approx(-20.0)
    assert level_db(np.zeros(100)) == config.SILENCE_DB


def test_analyzer_produces_one_frame_per_hop():
    frames = analyze(silence(1.0))
    times = [f.time for f in frames]
    assert np.allclose(np.diff(times), config.ANALYSIS_HOP_S)
    assert len(frames) == 1 + (SAMPLE_RATE - WINDOW) // 480


def test_analyzer_frame_times_match_the_sound():
    frames = analyze(np.concatenate((silence(0.5), tone(988, 1.0), silence(0.5))))
    pitched = [f for f in frames if f.frame_class is FrameClass.PITCHED]
    assert pitched[0].time == pytest.approx(0.5, abs=0.03)
    assert pitched[-1].time == pytest.approx(1.5, abs=0.03)
    assert all(abs(cents(f.f0_hz, 988)) < 2 for f in pitched)


def test_analyzer_classifies_frames():
    frames = analyze(np.concatenate((tone(988, 0.3, amplitude=0.0005), tone(988, 0.3), noise(0.3, 0.05))),
                     threshold_db=-50)
    middle = lambda start, end: [f.frame_class for f in frames if start + 0.06 < f.time < end - 0.06]
    assert set(middle(0.0, 0.3)) == {FrameClass.QUIET}  # whistle below the threshold
    assert set(middle(0.3, 0.6)) == {FrameClass.PITCHED}
    assert set(middle(0.6, 0.9)) == {FrameClass.UNCLEAR}


def test_analyzer_ignores_hum():
    frames = analyze(hum(1.0, 0.3), threshold_db=-50)
    assert all(f.frame_class is FrameClass.QUIET for f in frames)


def test_analyzer_latency_is_within_the_feedback_target():
    assert Analyzer(SAMPLE_RATE).latency_seconds < config.MAX_FEEDBACK_DELAY_S / 2


def test_analyzer_works_at_44_1_khz():
    analyzer = Analyzer(44100)
    t = np.arange(44100) / 44100
    frames = analyzer.feed(0.1 * np.sin(2 * np.pi * 1200 * t))
    pitched = [f for f in frames if f.frame_class is FrameClass.PITCHED]
    assert len(pitched) > 80
    assert all(abs(cents(f.f0_hz, 1200)) < 2 for f in pitched)
    assert frames[1].time - frames[0].time == pytest.approx(0.010)


@pytest.mark.parametrize("sample_format, dtype, values, expected", [
    (QAudioFormat.SampleFormat.Float, np.float32, [0.5, -0.5], [0.5, -0.5]),
    (QAudioFormat.SampleFormat.Int16, np.int16, [16384, -32768], [0.5, -1.0]),
    (QAudioFormat.SampleFormat.Int32, np.int32, [1073741824, 0], [0.5, 0.0]),
    (QAudioFormat.SampleFormat.UInt8, np.uint8, [192, 128], [0.5, 0.0]),
])
def test_to_mono_float_formats(sample_format, dtype, values, expected):
    data = np.array(values, dtype=dtype).tobytes()
    assert to_mono_float(data, sample_format, 1) == pytest.approx(expected)


def test_to_mono_float_mixes_channels_and_drops_partial_frames():
    data = np.array([0.2, 0.4, -1.0, 1.0, 0.7], dtype=np.float32).tobytes()
    assert to_mono_float(data, QAudioFormat.SampleFormat.Float, 2) == pytest.approx([0.3, 0.0])


def test_note_display_smooths_and_holds_before_changing():
    display = NoteDisplay()
    b5, c6 = 987.77, 1046.50
    for frame in FrameScript().pitched(b5, 0.1).frames:
        note = display.feed(frame)
    assert note.pitch.name == "B5" and abs(note.cents) < 1

    script = FrameScript()
    script.time = 0.1
    frames = script.pitched(c6, 0.1).frames
    shown = [display.feed(f).pitch.name for f in frames]
    # The median needs 3 of 5 frames, then the new note must persist for 50 ms.
    assert shown[:7] == ["B5"] * 7
    assert shown[-1] == "C6"


def test_note_display_single_glitch_does_not_change_note():
    display = NoteDisplay()
    script = FrameScript().pitched(987.77, 0.1).pitched(2000, 0.01).pitched(987.77, 0.1)
    assert {display.feed(f).pitch.name for f in script.frames} == {"B5"}


def test_note_display_times_out_after_150_ms():
    display = NoteDisplay()
    frames = FrameScript().pitched(987.77, 0.1).quiet(0.2).frames
    results = [display.feed(f) for f in frames]
    assert results[9 + 14] is not None  # 140 ms after the last pitched frame
    assert results[9 + 16] is None  # 160 ms after


def test_hz_to_midi():
    assert hz_to_midi(440.0) == pytest.approx(69)
    assert hz_to_midi(987.77) == pytest.approx(83, abs=0.01)


def run_calibration(frames) -> LevelCalibration:
    calibration = LevelCalibration(config.ANALYSIS_HOP_S)
    for frame in frames:
        if calibration.feed(frame) is LevelStep.DONE:
            break
    return calibration


def test_calibration_derives_threshold_between_noise_and_whistle():
    calibration = run_calibration(FrameScript().quiet(3.0, level=-60).quiet(0.5, level=-60).pitched(988, 1.5).frames)
    result = calibration.result
    assert calibration.step is LevelStep.DONE and result.problem is None
    assert result.noise_floor_db == pytest.approx(-60)
    assert result.whistle_level_db == pytest.approx(-30)
    assert result.activity_threshold_db == pytest.approx(-45)


def test_calibration_uses_95th_percentile_of_background():
    script = FrameScript().quiet(2.9, level=-60).quiet(0.1, level=-20)  # a short knock
    calibration = run_calibration(script.pitched(988, 1.5).frames)
    assert calibration.result.noise_floor_db == pytest.approx(-60)


def test_calibration_without_whistle_times_out():
    calibration = run_calibration(FrameScript().quiet(3.0).quiet(10.5).frames)
    assert calibration.result.problem is SetupProblem.NO_STEADY_WHISTLE


def test_calibration_too_quiet_whistle():
    script = FrameScript().quiet(3.0, level=-40)
    for frame in FrameScript().pitched(988, 1.5).frames:
        script.frames.append(type(frame)(frame.time + 3.0, -32.0, frame.f0_hz, frame.confidence, frame.frame_class))
    calibration = run_calibration(script.frames)
    assert calibration.result.problem is SetupProblem.TOO_QUIET


def test_calibration_from_real_audio():
    signal = np.concatenate((noise(3.0, 0.001), tone(1200, 2.0) + noise(2.0, 0.001)))
    calibration = run_calibration(analyze(signal))
    result = calibration.result
    assert result.problem is None
    assert result.whistle_level_db - result.noise_floor_db > 30


def test_range_measurement_median_note():
    measurement = RangeMeasurement(config.ANALYSIS_HOP_S)
    script = FrameScript().quiet(0.5).pitched(880.0, 0.8).unclear(0.2).pitched(880.0 * 2 ** (20 / 1200), 1.3)
    for frame in script.frames:
        if measurement.feed(frame):
            break
    assert measurement.done and measurement.midi == 81


def test_range_measurement_times_out():
    measurement = RangeMeasurement(config.ANALYSIS_HOP_S)
    frames = FrameScript().quiet(14.9).frames
    assert not any(measurement.feed(frame) for frame in frames)
    measurement.feed(FrameScript().quiet(15.01).frames[-1])  # the frame at 15.0 s
    assert measurement.done and measurement.midi is None


def test_pause_ends_after_its_duration():
    pause = Pause(3.0)
    frames = FrameScript().quiet(3.0).frames
    assert not any(pause.feed(frame) for frame in frames)
    assert pause.progress() == pytest.approx(2.99 / 3.0)
    assert pause.feed(FrameScript().quiet(3.01).frames[-1])
