"""Analysis frames: what the assessment engines see of the audio."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class FrameClass(StrEnum):
    QUIET = "quiet"  # below the activity threshold
    PITCHED = "pitched"  # active, with a clear pitch in the whistle range
    UNCLEAR = "unclear"  # active, but no clear pitch


@dataclass(frozen=True)
class AnalysisFrame:
    time: float  # seconds on the capture clock, at the center of the analysis window
    level_db: float  # RMS level of the band-passed signal in dBFS
    f0_hz: float | None
    confidence: float
    frame_class: FrameClass

    def cents_from(self, target_hz: float) -> float | None:
        """Deviation from a target frequency in cents, if the frame has a clear pitch."""
        if self.frame_class is not FrameClass.PITCHED or self.f0_hz is None:
            return None
        return 1200 * math.log2(self.f0_hz / target_hz)


def classify(level_db: float, f0_hz: float | None, confidence: float,
             activity_threshold_db: float, min_confidence: float) -> FrameClass:
    if level_db < activity_threshold_db:
        return FrameClass.QUIET
    if f0_hz is not None and confidence >= min_confidence:
        return FrameClass.PITCHED
    return FrameClass.UNCLEAR
