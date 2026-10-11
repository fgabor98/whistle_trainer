"""Listen page: hear the loaded song, whole or note by note. The microphone is never used."""

from __future__ import annotations

import time
from fractions import Fraction

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from whistle_trainer import config, strings
from whistle_trainer.audio.sounds import render
from whistle_trainer.config import Sound
from whistle_trainer.music.model import Event, Song
from whistle_trainer.music.timing import seconds
from whistle_trainer.music.transpose import transpose_song
from whistle_trainer.storage.settings import SettingsStore, SongPreferences
from whistle_trainer.ui.score_view import ScoreView

# Notes are rendered and scheduled this far ahead of the playback position.
_LOOKAHEAD_S = 1.0
_START_DELAY_S = 0.15
_REFRESH_MS = 20


def describe_beats(duration: Fraction, beat_length: Fraction) -> str:
    count = duration / beat_length
    if count == 1:
        return strings.BEATS[1]
    text = str(int(count)) if count.denominator == 1 else f"{float(count):g}"
    return strings.BEATS_MANY.format(count=text)


class ListenPage(QWidget):
    practice_requested = Signal(int)  # start index

    def __init__(self, devices, playback, settings: SettingsStore, parent: QWidget | None = None,
                 clock=time.monotonic):
        super().__init__(parent)
        self.devices = devices
        self.playback = playback
        self.store = settings
        self.clock = clock
        self.original: Song | None = None
        self.song: Song | None = None
        self.preferences: SongPreferences | None = None
        self.position = 0
        self.message: str | None = None
        # Playing the whole song: (start time, event index) per event, and the end time.
        self._plan: list[tuple[float, int]] = []
        self._plan_end = 0.0
        self._next_to_schedule = 0
        self._played_to_end = False

        self.score = ScoreView()
        self.score.set_interactive(True)
        self.score.note_clicked.connect(lambda index, _shift: self.play_note(index))
        self.note_label = QLabel()
        font = self.note_label.font()
        font.setPointSizeF(font.pointSizeF() * 1.8)
        font.setBold(True)
        self.note_label.setFont(font)
        self.note_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label = QLabel(strings.LISTEN_HINT)
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setWordWrap(True)

        self.tempo_spin = QSpinBox()
        self.tempo_spin.setRange(config.MIN_TEMPO, config.MAX_TEMPO)
        self.tempo_spin.setSuffix(strings.LIBRARY_TEMPO_SUFFIX)
        self.tempo_spin.valueChanged.connect(self._on_settings_changed)
        self.transposition_spin = QSpinBox()
        self.transposition_spin.setRange(config.MIN_TRANSPOSITION, config.MAX_TRANSPOSITION)
        self.transposition_spin.setSuffix(strings.TRANSPOSITION_SUFFIX)
        self.transposition_spin.valueChanged.connect(self._on_settings_changed)
        self.sound_combo = QComboBox()
        for sound in Sound:
            self.sound_combo.addItem(strings.SOUND_NAMES[sound], sound)
        self.sound_combo.setCurrentIndex(self.sound_combo.findData(settings.settings.listen_sound))
        self.sound_combo.currentIndexChanged.connect(self._on_sound_changed)
        self.credit_label = QLabel(strings.PIANO_CREDIT)
        self.credit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credit_font = self.credit_label.font()
        credit_font.setPointSizeF(credit_font.pointSizeF() * 0.85)
        self.credit_label.setFont(credit_font)
        form = QHBoxLayout()
        form.addStretch()
        for label, widget in ((strings.LISTEN_SOUND, self.sound_combo), (strings.LISTEN_TEMPO, self.tempo_spin),
                              (strings.LISTEN_TRANSPOSITION, self.transposition_spin)):
            form.addWidget(QLabel(label))
            form.addWidget(widget)
            form.addSpacing(16)
        form.addStretch()

        self.play_button = QPushButton(strings.LISTEN_PLAY)
        self.play_button.clicked.connect(self.toggle_play)
        self.previous_button = QPushButton(strings.LISTEN_PREVIOUS)
        self.previous_button.clicked.connect(self.previous_note)
        self.next_button = QPushButton(strings.LISTEN_NEXT)
        self.next_button.clicked.connect(self.next_note)
        self.practice_button = QPushButton(strings.LISTEN_PRACTICE)
        self.practice_button.clicked.connect(lambda: self.practice_requested.emit(self.position))
        buttons = QHBoxLayout()
        buttons.addStretch()
        for button in (self.previous_button, self.play_button, self.next_button, self.practice_button):
            buttons.addWidget(button)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self.score, stretch=1)
        layout.addWidget(self.note_label)
        layout.addWidget(self.hint_label)
        layout.addLayout(buttons)
        layout.addLayout(form)
        layout.addWidget(self.credit_label)

        for key, action in ((Qt.Key.Key_Space, self.toggle_play), (Qt.Key.Key_Left, self.previous_note),
                            (Qt.Key.Key_Right, self.next_note)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(action)

        self.timer = QTimer(self)
        self.timer.setInterval(_REFRESH_MS)
        self.timer.timeout.connect(self._tick)

    def title(self) -> str:
        return strings.PAGE_LISTEN.format(title=self.original.title) if self.original else ""

    @property
    def playing(self) -> bool:
        return bool(self._plan)

    # Loading and settings

    def load(self, song: Song, preferences: SongPreferences, position: int = 0) -> None:
        self.original = song
        self.preferences = preferences
        self.position = position
        self._played_to_end = False
        for spin, value in ((self.tempo_spin, preferences.tempo), (self.transposition_spin, preferences.transposition)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self._apply_transposition()

    def _apply_transposition(self) -> None:
        self.song = transpose_song(self.original, self.preferences.transposition)
        self.score.set_song(self.song, self.store.settings.show_note_names)
        self.score.set_current(self.position, animate=False)
        self._update()

    def _on_settings_changed(self) -> None:
        if self.preferences is None:
            return
        self.stop()
        transposition_changed = self.transposition_spin.value() != self.preferences.transposition
        self.preferences.tempo = self.tempo_spin.value()
        self.preferences.transposition = self.transposition_spin.value()
        self.store.save()
        if transposition_changed:
            self._apply_transposition()

    def activate(self) -> None:
        self.message = None
        self.sound_combo.blockSignals(True)
        self.sound_combo.setCurrentIndex(self.sound_combo.findData(self.sound))
        self.sound_combo.blockSignals(False)
        self._update()

    def deactivate(self) -> None:
        self.stop()
        self.playback.stop()

    # Playback

    def _open_output(self) -> bool:
        if self.playback.running:
            return True
        settings = self.store.settings
        output = next((d for d in self.devices.outputs() if d.id == settings.output_device), None)
        if self.playback.start(output):
            self.message = None
            return True
        self.message = strings.LISTEN_NO_OUTPUT
        self._update()
        return False

    @property
    def sound(self) -> Sound:
        return self.store.settings.listen_sound

    def _on_sound_changed(self) -> None:
        self.stop()
        # Qt returns combo box data as plain strings.
        self.store.settings.listen_sound = Sound(self.sound_combo.currentData())
        self.store.save()
        self._update()

    def _render(self, event: Event) -> object:
        return render(self.sound, event.pitch.frequency(), seconds(event.duration, self.preferences.tempo),
                       self.playback.rate, seed=event.index)

    def toggle_play(self) -> None:
        if self.playing:
            self.stop()
        else:
            self.play_song()

    def play_song(self) -> None:
        """Play from the highlighted note to the end, or from the start after the end was reached."""
        if self.song is None or not self._open_output():
            return
        self.stop()
        if self._played_to_end:
            self.position = 0
            self._played_to_end = False
        start = self.clock() + _START_DELAY_S
        origin = self.song.events[self.position].start
        self._plan = [(start + seconds(e.start - origin, self.preferences.tempo), e.index)
                      for e in self.song.events[self.position:]]
        self._plan_end = start + seconds(self.song.length - origin, self.preferences.tempo)
        self._next_to_schedule = 0
        self._schedule_ahead()
        self.timer.start()
        self._update()

    def _schedule_ahead(self) -> None:
        horizon = self.clock() + _LOOKAHEAD_S
        while self._next_to_schedule < len(self._plan) and self._plan[self._next_to_schedule][0] <= horizon:
            at, index = self._plan[self._next_to_schedule]
            event = self.song.events[index]
            if event.is_note:
                self.playback.schedule(self._render(event), at=at)
            self._next_to_schedule += 1

    def _tick(self) -> None:
        if not self._plan:
            return
        now = self.clock()
        self._schedule_ahead()
        started = [index for at, index in self._plan if at <= now]
        if started:
            self.position = started[-1]
        if now >= self._plan_end:
            self._plan = []
            self._played_to_end = True
            self.timer.stop()
        self._update()

    def stop(self) -> None:
        """Stop playing; the highlight stays on the last played note."""
        if self._plan:
            self._plan = []
            self.playback.clear()
            self.timer.stop()
        self._update()

    def play_note(self, index: int) -> None:
        if self.song is None:
            return
        self.stop()
        self.position = index
        self._played_to_end = False
        event = self.song.events[index]
        if event.is_note and self._open_output():
            self.playback.schedule(self._render(event))
        self._update()

    def next_note(self) -> None:
        if self.song is not None and self.position < len(self.song.events) - 1:
            self.play_note(self.position + 1)

    def previous_note(self) -> None:
        if self.song is not None and self.position > 0:
            self.play_note(self.position - 1)

    # Display

    def _update(self) -> None:
        if self.song is None:
            return
        if self.score.current != self.position:
            self.score.set_current(self.position)
        event = self.song.events[self.position]
        beats = describe_beats(event.duration, self.song.time.beat_length)
        self.note_label.setText(strings.LISTEN_NOTE.format(note=event.pitch.name, beats=beats) if event.is_note
                                else strings.LISTEN_REST.format(beats=beats))
        self.hint_label.setText(self.message or strings.LISTEN_HINT)
        self.credit_label.setVisible(self.sound is Sound.PIANO)
        self.play_button.setText(strings.LISTEN_STOP if self.playing else strings.LISTEN_PLAY)
        self.previous_button.setEnabled(self.position > 0)
        self.next_button.setEnabled(self.position < len(self.song.events) - 1)
