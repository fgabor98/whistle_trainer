"""Turns a stream of samples into analysis frames."""

from __future__ import annotations

import math

import numpy as np

from whistle_trainer import config
from whistle_trainer.assessment.frames import AnalysisFrame, classify
from whistle_trainer.pitch.bandpass import StreamingFilter, design_bandpass
from whistle_trainer.pitch.yin import yin


def level_db(samples: np.ndarray) -> float:
    """RMS level in dBFS, floored at config.SILENCE_DB."""
    if len(samples) == 0:
        return config.SILENCE_DB
    rms = math.sqrt(float(np.mean(np.square(samples, dtype=np.float64))))
    return max(20 * math.log10(rms), config.SILENCE_DB) if rms > 0 else config.SILENCE_DB


class Analyzer:
    """Band-pass filters the input and produces one frame per hop.

    Feed consecutive blocks of mono float samples; frame times are seconds
    since the first sample, measured at the center of each analysis window.
    """

    def __init__(self, sample_rate: int, activity_threshold_db: float = config.UNCALIBRATED_THRESHOLD_DB):
        self.sample_rate = sample_rate
        self.activity_threshold_db = activity_threshold_db
        self.window = round(config.ANALYSIS_WINDOW_S * sample_rate)
        self.hop = round(config.ANALYSIS_HOP_S * sample_rate)
        taps = round(config.BANDPASS_LENGTH_S * sample_rate) | 1
        self._filter = StreamingFilter(
            design_bandpass(sample_rate, config.BANDPASS_LOW_HZ, config.BANDPASS_HIGH_HZ, taps)
        )
        # Filtered samples not yet consumed, and the stream index of the first one.
        self._buffer = np.zeros(0)
        self._buffer_start = 0

    @property
    def hop_seconds(self) -> float:
        return self.hop / self.sample_rate

    @property
    def latency_seconds(self) -> float:
        """Delay from a sound reaching the input to the frame centered on it being produced."""
        return (self._filter.delay + self.window / 2) / self.sample_rate

    def feed(self, samples: np.ndarray) -> list[AnalysisFrame]:
        filtered = self._filter.process(np.asarray(samples, dtype=np.float64))
        self._buffer = np.concatenate((self._buffer, filtered))
        frames = []
        while len(self._buffer) >= self.window:
            frames.append(self._analyze(self._buffer[: self.window], self._buffer_start))
            self._buffer = self._buffer[self.hop:]
            self._buffer_start += self.hop
        return frames

    def _analyze(self, window: np.ndarray, start: int) -> AnalysisFrame:
        level = level_db(window)
        f0, confidence = yin(
            window, self.sample_rate, config.PITCH_MIN_HZ, config.PITCH_MAX_HZ, config.YIN_THRESHOLD
        )
        center = start + self.window / 2 - self._filter.delay
        return AnalysisFrame(
            time=center / self.sample_rate,
            level_db=level,
            f0_hz=f0,
            confidence=confidence,
            frame_class=classify(level, f0, confidence, self.activity_threshold_db, config.MIN_PITCH_CONFIDENCE),
        )
