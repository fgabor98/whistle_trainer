import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

from audio_helpers import FrameScript
from fakes import BUILTIN, MIC, SPEAKERS, FakeAudio, FakeClock, FakeDevices, FakePlayback
from whistle_trainer import config, strings
from whistle_trainer.app import MainWindow
from whistle_trainer.audio.capture import InputProblem
from whistle_trainer.config import Difficulty, Mode
from whistle_trainer.assessment.rhythm import RhythmStatus
from whistle_trainer.music.library import load_songs
from whistle_trainer.storage.progress import ProgressStore
from whistle_trainer.storage.settings import Calibration, SettingsStore
from whistle_trainer.ui.pages.practice import PracticeState

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
def playback():
    return FakePlayback()


@pytest.fixture
def window(qtbot, tmp_path, settings, devices, audio, playback):
    window = MainWindow(load_songs(), settings, ProgressStore(tmp_path / "progress.json"), devices, audio, playback)
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


def test_last_song_is_selected_and_remembered(qtbot, tmp_path, settings, devices, audio, playback):
    settings.settings.last_song_id = "ode-to-joy"
    window = MainWindow(load_songs(), settings, ProgressStore(tmp_path / "progress.json"), devices, audio, playback)
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
    script = FrameScript().pitched(587.33, 1.9)  # D5
    audio.send(script.frames)
    assert page.status_label.text() == strings.SETUP_RANGE_LOW  # two seconds are needed
    audio.send(script.pitched(587.33, 0.1).frames[-10:])
    assert page.status_label.text() == strings.SETUP_RANGE_PAUSE.format(low="D5")
    pause = FrameScript()
    pause.time = script.time
    audio.send(pause.pitched(2000.0, 2.9).frames)  # whistling during the pause is ignored
    assert page.status_label.text() == strings.SETUP_RANGE_PAUSE.format(low="D5")
    assert page.progress.value() == pytest.approx(2.9 / 3.0 * 1000, abs=10)
    audio.send(pause.quiet(0.2).frames[-20:])
    assert page.status_label.text() == strings.SETUP_RANGE_HIGH
    high = FrameScript()
    high.time = pause.time
    audio.send(high.pitched(1760.0, 2.0).frames)  # A6
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


# Library preparation panel and guided practice

G5, A5, B5_HZ = 783.99, 880.0, 987.77


def start_intro(window, settings, tempo=120):
    calibrate(settings, MIC)
    window.library_page.select_song("introductory-exercise")
    window.library_page.tempo_spin.setValue(tempo)
    window.library_page.start_button.click()
    return window.practice_page


def test_preparation_panel_saves_preferences_but_not_tempo(window, settings):
    page = window.library_page
    page.select_song("ode-to-joy")
    assert page.song_title.text() == "Ode to Joy"
    assert page.tempo_spin.value() == 100  # the song's own tempo
    assert page.estimate_label.text() == strings.LIBRARY_ESTIMATE.format(length="0:38")
    page.tempo_spin.setValue(50)
    page.difficulty_combo.setCurrentIndex(page.difficulty_combo.findData(Difficulty.STANDARD))
    assert page.estimate_label.text() == strings.LIBRARY_ESTIMATE.format(length="1:17")
    prefs = settings.settings.song_preferences["ode-to-joy"]
    assert (prefs.tempo, prefs.difficulty) == (50, Difficulty.STANDARD)
    page.select_song("introductory-exercise")
    assert page.tempo_spin.value() == 60
    page.select_song("ode-to-joy")
    assert page.tempo_spin.value() == 100  # back to the song's tempo
    assert page.difficulty_combo.currentData() == Difficulty.STANDARD  # still remembered


def test_changed_tempo_is_used_while_the_song_stays_selected(window, audio, settings):
    calibrate(settings, MIC)
    page = window.library_page
    page.select_song("frere-jacques")
    page.tempo_spin.setValue(70)
    page.listen_button.click()
    assert window.listen_page.tempo_spin.value() == 70
    window.listen_page.tempo_spin.setValue(80)
    window.listen_page.practice_button.click()
    assert window.practice_page.preferences.tempo == 80
    window.back_button.click()
    assert page.tempo_spin.value() == 80


def test_start_without_setup_explains(window, audio):
    window.library_page.start_button.click()
    page = window.practice_page
    assert window.pages.currentWidget() is page
    assert page.state is PracticeState.BLOCKED
    assert page.guide_label.text() == strings.PRACTICE_NOT_SET_UP
    assert page.setup_button.isVisibleTo(page) and not audio.running
    page.setup_button.click()
    assert window.pages.currentWidget() is window.setup_page


def test_practice_starts_listening_and_shows_first_note(window, audio, settings):
    page = start_intro(window, settings)
    assert window.title_label.text() == "Introductory exercise"
    assert audio.device_id == MIC.id and page.state is PracticeState.RUNNING
    assert page.target_label.text() == strings.PRACTICE_TARGET_NOTE.format(note="G5")
    assert page.progress_label.text() == strings.PRACTICE_PROGRESS.format(current=1, total=13)
    assert page.score.current == 0
    assert page.guide_label.text() == strings.GUIDE_START_WHEN_READY


def intro_script(script: FrameScript, a5_failures: int = 0) -> FrameScript:
    """The introductory exercise performed at 120 bpm (one beat = 0.5 s).

    a5_failures adds failed attempts at the second note before it is played correctly.
    """
    script.pitched(G5, 2.0)  # whole note G5
    for _ in range(a5_failures):
        script.pitched(A5, 0.5).quiet(0.3)
    return (script
            .pitched(A5, 1.0).quiet(1.0)  # half A5, half rest
            .pitched(B5_HZ, 1.0).quiet(0.15).pitched(B5_HZ, 1.0)  # repeated half notes
            .pitched(A5, 0.5).pitched(G5, 0.5).pitched(A5, 0.5).pitched(B5_HZ, 0.5)
            .quiet(0.15).pitched(B5_HZ, 1.0)  # B5 again: a repeated note needs a breath
            .pitched(A5, 2.0)  # tied A5 (half + half)
            .quiet(1.0)  # half rest
            .pitched(G5, 2.0))  # whole note G5


def test_full_song_in_guided_mode(window, audio, settings):
    page = start_intro(window, settings)
    audio.send(intro_script(FrameScript()).frames)
    assert page.state is PracticeState.FINISHED
    assert page.engine.retries == {}
    assert not audio.running
    summary = window.summary_page
    assert window.pages.currentWidget() is summary
    assert summary.heading.text() == strings.SUMMARY_SONG_COMPLETE
    assert summary.range_value.text() == strings.SUMMARY_WHOLE_SONG
    assert summary.retries_value.text() == "0"
    assert summary.hardest_label.text() == strings.SUMMARY_NO_RETRIES
    assert not summary.section_button.isVisibleTo(summary)
    summary.library_button.click()
    assert window.pages.currentWidget() is window.library_page and window.back_button.isHidden()


def test_practice_guidance_for_rests_and_repeated_notes(window, audio, settings):
    page = start_intro(window, settings)
    audio.send(FrameScript().pitched(G5, 2.0).pitched(A5, 1.0).frames)
    assert page.target_label.text() == strings.PRACTICE_TARGET_REST
    assert page.guide_label.text() == strings.GUIDE_TAKE_BREATH
    assert page.hold_indicator.format().startswith("Quiet:")
    audio.send(FrameScript().quiet(1.0).pitched(B5_HZ, 1.0).frames)
    assert page.engine.position == 4
    audio.send(FrameScript().pitched(B5_HZ, 0.2).frames)
    assert page.guide_label.text() == strings.GUIDE_RELEASE
    assert page.score.completed == {0, 1, 2, 3}


def test_pause_resets_current_note_and_resume_restarts_listening(window, audio, settings):
    page = start_intro(window, settings)
    audio.send(FrameScript().pitched(G5, 2.0).pitched(A5, 0.6).frames)
    assert page.engine.position == 1 and page.engine.tracker.credit_s > 0.5
    page.pause_button.click()
    assert page.state is PracticeState.PAUSED and not audio.running
    assert page.engine.tracker.credit_s == 0 and page.engine.completed == {0}
    assert page.guide_label.text() == strings.PRACTICE_PAUSED
    assert page.pause_button.text() == strings.PRACTICE_RESUME
    audio.send(FrameScript().pitched(A5, 2.0).frames)  # ignored while paused
    assert page.engine.position == 1
    page.pause_button.click()
    assert audio.running and page.state is PracticeState.RUNNING


def test_restart_begins_again(window, audio, settings):
    page = start_intro(window, settings)
    audio.send(FrameScript().pitched(G5, 2.0).frames)
    page.restart_button.click()
    assert page.engine.position == 0 and page.engine.completed == set()
    assert page.score.completed == set() and audio.running


def test_input_loss_pauses_practice(window, audio, settings):
    page = start_intro(window, settings)
    audio.send(FrameScript().pitched(G5, 1.0).frames)
    audio.fail(InputProblem.LOST)
    assert page.state is PracticeState.BLOCKED
    assert page.guide_label.text() == strings.PRACTICE_INPUT_LOST
    assert page.engine.tracker.credit_s == 0
    assert not audio.running
    page.pause_button.click()  # Resume
    assert audio.running


def test_leaving_practice_stops_listening_and_return_stays_paused(window, audio, settings):
    page = start_intro(window, settings)
    window.back_button.click()
    assert not audio.running
    window.show_page(page)
    assert page.state is PracticeState.PAUSED and not audio.running


def test_missing_microphone_blocks_practice(window, audio, devices, settings):
    calibrate(settings, MIC)
    devices.set_inputs([BUILTIN])
    window.library_page.start_button.click()
    page = window.practice_page
    assert page.state is PracticeState.BLOCKED
    assert page.guide_label.text() == strings.PRACTICE_INPUT_MISSING.format(name=MIC.name)
    assert not audio.running



# Rhythm mode

C6 = 1046.50


def start_rhythm(window, settings, song_id="introductory-exercise", tempo=60, metronome=False):
    calibrate(settings, MIC)
    settings.settings.metronome_sound = metronome
    settings.settings.output_device = SPEAKERS.id
    page = window.library_page
    page.select_song(song_id)
    page.mode_combo.setCurrentIndex(page.mode_combo.findData(Mode.RHYTHM))
    page.tempo_spin.setValue(tempo)
    page.start_button.click()
    return window.practice_page


def test_library_mode_choice_is_saved_and_shows_metronome_option(window, settings):
    page = window.library_page
    page.select_song("ode-to-joy")
    assert page.mode_combo.currentData() == Mode.GUIDED
    assert not page.metronome_check.isVisibleTo(page)
    page.mode_combo.setCurrentIndex(page.mode_combo.findData(Mode.RHYTHM))
    assert settings.settings.song_preferences["ode-to-joy"].mode is Mode.RHYTHM
    assert page.mode_description.text() == strings.MODE_DESCRIPTIONS["rhythm"]
    assert page.metronome_check.isVisibleTo(page)
    page.metronome_check.setChecked(True)
    assert settings.settings.metronome_sound is True


def test_rhythm_count_in_starts_with_first_frames(window, audio, settings):
    practice = start_rhythm(window, settings)
    assert practice.rhythm is not None and practice.rhythm.status is RhythmStatus.IDLE
    assert practice.beat_indicator.isVisibleTo(practice)
    assert practice.guide_label.text() == strings.GUIDE_COUNT_IN.format(beat=1)
    audio.send(FrameScript().quiet(0.05).frames)
    # The count-in begins half a second after the latest frame.
    assert practice.rhythm.status is RhythmStatus.COUNT_IN
    assert practice.rhythm.beat_times()[0] == pytest.approx(0.04 + config.COUNT_IN_LEAD_S)


def rhythm_intro_frames(start: float) -> FrameScript:
    """The introductory exercise at 60 bpm, starting with the first note at `start`."""
    script = FrameScript().quiet(start)
    return (script.pitched(G5, 3.8).quiet(0.2)  # whole note
            .pitched(A5, 1.9).quiet(2.1)  # half note, half rest
            .pitched(B5_HZ, 1.8).quiet(0.2).pitched(B5_HZ, 1.9).quiet(0.1)  # repeated half notes
            .pitched(A5, 1.0).pitched(G5, 1.0).pitched(A5, 1.0).pitched(B5_HZ, 0.85).quiet(0.15)
            .pitched(B5_HZ, 2.0).pitched(A5, 3.8).quiet(2.2)  # half, tied half + half, half rest
            .pitched(G5, 3.9).quiet(0.3))


def test_rhythm_full_song_with_metronome(window, audio, playback, settings):
    practice = start_rhythm(window, settings, metronome=True)
    assert playback.running and playback.device == SPEAKERS
    audio.send(FrameScript().quiet(0.01).frames)
    beats = practice.rhythm.beat_times()
    first = practice.rhythm.event_times(0)[0]
    # One click per beat: four count-in beats and 28 beats of music; beat one is accented.
    assert len(playback.scheduled) == len(beats) == 32
    assert [at for at, _ in playback.scheduled] == pytest.approx(beats)
    accents = [practice.rhythm.beat_in_measure(i) == 0 for i in range(len(beats))]
    assert accents[:5] == [True, False, False, False, True]

    script = rhythm_intro_frames(first)
    script.frames = [f for f in script.frames if f.time > 0.005]
    audio.send(script.frames)
    assert practice.state is PracticeState.FINISHED, practice.guide_label.text()
    assert practice.retries == 0 and not playback.running and not audio.running


def test_rhythm_failure_offers_retry_and_keeps_successes(window, audio, playback, settings, qtbot):
    practice = start_rhythm(window, settings, metronome=True)
    audio.send(FrameScript().quiet(0.01).frames)
    first = practice.rhythm.event_times(0)[0]
    script = FrameScript().quiet(first).pitched(G5, 3.8).quiet(0.2).quiet(1.0)  # A5 missed
    script.frames = [f for f in script.frames if f.time > 0.005]
    audio.send(script.frames)
    assert practice.rhythm.status is RhythmStatus.FAILED
    assert practice.rhythm.position == 1 and practice.rhythm.completed == {0}
    assert practice.score.failed == 1
    assert practice.retry_button.isVisibleTo(practice)
    assert practice.guide_label.text().startswith(strings.RHYTHM_FAILED["late_or_missing"].format(target="A5"))
    assert playback.scheduled == [] and audio.running

    practice.retry_button.click()
    assert practice.score.failed is None and not practice.retry_button.isVisibleTo(practice)
    retry = FrameScript()
    retry.time = script.time
    audio.send(retry.quiet(0.05).frames)
    assert practice.rhythm.status is RhythmStatus.COUNT_IN
    assert practice.rhythm.event_times(1)[0] == pytest.approx(script.time + 0.04 + config.COUNT_IN_LEAD_S + 4.0)
    assert len(playback.scheduled) == 4 + 24  # count-in, then bars 2 to 7
    assert practice.retries == 1


def test_rhythm_pause_needs_new_count_in(window, audio, settings):
    practice = start_rhythm(window, settings)
    audio.send(FrameScript().quiet(0.05).frames)
    practice.pause_button.click()
    assert practice.rhythm.status is RhythmStatus.IDLE and not audio.running
    practice.pause_button.click()
    assert audio.running and practice.rhythm.status is RhythmStatus.IDLE
    audio.send(FrameScript().quiet(0.05).frames)
    assert practice.rhythm.status is RhythmStatus.COUNT_IN


def test_rhythm_without_metronome_sound_does_not_open_output(window, audio, playback, settings):
    start_rhythm(window, settings, metronome=False)
    audio.send(FrameScript().quiet(0.05).frames)
    assert not playback.running and playback.scheduled == []


def test_rhythm_visual_beats_follow_the_clock(window, audio, settings):
    clock = FakeClock()
    window.practice_page.clock = clock
    practice = start_rhythm(window, settings)
    audio.send(FrameScript().quiet(0.05).frames)
    start = practice.rhythm.beat_times()[0]
    clock.now = start + 2.5  # third count-in beat
    practice._update()
    assert practice.guide_label.text() == strings.GUIDE_COUNT_IN.format(beat=3)
    assert practice.beat_indicator.current == 2
    clock.now = start + 4.2  # first beat of the song
    practice._update()
    assert practice.beat_indicator.current == 0


def test_rhythm_beats_stop_after_a_failure(window, audio, settings):
    clock = FakeClock()
    window.practice_page.clock = clock
    practice = start_rhythm(window, settings)
    audio.send(FrameScript().quiet(0.05).frames)
    first = practice.rhythm.event_times(0)[0]
    script = FrameScript()
    script.time = 0.05
    audio.send(script.quiet(first + 0.3 - 0.05).frames)  # the first note never starts
    assert practice.rhythm.status is RhythmStatus.FAILED
    clock.now = first + 0.3
    practice._update()
    assert practice.beat_indicator.current is None


# Milestone 5: progress, summary, sections, settings while paused, Hear note, Listen, transposition

def test_progress_is_saved_and_continue_is_offered(window, audio, settings, tmp_path):
    page = start_intro(window, settings)
    audio.send(FrameScript().pitched(G5, 2.0).pitched(A5, 1.0).quiet(0.5).frames)
    page.pause_button.click()
    progress = window.progress.songs["introductory-exercise"][Mode.GUIDED]
    assert progress.completed == {0, 1} and progress.next_index == 2
    assert progress.practice_seconds == pytest.approx(3.5, abs=0.05)
    assert (tmp_path / "progress.json").exists()

    window.back_button.click()
    library = window.library_page
    assert library.song_list.topLevelItem(0).text(3) == strings.LIBRARY_PROGRESS_NOTES.format(done=2, total=13)
    assert library.continue_button.isVisibleTo(library)
    assert library.continue_button.text() == strings.LIBRARY_CONTINUE.format(note=3)
    library.continue_button.click()
    assert window.practice_page.engine.position == 2


def test_completion_is_recorded_and_shown_in_library(window, audio, settings):
    start_intro(window, settings)
    audio.send(intro_script(FrameScript()).frames)
    progress = window.progress.songs["introductory-exercise"][Mode.GUIDED]
    assert len(progress.completions) == 1 and progress.next_index == 0
    assert window.summary_page.completed_label.isVisibleTo(window.summary_page)
    window.summary_page.library_button.click()
    assert window.library_page.song_list.topLevelItem(0).text(3) == strings.LIBRARY_PROGRESS_COMPLETE
    assert not window.library_page.continue_button.isVisibleTo(window.library_page)


def test_summary_lists_hardest_notes_and_offers_that_measure(window, audio, settings):
    page = start_intro(window, settings)
    audio.send(intro_script(FrameScript(), a5_failures=3).frames)  # three failed attempts at A5 in measure 2
    summary = window.summary_page
    assert window.pages.currentWidget() is summary
    assert summary.retries_value.text() == "3"
    assert strings.SUMMARY_HARDEST_ITEM.format(note="A5", measure="2", count=3) in summary.hardest_label.text()
    assert summary.section_button.text() == strings.SUMMARY_PRACTICE_MEASURE.format(measure="2")
    summary.section_button.click()
    assert window.pages.currentWidget() is page
    assert (page.range_start, page.range_end) == (1, 3)
    assert page.score.section == (1, 3)
    assert page.restart_button.text() == strings.PRACTICE_RESTART_SECTION


def test_section_practice_finishes_at_section_end(window, audio, settings):
    page = start_intro(window, settings)
    page.pause_button.click()
    assert page.paused_panel.isVisibleTo(page) and page.score.interactive
    page.score.note_clicked.emit(1, False)  # start at A5
    page.score.note_clicked.emit(2, True)  # end after the rest
    assert (page.range_start, page.range_end) == (1, 3) and page.engine.position == 1
    page.pause_button.click()
    assert not page.paused_panel.isVisibleTo(page) and not page.score.interactive
    audio.send(FrameScript().pitched(A5, 1.0).quiet(1.0).frames)
    summary = window.summary_page
    assert window.pages.currentWidget() is summary
    assert summary.heading.text() == strings.SUMMARY_SECTION_COMPLETE
    assert summary.range_value.text() == strings.SUMMARY_MEASURE.format(start="2")
    progress = window.progress.songs["introductory-exercise"][Mode.GUIDED]
    assert progress.completed == {1, 2} and progress.completions == []
    summary.repeat_button.click()
    assert window.pages.currentWidget() is page
    assert (page.range_start, page.range_end) == (1, 3) and audio.running


def test_clear_section_returns_to_whole_song(window, audio, settings):
    page = start_intro(window, settings)
    page.pause_button.click()
    page.score.note_clicked.emit(4, False)
    page.score.note_clicked.emit(6, True)
    page.clear_section_button.click()
    assert page.range_end is None and page.score.section is None and page.engine.position == 4


def test_settings_change_while_paused_keeps_position(window, audio, settings):
    page = start_intro(window, settings)
    audio.send(FrameScript().pitched(G5, 2.0).pitched(A5, 0.5).frames)
    page.pause_button.click()
    page.tempo_spin.setValue(60)
    assert page.engine.position == 1 and page.engine.tracker.credit_s == 0
    assert page.guided.required_s(page.event) == pytest.approx(2.0)
    page.mode_combo.setCurrentIndex(page.mode_combo.findData(Mode.RHYTHM))
    assert page.mode is Mode.RHYTHM and page.rhythm.position == 1
    assert settings.settings.song_preferences["introductory-exercise"].mode is Mode.RHYTHM
    page.transposition_spin.setValue(2)
    assert page.event.pitch.name == "B5"  # A5 up two semitones
    assert page.engine.position == 1


def test_settings_cannot_change_while_running(window, audio, settings):
    page = start_intro(window, settings)
    assert not page.paused_panel.isVisibleTo(page)
    page.score.note_clicked.emit(5, False)
    assert page.engine.position == 0


def test_hear_note_ignores_microphone_then_restarts_note(window, audio, playback, settings):
    clock = FakeClock()
    page = window.practice_page
    page.clock = clock
    start_intro(window, settings)
    audio.send(FrameScript().pitched(G5, 1.0).frames)
    assert page.guided.tracker.credit_s > 0.9
    clock.now = 1.0
    page.hear_button.click()
    assert playback.running and len(playback.scheduled) == 1
    assert page.guided.tracker.credit_s == 0
    script = FrameScript()
    script.time = 1.0
    audio.send(script.pitched(G5, 1.25).frames)  # the app's own note through the speakers: ignored
    assert page.guided.tracker.credit_s == 0 and page.engine.position == 0
    audio.send(script.pitched(G5, 2.1).frames)
    assert page.engine.position == 1


def test_hear_note_in_rhythm_mode_only_when_stopped(window, audio, playback, settings):
    page = start_rhythm(window, settings)
    audio.send(FrameScript().quiet(0.05).frames)
    assert not page.hear_button.isEnabled()
    page.pause_button.click()
    assert page.hear_button.isEnabled()
    page.hear_button.click()
    assert len(playback.scheduled) == 1


def test_listen_page_plays_song_and_notes(window, playback, settings, qtbot):
    clock = FakeClock(100.0)
    listen = window.listen_page
    listen.clock = clock
    window.library_page.select_song("introductory-exercise")
    window.library_page.listen_button.click()
    assert window.pages.currentWidget() is listen
    assert window.title_label.text() == strings.PAGE_LISTEN.format(title="Introductory exercise")
    assert listen.note_label.text() == strings.LISTEN_NOTE.format(note="G5", beats="4 beats")

    listen.play_button.click()
    assert listen.playing and playback.running
    assert listen.play_button.text() == strings.LISTEN_STOP
    # Only notes within the next second are rendered ahead.
    assert [round(at - 100.0, 2) for at, _ in playback.scheduled] == [0.15]
    clock.now = 100.15 + 4.5
    listen._tick()
    assert listen.position == 1  # A5 after the 4-beat G5
    listen.play_button.click()  # Stop
    assert not listen.playing and listen.position == 1 and playback.scheduled == []

    listen.next_button.click()
    assert listen.position == 2 and listen.note_label.text() == strings.LISTEN_REST.format(beats="2 beats")
    assert playback.scheduled == []  # rests are silent
    listen.score.note_clicked.emit(3, False)
    assert listen.position == 3 and len(playback.scheduled) == 1

    listen.practice_button.click()
    assert window.pages.currentWidget() is window.practice_page
    assert window.practice_page.engine.position == 3


def test_listen_plays_to_end_then_restarts_from_beginning(window, playback, settings):
    clock = FakeClock(0.0)
    listen = window.listen_page
    listen.clock = clock
    window.start_listening("introductory-exercise")
    listen.play_note(12)  # last note
    listen.play_song()
    clock.now = 10.0
    listen._tick()
    assert not listen.playing and listen.position == 12
    listen.play_song()
    assert listen._plan[0][1] == 0


def test_listen_transposition_changes_score_and_saves(window, settings):
    window.start_listening("introductory-exercise")
    listen = window.listen_page
    listen.transposition_spin.setValue(-2)
    assert listen.song.events[0].pitch.name == "F5"
    assert settings.settings.song_preferences["introductory-exercise"].transposition == -2


def test_library_suggests_transposition_for_measured_range(window, settings):
    calibrate(settings, MIC, low=79, high=91)  # G5 to G6
    library = window.library_page
    library.select_song("ode-to-joy")  # D5 to D6
    library.activate()
    assert library.suggestion_label.isVisibleTo(library)
    assert library.suggestion_label.text() == strings.LIBRARY_SUGGESTION.format(low="G5", high="G6", shift=5)
    library.use_suggestion_button.click()
    assert library.transposition_spin.value() == 5
    assert settings.settings.song_preferences["ode-to-joy"].transposition == 5
    assert library.range_label.text() == strings.LIBRARY_RANGE.format(low="G5", high="G6")
    assert library.suggestion_label.text() == strings.LIBRARY_SUGGESTION_FITS.format(low="G5", high="G6")


def test_practice_uses_transposition(window, audio, settings):
    window.library_page.select_song("introductory-exercise")
    window.library_page.transposition_spin.setValue(3)
    page = start_intro(window, settings)
    assert page.target_label.text() == strings.PRACTICE_TARGET_NOTE.format(note="B♭5")


def test_reset_song_progress_asks_first(window, audio, settings):
    start_intro(window, settings)
    audio.send(FrameScript().pitched(G5, 2.0).frames)
    window.back_button.click()
    library = window.library_page
    library.confirm = lambda text: False
    library.reset_song_button.click()
    assert "introductory-exercise" in window.progress.songs
    library.confirm = lambda text: True
    library.reset_song_button.click()
    assert "introductory-exercise" not in window.progress.songs
    assert library.song_list.topLevelItem(0).text(3) == strings.LIBRARY_PROGRESS_NONE


def test_reset_all_data_clears_settings_and_progress(window, audio, settings):
    start_intro(window, settings)
    audio.send(FrameScript().pitched(G5, 2.0).frames)
    window.back_button.click()
    library = window.library_page
    library.confirm = lambda text: True
    library.reset_all_button.click()
    assert settings.settings.calibrations == {} and window.progress.songs == {}


def test_note_names_setting(window, audio, settings):
    window.library_page.note_names_check.setChecked(False)
    assert settings.settings.show_note_names is False
    page = start_intro(window, settings)
    assert page.score.show_note_names is False


def test_escape_returns_to_library(window, audio, settings):
    start_intro(window, settings)
    assert window.escape_shortcut.key() == QKeySequence(Qt.Key.Key_Escape)
    window.escape_shortcut.activated.emit()
    assert window.pages.currentWidget() is window.library_page and not audio.running


# Test input: random notes

def hz(midi: int) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def test_random_notes_move_on_after_each_hit(window, audio, settings):
    calibrate(settings, MIC)
    window.show_page(window.test_input_page)
    page = window.test_input_page
    page.random_check.setChecked(True)
    assert not page.target_combo.isEnabled() and page.hits_label.isVisibleTo(page)
    assert page.try_again_button.text() == strings.TEST_NEW_NOTE
    assert page.hits_label.text() == strings.TEST_HITS.format(count=0)

    targets = []
    script = FrameScript()
    for expected_hits in (1, 2, 3):
        target = page.target_combo.currentData()
        targets.append(target)
        low, high = config.TEST_RANDOM_DEFAULT_RANGE
        assert low <= target <= high
        audio.send(script.pitched(hz(target), 1.0).frames[-100:])
        assert page.guide_label.text() == strings.TEST_RANDOM_PASSED
        assert page.hits_label.text() == strings.TEST_HITS.format(count=expected_hits)
        audio.send(script.quiet(1.4).frames[-140:])
        assert page.target_combo.currentData() == target  # still showing the hit
        audio.send(script.quiet(0.2).frames[-20:])
        assert page.target_combo.currentData() != target  # a new note
        assert page.hold.progress == 0
    assert all(a != b for a, b in zip(targets, targets[1:]))


def test_random_notes_use_measured_range_and_never_repeat(window, settings):
    calibrate(settings, MIC, low=79, high=81)  # G5 to A5: three notes
    window.show_page(window.test_input_page)
    page = window.test_input_page
    page.random_check.setChecked(True)
    seen = [page.target_combo.currentData()]
    for _ in range(30):
        page.try_again_button.click()  # New note
        seen.append(page.target_combo.currentData())
    assert set(seen) <= {79, 80, 81}
    assert all(a != b for a, b in zip(seen, seen[1:]))


def test_turning_random_off_restores_chosen_targets(window, settings):
    calibrate(settings, MIC)
    window.show_page(window.test_input_page)
    page = window.test_input_page
    page.random_check.setChecked(True)
    page.random_check.setChecked(False)
    assert page.target_combo.isEnabled() and not page.hits_label.isVisibleTo(page)
    assert page.try_again_button.text() == strings.TEST_TRY_AGAIN
