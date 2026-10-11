"""Conversion of written durations to seconds at a tempo."""

from __future__ import annotations

from fractions import Fraction

from whistle_trainer.music.model import Song, TimeSignature


def seconds(quarters: Fraction, tempo: float) -> float:
    """Seconds for a length in quarter notes at a tempo in quarter notes per minute."""
    return float(quarters) * 60.0 / tempo


def beat_seconds(time: TimeSignature, tempo: float) -> float:
    return seconds(time.beat_length, tempo)


def song_seconds(song: Song, tempo: float, start_index: int = 0) -> float:
    """Playing time from an event to the end, excluding waiting and retries."""
    if start_index >= len(song.events):
        return 0.0
    return seconds(song.length - song.events[start_index].start, tempo)


def event_times(song: Song, tempo: float, start_index: int = 0) -> list[tuple[float, float]]:
    """Start and end in seconds of each event from start_index, relative to its start."""
    if start_index >= len(song.events):
        return []
    origin = song.events[start_index].start
    return [
        (seconds(e.start - origin, tempo), seconds(e.end - origin, tempo))
        for e in song.events[start_index:]
    ]
