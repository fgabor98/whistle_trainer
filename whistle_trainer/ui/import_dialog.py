"""Add song dialog: choose the melody line of an imported score, preview it, and add it."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from whistle_trainer import strings
from whistle_trainer.audio.sounds import render
from whistle_trainer.music.importer import ImportedScore, ImportResult, extract, save
from whistle_trainer.music.timing import seconds
from whistle_trainer.storage.settings import SettingsStore

PREVIEW_S = 20.0  # length of the preview
_START_DELAY_S = 0.15


def counted(forms: tuple[str, str], count: int) -> str:
    return (forms[0] if count == 1 else forms[1]).format(count=count)


def report_lines(result: ImportResult) -> list[str]:
    report = result.report
    lines = []
    for count, text in ((report.notes_left_out, strings.ADD_SONG_LEFT_OUT),
                        (report.grace_notes_removed, strings.ADD_SONG_GRACE),
                        (report.measures_written_out, strings.ADD_SONG_WRITTEN_OUT),
                        (report.notes_rounded, strings.ADD_SONG_ROUNDED),
                        (report.measures_too_long, strings.ADD_SONG_TOO_LONG),
                        (report.measures_too_short, strings.ADD_SONG_TOO_SHORT)):
        if count > 0:
            lines.append(counted(text, count))
    if report.octave_shift > 0:
        lines.append(counted(strings.ADD_SONG_MOVED_UP, report.octave_shift // 12))
    elif report.octave_shift < 0:
        lines.append(counted(strings.ADD_SONG_MOVED_DOWN, -report.octave_shift // 12))
    return lines or [strings.ADD_SONG_NOTHING]


class ImportDialog(QDialog):
    def __init__(self, score: ImportedScore, devices, playback, settings: SettingsStore, user_directory: Path,
                 parent: QWidget | None = None, clock=time.monotonic):
        super().__init__(parent)
        self.score = score
        self.devices = devices
        self.playback = playback
        self.store = settings
        self.user_directory = user_directory
        self.clock = clock
        self.result: ImportResult | None = None
        self.saved_path: Path | None = None
        self.setWindowTitle(strings.ADD_SONG_TITLE)
        self.setMinimumWidth(520)

        self.title_edit = QLineEdit(score.title)
        self.line_combo = QComboBox()
        for candidate in score.candidates:
            self.line_combo.addItem(strings.ADD_SONG_CANDIDATE.format(
                label=candidate.label, count=candidate.note_count, low=candidate.low, high=candidate.high))
        self.line_combo.setCurrentIndex(score.default_candidate)
        self.line_combo.currentIndexChanged.connect(self._extract)
        form = QFormLayout()
        form.addRow(strings.ADD_SONG_FILE, QLabel(score.file_name))
        form.addRow(strings.ADD_SONG_NAME, self.title_edit)
        form.addRow(strings.ADD_SONG_LINE, self.line_combo)

        self.result_label = QLabel()
        self.report_label = QLabel()
        self.report_label.setWordWrap(True)
        hint = QLabel(strings.ADD_SONG_HINT)
        hint.setWordWrap(True)
        self.preview_button = QPushButton(strings.ADD_SONG_PREVIEW)
        self.preview_button.clicked.connect(self.toggle_preview)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.add_button = self.buttons.addButton(strings.ADD_SONG_ADD, QDialogButtonBox.ButtonRole.AcceptRole)
        self.add_button.setDefault(True)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.result_label)
        layout.addWidget(self.report_label)
        layout.addWidget(hint)
        layout.addWidget(self.preview_button)
        layout.addWidget(self.buttons)

        self._preview_end: float | None = None
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(100)
        self.preview_timer.timeout.connect(self._check_preview)
        self._extract()

    def _extract(self) -> None:
        self.stop_preview()
        self.result = extract(self.score, self.line_combo.currentIndex())
        song = self.result.song
        self.result_label.setText(strings.ADD_SONG_RESULT.format(
            count=len(song.notes), low=song.lowest.name, high=song.highest.name, measures=len(song.measures)))
        self.report_label.setText(strings.ADD_SONG_SIMPLIFIED + "\n• " + "\n• ".join(report_lines(self.result)))

    # Preview

    @property
    def previewing(self) -> bool:
        return self._preview_end is not None

    def toggle_preview(self) -> None:
        if self.previewing:
            self.stop_preview()
        else:
            self.play_preview()

    def play_preview(self) -> None:
        output = next((d for d in self.devices.outputs() if d.id == self.store.settings.output_device), None)
        if not self.playback.start(output):
            return
        song = self.result.song
        sound = self.store.settings.listen_sound
        start = self.clock() + _START_DELAY_S
        for event in song.notes:
            offset = seconds(event.start, song.tempo)
            if offset >= PREVIEW_S:
                break
            duration = min(seconds(event.duration, song.tempo), PREVIEW_S - offset)
            self.playback.schedule(render(sound, event.pitch.frequency(), duration, self.playback.rate,
                                          seed=event.index), at=start + offset)
        self._preview_end = start + min(PREVIEW_S, seconds(song.length, song.tempo))
        self.preview_button.setText(strings.ADD_SONG_STOP)
        self.preview_timer.start()

    def stop_preview(self) -> None:
        if self.previewing:
            self.playback.stop()
        self._preview_end = None
        self.preview_timer.stop()
        self.preview_button.setText(strings.ADD_SONG_PREVIEW)

    def _check_preview(self) -> None:
        if self._preview_end is not None and self.clock() >= self._preview_end:
            self.stop_preview()

    # Closing

    def accept(self) -> None:
        self.stop_preview()
        self.saved_path = save(self.result, self.title_edit.text() or self.score.title, self.user_directory)
        super().accept()

    def reject(self) -> None:
        self.stop_preview()
        super().reject()
