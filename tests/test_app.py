import pytest

from whistle_trainer.app import MainWindow
from whistle_trainer.music.library import load_songs
from whistle_trainer.storage.progress import ProgressStore
from whistle_trainer.storage.settings import SettingsStore


@pytest.fixture
def window(qtbot, tmp_path):
    settings = SettingsStore(tmp_path / "settings.json")
    settings.settings.last_song_id = "ode-to-joy"
    window = MainWindow(load_songs(), settings, ProgressStore(tmp_path / "progress.json"))
    qtbot.addWidget(window)
    return window


def test_library_lists_bundled_songs(window):
    song_list = window.library_page.song_list
    titles = [song_list.topLevelItem(i).text(0) for i in range(song_list.topLevelItemCount())]
    assert titles == ["Introductory exercise", "Frère Jacques", "Ode to Joy", "Twinkle Twinkle Little Star"]
    assert song_list.topLevelItem(0).text(1) == "0:28"
    assert song_list.topLevelItem(0).text(2) == "G5–B5"


def test_last_song_is_selected_and_remembered(window):
    song_list = window.library_page.song_list
    assert song_list.currentItem().text(0) == "Ode to Joy"
    song_list.setCurrentItem(song_list.topLevelItem(1))
    assert window.settings.settings.last_song_id == "frere-jacques"


def test_closing_saves_settings_and_progress(window, tmp_path):
    window.close()
    assert (tmp_path / "settings.json").exists()
    assert (tmp_path / "progress.json").exists()


def test_back_button_hidden_on_library(window):
    assert window.back_button.isHidden()
