"""Notes rendered in the sound chosen for Listen and Hear note: whistle or piano."""

from __future__ import annotations

import math
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np

from whistle_trainer import config
from whistle_trainer.audio.synth import whistle
from whistle_trainer.config import Sound

PIANO_DIR = Path(__file__).resolve().parent.parent / "resources" / "sounds" / "piano"


@lru_cache(maxsize=1)
def piano_notes() -> tuple[int, ...]:
    """MIDI notes that have a piano sample."""
    return tuple(sorted(int(path.stem) for path in PIANO_DIR.glob("*.wav")))


@lru_cache(maxsize=None)
def piano_sample(midi: int) -> tuple[np.ndarray, int]:
    """The sample for a MIDI note as floats from -1 to 1, and its sample rate."""
    with wave.open(str(PIANO_DIR / f"{midi}.wav")) as file:
        if file.getsampwidth() != 2 or file.getnchannels() != 1:
            raise ValueError(f"{file} must be 16-bit mono")
        data = np.frombuffer(file.readframes(file.getnframes()), dtype="<i2")
        return data.astype(np.float32) / 32768.0, file.getframerate()


def piano(frequency: float, duration: float, sample_rate: int) -> np.ndarray:
    """A piano note: the nearest recorded note, resampled to the frequency and cut at the duration."""
    target_midi = 69 + 12 * math.log2(frequency / config.A4_HZ)
    nearest = min(piano_notes(), key=lambda m: abs(m - target_midi))
    sample, sample_rate_in = piano_sample(nearest)
    sample_frequency = config.A4_HZ * 2 ** ((nearest - 69) / 12)
    # Stepping through the sample faster raises the pitch; the rate ratio converts sample rates.
    step = frequency / sample_frequency * sample_rate_in / sample_rate
    count = min(round(duration * sample_rate), int((len(sample) - 1) / step))
    note = np.interp(np.arange(count) * step, np.arange(len(sample)), sample).astype(np.float32)
    release = min(round(config.PIANO_RELEASE_S * sample_rate), count)
    if release:
        note[count - release:] *= np.linspace(1.0, 0.0, release, dtype=np.float32)
    return note


def render(sound: Sound, frequency: float, duration: float, sample_rate: int, seed: int = 0) -> np.ndarray:
    if sound is Sound.PIANO:
        return piano(frequency, duration, sample_rate)
    return whistle(frequency, duration, sample_rate, seed=seed)
