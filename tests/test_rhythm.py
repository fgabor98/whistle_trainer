import numpy as np
import pytest

from audio_helpers import SAMPLE_RATE, FrameScript, analyze, silence, tone
from conftest import note, score
from whistle_trainer import config
from whistle_trainer.assessment.frames import AnalysisFrame, FrameClass
from whistle_trainer.assessment.rhythm import FailReason, RhythmEngine, RhythmStatus
from whistle_trainer.audio.synth import click

HOP = config.ANALYSIS_HOP_S
C6, D6, E6 = 1046.50, 1174.66, 1318.51
COUNT_IN = 4.0  # four beats at 60 bpm


def engine_for(parse, *measures, tempo=60) -> RhythmEngine:
    engine = RhythmEngine(parse(score(*measures)), tempo, 40.0, HOP)
    engine.schedule(0.0)
    return engine


def feed(engine: RhythmEngine, script: FrameScript) -> list:
    return [engine.feed(f) for f in script.frames]


def four_notes(parse, tempo=60) -> RhythmEngine:
    return engine_for(parse, note("C5") + note("D5") + note("E5") + note("D5"), tempo=tempo)


def test_count_in_then_playing(parse):
    engine = four_notes(parse)
    updates = feed(engine, FrameScript().quiet(COUNT_IN))
    assert all(u.status is RhythmStatus.COUNT_IN for u in updates)
    assert engine.beat_times()[:5] == pytest.approx([0, 1, 2, 3, 4])
    updates = feed(engine, FrameScript().quiet(0.01))
    assert engine.event_times(0) == pytest.approx((4.0, 5.0))


def on_time(script: FrameScript, hz: float, held: float, duration: float = 1.0) -> FrameScript:
    return script.pitched(hz, held).quiet(duration - held)


def test_on_time_note_with_900_ms_passes_at_scheduled_end(parse):
    engine = four_notes(parse)
    script = FrameScript().quiet(COUNT_IN)
    updates = feed(engine, on_time(script, C6, 0.9))
    assert engine.position == 0 and engine.status is RhythmStatus.PLAYING
    assert updates[-1].progress == pytest.approx(1.0)
    # The note passes with the first frame at or after its scheduled end.
    update = engine.feed(AnalysisFrame(5.0, -30.0, D6, 0.95, FrameClass.PITCHED))
    assert update.passed == (0,) and engine.position == 1


def test_reaching_800_ms_does_not_advance_early(parse):
    engine = four_notes(parse)
    script = FrameScript().quiet(COUNT_IN).pitched(C6, 0.85)
    updates = feed(engine, script)
    assert all(u.index == 0 and not u.passed for u in updates)


def test_whole_song_on_time(parse):
    engine = four_notes(parse)
    script = FrameScript().quiet(COUNT_IN)
    for hz in (C6, D6, E6, D6):
        on_time(script, hz, 0.9)
    script.quiet(0.05)
    feed(engine, script)
    assert engine.status is RhythmStatus.FINISHED and engine.completed == {0, 1, 2, 3}


def test_legato_without_gaps_passes(parse):
    engine = four_notes(parse)
    feed(engine, FrameScript().quiet(COUNT_IN).pitched(C6, 1.0).pitched(D6, 1.0).pitched(E6, 1.0).pitched(D6, 1.0).quiet(0.05))
    assert engine.status is RhythmStatus.FINISHED


def test_250_ms_late_onset_fails_as_soon_as_window_passes(parse):
    engine = four_notes(parse)
    script = FrameScript().quiet(COUNT_IN + 0.25).pitched(C6, 0.75)
    updates = feed(engine, script)
    assert engine.failure is FailReason.LATE_OR_MISSING
    assert engine.status is RhythmStatus.FAILED and engine.position == 0
    # The failure is reported as soon as the 150 ms window has passed.
    first = next(i for i, u in enumerate(updates) if u.failed)
    assert script.frames[first].time == pytest.approx(COUNT_IN + 0.15 + HOP, abs=HOP / 2)


def test_missed_onset_fails(parse):
    engine = four_notes(parse)
    feed(engine, FrameScript().quiet(COUNT_IN + 1.0))
    assert engine.failure is FailReason.LATE_OR_MISSING and engine.failures == {0: 1}


def test_onset_within_window_late_side_passes(parse):
    engine = four_notes(parse)
    feed(engine, FrameScript().quiet(COUNT_IN + 0.12).pitched(C6, 0.88).pitched(D6, 0.05))
    assert engine.completed == {0}


def test_early_onset_within_window_earns_no_credit_before_start(parse):
    engine = four_notes(parse)
    feed(engine, FrameScript().quiet(COUNT_IN - 0.14).pitched(C6, 0.14 + 0.7).quiet(0.3))
    # Only 700 ms fall inside the interval; stopping there is a break before 80 percent.
    assert engine.failure is FailReason.INTERRUPTED


def test_too_early_onset_is_not_an_onset(parse):
    engine = four_notes(parse)
    feed(engine, FrameScript().quiet(COUNT_IN - 0.3).pitched(C6, 1.3))
    assert engine.failure is FailReason.LATE_OR_MISSING


def test_700_ms_fails(parse):
    engine = four_notes(parse)
    feed(engine, on_time(FrameScript().quiet(COUNT_IN), C6, 0.7).quiet(0.05))
    assert engine.failure is FailReason.INTERRUPTED and engine.position == 0


def test_too_little_pitch_without_a_long_break_fails_as_too_short(parse):
    engine = four_notes(parse)
    script = FrameScript().quiet(COUNT_IN)
    for _ in range(5):  # 150 ms on, 50 ms off: short breaks, but only 75 percent credit
        script.pitched(C6, 0.15).quiet(0.05)
    feed(engine, script.pitched(D6, 0.05))
    assert engine.failure is FailReason.TOO_SHORT and engine.position == 0


def test_short_dropout_is_allowed(parse):
    engine = four_notes(parse)
    feed(engine, FrameScript().quiet(COUNT_IN).pitched(C6, 0.4).quiet(0.08).pitched(C6, 0.52).pitched(D6, 0.05))
    assert engine.completed == {0}


def test_long_interruption_fails_even_if_total_would_suffice(parse):
    engine = engine_for(parse, note("C5", 8, "whole"), tempo=60)  # 4 seconds
    feed(engine, FrameScript().quiet(COUNT_IN).pitched(C6, 1.0).quiet(0.2).pitched(C6, 2.8))
    assert engine.failure is FailReason.INTERRUPTED


def test_release_after_80_percent_is_allowed(parse):
    engine = four_notes(parse)
    feed(engine, FrameScript().quiet(COUNT_IN).pitched(C6, 0.8).quiet(0.2).pitched(D6, 0.05))
    assert engine.completed == {0} and engine.status is RhythmStatus.PLAYING


def test_warm_up_before_window_is_ignored(parse):
    engine = four_notes(parse)
    feed(engine, FrameScript().pitched(C6, 2.0).quiet(2.0).pitched(C6, 1.0).pitched(D6, 0.05))
    assert engine.completed == {0}


def test_repeated_notes_need_a_fresh_attack(parse):
    engine = engine_for(parse, note("C5") + note("C5") + note("D5", 4, "half"))
    feed(engine, FrameScript().quiet(COUNT_IN).pitched(C6, 2.0))
    assert engine.completed == {0}
    assert engine.failure is FailReason.LATE_OR_MISSING and engine.position == 1

    engine = engine_for(parse, note("C5") + note("C5") + note("D5", 4, "half"))
    feed(engine, FrameScript().quiet(COUNT_IN).pitched(C6, 0.85).quiet(0.15).pitched(C6, 0.9).quiet(0.1).pitched(D6, 0.05))
    assert engine.completed == {0, 1}


def test_tied_notes_are_one_continuous_hold(parse):
    engine = engine_for(parse, note("C5", 2, "quarter", '<tie type="start"/>')
                        + note("C5", 2, "quarter", '<tie type="stop"/>') + note("D5", 4, "half"))
    feed(engine, FrameScript().quiet(COUNT_IN).pitched(C6, 2.0).pitched(D6, 0.05))
    assert engine.completed == {0}


def test_rest_passes_with_quiet(parse):
    engine = engine_for(parse, note("C5") + note("rest") + note("D5", 4, "half"))
    feed(engine, FrameScript().quiet(COUNT_IN).pitched(C6, 0.9).quiet(1.1).pitched(D6, 0.05))
    assert engine.completed == {0, 1}


def test_rest_fails_with_whistling(parse):
    engine = engine_for(parse, note("C5") + note("rest") + note("D5", 4, "half"))
    feed(engine, FrameScript().quiet(COUNT_IN).pitched(C6, 1.3))
    assert engine.failure is FailReason.REST_NOT_QUIET and engine.position == 1


def test_rest_tolerates_short_noise(parse):
    engine = engine_for(parse, note("C5") + note("rest") + note("D5", 4, "half"))
    feed(engine, FrameScript().quiet(COUNT_IN).pitched(C6, 0.9).quiet(0.4).unclear(0.08).quiet(0.62).pitched(D6, 0.05))
    assert engine.completed == {0, 1}


def test_starting_next_note_early_does_not_fail_a_rest(parse):
    engine = engine_for(parse, note("C5") + note("rest") + note("D5", 4, "half") , tempo=60)
    # D5 is a half note (2 s), so its window is 150 ms; start it 140 ms early inside the rest.
    feed(engine, FrameScript().quiet(COUNT_IN).pitched(C6, 0.9).quiet(0.96).pitched(D6, 2.0).quiet(0.2))
    assert engine.status is RhythmStatus.FINISHED


def test_retry_keeps_earlier_successes(parse):
    engine = four_notes(parse)
    script = FrameScript().quiet(COUNT_IN)
    on_time(script, C6, 0.9).quiet(1.0)  # D6 missed
    feed(engine, script)
    assert engine.status is RhythmStatus.FAILED and engine.position == 1
    assert engine.completed == {0} and engine.failures == {1: 1}

    retry_at = script.time + 0.5
    engine.schedule(retry_at)
    assert engine.status is RhythmStatus.COUNT_IN
    assert engine.event_times(1) == pytest.approx((retry_at + 4.0, retry_at + 5.0))
    assert engine.event_times(0) is None
    retry = FrameScript()
    retry.time = script.time
    retry.quiet(0.5 + COUNT_IN)
    for hz in (D6, E6, D6):
        on_time(retry, hz, 0.9)
    feed(engine, retry.quiet(0.05))
    assert engine.status is RhythmStatus.FINISHED and engine.completed == {0, 1, 2, 3}


def test_stop_requires_new_count_in(parse):
    engine = four_notes(parse)
    feed(engine, FrameScript().quiet(COUNT_IN).pitched(C6, 0.5))
    engine.stop()
    assert engine.status is RhythmStatus.IDLE and engine.schedule_data is None
    update = engine.feed(FrameScript().pitched(C6, 0.01).frames[0])
    assert update.status is RhythmStatus.IDLE


def test_eighth_notes_at_120_bpm(parse):
    engine = engine_for(parse, note("C5", 1, "eighth") + note("D5", 1, "eighth") + note("E5", 6, "half", dots=1),
                        tempo=120)
    # Count-in: 4 beats of 0.5 s. Eighths last 0.25 s; their window is 50 ms.
    feed(engine, FrameScript().quiet(2.0).pitched(C6, 0.25).pitched(D6, 0.25).pitched(E6, 1.5).quiet(0.05))
    assert engine.status is RhythmStatus.FINISHED


def test_audio_performance_with_metronome_clicks(parse):
    """A synthesized performance, with clicks leaking into the microphone, passes."""
    engine = RhythmEngine(parse(score(note("C5") + note("D5") + note("rest") + note("E5"))), 60, 40.0, HOP)
    engine.schedule(0.0)
    signal = np.concatenate((silence(4.0), tone(C6, 0.95), tone(D6, 0.9), silence(1.1), tone(E6, 0.95), silence(0.3)))
    beat = click(accent=False, sample_rate=SAMPLE_RATE) * 0.3
    for second in range(8):
        start = second * SAMPLE_RATE
        signal[start:start + len(beat)] += beat
    for frame in analyze(signal):
        engine.feed(frame)
    assert engine.status is RhythmStatus.FINISHED, engine.failure
