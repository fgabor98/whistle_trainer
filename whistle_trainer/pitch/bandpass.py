"""Streaming linear-phase band-pass filter."""

from __future__ import annotations

import numpy as np


def design_bandpass(sample_rate: float, low_hz: float, high_hz: float, taps: int) -> np.ndarray:
    """Windowed-sinc FIR band-pass filter with a Hann window and unity passband gain."""
    if taps % 2 == 0:
        raise ValueError("taps must be odd for a whole-sample delay")
    n = np.arange(taps) - (taps - 1) / 2

    def lowpass(cutoff: float) -> np.ndarray:
        return 2 * cutoff / sample_rate * np.sinc(2 * cutoff / sample_rate * n)

    kernel = (lowpass(high_hz) - lowpass(low_hz)) * np.hanning(taps)
    center = (low_hz + high_hz) / 2
    gain = abs(np.sum(kernel * np.exp(-2j * np.pi * center / sample_rate * n)))
    return kernel / gain


class StreamingFilter:
    """Applies an FIR kernel to consecutive blocks as if they were one signal.

    Output sample k corresponds to input sample k - delay.
    """

    def __init__(self, kernel: np.ndarray):
        self.kernel = kernel
        self.delay = (len(kernel) - 1) // 2
        self._history = np.zeros(len(kernel) - 1)
        self._spectra: dict[int, np.ndarray] = {}

    def process(self, block: np.ndarray) -> np.ndarray:
        if len(block) == 0:
            return np.zeros(0)
        signal = np.concatenate((self._history, block))
        size = 1 << (len(signal) + len(self.kernel) - 2).bit_length()
        if size not in self._spectra:
            self._spectra[size] = np.fft.rfft(self.kernel, size)
        filtered = np.fft.irfft(np.fft.rfft(signal, size) * self._spectra[size], size)
        self._history = signal[len(signal) - len(self._history):]
        return filtered[len(self.kernel) - 1 : len(signal)]
