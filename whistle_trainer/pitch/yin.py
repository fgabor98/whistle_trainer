"""YIN pitch estimator (de Cheveigné and Kawahara, 2002)."""

from __future__ import annotations

import numpy as np

# Frames with less energy than this per sample (about -100 dBFS) carry no pitch.
_MIN_ENERGY = 1e-10


def _next_power_of_two(n: int) -> int:
    return 1 << (n - 1).bit_length()


def yin(
    frame: np.ndarray,
    sample_rate: float,
    min_hz: float,
    max_hz: float,
    threshold: float = 0.15,
) -> tuple[float | None, float]:
    """Estimate the fundamental frequency of a frame.

    Returns (frequency in Hz or None, confidence from 0 to 1). The frame must
    be longer than one period of min_hz plus the integration window.
    """
    tau_min = max(2, int(sample_rate / max_hz))
    tau_max = int(np.ceil(sample_rate / min_hz)) + 1
    window = len(frame) - tau_max
    if window <= tau_max:
        raise ValueError("frame is too short for the lowest frequency")
    x = np.asarray(frame, dtype=np.float64)
    if np.dot(x, x) / len(x) < _MIN_ENERGY:
        return None, 0.0

    # Difference function d(τ) = Σ (x[j] - x[j+τ])² over j < window, computed as
    # energy(0) + energy(τ) - 2·autocorrelation(τ), with the correlation by FFT.
    size = _next_power_of_two(len(x) + window)
    correlation = np.fft.irfft(np.fft.rfft(x, size) * np.conj(np.fft.rfft(x[:window], size)), size)
    correlation = correlation[: tau_max + 1]
    cumulative = np.concatenate(([0.0], np.cumsum(x * x)))
    taus = np.arange(tau_max + 1)
    energy = cumulative[window + taus] - cumulative[taus]
    difference = np.maximum(energy[0] + energy - 2 * correlation, 0.0)
    difference[0] = 0.0

    # Cumulative mean normalized difference d'(τ).
    running = np.cumsum(difference[1:])
    normalized = np.ones(tau_max + 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        normalized[1:] = np.where(running > 0, difference[1:] * taus[1:] / running, 1.0)

    search = normalized[tau_min:tau_max]
    below = np.flatnonzero(search < threshold)
    if below.size:
        tau = tau_min + below[0]
        while tau + 1 < tau_max and normalized[tau + 1] < normalized[tau]:
            tau += 1
    else:
        tau = tau_min + int(np.argmin(search))
    confidence = float(np.clip(1.0 - normalized[tau], 0.0, 1.0))

    refined = _parabolic_peak(difference, tau)
    frequency = sample_rate / refined
    if not min_hz <= frequency <= max_hz:
        return None, confidence
    return frequency, confidence


def _parabolic_peak(values: np.ndarray, index: int) -> float:
    """Sub-sample position of the minimum near index."""
    if index <= 0 or index >= len(values) - 1:
        return float(index)
    left, center, right = values[index - 1], values[index], values[index + 1]
    denominator = left - 2 * center + right
    if denominator <= 0:
        return float(index)
    return index + 0.5 * (left - right) / denominator
