"""Practice page: guided or rhythm practice through a song or a section of it."""

from __future__ import annotations

import bisect
import time
from enum import StrEnum

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from whistle_trainer import config, strings
from whistle_trainer.assessment.frames import AnalysisFrame, FrameClass
from whistle_trainer.assessment.guided import GuidedEngine
from whistle_trainer.assessment.hold import HoldStatus
from whistle_trainer.assessment.rhythm import RhythmEngine, RhythmStatus
from whistle_trainer.audio.capture import InputProblem
from whistle_trainer.audio.sounds import render
from whistle_trainer.audio.synth import click
from whistle_trainer.config import Difficulty, Mode
from whistle_trainer.music.model import Event, Song
from whistle_trainer.music.transpose import transpose_song
from whistle_trainer.pitch.display import NoteDisplay
from whistle_trainer.storage.progress import ProgressStore, SongProgress
from whistle_trainer.storage.settings import SettingsStore, SongPreferences
from whistle_trainer.ui.guidance import guide_text, smoothed_cents
from whistle_trainer.ui.meters import BeatIndicator, HoldIndicator, PitchMeter
from whistle_trainer.ui.pages.setup import describe_detected
from whistle_trainer.ui.pages.summary import SessionSummary
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
    finished = Signal(object)  # SessionSummary

    def __init__(self, devices, audio, playback, settings: SettingsStore, progress: ProgressStore,
                 parent: QWidget | None = None, clock=time.monotonic):
        super().__init__(parent)
        self.devices = devices
        self.audio = audio
        self.playback = playback
        self.store = settings
        self.progress_store = progress
        self.clock = clock
        self.active = False
        self.original: Song | None = None
        self.song: Song | None = None  # transposed
        self.preferences: SongPreferences | None = None
        self.mode = Mode.GUIDED
        self.guided: GuidedEngine | None = None
        self.rhythm: RhythmEngine | None = None
        self.range_start = 0
        self.range_end: int | None = None  # exclusive; None means the end of the song
        self.state = PracticeState.PAUSED
        self.message: str | None = None
        self._start_on_activate = False
        self._count_in_pending = False
        self._ignore_until: float | None = None  # capture time; set while a reference note plays
        self.display = NoteDisplay()
        self.last_class: FrameClass | None = None
        self.last_frame_time: float | None = None
        # Session totals, kept across settings changes, and what has been saved to progress.
        self.practice_seconds = 0.0
        self.session_retries: dict[int, int] = {}
        self._seen_retries: dict[int, int] = {}
        self._recorded_seconds = 0.0

        self.score = ScoreView()
        self.score.note_clicked.connect(self._on_note_clicked)
        self.progress_label = QLabel()
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.target_label = _big_label(2.0, bold=True)
        self.detected_label = QLabel(strings.DETECTED_NONE)
        self.detected_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.beat_indicator = BeatIndicator()
        self.pitch_meter = PitchMeter()
        self.hold_indicator = HoldIndicator()
        self.guide_label = _big_label(1.4)

        self.paused_panel = self._build_paused_panel()

        self.hear_button = QPushButton(strings.PRACTICE_HEAR_NOTE)
        self.hear_button.clicked.connect(self.hear_note)
        self.pause_button = QPushButton(strings.PRACTICE_PAUSE)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.retry_button = QPushButton(strings.PRACTICE_RETRY)
        self.retry_button.clicked.connect(self.retry)
        self.restart_button = QPushButton(strings.PRACTICE_RESTART)
        self.restart_button.clicked.connect(self.restart)
        self.setup_button = QPushButton(strings.PRACTICE_AUDIO_SETUP)
        self.setup_button.clicked.connect(self.audio_setup_requested)
        buttons = QHBoxLayout()
        buttons.addStretch()
        for button in (self.retry_button, self.hear_button, self.pause_button, self.restart_button,
                       self.setup_button):
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
        layout.addWidget(self.paused_panel)

        for key, action in ((Qt.Key.Key_Space, self.toggle_pause), (Qt.Key.Key_H, self.hear_note),
                            (Qt.Key.Key_R, self.retry)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(action)

        self.beat_timer = QTimer(self)
        self.beat_timer.setInterval(_BEAT_REFRESH_MS)
        self.beat_timer.timeout.connect(self._update)

        audio.frames_ready.connect(self._on_frames)
        audio.failed.connect(self._on_failed)

    def _build_paused_panel(self) -> QGroupBox:
        self.mode_combo = QComboBox()
        for mode in Mode:
            self.mode_combo.addItem(strings.MODE_NAMES[mode], mode)
        self.tempo_spin = QSpinBox()
        self.tempo_spin.setRange(config.MIN_TEMPO, config.MAX_TEMPO)
        self.tempo_spin.setSuffix(strings.LIBRARY_TEMPO_SUFFIX)
        self.difficulty_combo = QComboBox()
        for difficulty in Difficulty:
            self.difficulty_combo.addItem(strings.DIFFICULTY_NAMES[difficulty], difficulty)
        self.transposition_spin = QSpinBox()
        self.transposition_spin.setRange(config.MIN_TRANSPOSITION, config.MAX_TRANSPOSITION)
        self.transposition_spin.setSuffix(strings.TRANSPOSITION_SUFFIX)
        for widget in (self.mode_combo, self.difficulty_combo):
            widget.currentIndexChanged.connect(self._on_settings_changed)
        for widget in (self.tempo_spin, self.transposition_spin):
            widget.valueChanged.connect(self._on_settings_changed)
        self.clear_section_button = QPushButton(strings.PRACTICE_CLEAR_SECTION)
        self.clear_section_button.clicked.connect(self.clear_section)
        hint = QLabel(strings.PRACTICE_SECTION_HINT)
        hint.setWordWrap(True)

        left = QFormLayout()
        left.addRow(strings.LIBRARY_MODE, self.mode_combo)
        left.addRow(strings.LIBRARY_TEMPO, self.tempo_spin)
        right = QFormLayout()
        right.addRow(strings.LIBRARY_DIFFICULTY, self.difficulty_combo)
        right.addRow(strings.PRACTICE_TRANSPOSITION, self.transposition_spin)
        section = QVBoxLayout()
        section.addWidget(hint)
        section.addWidget(self.clear_section_button, alignment=Qt.AlignmentFlag.AlignLeft)
        panel = QGroupBox()
        row = QHBoxLayout(panel)
        row.addLayout(left)
        row.addLayout(right)
        row.addLayout(section, stretch=1)
        return panel

    @property
    def settings(self):
        return self.store.settings

    def title(self) -> str:
        return self.original.title if self.original else ""

    # Mode-independent views of the engine

    @property
    def engine(self) -> GuidedEngine | RhythmEngine:
        return self.rhythm if self.mode is Mode.RHYTHM else self.guided

    @property
    def done(self) -> bool:
        return self.engine.finished

    @property
    def event(self) -> Event:
        return self.engine.event

    @property
    def end(self) -> int:
        return len(self.song.events) if self.range_end is None else self.range_end

    @property
    def retries(self) -> int:
        return sum(self.session_retries.values())

    @property
    def rhythm_failed(self) -> bool:
        return self.mode is Mode.RHYTHM and self.rhythm.status is RhythmStatus.FAILED

    @property
    def song_progress(self) -> SongProgress:
        return self.progress_store.get(self.original.id, self.mode, len(self.original.events))

    # Session control

    def load(self, song: Song, preferences: SongPreferences, start: int = 0, end: int | None = None) -> None:
        """Prepare a new session; listening starts when the page is shown."""
        self.original = song
        self.preferences = preferences
        self.range_start, self.range_end = start, end
        self._apply_preferences()
        self._new_session()
        self._build_engine(start)
        self.state = PracticeState.PAUSED
        self._start_on_activate = True

    def _apply_preferences(self) -> None:
        preferences = self.preferences
        self.mode = preferences.mode
        self.tolerance = config.PITCH_TOLERANCE_CENTS[preferences.difficulty]
        self.pitch_meter.set_tolerance(self.tolerance)
        self.song = transpose_song(self.original, preferences.transposition)
        self.score.set_song(self.song, self.settings.show_note_names)
        self.beat_indicator.setVisible(self.mode is Mode.RHYTHM)
        widgets = (self.mode_combo, self.tempo_spin, self.difficulty_combo, self.transposition_spin)
        for widget in widgets:
            widget.blockSignals(True)
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(preferences.mode))
        self.tempo_spin.setValue(preferences.tempo)
        self.difficulty_combo.setCurrentIndex(self.difficulty_combo.findData(preferences.difficulty))
        self.transposition_spin.setValue(preferences.transposition)
        for widget in widgets:
            widget.blockSignals(False)

    def _new_session(self) -> None:
        self.practice_seconds = 0.0
        self.session_retries = {}
        self._recorded_seconds = 0.0
        self.score.set_completed(set())

    def _build_engine(self, position: int) -> None:
        """A fresh engine at `position`; unfinished progress is discarded."""
        tempo, hop = self.preferences.tempo, self.audio.hop_seconds
        if self.mode is Mode.RHYTHM:
            self.rhythm = RhythmEngine(self.song, tempo, self.tolerance, hop, position, self.end)
        else:
            self.guided = GuidedEngine(self.song, tempo, self.tolerance, hop, position, self.end)
        self._seen_retries = {}
        self._count_in_pending = self.state is PracticeState.RUNNING and self.mode is Mode.RHYTHM
        self.score.set_failed(None)
        self.score.set_section((self.range_start, self.end) if self.range_end is not None else None)
        self.score.set_current(position, animate=False)

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
        if self.engine is not None and self.state is not PracticeState.FINISHED:
            self._interrupt_engine()
        self._save_progress()

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
        self._ignore_until = None
        self.audio.start(device, calibration.activity_threshold_db)
        if self.mode is Mode.RHYTHM:
            self._count_in_pending = True
            if self.settings.metronome_sound:
                self._open_output()
            self.beat_timer.start()

    def _open_output(self) -> bool:
        output = next((d for d in self.devices.outputs() if d.id == self.settings.output_device), None)
        return self.playback.start(output)

    def _stop_listening(self) -> None:
        self.audio.stop()
        self.playback.stop()
        self.beat_timer.stop()
        self._count_in_pending = False
        self._ignore_until = None

    def _interrupt_engine(self) -> None:
        """Discard the unfinished event; rhythm mode needs a new count-in afterwards."""
        if self.mode is Mode.RHYTHM:
            self.rhythm.stop()
        else:
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
            self._save_progress()
        elif self.state in (PracticeState.PAUSED, PracticeState.BLOCKED):
            self._start_listening()
        self._update()

    def restart(self) -> None:
        """Start the section (or song) again from its first note."""
        self._stop_listening()
        self._save_progress()
        self._new_session()
        self.state = PracticeState.PAUSED
        self._build_engine(self.range_start)
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
        progress = self.song_progress
        self._record(progress)
        reached_end = self.end == len(self.song.events)
        song_completed = reached_end and progress.is_complete
        if song_completed:
            progress.record_completion()
        progress.next_index = 0 if reached_end else self.end
        self.progress_store.save()
        self.finished.emit(SessionSummary(
            song=self.song, mode=self.mode, start=self.range_start, end=self.end,
            active_seconds=self.practice_seconds, retries=dict(self.session_retries),
            song_completed=song_completed,
        ))

    # Settings and section changes while paused

    def _changeable(self) -> bool:
        return self.state in (PracticeState.PAUSED, PracticeState.BLOCKED)

    def _on_settings_changed(self) -> None:
        if self.preferences is None or not self._changeable():
            return
        position = self.engine.position
        self._save_progress()
        # Qt returns combo box data as plain strings.
        self.preferences.mode = Mode(self.mode_combo.currentData())
        self.preferences.difficulty = Difficulty(self.difficulty_combo.currentData())
        self.preferences.tempo = self.tempo_spin.value()
        self.preferences.transposition = self.transposition_spin.value()
        self.store.save()
        self._apply_preferences()
        self._build_engine(min(position, self.end - 1))
        self._update()

    def _on_note_clicked(self, index: int, shift: bool) -> None:
        if not self._changeable():
            return
        if shift:
            if index >= self.engine.position:
                self.range_start, self.range_end = self.engine.position, index + 1
            else:
                self.range_start, self.range_end = index, self.engine.position + 1
        else:
            self.range_start = index
            if self.range_end is not None and self.range_end <= index:
                self.range_end = None
        self._build_engine(self.range_start)
        self._update()

    def clear_section(self) -> None:
        if self._changeable():
            position = self.engine.position
            self.range_start, self.range_end = 0, None
            self._build_engine(position)
            self._update()

    # Hear target note

    def can_hear_note(self) -> bool:
        if self.song is None or self.done or self.state is PracticeState.FINISHED:
            return False
        if self.mode is Mode.RHYTHM:
            return self.rhythm_failed or self._changeable()
        return True

    def hear_note(self) -> None:
        """Play the target note; while it plays the microphone is ignored, then the note starts over."""
        if not self.can_hear_note() or not self.event.is_note or not self._open_output():
            return
        self.playback.clear()
        self.playback.schedule(render(self.settings.listen_sound, self.event.pitch.frequency(),
                                      config.REFERENCE_NOTE_S, self.playback.rate))
        now = self.capture_now()
        if self.state is PracticeState.RUNNING and now is not None:
            self._ignore_until = now + config.REFERENCE_NOTE_S + config.REFERENCE_SETTLE_S
            self._interrupt_engine()
            if self.mode is Mode.RHYTHM:
                self._count_in_pending = False  # wait for Retry
        self._update()

    # Progress

    def _record(self, progress: SongProgress) -> None:
        """Add this session's results since the last call to the saved progress."""
        counts = self.rhythm.failures if self.mode is Mode.RHYTHM else self.guided.retries
        for index, count in counts.items():
            delta = count - self._seen_retries.get(index, 0)
            if delta:
                self.session_retries[index] = self.session_retries.get(index, 0) + delta
                progress.add_retry(index, delta)
        self._seen_retries = dict(counts)
        progress.practice_seconds += self.practice_seconds - self._recorded_seconds
        self._recorded_seconds = self.practice_seconds
        progress.completed |= self.engine.completed
        if not self.done:
            progress.next_index = self.engine.position

    def _save_progress(self) -> None:
        if self.engine is not None and self.original is not None and self.state is not PracticeState.FINISHED:
            self._record(self.song_progress)
            self.progress_store.save()

    # Rhythm scheduling

    def _schedule_count_in(self, latest_frame_time: float) -> None:
        self._count_in_pending = False
        self.rhythm.schedule(latest_frame_time + config.COUNT_IN_LEAD_S)
        offset = self.audio.capture_offset
        if self.settings.metronome_sound and self.playback.running and offset is not None:
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
        if self._ignore_until is not None:
            frames = [f for f in frames if f.time >= self._ignore_until]
            if not frames:
                return
            self._ignore_until = None
            self.display.reset()
        if self.mode is Mode.RHYTHM and self._count_in_pending:
            self._schedule_count_in(frames[-1].time)
        session_completed = set(self.score.completed)
        for frame in frames:
            if self.last_frame_time is not None:
                self.practice_seconds += frame.time - self.last_frame_time
            self.last_frame_time = frame.time
            self.display.feed(frame)
            self.last_class = frame.frame_class
            update = self.engine.feed(frame)
            if self.done:
                self.score.set_completed(session_completed | self.engine.completed)
                self._finish()
                return
            if self.mode is Mode.RHYTHM and update.failed is not None:
                self.playback.clear()
                self.score.set_failed(self.rhythm.position)
                break
        self.score.set_completed(session_completed | self.engine.completed)
        self._record(self.song_progress)
        self._update()

    def _on_failed(self, problem: str) -> None:
        if self.active and self.state is PracticeState.RUNNING:
            self._interrupt_engine()
            self._block(strings.PRACTICE_INPUT_LOST if problem == InputProblem.LOST else strings.SETUP_INPUT_FAILED)
            self._save_progress()
            self._update()

    # Display

    def _rhythm_beat(self) -> tuple[int | None, int | None]:
        """(beat index in beat_times(), position in the measure) at the current time."""
        now = self.capture_now()
        beats = self.rhythm.beat_times()
        if now is None or not beats or now < beats[0]:
            return None, None
        # Beats can differ in length when the time signature changes, so search for the last one started.
        index = bisect.bisect_right(beats, now) - 1
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
        if self.song is None or self.engine is None:
            return
        done = self.done
        total = len(self.song.events)
        position = self.engine.position
        self.progress_label.setText(strings.PRACTICE_PROGRESS.format(current=min(position + 1, total), total=total))
        if self.score.current != (None if done else position):
            self.score.set_current(None if done else position)

        cents = None
        if not done:
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
                if self.state is PracticeState.RUNNING and self._ignore_until is None:
                    cents = smoothed_cents(self.display, event.pitch.frequency())
            else:
                self.target_label.setText(strings.PRACTICE_TARGET_REST)
            self.pitch_meter.setEnabled(event.is_note)
        self.pitch_meter.set_cents(cents)

        if self.mode is Mode.RHYTHM:
            beating = self.state is PracticeState.RUNNING and \
                self.rhythm.status in (RhythmStatus.COUNT_IN, RhythmStatus.PLAYING)
            index, beat = self._rhythm_beat() if beating else (None, None)
            beats = self.rhythm.beats_per_measure(index) if index is not None else self.song.time.beats
            self.beat_indicator.set_beat(beat, beats)

        self.detected_label.setText(describe_detected(self.display) if self.state is PracticeState.RUNNING else "")
        self.guide_label.setText(self._guidance(cents))

        changeable = self._changeable()
        self.score.set_interactive(changeable)
        self.paused_panel.setVisible(changeable)
        self.clear_section_button.setEnabled(self.range_end is not None or self.range_start > 0)
        active = self.state is not PracticeState.FINISHED
        self.retry_button.setVisible(self.rhythm_failed and self.state is PracticeState.RUNNING)
        self.hear_button.setVisible(active and not done and self.event.is_note)
        self.hear_button.setEnabled(self.can_hear_note())
        self.pause_button.setVisible(active)
        self.pause_button.setText(strings.PRACTICE_PAUSE if self.state is PracticeState.RUNNING
                                  else strings.PRACTICE_RESUME)
        self.restart_button.setVisible(active)
        self.restart_button.setText(strings.PRACTICE_RESTART_SECTION if self.range_end is not None
                                    else strings.PRACTICE_RESTART)
        self.setup_button.setVisible(self.state is PracticeState.BLOCKED)
