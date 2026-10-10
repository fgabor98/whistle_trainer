"""Plain-language guidance shown while whistling."""

from __future__ import annotations

import math

from whistle_trainer import strings
from whistle_trainer.assessment.frames import FrameClass
from whistle_trainer.assessment.hold import HoldStatus
from whistle_trainer.pitch.display import NoteDisplay


def smoothed_cents(display: NoteDisplay, target_hz: float) -> float | None:
    """Deviation of the displayed (smoothed) pitch from the target, for guidance only."""
    note = display.current
    return None if note is None else 1200 * math.log2(note.frequency / target_hz)


def guide_text(status: HoldStatus, last_class: FrameClass | None, cents: float | None,
               tolerance: float, is_rest: bool = False, needs_release: bool = False) -> str:
    if is_rest:
        return strings.GUIDE_TAKE_BREATH
    if needs_release:
        return strings.GUIDE_RELEASE
    if status is HoldStatus.INTERRUPTED:
        return strings.GUIDE_KEEP_GOING
    if status in (HoldStatus.CONFIRMING, HoldStatus.HOLDING):
        return strings.GUIDE_HOLD
    if last_class is FrameClass.UNCLEAR:
        return strings.GUIDE_NO_CLEAR_PITCH
    if last_class is FrameClass.PITCHED and cents is not None:
        if cents > tolerance:
            return strings.GUIDE_WHISTLE_LOWER
        if cents < -tolerance:
            return strings.GUIDE_WHISTLE_HIGHER
        return strings.GUIDE_HOLD
    return strings.GUIDE_START_WHEN_READY
