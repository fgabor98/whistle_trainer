"""User settings: devices, calibration, notation, and per-song preferences."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import platformdirs

from whistle_trainer import config, strings
from whistle_trainer.config import Difficulty, Mode
from whistle_trainer.storage.jsonfile import UnreadableFile, quarantine, read_json, require, write_json_atomic

SCHEMA_VERSION = 1
APP_DIR_NAME = "whistle-trainer"


def default_settings_path() -> Path:
    return platformdirs.user_config_path(APP_DIR_NAME, appauthor=False) / "settings.json"


@dataclass
class Calibration:
    """Audio setup results for one input device."""

    noise_floor_db: float
    whistle_level_db: float
    activity_threshold_db: float
    practice_low_midi: int | None = None
    practice_high_midi: int | None = None

    @classmethod
    def from_dict(cls, data: dict) -> Calibration:
        number = (int, float)
        return cls(
            noise_floor_db=float(_required(data, "noise_floor_db", number)),
            whistle_level_db=float(_required(data, "whistle_level_db", number)),
            activity_threshold_db=float(_required(data, "activity_threshold_db", number)),
            practice_low_midi=require(data, "practice_low_midi", int),
            practice_high_midi=require(data, "practice_high_midi", int),
        )


@dataclass
class SongPreferences:
    mode: Mode = config.DEFAULT_MODE
    difficulty: Difficulty = config.DEFAULT_DIFFICULTY
    tempo: int = config.DEFAULT_TEMPO
    transposition: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> SongPreferences:
        try:
            mode = Mode(require(data, "mode", str, config.DEFAULT_MODE))
            difficulty = Difficulty(require(data, "difficulty", str, config.DEFAULT_DIFFICULTY))
        except ValueError as error:
            raise UnreadableFile(str(error)) from error
        tempo = require(data, "tempo", int, config.DEFAULT_TEMPO)
        transposition = require(data, "transposition", int, 0)
        return cls(
            mode=mode,
            difficulty=difficulty,
            tempo=min(max(tempo, config.MIN_TEMPO), config.MAX_TEMPO),
            transposition=min(max(transposition, config.MIN_TRANSPOSITION), config.MAX_TRANSPOSITION),
        )


@dataclass
class Settings:
    input_device: str | None = None
    output_device: str | None = None
    calibrations: dict[str, Calibration] = field(default_factory=dict)
    show_note_names: bool = config.SHOW_NOTE_NAMES
    last_song_id: str | None = None
    song_preferences: dict[str, SongPreferences] = field(default_factory=dict)

    def preferences_for(self, song_id: str, default_tempo: int) -> SongPreferences:
        """Saved preferences for a song, or defaults using the song's own tempo."""
        if song_id not in self.song_preferences:
            self.song_preferences[song_id] = SongPreferences(tempo=default_tempo)
        return self.song_preferences[song_id]

    def to_dict(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, data: dict) -> Settings:
        if data.get("schema_version") != SCHEMA_VERSION:
            raise UnreadableFile("unsupported schema version")
        return cls(
            input_device=require(data, "input_device", str),
            output_device=require(data, "output_device", str),
            calibrations={
                device: Calibration.from_dict(_object(value))
                for device, value in require(data, "calibrations", dict, {}).items()
            },
            show_note_names=require(data, "show_note_names", bool, config.SHOW_NOTE_NAMES),
            last_song_id=require(data, "last_song_id", str),
            song_preferences={
                song_id: SongPreferences.from_dict(_object(value))
                for song_id, value in require(data, "song_preferences", dict, {}).items()
            },
        )


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path or default_settings_path()
        self.settings = Settings()

    def load(self) -> str | None:
        """Load settings. Returns a message for the user if they had to be reset."""
        try:
            data = read_json(self.path)
            self.settings = Settings.from_dict(data) if data is not None else Settings()
        except UnreadableFile:
            self.settings = Settings()
            backup = quarantine(self.path)
            return strings.SETTINGS_RESET.format(backup=backup)
        return None

    def save(self) -> None:
        write_json_atomic(self.path, self.settings.to_dict())

    def clear(self) -> None:
        self.settings = Settings()
        self.path.unlink(missing_ok=True)


def _required(data: dict, key: str, kind):
    value = require(data, key, kind)
    if value is None:
        raise UnreadableFile(f"{key!r} is missing")
    return value


def _object(value) -> dict:
    if not isinstance(value, dict):
        raise UnreadableFile("expected an object")
    return value
