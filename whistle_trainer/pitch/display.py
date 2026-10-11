"""The smoothed "detected note" shown to the user. Never used for assessment."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from whistle_trainer import config
from whistle_trainer.assessment.frames import AnalysisFrame, FrameClass
from whistle_trainer.music.model import Pitch
from whistle_trainer.music.transpose import spell_midi


def hz_to_midi(frequency: float, a4_hz: float = config.A4_HZ) -> float:
    return 69 + 12 * math.log2(frequency / a4_hz)


@dataclass(frozen=True)
class DetectedNote:
    pitch: Pitch  # nearest note, spelled with sharps
    frequency: float  # smoothed frequency
    cents: float  # deviation of the smoothed frequency from the nearest note


class NoteDisplay:
    """Median-smoothed pitch with a short hold before the shown note changes."""

    def __init__(self):
        self._recent: deque[float] = deque(maxlen=config.DISPLAY_MEDIAN_FRAMES)
        self._shown: int | None = None
        self._candidate: int | None = None
        self._candidate_since = 0.0
        self._last_pitched = -math.inf
        self.current: DetectedNote | None = None

    def reset(self) -> None:
        self.__init__()

    def feed(self, frame: AnalysisFrame) -> DetectedNote | None:
        if frame.frame_class is FrameClass.PITCHED and frame.f0_hz is not None:
            self._last_pitched = frame.time
            self._recent.append(frame.f0_hz)
            frequency = float(np.median(self._recent))
            nearest = round(hz_to_midi(frequency))
            if self._shown is None:
                self._shown = nearest
            elif nearest != self._shown:
                if nearest != self._candidate:
                    self._candidate, self._candidate_since = nearest, frame.time
                elif frame.time - self._candidate_since >= config.DISPLAY_STABLE_S:
                    self._shown = nearest
            if nearest == self._shown:
                self._candidate = None
            cents = (hz_to_midi(frequency) - self._shown) * 100
            self.current = DetectedNote(spell_midi(self._shown), frequency, cents)
        elif frame.time - self._last_pitched > config.DISPLAY_TIMEOUT_S:
            self._recent.clear()
            self._shown = self._candidate = None
            self.current = None
        return self.current
