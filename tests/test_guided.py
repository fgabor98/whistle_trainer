import numpy as np
import pytest

from audio_helpers import FrameScript, analyze, silence, tone
from conftest import note, score
from whistle_trainer import config
from whistle_trainer.assessment.guided import GuidedEngine
from whistle_trainer.assessment.hold import HoldStatus

HOP = config.ANALYSIS_HOP_S
TIE_START = '<tie type="start"/>'
TIE_STOP = '<tie type="stop"/>'

# Sounding pitches: written C5 sounds C6 and so on.
C6, D6, E6 = 1046.50, 1174.66, 1318.51


def engine_for(parse, *measures, tempo=60, start=0) -> GuidedEngine:
    return GuidedEngine(parse(score(*measures)), tempo, 40.0, HOP, start)


def feed(engine: GuidedEngine, script: FrameScript) -> list:
    return [engine.feed(f) for f in script.frames]


def test_notes_pass_in_order_with_tempo_durations(parse):
    engine = engine_for(parse, note("C5", 4, "half") + note("D5") + note("E5"))
    updates = feed(engine, FrameScript().pitched(C6, 2.0))
    assert updates[-1].index == 0 and updates[-1].status is HoldStatus.PASSED
    assert engine.position == 1
    feed(engine, FrameScript().pitched(D6, 1.0).pitched(E6, 1.0))
    assert engine.finished and engine.completed == {0, 1, 2}


def test_tempo_changes_required_hold(parse):
    engine = engine_for(parse, note("C5") * 4, tempo=120)
    updates = feed(engine, FrameScript().pitched(C6, 0.5))
    assert updates[-1].required_s == pytest.approx(0.5)
    assert updates[-1].status is HoldStatus.PASSED


def test_dotted_notes_use_total_duration(parse):
    engine = engine_for(parse, note("C5", 3, "quarter", dots=1) + note("D5", 1, "eighth") + note("E5", 4, "half"))
    updates = feed(engine, FrameScript().pitched(C6, 1.5))
    assert [u.status for u in updates[-2:]] == [HoldStatus.HOLDING, HoldStatus.PASSED]


def test_moving_to_a_different_pitch_needs_no_silence(parse):
    engine = engine_for(parse, note("C5") + note("D5") + note("C5") + note("D5"))
    feed(engine, FrameScript().pitched(C6, 1.0).pitched(D6, 1.0).pitched(C6, 1.0).pitched(D6, 1.0))
    assert engine.finished


def test_continuous_whistle_cannot_clear_repeated_notes(parse):
    engine = engine_for(parse, note("C5") + note("C5") + note("D5") * 2)
    updates = feed(engine, FrameScript().pitched(C6, 3.0))
    assert engine.position == 1 and engine.completed == {0}
    assert all(u.needs_release for u in updates[100:])
    assert engine.tracker.status is HoldStatus.WAITING


def test_repeated_note_after_release(parse):
    engine = engine_for(parse, note("C5") + note("C5") + note("D5") * 2)
    feed(engine, FrameScript().pitched(C6, 1.0).quiet(0.05).pitched(C6, 1.0))
    assert engine.position == 1  # 50 ms is too short a release
    engine = engine_for(parse, note("C5") + note("C5") + note("D5") * 2)
    feed(engine, FrameScript().pitched(C6, 1.0).quiet(config.REPEATED_NOTE_RELEASE_S).pitched(C6, 1.0))
    assert engine.position == 2


def test_unclear_input_is_not_a_release(parse):
    engine = engine_for(parse, note("C5") + note("C5") + note("D5") * 2)
    feed(engine, FrameScript().pitched(C6, 1.0).unclear(0.3).pitched(C6, 1.0))
    assert engine.position == 1


def test_tied_notes_accept_one_continuous_hold(parse):
    engine = engine_for(parse, note("C5", 1, "eighth", TIE_START) + note("C5", 1, "eighth", TIE_STOP)
                        + note("D5", 2) + note("E5", 4, "half"), tempo=60)
    assert len(engine.song.events) == 3
    updates = feed(engine, FrameScript().pitched(C6, 1.0))
    assert updates[-1].index == 0 and updates[-1].status is HoldStatus.PASSED
    assert updates[-1].required_s == pytest.approx(1.0)


def test_tied_half_second_notes_at_tempo(parse):
    # Two tied eighths at 60 bpm are half a second each: one continuous 1-second hold.
    engine = engine_for(parse, note("C5", 1, "eighth", TIE_START) + note("C5", 1, "eighth", TIE_STOP)
                        + note("D5", 6, "half", dots=1))
    feed(engine, FrameScript().pitched(C6, 0.6).quiet(0.2).pitched(C6, 0.6))
    assert engine.position == 0  # a gap is not allowed inside a tie
    engine.reset_current()
    feed(engine, FrameScript().pitched(C6, 1.0))
    assert engine.position == 1


def test_rest_requires_quiet_for_its_duration(parse):
    engine = engine_for(parse, note("C5") + note("rest") + note("D5", 4, "half"))
    feed(engine, FrameScript().pitched(C6, 1.0))
    updates = feed(engine, FrameScript().quiet(1.0))
    assert updates[0].index == 1 and updates[-1].status is HoldStatus.PASSED
    assert engine.position == 2


def test_whistling_cannot_pass_a_rest(parse):
    engine = engine_for(parse, note("C5") + note("rest") + note("D5", 4, "half"))
    feed(engine, FrameScript().pitched(C6, 1.0))
    updates = feed(engine, FrameScript().pitched(C6, 2.0).pitched(D6, 2.0).unclear(1.0))
    assert engine.position == 1
    assert all(u.status is HoldStatus.WAITING for u in updates)
    assert engine.retries == {}


def test_rest_brief_interruption_freezes_long_resets(parse):
    engine = engine_for(parse, note("C5") + note("rest") + note("D5", 4, "half"))
    feed(engine, FrameScript().pitched(C6, 1.0))
    updates = feed(engine, FrameScript().quiet(0.5).unclear(0.08).quiet(0.5))
    assert updates[55].status is HoldStatus.INTERRUPTED
    assert updates[-1].status is HoldStatus.PASSED and engine.retries == {}

    engine = engine_for(parse, note("C5") + note("rest") + note("D5", 4, "half"))
    feed(engine, FrameScript().pitched(C6, 1.0))
    feed(engine, FrameScript().quiet(0.5).pitched(C6, 0.2))
    assert engine.position == 1 and engine.retries == {1: 1}


def test_background_noise_below_threshold_does_not_block_rest(parse):
    engine = engine_for(parse, note("rest") + note("C5") * 3)
    feed(engine, FrameScript().quiet(1.0, level=-48))
    assert engine.position == 1


def test_retries_are_counted_per_event(parse):
    engine = engine_for(parse, note("C5") + note("D5") + note("E5") * 2)
    feed(engine, FrameScript().pitched(C6, 0.5).quiet(0.3).pitched(C6, 0.5).quiet(0.3).pitched(C6, 1.0))
    feed(engine, FrameScript().pitched(D6, 0.4).quiet(0.3).pitched(D6, 1.0))
    assert engine.retries == {0: 2, 1: 1}


def test_silence_and_wrong_notes_before_starting_are_free(parse):
    engine = engine_for(parse, note("C5") * 4)
    feed(engine, FrameScript().quiet(3.0).pitched(E6, 1.0).pitched(C6, 0.05).quiet(0.5))
    assert engine.retries == {}


def test_start_position_and_reset(parse):
    engine = engine_for(parse, note("C5") + note("D5") + note("E5") * 2, start=2)
    assert engine.position == 2
    feed(engine, FrameScript().pitched(E6, 0.5))
    assert engine.tracker.credit_s == pytest.approx(0.5)
    engine.reset_current()
    assert engine.tracker.credit_s == 0 and engine.retries == {}


def test_finished_update_and_later_frames(parse):
    engine = engine_for(parse, note("C5", 8, "whole"))
    updates = feed(engine, FrameScript().pitched(C6, 4.0))
    assert updates[-1].finished and engine.finished
    assert engine.feed(FrameScript().pitched(C6, 0.01).frames[0]).finished


def test_audio_melody_with_repeated_notes_rest_and_tie(parse):
    engine = engine_for(
        parse,
        note("C5") + note("C5") + note("D5", 4, "half", TIE_START),
        note("D5", 2, "quarter", TIE_STOP) + note("rest") + note("E5", 4, "half"),
        tempo=120,
    )
    signal = np.concatenate((
        tone(C6, 0.6), silence(0.2), tone(C6, 0.6),  # repeated note with a breath
        tone(D6, 1.6),  # tied half + quarter: 1.5 s at 120 bpm
        silence(0.7),  # rest: 0.5 s
        tone(E6, 1.2), silence(0.2),
    ))
    for frame in analyze(signal):
        engine.feed(frame)
    assert engine.finished and engine.retries == {}


def test_section_ends_at_end_index(parse):
    engine = GuidedEngine(parse(score(note("C5") + note("D5") + note("E5") + note("D5"))), 60, 40.0, HOP, 1, 3)
    feed(engine, FrameScript().pitched(D6, 1.0))
    assert not engine.finished
    updates = feed(engine, FrameScript().pitched(E6, 1.0))
    assert updates[-1].finished and engine.completed == {1, 2}
