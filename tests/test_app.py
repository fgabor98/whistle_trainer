import pytest

from audio_helpers import FrameScript
from fakes import BUILTIN, MIC, FakeAudio, FakeDevices
from whistle_trainer import config, strings
from whistle_trainer.app import MainWindow
from whistle_trainer.audio.capture import InputProblem
from whistle_trainer.music.library import load_songs
from whistle_trainer.storage.progress import ProgressStore
from whistle_trainer.storage.settings import Calibration, SettingsStore

B5 = 987.77


@pytest.fixture
def settings(tmp_path):
    return SettingsStore(tmp_path / "settings.json")


@pytest.fixture
def devices():
    return FakeDevices()


@pytest.fixture
def audio():
    return FakeAudio()


@pytest.fixture
def window(qtbot, tmp_path, settings, devices, audio):
    window = MainWindow(load_songs(), settings, ProgressStore(tmp_path / "progress.json"), devices, audio)
    qtbot.addWidget(window)
    return window


def calibrate(settings: SettingsStore, device=MIC, low=None, high=None) -> None:
    settings.settings.input_device, settings.settings.input_device_name = device.id, device.name
    settings.settings.calibrations[device.id] = Calibration(-60, -30, -45, low, high)


def test_library_lists_bundled_songs(window):
    song_list = window.library_page.song_list
    titles = [song_list.topLevelItem(i).text(0) for i in range(song_list.topLevelItemCount())]
    assert titles == ["Introductory exercise", "Frère Jacques", "Ode to Joy", "Twinkle Twinkle Little Star"]
    assert song_list.topLevelItem(0).text(1) == "0:28"
    assert song_list.topLevelItem(0).text(2) == "G5–B5"


def test_last_song_is_selected_and_remembered(qtbot, tmp_path, settings, devices, audio):
    settings.settings.last_song_id = "ode-to-joy"
    window = MainWindow(load_songs(), settings, ProgressStore(tmp_path / "progress.json"), devices, audio)
    qtbot.addWidget(window)
    song_list = window.library_page.song_list
    assert song_list.currentItem().text(0) == "Ode to Joy"
    song_list.setCurrentItem(song_list.topLevelItem(1))
    assert settings.settings.last_song_id == "frere-jacques"


def test_closing_saves_settings_and_progress(window, tmp_path):
    window.close()
    assert (tmp_path / "settings.json").exists()
    assert (tmp_path / "progress.json").exists()


def test_library_does_not_listen(window, audio):
    assert window.back_button.isHidden()
    assert not audio.running
    assert window.listening_label.isHidden()


def test_setup_page_listens_to_default_input_and_back_stops(window, audio):
    window.library_page.audio_setup_button.click()
    assert window.pages.currentWidget() is window.setup_page
    assert audio.starts == [BUILTIN.id] and audio.threshold_db == config.UNCALIBRATED_THRESHOLD_DB
    assert not window.listening_label.isHidden()
    assert window.setup_page.status_label.text() == strings.SETUP_INTRO
    window.back_button.click()
    assert window.pages.currentWidget() is window.library_page
    assert not audio.running and window.listening_label.isHidden()


def test_setup_calibration_saves_threshold(window, audio, settings):
    window.show_page(window.setup_page)
    page = window.setup_page
    page.start_button.click()
    assert page.status_label.text() == strings.SETUP_STEP_SILENCE
    assert not page.start_button.isEnabled() and page.progress.isVisibleTo(page)
    audio.send(FrameScript().quiet(3.0, level=-60).frames)
    assert page.status_label.text() == strings.SETUP_STEP_WHISTLE
    script = FrameScript()
    script.time = 3.0
    audio.send(script.pitched(B5, 1.5).frames)

    calibration = settings.settings.calibrations[BUILTIN.id]
    assert calibration.activity_threshold_db == pytest.approx(-45)
    assert settings.settings.input_device == BUILTIN.id
    assert audio.threshold_db == pytest.approx(-45)
    assert page.status_label.text().startswith("Setup complete.")
    assert page.start_button.text() == strings.SETUP_REPEAT
    assert page.range_button.isEnabled() and page.test_button.isEnabled()
    assert settings.path.exists()


def test_setup_reports_missing_whistle(window, audio, settings):
    window.show_page(window.setup_page)
    window.setup_page.start_button.click()
    audio.send(FrameScript().quiet(3.0).quiet(10.5).frames)
    assert window.setup_page.status_label.text() == strings.SETUP_NO_STEADY_WHISTLE
    assert settings.settings.calibrations == {}


def test_setup_range_measurement(window, audio, settings):
    calibrate(settings, BUILTIN)
    window.show_page(window.setup_page)
    page = window.setup_page
    page.range_button.click()
    assert page.status_label.text() == strings.SETUP_RANGE_LOW
    audio.send(FrameScript().pitched(587.33, 1.0).frames)  # D5
    assert page.status_label.text() == strings.SETUP_RANGE_HIGH
    audio.send(FrameScript().pitched(1760.0, 1.0).frames)  # A6
    calibration = settings.settings.calibrations[BUILTIN.id]
    assert (calibration.practice_low_midi, calibration.practice_high_midi) == (74, 93)
    assert page.status_label.text() == strings.SETUP_RANGE_DONE.format(low="D5", high="A6")


def test_choosing_another_input_restarts_capture_and_saves(window, audio, settings):
    window.show_page(window.setup_page)
    page = window.setup_page
    page.input_combo.setCurrentIndex(page.input_combo.findData(MIC.id))
    page.input_combo.activated.emit(page.input_combo.currentIndex())
    assert audio.device_id == MIC.id
    assert settings.settings.input_device == MIC.id


def test_missing_saved_input_is_shown_and_not_replaced(window, audio, devices, settings):
    calibrate(settings, MIC)
    devices.set_inputs([BUILTIN])
    window.show_page(window.setup_page)
    page = window.setup_page
    assert page.input_combo.currentText() == strings.SETUP_UNAVAILABLE.format(name=MIC.name)
    assert not audio.running
    assert page.status_label.text() == strings.SETUP_INPUT_MISSING.format(name=MIC.name)
    assert not page.start_button.isEnabled()
    # Reconnecting does not start listening by itself.
    devices.set_inputs([BUILTIN, MIC])
    assert page.input_combo.currentData() == MIC.id
    assert not audio.running
    assert page.start_button.isEnabled()


def test_input_loss_stops_and_explains(window, audio):
    window.show_page(window.setup_page)
    window.setup_page.start_button.click()
    audio.fail(InputProblem.LOST)
    assert window.setup_page.status_label.text() == strings.SETUP_INPUT_LOST
    assert not audio.running and window.listening_label.isHidden()
    assert not window.setup_page.measuring()


def test_test_input_requires_setup(window, audio):
    window.show_page(window.test_input_page)
    assert window.test_input_page.guide_label.text() == strings.TEST_NOT_SET_UP
    assert not audio.running


def test_test_input_defaults_to_middle_of_range(window, settings):
    calibrate(settings, MIC, low=74, high=90)  # D5 to F♯6
    window.show_page(window.test_input_page)
    assert window.test_input_page.target_combo.currentText() == "A♯5"


def test_test_input_guides_and_passes(window, audio, settings):
    calibrate(settings, MIC)
    window.show_page(window.setup_page)
    window.setup_page.test_button.click()
    page = window.test_input_page
    assert window.pages.currentWidget() is page
    assert audio.device_id == MIC.id and audio.threshold_db == -45
    assert page.target_combo.currentText() == "B5"
    assert page.guide_label.text() == strings.GUIDE_START_WHEN_READY

    audio.send(FrameScript().pitched(880.0, 0.3).frames)
    assert page.guide_label.text() == strings.GUIDE_WHISTLE_HIGHER
    audio.send(FrameScript().pitched(B5 * 2, 0.3).frames)
    assert page.guide_label.text() == strings.GUIDE_WHISTLE_LOWER
    audio.send(FrameScript().unclear(0.2).frames)
    assert page.guide_label.text() == strings.GUIDE_NO_CLEAR_PITCH
    audio.send(FrameScript().pitched(B5, 0.5).frames)
    assert page.guide_label.text() == strings.GUIDE_HOLD
    assert page.hold_indicator.value() == 500
    audio.send(FrameScript().quiet(0.05).frames)
    assert page.guide_label.text() == strings.GUIDE_KEEP_GOING
    audio.send(FrameScript().pitched(B5, 0.5).frames)
    assert page.guide_label.text() == strings.TEST_PASSED

    page.try_again_button.click()
    assert page.hold_indicator.value() == 0
    assert page.guide_label.text() == strings.GUIDE_START_WHEN_READY


def test_test_input_standard_difficulty_is_stricter(window, audio, settings):
    calibrate(settings, MIC)
    window.show_page(window.test_input_page)
    page = window.test_input_page
    page.difficulty_combo.setCurrentIndex(1)
    page.difficulty_combo.activated.emit(1)
    audio.send(FrameScript().pitched(B5 * 2 ** (30 / 1200), 1.5).frames)
    assert page.guide_label.text() == strings.GUIDE_WHISTLE_LOWER
    assert page.hold_indicator.value() == 0
