"""Converts Salamander Grand Piano samples into the small WAV files bundled with the app.

The source is https://github.com/sfzinstruments/SalamanderGrandPiano (Samples/<note>v10.flac),
by Alexander Holm, licensed under CC BY 3.0. Reading FLAC needs the `soundfile` package,
which the app itself does not use, so run this in a separate environment:

    python3 -m venv /tmp/convert && /tmp/convert/bin/pip install soundfile numpy
    /tmp/convert/bin/python scripts/make_piano_samples.py <folder with the .flac files>

Each sample is mixed to mono, trimmed to start at the hammer strike, retuned to exact
equal-tempered pitch (pianos are tuned slightly sharp toward the treble, but the app grades
whistling against exact pitch), cut to a few seconds with a fade-out, normalized to the
same peak level, and written as 16-bit WAV named after its MIDI note number.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile

NOTES = ["C4", "D#4", "F#4", "A4", "C5", "D#5", "F#5", "A5", "C6", "D#6", "F#6", "A6", "C7", "D#7", "F#7"]
SEMITONES = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
VELOCITY = 10  # of 16 layers: a moderately strong touch
LENGTH_S = 4.0
FADE_S = 1.0
PEAK = 10 ** (-6 / 20)
ONSET_FRACTION = 0.02  # the strike starts where the signal first reaches 2 percent of its peak
PRE_ROLL_S = 0.002

OUTPUT = Path(__file__).resolve().parent.parent / "whistle_trainer" / "resources" / "sounds" / "piano"


def midi(note: str) -> int:
    return (int(note[-1]) + 1) * 12 + SEMITONES[note[:-1]]


def fundamental(signal: np.ndarray, rate: int, expected: float) -> float:
    """The strongest frequency within a semitone of the expected one, from 0.2 to 1.2 s after the strike."""
    segment = signal[round(0.2 * rate):round(1.2 * rate)] * np.hanning(round(1.2 * rate) - round(0.2 * rate))
    size = 4 * len(segment)
    spectrum = np.log(np.abs(np.fft.rfft(segment, size)) + 1e-12)
    frequencies = np.fft.rfftfreq(size, 1 / rate)
    band = np.flatnonzero((frequencies > expected * 2 ** (-1 / 12)) & (frequencies < expected * 2 ** (1 / 12)))
    peak = band[np.argmax(spectrum[band])]
    left, center, right = spectrum[peak - 1:peak + 2]
    offset = 0.5 * (left - right) / (left - 2 * center + right)
    return (peak + offset) * rate / size


def convert(source: Path, target: Path, note_midi: int) -> float:
    """Writes the converted sample; returns the correction applied in cents."""
    data, rate = soundfile.read(source, dtype="float64", always_2d=True)
    mono = data.mean(axis=1)
    onset = int(np.argmax(np.abs(mono) >= ONSET_FRACTION * np.abs(mono).max()))
    start = max(0, onset - round(PRE_ROLL_S * rate))
    mono = mono[start:]

    expected = 440.0 * 2 ** ((note_midi - 69) / 12)
    ratio = fundamental(mono, rate, expected) / expected
    # Stepping through the recording in steps of 1/ratio samples moves the pitch to exact.
    positions = np.arange(0, len(mono) - 1, 1 / ratio)
    mono = np.interp(positions, np.arange(len(mono)), mono)

    clip = mono[:round(LENGTH_S * rate)].copy()
    fade = round(FADE_S * rate)
    clip[-fade:] *= 0.5 * (1 + np.cos(np.linspace(0, np.pi, fade)))
    clip *= PEAK / np.abs(clip).max()
    soundfile.write(target, clip, rate, subtype="PCM_16")
    return -1200 * np.log2(ratio)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="folder containing the Salamander .flac samples")
    arguments = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for note in NOTES:
        target = OUTPUT / f"{midi(note)}.wav"
        correction = convert(arguments.source / f"{note}v{VELOCITY}.flac", target, midi(note))
        print(f"{note} -> {target.name} (retuned {correction:+.1f} cents)")


if __name__ == "__main__":
    main()
