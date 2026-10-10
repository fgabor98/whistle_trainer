"""Practice page: guided practice through a song."""

from __future__ import annotations

from enum import StrEnum

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from whistle_trainer import config, strings
from whistle_trainer.assessment.frames import FrameClass
from whistle_trainer.assessment.guided import GuidedEngine, GuidedUpdate
from whistle_trainer.audio.capture import InputProblem
from whistle_trainer.music.model import Song
from whistle_trainer.pitch.display import NoteDisplay
from whistle_trainer.storage.settings import SettingsStore, SongPreferences
from whistle_trainer.ui.guidance import guide_text, smoothed_cents
from whistle_trainer.ui.meters import HoldIndicator, PitchMeter
from whistle_trainer.ui.pages.library import format_length
from whistle_trainer.ui.pages.setup import describe_detected
from whistle_trainer.ui.score_view import ScoreView


class PracticeState(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    BLOCKED = "blocked"  # cannot listen: input not set up, missing, or lost
    FINISHED = "finished"


def _big_label(scale: float, bold: bool = False) -> QLabel:
    label = QLabel()
    font = label.font()
    font.setPointSizeF(font.pointSizeF() * scale)
    font.setBold(bold)
    label.setFont(font)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    return label


class PracticePage(QWidget):
    audio_setup_requested = Signal()
    library_requested = Signal()

    def __init__(self, devices, audio, settings: SettingsStore, parent: QWidget | None = None):
        super().__init__(parent)
        self.devices = devices
        self.audio = audio
        self.store = settings
        self.active = False
        self.song: Song | None = None
        self.engine: GuidedEngine | None = None
        self.state = PracticeState.PAUSED
        self.message: str | None = None
        self._start_on_activate = False
        self.display = NoteDisplay()
        self.last_class: FrameClass | None = None
        self.last_update: GuidedUpdate | None = None
        self.practice_seconds = 0.0
        self._previous_frame_time: float | None = None

        self.score = ScoreView()
        self.progress_label = QLabel()
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.target_label = _big_label(2.0, bold=True)
        self.detected_label = QLabel(strings.DETECTED_NONE)
        self.detected_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pitch_meter = PitchMeter()
        self.hold_indicator = HoldIndicator()
        self.guide_label = _big_label(1.4)

        self.pause_button = QPushButton(strings.PRACTICE_PAUSE)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.restart_button = QPushButton(strings.PRACTICE_RESTART)
        self.restart_button.clicked.connect(self.restart)
        self.setup_button = QPushButton(strings.PRACTICE_AUDIO_SETUP)
        self.setup_button.clicked.connect(self.audio_setup_requested)
        self.repeat_button = QPushButton(strings.PRACTICE_REPEAT)
        self.repeat_button.clicked.connect(self.restart)
        self.library_button = QPushButton(strings.PRACTICE_LIBRARY)
        self.library_button.clicked.connect(self.library_requested)
        buttons = QHBoxLayout()
        buttons.addStretch()
        for button in (self.pause_button, self.restart_button, self.setup_button,
                       self.repeat_button, self.library_button):
            buttons.addWidget(button)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.score, stretch=1)
        layout.addWidget(self.target_label)
        layout.addWidget(self.detected_label)
        layout.addWidget(self.pitch_meter)
        layout.addWidget(self.hold_indicator)
        layout.addWidget(self.guide_label)
        layout.addLayout(buttons)

        audio.frames_ready.connect(self._on_frames)
        audio.failed.connect(self._on_failed)

    @property
    def settings(self):
        return self.store.settings

    def title(self) -> str:
        return self.song.title if self.song else ""

    # Session control

    def load(self, song: Song, preferences: SongPreferences) -> None:
        self.song = song
        self.preferences = preferences
        self.tolerance = config.PITCH_TOLERANCE_CENTS[preferences.difficulty]
        self.pitch_meter.set_tolerance(self.tolerance)
        self.score.set_song(song, self.settings.show_note_names)
        self._new_engine()
        self.state = PracticeState.PAUSED
        self._start_on_activate = True

    def _new_engine(self) -> None:
        self.engine = GuidedEngine(self.song, self.preferences.tempo, self.tolerance, self.audio.hop_seconds)
        self.practice_seconds = 0.0
        self.last_update = None
        self.score.set_completed(set())
        self.score.set_current(0, animate=False)

    def activate(self) -> None:
        """Start listening only for a newly loaded song; returning to the page stays paused."""
        self.active = True
        if self._start_on_activate:
            self._start_on_activate = False
            self._start_listening()
        self._update()

    def deactivate(self) -> None:
        self.active = False
        self.audio.stop()
        if self.state is PracticeState.RUNNING:
            self.state = PracticeState.PAUSED
            self.message = strings.PRACTICE_PAUSED
        if self.engine is not None:
            self.engine.reset_current()

    def _start_listening(self) -> None:
        device_id = self.settings.input_device
        device = next((d for d in self.devices.inputs() if d.id == device_id), None)
        calibration = self.settings.calibrations.get(device_id or "")
        if device_id is None or calibration is None:
            self._block(strings.PRACTICE_NOT_SET_UP)
        elif device is None:
            self._block(strings.PRACTICE_INPUT_MISSING.format(name=self.settings.input_device_name or device_id))
        else:
            self.state = PracticeState.RUNNING
            self.message = None
            self.display.reset()
            self.last_class = None
            self._previous_frame_time = None
            self.audio.start(device, calibration.activity_threshold_db)

    def _block(self, message: str) -> None:
        self.audio.stop()
        self.state = PracticeState.BLOCKED
        self.message = message

    def toggle_pause(self) -> None:
        if self.state is PracticeState.RUNNING:
            self.audio.stop()
            self.engine.reset_current()
            self.state = PracticeState.PAUSED
            self.message = strings.PRACTICE_PAUSED
        elif self.state in (PracticeState.PAUSED, PracticeState.BLOCKED):
            self._start_listening()
        self._update()

    def restart(self) -> None:
        self.audio.stop()
        self._new_engine()
        self._start_listening()
        self._update()

    def _finish(self) -> None:
        self.audio.stop()
        self.state = PracticeState.FINISHED
        retries = sum(self.engine.retries.values())
        time = format_length(self.practice_seconds)
        self.message = (strings.PRACTICE_FINISHED.format(time=time, retries=retries) if retries
                        else strings.PRACTICE_FINISHED_NO_RETRIES.format(time=time))

    # Audio

    def _on_frames(self, frames: list) -> None:
        if not self.active or self.state is not PracticeState.RUNNING:
            return
        for frame in frames:
            if self._previous_frame_time is not None:
                self.practice_seconds += frame.time - self._previous_frame_time
            self._previous_frame_time = frame.time
            self.display.feed(frame)
            self.last_class = frame.frame_class
            self.last_update = self.engine.feed(frame)
            if self.last_update.finished:
                self._finish()
                break
        self._update()

    def _on_failed(self, problem: str) -> None:
        if self.active and self.state is PracticeState.RUNNING:
            self.engine.reset_current()
            self._block(strings.PRACTICE_INPUT_LOST if problem == InputProblem.LOST else strings.SETUP_INPUT_FAILED)
            self._update()

    # Display

    def _update(self) -> None:
        engine = self.engine
        if engine is None:
            return
        finished = engine.finished
        cents = None
        total = len(self.song.events)
        self.progress_label.setText(strings.PRACTICE_PROGRESS.format(current=min(engine.position + 1, total), total=total))
        self.score.set_completed(engine.completed)
        if self.score.current != (None if finished else engine.position):
            self.score.set_current(None if finished else engine.position)

        if finished:
            self.target_label.setText("")
            self.pitch_meter.set_cents(None)
            self.hold_indicator.set_progress(1.0, 0.0, 0.0)
        else:
            event = engine.event
            tracker = engine.tracker
            required = engine.required_s(event)
            if event.is_note:
                target_hz = event.pitch.frequency()
                cents = smoothed_cents(self.display, target_hz) if self.state is PracticeState.RUNNING else None
                self.target_label.setText(strings.PRACTICE_TARGET_NOTE.format(note=event.pitch.name))
                self.hold_indicator.set_progress(tracker.progress, tracker.credit_s, required)
            else:
                self.target_label.setText(strings.PRACTICE_TARGET_REST)
                self.hold_indicator.set_progress(tracker.progress, tracker.credit_s, required, strings.REST_LABEL)
            self.pitch_meter.set_cents(cents)
            self.pitch_meter.setEnabled(event.is_note)

        self.detected_label.setText(describe_detected(self.display) if self.state is PracticeState.RUNNING else "")
        if self.state is PracticeState.RUNNING:
            self.guide_label.setText(guide_text(
                engine.tracker.status, self.last_class, cents, self.tolerance,
                is_rest=not engine.event.is_note, needs_release=engine.needs_release,
            ))
        else:
            self.guide_label.setText(self.message or "")

        running_or_paused = self.state in (PracticeState.RUNNING, PracticeState.PAUSED, PracticeState.BLOCKED)
        self.pause_button.setVisible(running_or_paused)
        self.pause_button.setText(strings.PRACTICE_PAUSE if self.state is PracticeState.RUNNING
                                  else strings.PRACTICE_RESUME)
        self.restart_button.setVisible(running_or_paused)
        self.setup_button.setVisible(self.state is PracticeState.BLOCKED)
        self.repeat_button.setVisible(self.state is PracticeState.FINISHED)
        self.library_button.setVisible(self.state is PracticeState.FINISHED)
