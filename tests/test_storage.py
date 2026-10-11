import json
import os

import pytest

from whistle_trainer.config import Difficulty, Mode, Sound
from whistle_trainer.storage import jsonfile
from whistle_trainer.storage.progress import ProgressStore
from whistle_trainer.storage.settings import Calibration, SettingsStore, SongPreferences


@pytest.fixture
def settings_path(tmp_path):
    return tmp_path / "config" / "settings.json"


@pytest.fixture
def progress_path(tmp_path):
    return tmp_path / "data" / "progress.json"


def test_settings_default_when_missing(settings_path):
    store = SettingsStore(settings_path)
    assert store.load() is None
    assert store.settings.show_note_names is True
    assert store.settings.listen_sound is Sound.PIANO
    assert store.settings.input_device is None


def test_settings_round_trip(settings_path):
    store = SettingsStore(settings_path)
    store.settings.input_device = "USB Microphone"
    store.settings.show_note_names = False
    store.settings.listen_sound = Sound.PIANO
    store.settings.calibrations["USB Microphone"] = Calibration(-60.0, -20.0, -40.0, 76, 88)
    prefs = store.settings.preferences_for("ode-to-joy", default_tempo=72)
    assert prefs.tempo == 72
    prefs.mode = Mode.RHYTHM
    prefs.difficulty = Difficulty.STANDARD
    prefs.transposition = -2
    store.settings.last_song_id = "ode-to-joy"
    store.save()

    loaded = SettingsStore(settings_path)
    assert loaded.load() is None
    assert "tempo" not in json.loads(settings_path.read_text())["song_preferences"]["ode-to-joy"]
    prefs.tempo = loaded.settings.song_preferences["ode-to-joy"].tempo  # tempo is session-only
    assert loaded.settings == store.settings
    assert loaded.settings.song_preferences["ode-to-joy"] == \
        SongPreferences(Mode.RHYTHM, Difficulty.STANDARD, transposition=-2)


@pytest.mark.parametrize("content", [
    "{not json",
    "[]",
    json.dumps({"schema_version": 99}),
    json.dumps({"schema_version": 1, "show_note_names": "yes"}),
    json.dumps({"schema_version": 1, "song_preferences": {"x": {"mode": "freestyle"}}}),
    json.dumps({"schema_version": 1, "calibrations": {"mic": {"noise_floor_db": -60}}}),
    json.dumps({"schema_version": 1, "song_preferences": {"x": {"transposition": True}}}),
    json.dumps({"schema_version": 1, "listen_sound": "kazoo"}),
])
def test_unreadable_settings_are_kept_aside_and_reset(settings_path, content):
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(content, encoding="utf-8")
    store = SettingsStore(settings_path)
    message = store.load()
    assert message and "settings.json.corrupt" in message
    assert not settings_path.exists()
    assert (settings_path.parent / "settings.json.corrupt").read_text(encoding="utf-8") == content
    assert store.settings.input_device is None


def test_out_of_range_preferences_are_clamped_and_old_tempo_ignored(settings_path):
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({
        "schema_version": 1,
        "song_preferences": {"x": {"tempo": 45, "transposition": -40}},  # tempo saved by older versions
    }), encoding="utf-8")
    store = SettingsStore(settings_path)
    assert store.load() is None
    assert store.settings.song_preferences["x"].tempo is None
    assert store.settings.preferences_for("x", default_tempo=90).tempo == 90  # the song's own tempo
    assert store.settings.song_preferences["x"].transposition == -12


def test_settings_clear(settings_path):
    store = SettingsStore(settings_path)
    store.settings.input_device = "mic"
    store.save()
    store.clear()
    assert not settings_path.exists()
    assert store.settings.input_device is None


def test_atomic_write_keeps_old_file_on_failure(tmp_path, monkeypatch):
    path = tmp_path / "file.json"
    jsonfile.write_json_atomic(path, {"value": 1})

    def fail(*_args):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        jsonfile.write_json_atomic(path, {"value": 2})
    assert json.loads(path.read_text()) == {"value": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["file.json"]


def test_progress_round_trip(progress_path):
    store = ProgressStore(progress_path)
    assert store.load() is None
    guided = store.get("ode-to-joy", Mode.GUIDED, event_count=5)
    guided.mark_completed(0)
    guided.mark_completed(1)
    guided.add_retry(1)
    guided.add_retry(1)
    guided.next_index = 2
    guided.practice_seconds = 12.5
    store.get("ode-to-joy", Mode.RHYTHM, event_count=5).mark_completed(0)
    store.save()

    loaded = ProgressStore(progress_path)
    assert loaded.load() is None
    progress = loaded.get("ode-to-joy", Mode.GUIDED, event_count=5)
    assert progress.completed == {0, 1}
    assert progress.retries == {1: 2}
    assert progress.next_index == 2
    assert progress.practice_seconds == 12.5
    assert loaded.get("ode-to-joy", Mode.RHYTHM, event_count=5).completed == {0}


def test_song_complete_only_when_every_event_completed(progress_path):
    progress = ProgressStore(progress_path).get("song", Mode.GUIDED, event_count=3)
    progress.mark_completed(0)
    progress.mark_completed(2)
    assert not progress.is_complete
    progress.mark_completed(1)
    assert progress.is_complete


def test_modes_are_tracked_separately(progress_path):
    store = ProgressStore(progress_path)
    store.get("song", Mode.GUIDED, 3).mark_completed(0)
    assert store.get("song", Mode.RHYTHM, 3).completed == set()


def test_changed_songs_are_reset(progress_path):
    store = ProgressStore(progress_path)
    store.get("changed", Mode.GUIDED, 5).mark_completed(0)
    store.get("same", Mode.GUIDED, 3).mark_completed(0)
    assert store.reset_changed_songs([("changed", 6), ("same", 3), ("new", 4)]) == ["changed"]
    assert "changed" not in store.songs
    assert store.get("same", Mode.GUIDED, 3).completed == {0}


def test_reset_single_song(progress_path):
    store = ProgressStore(progress_path)
    store.get("a", Mode.GUIDED, 3).mark_completed(0)
    store.get("b", Mode.GUIDED, 3).mark_completed(0)
    store.reset_song("a")
    assert list(store.songs) == ["b"]


@pytest.mark.parametrize("content", [
    "garbage",
    json.dumps({"schema_version": 1, "songs": {"a": {"guided": {"event_count": 2, "completed": [5]}}}}),
    json.dumps({"schema_version": 1, "songs": {"a": {"karaoke": {"event_count": 2}}}}),
    json.dumps({"schema_version": 1, "songs": {"a": {"guided": {"event_count": 2, "retries": {"x": 1}}}}}),
    json.dumps({"schema_version": 1, "songs": {"a": {"guided": {}}}}),
])
def test_unreadable_progress_is_kept_aside_and_reset(progress_path, content):
    progress_path.parent.mkdir(parents=True)
    progress_path.write_text(content, encoding="utf-8")
    store = ProgressStore(progress_path)
    message = store.load()
    assert message and "progress.json.corrupt" in message
    assert store.songs == {}
    assert (progress_path.parent / "progress.json.corrupt").exists()
