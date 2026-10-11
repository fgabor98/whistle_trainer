"""Audio setup measurements: background level, whistle level, and practice range."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from whistle_trainer import config
from whistle_trainer.assessment.frames import AnalysisFrame, FrameClass
from whistle_trainer.pitch.display import hz_to_midi


class SetupProblem(StrEnum):
    NO_STEADY_WHISTLE = "no_steady_whistle"
    TOO_QUIET = "too_quiet"


@dataclass(frozen=True)
class LevelResult:
    noise_floor_db: float
    whistle_level_db: float | None
    activity_threshold_db: float | None
    problem: SetupProblem | None


class LevelStep(StrEnum):
    SILENCE = "silence"
    WHISTLE = "whistle"
    DONE = "done"


class LevelCalibration:
    """Measures the background, then a steady whistle, and derives the activity threshold.

    Frame classes are ignored because the threshold is not known yet; frames
    are judged by their level and pitch confidence directly.
    """

    def __init__(self, hop_seconds: float):
        self.hop = hop_seconds
        self.step = LevelStep.SILENCE
        self.result: LevelResult | None = None
        self._step_start: float | None = None
        self._silence_levels: list[float] = []
        self._noise_floor = config.SILENCE_DB
        self._whistle_levels: list[float] = []

    def progress(self) -> float:
        """Progress of the current step from 0 to 1."""
        if self.step is LevelStep.SILENCE:
            return min(1.0, len(self._silence_levels) * self.hop / config.SETUP_SILENCE_S)
        if self.step is LevelStep.WHISTLE:
            return min(1.0, len(self._whistle_levels) * self.hop / config.SETUP_WHISTLE_S)
        return 1.0

    def feed(self, frame: AnalysisFrame) -> LevelStep:
        if self.step is LevelStep.DONE:
            return self.step
        if self._step_start is None:
            self._step_start = frame.time

        if self.step is LevelStep.SILENCE:
            self._silence_levels.append(frame.level_db)
            if len(self._silence_levels) * self.hop >= config.SETUP_SILENCE_S:
                self._noise_floor = float(np.percentile(self._silence_levels, 95))
                self.step, self._step_start = LevelStep.WHISTLE, None
        elif self.step is LevelStep.WHISTLE:
            provisional = self._noise_floor + config.SETUP_MIN_MARGIN_DB
            if (frame.level_db >= provisional and frame.f0_hz is not None
                    and frame.confidence >= config.MIN_PITCH_CONFIDENCE):
                self._whistle_levels.append(frame.level_db)
            if len(self._whistle_levels) * self.hop >= config.SETUP_WHISTLE_S:
                self._finish()
            elif frame.time - self._step_start >= config.SETUP_WHISTLE_TIMEOUT_S:
                self._finish()
        return self.step

    def _finish(self) -> None:
        self.step = LevelStep.DONE
        noise = self._noise_floor
        if len(self._whistle_levels) * self.hop < config.SETUP_WHISTLE_S:
            self.result = LevelResult(noise, None, None, SetupProblem.NO_STEADY_WHISTLE)
            return
        whistle = float(np.median(self._whistle_levels))
        if whistle - noise < config.SETUP_MIN_USABLE_MARGIN_DB:
            self.result = LevelResult(noise, whistle, None, SetupProblem.TOO_QUIET)
            return
        threshold = max((noise + whistle) / 2, noise + config.SETUP_MIN_MARGIN_DB)
        self.result = LevelResult(noise, whistle, threshold, None)


class RangeMeasurement:
    """Measures one comfortable note: the median pitch of a steady whistle."""

    def __init__(self, hop_seconds: float):
        self.hop = hop_seconds
        self.done = False
        self.midi: int | None = None  # None if no steady note was found in time
        self._start: float | None = None
        self._pitches: list[float] = []

    def progress(self) -> float:
        return min(1.0, len(self._pitches) * self.hop / config.SETUP_RANGE_NOTE_S)

    def feed(self, frame: AnalysisFrame) -> bool:
        """Returns True when the measurement has finished."""
        if self.done:
            return True
        if self._start is None:
            self._start = frame.time
        if frame.frame_class is FrameClass.PITCHED and frame.f0_hz is not None:
            self._pitches.append(hz_to_midi(frame.f0_hz))
        if len(self._pitches) * self.hop >= config.SETUP_RANGE_NOTE_S:
            self.midi = round(float(np.median(self._pitches)))
            self.done = True
        elif frame.time - self._start >= config.SETUP_RANGE_TIMEOUT_S:
            self.done = True
        return self.done


class Pause:
    """A timed pause between measurements; input during it is ignored."""

    def __init__(self, seconds: float):
        self.seconds = seconds
        self.done = False
        self._start: float | None = None
        self._elapsed = 0.0

    def progress(self) -> float:
        return min(1.0, self._elapsed / self.seconds)

    def feed(self, frame: AnalysisFrame) -> bool:
        """Returns True when the pause is over."""
        if self._start is None:
            self._start = frame.time
        self._elapsed = frame.time - self._start
        self.done = self.done or self._elapsed >= self.seconds
        return self.done
