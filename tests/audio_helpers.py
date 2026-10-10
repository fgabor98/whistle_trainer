"""Synthetic whistle audio and analysis frames for tests."""

from __future__ import annotations

import numpy as np

from whistle_trainer import config
from whistle_trainer.assessment.frames import AnalysisFrame, FrameClass
from whistle_trainer.pitch.analyzer import Analyzer

SAMPLE_RATE = 48000
HOP = config.ANALYSIS_HOP_S
_rng = np.random.default_rng(1234)


def tone(hz: float, seconds: float, amplitude: float = 0.1, vibrato_cents: float = 0.0,
         harmonic: float = 0.0) -> np.ndarray:
    """A whistle-like tone: sine with optional 5 Hz vibrato and second harmonic."""
    t = np.arange(round(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    instantaneous = hz * 2 ** (vibrato_cents / 1200 * np.sin(2 * np.pi * 5 * t))
    phase = 2 * np.pi * np.cumsum(instantaneous) / SAMPLE_RATE
    return amplitude * (np.sin(phase) + harmonic * np.sin(2 * phase))


def silence(seconds: float) -> np.ndarray:
    return np.zeros(round(seconds * SAMPLE_RATE))


def noise(seconds: float, amplitude: float) -> np.ndarray:
    return amplitude * _rng.standard_normal(round(seconds * SAMPLE_RATE))


def hum(seconds: float, amplitude: float) -> np.ndarray:
    t = np.arange(round(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    return amplitude * np.sin(2 * np.pi * 50 * t)


def analyze(signal: np.ndarray, threshold_db: float = -50.0, block: int = 1024) -> list[AnalysisFrame]:
    """Run a signal through the analyzer in capture-sized blocks."""
    analyzer = Analyzer(SAMPLE_RATE, threshold_db)
    frames = []
    for start in range(0, len(signal), block):
        frames.extend(analyzer.feed(signal[start:start + block]))
    return frames


class FrameScript:
    """Builds frame sequences, for example FrameScript().pitched(988, 1.0).quiet(0.08)."""

    def __init__(self):
        self.frames: list[AnalysisFrame] = []
        self.time = 0.0

    def _add(self, seconds: float, frame_class: FrameClass, hz: float | None, level: float) -> FrameScript:
        for _ in range(round(seconds / HOP)):
            confidence = 0.95 if frame_class is FrameClass.PITCHED else 0.3
            self.frames.append(AnalysisFrame(self.time, level, hz, confidence, frame_class))
            self.time += HOP
        return self

    def pitched(self, hz: float, seconds: float) -> FrameScript:
        return self._add(seconds, FrameClass.PITCHED, hz, -30.0)

    def quiet(self, seconds: float, level: float = -70.0) -> FrameScript:
        return self._add(seconds, FrameClass.QUIET, None, level)

    def unclear(self, seconds: float) -> FrameScript:
        return self._add(seconds, FrameClass.UNCLEAR, None, -35.0)
