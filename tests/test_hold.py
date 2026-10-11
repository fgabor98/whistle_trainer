import numpy as np
import pytest

from audio_helpers import FrameScript, analyze, noise, silence, tone
from whistle_trainer import config
from whistle_trainer.assessment.hold import HoldStatus, NoteHold

B5 = 987.77
CENTS_30 = 2 ** (30 / 1200)


def make_hold(required_s: float = 1.0, tolerance: float = 40.0) -> NoteHold:
    return NoteHold(B5, required_s, tolerance, config.STABLE_CONFIRMATION_S, config.GRACE_PERIOD_S,
                    config.ANALYSIS_HOP_S)


def run(hold: NoteHold, frames) -> list:
    return [hold.feed(f) for f in frames]


def test_one_second_target_passes_after_one_second_including_confirmation():
    hold = make_hold()
    updates = run(hold, FrameScript().pitched(B5, 1.0).frames)
    assert [u.status for u in updates[:9]] == [HoldStatus.CONFIRMING] * 9
    assert updates[9].status is HoldStatus.HOLDING and updates[9].credit_s == pytest.approx(0.1)
    assert updates[98].status is HoldStatus.HOLDING
    assert updates[99].status is HoldStatus.PASSED
    assert hold.retries == 0


def test_holding_longer_never_reverses_success():
    hold = make_hold()
    run(hold, FrameScript().pitched(B5, 1.0).quiet(0.5).pitched(B5 * 2, 0.5).frames)
    assert hold.status is HoldStatus.PASSED


def test_within_tolerance_passes_and_outside_does_not():
    assert run(make_hold(tolerance=40), FrameScript().pitched(B5 * CENTS_30, 1.0).frames)[-1].status is HoldStatus.PASSED
    assert run(make_hold(tolerance=25), FrameScript().pitched(B5 * CENTS_30, 1.0).frames)[-1].status is HoldStatus.WAITING


@pytest.mark.parametrize("hz", [B5 / 2, B5 * 2, 880.0, 1046.5])
def test_wrong_pitches_and_octave_errors_never_pass(hz):
    hold = make_hold()
    updates = run(hold, FrameScript().pitched(hz, 3.0).frames)
    assert all(u.status is HoldStatus.WAITING for u in updates)
    assert hold.retries == 0


def test_weak_or_unclear_input_earns_nothing():
    hold = make_hold()
    updates = run(hold, FrameScript().quiet(1.0, level=-40).unclear(2.0).frames)
    assert all(u.credit_s == 0 and u.status is HoldStatus.WAITING for u in updates)


def test_silence_before_starting_is_not_penalized():
    hold = make_hold()
    run(hold, FrameScript().quiet(5.0).pitched(B5, 1.0).frames)
    assert hold.status is HoldStatus.PASSED and hold.retries == 0


def test_breaking_off_during_confirmation_is_not_a_retry():
    hold = make_hold()
    run(hold, FrameScript().pitched(B5, 0.05).quiet(0.5).frames)
    assert hold.status is HoldStatus.WAITING and hold.retries == 0


def test_short_attempts_do_not_accumulate():
    hold = make_hold()
    script = FrameScript()
    for _ in range(4):
        script.pitched(B5, 0.4).quiet(0.3)
    updates = run(hold, script.frames)
    assert hold.status is HoldStatus.WAITING
    assert max(u.credit_s for u in updates) == pytest.approx(0.4)
    assert hold.retries == 4


def test_80_ms_dropout_freezes_progress_without_credit():
    hold = make_hold()
    updates = run(hold, FrameScript().pitched(B5, 0.5).quiet(0.08).frames)
    frozen = updates[50:]
    assert all(u.status is HoldStatus.INTERRUPTED for u in frozen)
    assert all(u.credit_s == pytest.approx(0.5) for u in frozen)
    updates = run(hold, FrameScript().pitched(B5, 0.5).frames)
    assert updates[-2].status is HoldStatus.HOLDING
    assert updates[-1].status is HoldStatus.PASSED  # 0.5 + 0.5 s credited, the gap excluded
    assert hold.retries == 0


def test_wrong_pitch_during_hold_is_an_interruption():
    hold = make_hold()
    updates = run(hold, FrameScript().pitched(B5, 0.5).pitched(880, 0.05).pitched(B5, 0.5).frames)
    assert updates[-1].status is HoldStatus.PASSED and hold.retries == 0


def test_interruption_beyond_grace_resets_and_counts_a_retry():
    hold = make_hold()
    updates = run(hold, FrameScript().pitched(B5, 0.5).quiet(0.11).frames)
    assert updates[-2].status is HoldStatus.INTERRUPTED
    assert updates[-1].status is HoldStatus.WAITING and updates[-1].retry
    assert hold.retries == 1 and hold.credit_s == 0


def test_exactly_the_grace_period_is_still_allowed():
    hold = make_hold()
    run(hold, FrameScript().pitched(B5, 0.5).quiet(config.GRACE_PERIOD_S).frames)
    assert hold.status is HoldStatus.INTERRUPTED and hold.retries == 0


def test_confirmation_is_capped_at_short_notes():
    hold = make_hold(required_s=0.05)
    updates = run(hold, FrameScript().pitched(B5, 0.05).frames)
    assert updates[-1].status is HoldStatus.PASSED


def test_reset_discards_attempt_without_retry():
    hold = make_hold()
    run(hold, FrameScript().pitched(B5, 0.5).frames)
    hold.reset()
    assert hold.status is HoldStatus.WAITING and hold.credit_s == 0 and hold.retries == 0


# The same rules on synthesized audio through the full analyzer.

def held_status(signal: np.ndarray) -> NoteHold:
    hold = make_hold()
    run(hold, analyze(signal))
    return hold


def test_audio_whistle_with_vibrato_and_noise_passes():
    signal = np.concatenate((silence(0.5), tone(B5, 1.2, vibrato_cents=15), silence(0.3)))
    hold = held_status(signal + noise(len(signal) / 48000, 0.002))
    assert hold.status is HoldStatus.PASSED and hold.retries == 0


def test_audio_too_short_whistle_does_not_pass():
    hold = held_status(np.concatenate((silence(0.5), tone(B5, 0.9), silence(0.5))))
    assert hold.status is not HoldStatus.PASSED


def test_audio_short_dropout_is_bridged():
    signal = np.concatenate((silence(0.3), tone(B5, 0.6), silence(0.04), tone(B5, 0.6), silence(0.3)))
    hold = held_status(signal)
    assert hold.status is HoldStatus.PASSED and hold.retries == 0


def test_audio_long_dropout_resets():
    signal = np.concatenate((silence(0.3), tone(B5, 0.6), silence(0.25), tone(B5, 0.6), silence(0.3)))
    hold = held_status(signal)
    assert hold.status is not HoldStatus.PASSED and hold.retries >= 1


def test_audio_octave_error_never_passes():
    hold = held_status(np.concatenate((silence(0.3), tone(B5 * 2, 2.0), tone(B5 / 2, 2.0))))
    assert hold.status is HoldStatus.WAITING
