"""Hold tracking for one target note, following the guided-mode rules.

Credit is counted in whole frames so that long holds do not drift.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from whistle_trainer.assessment.frames import AnalysisFrame


class HoldStatus(StrEnum):
    WAITING = "waiting"  # no attempt in progress; no penalty
    CONFIRMING = "confirming"  # correct pitch, not yet stable long enough
    HOLDING = "holding"  # credit is growing
    INTERRUPTED = "interrupted"  # credit frozen during a short interruption
    PASSED = "passed"


@dataclass(frozen=True)
class HoldUpdate:
    status: HoldStatus
    credit_s: float
    progress: float  # credit as a fraction of the required duration
    cents: float | None  # deviation of this frame from the target, if pitched
    retry: bool  # this frame ended an attempt that had started holding


class NoteHold:
    def __init__(self, target_hz: float, required_s: float, tolerance_cents: float,
                 confirmation_s: float, grace_s: float, hop_s: float):
        self.target_hz = target_hz
        self.tolerance_cents = tolerance_cents
        self.hop_s = hop_s
        # Durations in frames; small epsilons absorb floating point error in s / hop.
        self.required_frames = max(1, math.ceil(required_s / hop_s - 1e-6))
        self.confirm_frames = max(1, min(math.ceil(confirmation_s / hop_s - 1e-6), self.required_frames))
        self.grace_frames = math.floor(grace_s / hop_s + 1e-6)
        self.status = HoldStatus.WAITING
        self.retries = 0
        self._run = 0  # accepted frames in the current attempt
        self._interruption = 0  # consecutive frames without accepted pitch while holding

    def accepts(self, cents: float | None) -> bool:
        return cents is not None and abs(cents) <= self.tolerance_cents

    def reset(self) -> None:
        """Discard the unfinished attempt without counting a retry."""
        self.status = HoldStatus.WAITING
        self._run = self._interruption = 0

    def feed(self, frame: AnalysisFrame) -> HoldUpdate:
        cents = frame.cents_from(self.target_hz)
        retry = False
        if self.status is not HoldStatus.PASSED:
            if self.accepts(cents):
                self._accept()
            else:
                retry = self._reject()
        return HoldUpdate(
            status=self.status,
            credit_s=self.credit_s,
            progress=self.credit_frames / self.required_frames,
            cents=cents,
            retry=retry,
        )

    @property
    def credit_frames(self) -> int:
        return self._run if self.status in (HoldStatus.HOLDING, HoldStatus.INTERRUPTED, HoldStatus.PASSED) else 0

    @property
    def credit_s(self) -> float:
        return self.credit_frames * self.hop_s

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
