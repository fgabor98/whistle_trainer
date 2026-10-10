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
