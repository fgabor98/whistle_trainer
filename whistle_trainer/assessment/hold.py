"""Hold tracking following the guided-mode rules.

HoldTracker implements the shared state machine for one event, given whether
each frame is acceptable: correct pitch for notes, quiet for rests. Credit is
counted in whole frames so that long holds do not drift.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from whistle_trainer.assessment.frames import AnalysisFrame


class HoldStatus(StrEnum):
    WAITING = "waiting"  # no attempt in progress; no penalty
    CONFIRMING = "confirming"  # acceptable input, not yet stable long enough
    HOLDING = "holding"  # credit is growing
    INTERRUPTED = "interrupted"  # credit frozen during a short interruption
    PASSED = "passed"


def frames_for(seconds: float, hop_s: float) -> int:
    """Whole frames covering a duration; the epsilon absorbs floating point error."""
    return math.ceil(seconds / hop_s - 1e-6)


class HoldTracker:
    def __init__(self, required_s: float, confirmation_s: float, grace_s: float, hop_s: float):
        self.hop_s = hop_s
        self.required_frames = max(1, frames_for(required_s, hop_s))
        self.confirm_frames = max(1, min(frames_for(confirmation_s, hop_s), self.required_frames))
        self.grace_frames = math.floor(grace_s / hop_s + 1e-6)
        self.status = HoldStatus.WAITING
        self.retries = 0
        self._run = 0  # acceptable frames in the current attempt
        self._interruption = 0  # consecutive unacceptable frames while holding

    @property
    def credit_frames(self) -> int:
        holding = self.status in (HoldStatus.HOLDING, HoldStatus.INTERRUPTED, HoldStatus.PASSED)
        return self._run if holding else 0

    @property
    def credit_s(self) -> float:
        return self.credit_frames * self.hop_s

    @property
    def progress(self) -> float:
        return self.credit_frames / self.required_frames

    def reset(self) -> None:
        """Discard the unfinished attempt without counting a retry."""
        if self.status is not HoldStatus.PASSED:
            self.status = HoldStatus.WAITING
            self._run = self._interruption = 0

    def feed(self, acceptable: bool) -> bool:
        """Advance by one frame. Returns True if this frame ended an attempt (a retry)."""
        if self.status is HoldStatus.PASSED:
            return False
        if acceptable:
            self._accept()
            return False
        return self._reject()

    def _accept(self) -> None:
        self._interruption = 0
        self._run += 1
        if self.status in (HoldStatus.WAITING, HoldStatus.CONFIRMING):
            # Confirmation time counts toward the hold once it completes.
            self.status = HoldStatus.HOLDING if self._run >= self.confirm_frames else HoldStatus.CONFIRMING
        else:
            self.status = HoldStatus.HOLDING
        if self.status is HoldStatus.HOLDING and self._run >= self.required_frames:
            self.status = HoldStatus.PASSED

    def _reject(self) -> bool:
        if self.status in (HoldStatus.WAITING, HoldStatus.CONFIRMING):
            self.status = HoldStatus.WAITING
            self._run = 0
            return False
        self._interruption += 1
        if self._interruption > self.grace_frames:
            self.retries += 1
            self.reset()
            return True
        self.status = HoldStatus.INTERRUPTED
        return False


@dataclass(frozen=True)
class HoldUpdate:
    status: HoldStatus
    credit_s: float
    progress: float  # credit as a fraction of the required duration
    cents: float | None  # deviation of this frame from the target, if pitched
    retry: bool  # this frame ended an attempt that had started holding


class NoteHold:
    """Hold of a single target note, as used by the Test input page."""

    def __init__(self, target_hz: float, required_s: float, tolerance_cents: float,
                 confirmation_s: float, grace_s: float, hop_s: float):
        self.target_hz = target_hz
        self.tolerance_cents = tolerance_cents
        self.tracker = HoldTracker(required_s, confirmation_s, grace_s, hop_s)

    def accepts(self, cents: float | None) -> bool:
        return cents is not None and abs(cents) <= self.tolerance_cents

    @property
    def status(self) -> HoldStatus:
        return self.tracker.status

    @property
    def retries(self) -> int:
        return self.tracker.retries

    @property
    def credit_s(self) -> float:
        return self.tracker.credit_s

    @property
    def progress(self) -> float:
        return self.tracker.progress

    def reset(self) -> None:
        self.tracker.reset()

    def feed(self, frame: AnalysisFrame) -> HoldUpdate:
        cents = frame.cents_from(self.target_hz)
        retry = self.tracker.feed(self.accepts(cents))
        return HoldUpdate(self.status, self.credit_s, self.progress, cents, retry)
