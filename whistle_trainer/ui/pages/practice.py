"""Practice page: guided or rhythm practice through a song."""

from __future__ import annotations

import time
from enum import StrEnum

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from whistle_trainer import config, strings
from whistle_trainer.assessment.frames import AnalysisFrame, FrameClass
from whistle_trainer.assessment.guided import GuidedEngine
from whistle_trainer.assessment.hold import HoldStatus
from whistle_trainer.assessment.rhythm import RhythmEngine, RhythmStatus
from whistle_trainer.audio.capture import InputProblem
from whistle_trainer.audio.synth import click
from whistle_trainer.config import Mode
from whistle_trainer.music.model import Event, Song
from whistle_trainer.pitch.display import NoteDisplay
from whistle_trainer.storage.settings import SettingsStore, SongPreferences
from whistle_trainer.ui.guidance import guide_text, smoothed_cents
from whistle_trainer.ui.meters import BeatIndicator, HoldIndicator, PitchMeter
from whistle_trainer.ui.pages.library import format_length
from whistle_trainer.ui.pages.setup import describe_detected
from whistle_trainer.ui.score_view import ScoreView

_BEAT_REFRESH_MS = 20


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

    def __init__(self, devices, audio, playback, settings: SettingsStore, parent: QWidget | None = None,
                 clock=time.monotonic):
        super().__init__(parent)
        self.devices = devices
        self.audio = audio
        self.playback = playback
        self.store = settings
        self.clock = clock
        self.active = False
        self.song: Song | None = None
        self.mode = Mode.GUIDED
        self.guided: GuidedEngine | None = None
        self.rhythm: RhythmEngine | None = None
        self.state = PracticeState.PAUSED
        self.message: str | None = None
        self._start_on_activate = False
        self._count_in_pending = False
        self.display = NoteDisplay()
        self.last_class: FrameClass | None = None
        self.last_frame_time: float | None = None
        self.practice_seconds = 0.0

        self.score = ScoreView()
        self.progress_label = QLabel()
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.target_label = _big_label(2.0, bold=True)
        self.detected_label = QLabel(strings.DETECTED_NONE)
        self.detected_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.beat_indicator = BeatIndicator()
        self.pitch_meter = PitchMeter()
        self.hold_indicator = HoldIndicator()
        self.guide_label = _big_label(1.4)

        self.pause_button = QPushButton(strings.PRACTICE_PAUSE)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.retry_button = QPushButton(strings.PRACTICE_RETRY)
        self.retry_button.clicked.connect(self.retry)
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
        for button in (self.retry_button, self.pause_button, self.restart_button, self.setup_button,
                       self.repeat_button, self.library_button):
            buttons.addWidget(button)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.score, stretch=1)
        layout.addWidget(self.beat_indicator)
        layout.addWidget(self.target_label)
        layout.addWidget(self.detected_label)
        layout.addWidget(self.pitch_meter)
        layout.addWidget(self.hold_indicator)
        layout.addWidget(self.guide_label)
        layout.addLayout(buttons)

        self.beat_timer = QTimer(self)
        self.beat_timer.setInterval(_BEAT_REFRESH_MS)
        self.beat_timer.timeout.connect(self._update)

        audio.frames_ready.connect(self._on_frames)
        audio.failed.connect(self._on_failed)

    @property
    def settings(self):
        return self.store.settings

    def title(self) -> str:
        return self.song.title if self.song else ""

    # Mode-independent views of the engine

    @property
    def engine(self) -> GuidedEngine | RhythmEngine:
        return self.rhythm if self.mode is Mode.RHYTHM else self.guided

    @property
    def finished(self) -> bool:
        return self.engine.finished

    @property
    def event(self) -> Event:
        return self.engine.event

    @property
    def retries(self) -> int:
        counts = self.rhythm.failures if self.mode is Mode.RHYTHM else self.guided.retries
        return sum(counts.values())

    @property
    def rhythm_failed(self) -> bool:
        return self.mode is Mode.RHYTHM and self.rhythm.status is RhythmStatus.FAILED

    # Session control

    def load(self, song: Song, preferences: SongPreferences) -> None:
        self.song = song
        self.preferences = preferences
        self.mode = preferences.mode
        self.tolerance = config.PITCH_TOLERANCE_CENTS[preferences.difficulty]
        self.pitch_meter.set_tolerance(self.tolerance)
        self.score.set_song(song, self.settings.show_note_names)
        self.beat_indicator.setVisible(self.mode is Mode.RHYTHM)
        self._new_engine()
        self.state = PracticeState.PAUSED
        self._start_on_activate = True

    def _new_engine(self) -> None:
        tempo, hop = self.preferences.tempo, self.audio.hop_seconds
        if self.mode is Mode.RHYTHM:
            self.rhythm = RhythmEngine(self.song, tempo, self.tolerance, hop)
        else:
            self.guided = GuidedEngine(self.song, tempo, self.tolerance, hop)
        self.practice_seconds = 0.0
        self.score.set_completed(set())
        self.score.set_failed(None)
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
        self._stop_listening()
        if self.state is PracticeState.RUNNING:
            self.state = PracticeState.PAUSED
            self.message = strings.PRACTICE_PAUSED
        self._interrupt_engine()

    def _start_listening(self) -> None:
        device_id = self.settings.input_device
        device = next((d for d in self.devices.inputs() if d.id == device_id), None)
        calibration = self.settings.calibrations.get(device_id or "")
        if device_id is None or calibration is None:
            self._block(strings.PRACTICE_NOT_SET_UP)
            return
        if device is None:
            self._block(strings.PRACTICE_INPUT_MISSING.format(name=self.settings.input_device_name or device_id))
            return
        self.state = PracticeState.RUNNING
        self.message = None
        self.display.reset()
        self.last_class = None
        self.last_frame_time = None
        self.audio.start(device, calibration.activity_threshold_db)
        if self.mode is Mode.RHYTHM:
            self._count_in_pending = True
            if self.settings.metronome_sound:
                output = next((d for d in self.devices.outputs() if d.id == self.settings.output_device), None)
                self.playback.start(output)
            self.beat_timer.start()

    def _stop_listening(self) -> None:
        self.audio.stop()
        self.playback.stop()
        self.beat_timer.stop()
        self._count_in_pending = False

    def _interrupt_engine(self) -> None:
        """Discard the unfinished event; rhythm mode needs a new count-in afterwards."""
        if self.mode is Mode.RHYTHM:
            if self.rhythm is not None:
                self.rhythm.stop()
        elif self.guided is not None:
            self.guided.reset_current()

    def _block(self, message: str) -> None:
        self._stop_listening()
        self.state = PracticeState.BLOCKED
        self.message = message

    def toggle_pause(self) -> None:
        if self.state is PracticeState.RUNNING:
            self._stop_listening()
            self._interrupt_engine()
            self.state = PracticeState.PAUSED
            self.message = strings.PRACTICE_PAUSED
        elif self.state in (PracticeState.PAUSED, PracticeState.BLOCKED):
            self._start_listening()
        self._update()

    def restart(self) -> None:
        self._stop_listening()
        self._new_engine()
        self._start_listening()
        self._update()

    def retry(self) -> None:
        """Rhythm mode: a new count-in from the failed note."""
        if self.rhythm_failed and self.state is PracticeState.RUNNING:
            self.rhythm.stop()
            self.score.set_failed(None)
            self._count_in_pending = True
            self._update()

    def _finish(self) -> None:
        self._stop_listening()
        self.state = PracticeState.FINISHED
        time_text = format_length(self.practice_seconds)
        retries = self.retries
        self.message = (strings.PRACTICE_FINISHED.format(time=time_text, retries=retries) if retries
                        else strings.PRACTICE_FINISHED_NO_RETRIES.format(time=time_text))

    # Rhythm scheduling

    def _schedule_count_in(self, latest_frame_time: float) -> None:
        self._count_in_pending = False
        self.rhythm.schedule(latest_frame_time + config.COUNT_IN_LEAD_S)
        offset = self.audio.capture_offset
        if self.playback.running and offset is not None:
            self.playback.clear()
            for index, beat in enumerate(self.rhythm.beat_times()):
                accent = self.rhythm.beat_in_measure(index) == 0
                self.playback.schedule(click(accent, self.playback.rate), at=beat + offset)

    def capture_now(self) -> float | None:
        """The current time on the capture clock."""
        offset = self.audio.capture_offset
        if offset is not None:
            return self.clock() - offset
        return self.last_frame_time

    # Audio

    def _on_frames(self, frames: list[AnalysisFrame]) -> None:
        if not self.active or self.state is not PracticeState.RUNNING:
            return
        if self.mode is Mode.RHYTHM and self._count_in_pending:
            self._schedule_count_in(frames[-1].time)
        for frame in frames:
            if self.last_frame_time is not None:
                self.practice_seconds += frame.time - self.last_frame_time
            self.last_frame_time = frame.time
            self.display.feed(frame)
            self.last_class = frame.frame_class
            update = self.engine.feed(frame)
            if self.finished:
                self._finish()
                break
            if self.mode is Mode.RHYTHM and update.failed is not None:
                self.playback.clear()
                self.score.set_failed(self.rhythm.position)
                break
        self._update()

    def _on_failed(self, problem: str) -> None:
        if self.active and self.state is PracticeState.RUNNING:
            self._interrupt_engine()
            self._block(strings.PRACTICE_INPUT_LOST if problem == InputProblem.LOST else strings.SETUP_INPUT_FAILED)
            self._update()

    # Display

    def _rhythm_beat(self) -> tuple[int | None, int | None]:
        """(beat index in beat_times(), position in the measure) at the current time."""
        now = self.capture_now()
        beats = self.rhythm.beat_times()
        if now is None or not beats or now < beats[0]:
            return None, None
        index = min(int((now - beats[0]) / (beats[1] - beats[0])) if len(beats) > 1 else 0, len(beats) - 1)
        return index, self.rhythm.beat_in_measure(index)

    def _guidance(self, cents: float | None) -> str:
        if self.state is not PracticeState.RUNNING:
            return self.message or ""
        event = self.event
        if self.mode is Mode.GUIDED:
            return guide_text(self.guided.tracker.status, self.last_class, cents, self.tolerance,
                              is_rest=not event.is_note, needs_release=self.guided.needs_release)
        status = self.rhythm.status
        if status is RhythmStatus.FAILED:
            target = event.pitch.name if event.pitch else strings.PRACTICE_TARGET_REST
            return strings.RHYTHM_FAILED[self.rhythm.failure].format(target=target) + " " + strings.RHYTHM_RETRY_HINT
        if status in (RhythmStatus.IDLE, RhythmStatus.COUNT_IN):
            index, _ = self._rhythm_beat()
            beat = 1 if index is None else index + 1
            return strings.GUIDE_COUNT_IN.format(beat=min(beat, config.COUNT_IN_BEATS))
        if not event.is_note:
            return strings.GUIDE_TAKE_BREATH
        text = guide_text(HoldStatus.WAITING, self.last_class, cents, self.tolerance)
        return strings.GUIDE_WHISTLE_NOW.format(note=event.pitch.name) \
            if text == strings.GUIDE_START_WHEN_READY else text

    def _update(self) -> None:
        if self.song is None:
            return
        finished = self.finished
        total = len(self.song.events)
        position = self.engine.position
        self.progress_label.setText(strings.PRACTICE_PROGRESS.format(current=min(position + 1, total), total=total))
        self.score.set_completed(self.engine.completed)
        if self.score.current != (None if finished else position):
            self.score.set_current(None if finished else position)

        cents = None
        if finished:
            self.target_label.setText("")
            self.hold_indicator.set_progress(1.0, 0.0, 0.0)
        else:
            event = self.event
            if self.mode is Mode.RHYTHM:
                credit, required = self.rhythm.current_credit()
                fraction = credit / required if required else 0.0
            else:
                tracker = self.guided.tracker
                credit, required, fraction = tracker.credit_s, self.guided.required_s(event), tracker.progress
            label = strings.HOLD_LABEL if event.is_note else strings.REST_LABEL
            self.hold_indicator.set_progress(fraction, credit, required, label)
            if event.is_note:
                self.target_label.setText(strings.PRACTICE_TARGET_NOTE.format(note=event.pitch.name))
                if self.state is PracticeState.RUNNING:
                    cents = smoothed_cents(self.display, event.pitch.frequency())
            else:
                self.target_label.setText(strings.PRACTICE_TARGET_REST)
            self.pitch_meter.setEnabled(event.is_note)
        self.pitch_meter.set_cents(cents)

        if self.mode is Mode.RHYTHM:
            beating = self.state is PracticeState.RUNNING and \
                self.rhythm.status in (RhythmStatus.COUNT_IN, RhythmStatus.PLAYING)
            _, beat = self._rhythm_beat() if beating else (None, None)
            self.beat_indicator.set_beat(beat, self.song.time.beats)

        self.detected_label.setText(describe_detected(self.display) if self.state is PracticeState.RUNNING else "")
        self.guide_label.setText(self._guidance(cents))

        active = self.state in (PracticeState.RUNNING, PracticeState.PAUSED, PracticeState.BLOCKED)
        self.retry_button.setVisible(self.rhythm_failed and self.state is PracticeState.RUNNING)
        self.pause_button.setVisible(active)
        self.pause_button.setText(strings.PRACTICE_PAUSE if self.state is PracticeState.RUNNING
                                  else strings.PRACTICE_RESUME)
        self.restart_button.setVisible(active)
        self.setup_button.setVisible(self.state is PracticeState.BLOCKED)
        self.repeat_button.setVisible(self.state is PracticeState.FINISHED)
        self.library_button.setVisible(self.state is PracticeState.FINISHED)
