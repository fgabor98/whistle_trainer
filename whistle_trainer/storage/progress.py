"""Practice progress per song and mode."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import platformdirs

from whistle_trainer import strings
from whistle_trainer.config import Mode
from whistle_trainer.storage.jsonfile import UnreadableFile, quarantine, read_json, require, write_json_atomic
from whistle_trainer.storage.settings import APP_DIR_NAME

SCHEMA_VERSION = 1


def default_progress_path() -> Path:
    return platformdirs.user_data_path(APP_DIR_NAME, appauthor=False) / "progress.json"


@dataclass
class SongProgress:
    """Progress of one song in one mode."""

    event_count: int
    completed: set[int] = field(default_factory=set)
    next_index: int = 0
    retries: dict[int, int] = field(default_factory=dict)
    practice_seconds: float = 0.0
    completions: list[str] = field(default_factory=list)  # ISO dates

    @property
    def is_complete(self) -> bool:
        """Every event has been completed in this mode."""
        return len(self.completed) == self.event_count

    def mark_completed(self, index: int) -> None:
        self.completed.add(index)

    def add_retry(self, index: int, count: int = 1) -> None:
        self.retries[index] = self.retries.get(index, 0) + count

    def record_completion(self, on: date | None = None) -> None:
        self.completions.append((on or date.today()).isoformat())

    def to_dict(self) -> dict:
        return {
            "event_count": self.event_count,
            "completed": sorted(self.completed),
            "next_index": self.next_index,
            "retries": {str(i): n for i, n in sorted(self.retries.items())},
            "practice_seconds": self.practice_seconds,
            "completions": self.completions,
        }

    @classmethod
    def from_dict(cls, data: dict) -> SongProgress:
        event_count = require(data, "event_count", int)
        if event_count is None or event_count < 0:
            raise UnreadableFile("invalid event count")
        completed = require(data, "completed", list, [])
        if not all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i < event_count for i in completed):
            raise UnreadableFile("invalid completed events")
        try:
            retries = {int(i): n for i, n in require(data, "retries", dict, {}).items()}
        except ValueError as error:
            raise UnreadableFile("invalid retries") from error
        if not all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in retries.values()):
            raise UnreadableFile("invalid retries")
        completions = require(data, "completions", list, [])
        if not all(isinstance(d, str) for d in completions):
            raise UnreadableFile("invalid completions")
        next_index = require(data, "next_index", int, 0)
        return cls(
            event_count=event_count,
            completed=set(completed),
            next_index=min(max(next_index, 0), event_count),
            retries=retries,
            practice_seconds=float(require(data, "practice_seconds", (int, float), 0.0)),
            completions=completions,
        )


class ProgressStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_progress_path()
        self.songs: dict[str, dict[Mode, SongProgress]] = {}

    def load(self) -> str | None:
        """Load progress. Returns a message for the user if it had to be reset."""
        try:
            data = read_json(self.path)
            self.songs = self._from_dict(data) if data is not None else {}
        except UnreadableFile:
            self.songs = {}
            backup = quarantine(self.path)
            return strings.PROGRESS_RESET.format(backup=backup)
        return None

    def save(self) -> None:
        write_json_atomic(self.path, {
            "schema_version": SCHEMA_VERSION,
            "songs": {
                song_id: {str(mode): progress.to_dict() for mode, progress in modes.items()}
                for song_id, modes in self.songs.items()
            },
        })

    def get(self, song_id: str, mode: Mode, event_count: int) -> SongProgress:
        """Progress for a song and mode, created empty if there is none."""
        modes = self.songs.setdefault(song_id, {})
        if mode not in modes:
            modes[mode] = SongProgress(event_count)
        return modes[mode]

    def reset_song(self, song_id: str) -> None:
        self.songs.pop(song_id, None)

    def clear(self) -> None:
        self.songs = {}
        self.path.unlink(missing_ok=True)

    def reset_changed_songs(self, songs: Iterable[tuple[str, int]]) -> list[str]:
        """Reset progress of songs whose event count no longer matches.

        Takes (song id, event count) pairs; returns the ids that were reset.
        """
        reset = []
        for song_id, event_count in songs:
            modes = self.songs.get(song_id, {})
            if any(p.event_count != event_count for p in modes.values()):
                self.reset_song(song_id)
                reset.append(song_id)
        return reset

    @staticmethod
    def _from_dict(data: dict) -> dict[str, dict[Mode, SongProgress]]:
        if data.get("schema_version") != SCHEMA_VERSION:
            raise UnreadableFile("unsupported schema version")
        songs = {}
        for song_id, modes in require(data, "songs", dict, {}).items():
            if not isinstance(modes, dict):
                raise UnreadableFile("invalid song progress")
            try:
                songs[song_id] = {
                    Mode(mode): SongProgress.from_dict(progress if isinstance(progress, dict) else {})
                    for mode, progress in modes.items()
                }
            except ValueError as error:
                raise UnreadableFile(str(error)) from error
        return songs
