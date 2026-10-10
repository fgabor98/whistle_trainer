"""Sound synthesis for playback."""

from __future__ import annotations

import numpy as np

CLICK_S = 0.020
CLICK_ACCENT_HZ = 2000.0
CLICK_HZ = 1500.0
CLICK_PEAK = 0.5


def click(accent: bool, sample_rate: int) -> np.ndarray:
    """Metronome click: a 20 ms exponentially decaying tone burst, higher on beat one."""
    t = np.arange(round(CLICK_S * sample_rate)) / sample_rate
    frequency = CLICK_ACCENT_HZ if accent else CLICK_HZ
    envelope = np.exp(-t / (CLICK_S / 5))
    return (CLICK_PEAK * envelope * np.sin(2 * np.pi * frequency * t)).astype(np.float32)


WHISTLE_PEAK = 10 ** (-12 / 20)  # −12 dBFS
WHISTLE_HARMONIC = 10 ** (-30 / 20)
WHISTLE_BREATH = 10 ** (-35 / 20)
WHISTLE_ATTACK_S = 0.015
WHISTLE_RELEASE_S = 0.040
VIBRATO_HZ = 5.0
VIBRATO_CENTS = 8.0
VIBRATO_DELAY_S = 0.200


def whistle(frequency: float, duration: float, sample_rate: int, seed: int = 0) -> np.ndarray:
    """A whistle-like note: a near-sine with soft edges, gentle vibrato, and a little breath."""
    count = max(1, round(duration * sample_rate))
    t = np.arange(count) / sample_rate
    vibrato_depth = VIBRATO_CENTS * np.clip((t - VIBRATO_DELAY_S) / VIBRATO_DELAY_S, 0.0, 1.0)
    instantaneous = frequency * 2 ** (vibrato_depth * np.sin(2 * np.pi * VIBRATO_HZ * t) / 1200)
    phase = 2 * np.pi * np.cumsum(instantaneous) / sample_rate
    tone = np.sin(phase) + WHISTLE_HARMONIC * np.sin(2 * phase)

    # Breath: noise shaped into a narrow band around the fundamental by ring modulation
    # with the tone, after smoothing it to a few hundred hertz of bandwidth.
    noise = np.random.default_rng(seed).standard_normal(count)
    kernel = np.hanning(max(3, round(sample_rate / 300)))
    breath = np.convolve(noise, kernel / kernel.sum(), mode="same") * np.sin(phase)
    breath *= WHISTLE_BREATH / (np.sqrt(np.mean(breath ** 2)) + 1e-12) / np.sqrt(2)

    envelope = np.ones(count)
    attack, release = round(WHISTLE_ATTACK_S * sample_rate), round(WHISTLE_RELEASE_S * sample_rate)
    attack, release = min(attack, count // 2), min(release, count // 2)
    if attack:
        envelope[:attack] = np.linspace(0.0, 1.0, attack)
    if release:
        envelope[count - release:] *= np.linspace(1.0, 0.0, release)
    signal = (tone + breath) * envelope
    peak = np.abs(signal).max()
    return (signal * (WHISTLE_PEAK / peak if peak > 0 else 0.0)).astype(np.float32)
