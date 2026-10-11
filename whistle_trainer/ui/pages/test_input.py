"""Test input page: whistle one target note, or a series of random ones, with live pitch guidance."""

from __future__ import annotations

import random

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from whistle_trainer import config, strings
from whistle_trainer.assessment.frames import FrameClass
from whistle_trainer.assessment.hold import HoldStatus, NoteHold
from whistle_trainer.audio.capture import InputProblem
from whistle_trainer.audio.devices import DeviceInfo
from whistle_trainer.config import Difficulty
from whistle_trainer.music.transpose import spell_midi
from whistle_trainer.pitch.display import NoteDisplay
from whistle_trainer.storage.settings import SettingsStore
from whistle_trainer.ui.guidance import guide_text, smoothed_cents
from whistle_trainer.ui.meters import HoldIndicator, PitchMeter
from whistle_trainer.ui.pages.setup import describe_detected

# Selectable targets: C5 to C7.
TARGET_MIDI = range(72, 97)
DEFAULT_TARGET_MIDI = 83  # B5


class TestInputPage(QWidget):
    __test__ = False  # not a pytest test class

    def __init__(self, devices, audio, settings: SettingsStore, parent: QWidget | None = None,
                 rng: random.Random | None = None):
        super().__init__(parent)
        self.devices = devices
        self.audio = audio
        self.store = settings
        self.rng = rng or random.Random()
        self.active = False
        self.hits = 0
        self._passed_at: float | None = None  # frame time of the last hit in random mode
        self.display = NoteDisplay()
        self.hold: NoteHold | None = None
        self.last_class: FrameClass | None = None
        self.message: str | None = None

        self.target_combo = QComboBox()
        for midi in TARGET_MIDI:
            self.target_combo.addItem(spell_midi(midi).name, midi)
        self.target_combo.activated.connect(self.reset)
        self.difficulty_combo = QComboBox()
        for difficulty in Difficulty:
            self.difficulty_combo.addItem(strings.DIFFICULTY_NAMES[difficulty], difficulty)
        self.difficulty_combo.activated.connect(self.reset)
        self.random_check = QCheckBox(strings.TEST_RANDOM)
        self.random_check.toggled.connect(self._on_random_toggled)
        target_row = QHBoxLayout()
        target_row.addWidget(self.target_combo, stretch=1)
        target_row.addWidget(self.random_check)
        form = QFormLayout()
        form.addRow(strings.TEST_TARGET, target_row)
        form.addRow(strings.TEST_DIFFICULTY, self.difficulty_combo)
        self.hits_label = QLabel()
        self.hits_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hits_label.hide()

        self.target_label = QLabel()
        font = self.target_label.font()
        font.setPointSizeF(font.pointSizeF() * 2)
        font.setBold(True)
        self.target_label.setFont(font)
        self.target_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detected_label = QLabel(strings.DETECTED_NONE)
        self.detected_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pitch_meter = PitchMeter()
        self.hold_indicator = HoldIndicator()
        self.guide_label = QLabel()
        guide_font = self.guide_label.font()
        guide_font.setPointSizeF(guide_font.pointSizeF() * 1.4)
        self.guide_label.setFont(guide_font)
        self.guide_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.guide_label.setWordWrap(True)
        self.try_again_button = QPushButton(strings.TEST_TRY_AGAIN)
        self.try_again_button.clicked.connect(self._on_try_again)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.try_again_button)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addSpacing(16)
        layout.addWidget(self.target_label)
        layout.addWidget(self.detected_label)
        layout.addWidget(self.pitch_meter)
        layout.addWidget(self.hold_indicator)
        layout.addWidget(self.guide_label)
        layout.addWidget(self.hits_label)
        layout.addLayout(buttons)
        layout.addStretch()

        audio.frames_ready.connect(self._on_frames)
        audio.failed.connect(self._on_failed)

    @property
    def settings(self):
        return self.store.settings

    def _input(self) -> DeviceInfo | None:
        return next((d for d in self.devices.inputs() if d.id == self.settings.input_device), None)

    def activate(self) -> None:
        self.active = True
        self.message = None
        device = self._input()
        calibration = self.settings.calibrations.get(self.settings.input_device or "")
        if self.hold is None:
            self.target_combo.setCurrentIndex(self.target_combo.findData(self._default_target(calibration)))
        self.hits = 0
        if self.random_check.isChecked():
            self._choose_random_target()
        if device is None or calibration is None:
            self.message = strings.TEST_NOT_SET_UP
            self.audio.stop()
        else:
            self.audio.start(device, calibration.activity_threshold_db)
        self.reset()

    def deactivate(self) -> None:
        self.active = False
        self.audio.stop()

    @staticmethod
    def _default_target(calibration) -> int:
        if calibration and calibration.practice_low_midi is not None and calibration.practice_high_midi is not None:
            middle = round((calibration.practice_low_midi + calibration.practice_high_midi) / 2)
            return min(max(middle, TARGET_MIDI.start), TARGET_MIDI.stop - 1)
        return DEFAULT_TARGET_MIDI

    def random_range(self) -> tuple[int, int]:
        """Lowest and highest MIDI note for random targets."""
        calibration = self.settings.calibrations.get(self.settings.input_device or "")
        if calibration and calibration.practice_low_midi is not None and calibration.practice_high_midi is not None:
            low = min(max(calibration.practice_low_midi, TARGET_MIDI.start), TARGET_MIDI.stop - 1)
            high = min(max(calibration.practice_high_midi, TARGET_MIDI.start), TARGET_MIDI.stop - 1)
            if high > low:
                return low, high
        return config.TEST_RANDOM_DEFAULT_RANGE

    def _choose_random_target(self) -> None:
        """A random note in the range, never the current one again."""
        low, high = self.random_range()
        current = self.target_combo.currentData()
        choices = [midi for midi in range(low, high + 1) if midi != current]
        self.target_combo.setCurrentIndex(self.target_combo.findData(self.rng.choice(choices)))

    def _on_random_toggled(self, checked: bool) -> None:
        self.hits = 0
        self.try_again_button.setText(strings.TEST_NEW_NOTE if checked else strings.TEST_TRY_AGAIN)
        if checked:
            self._choose_random_target()
        self.reset()

    def _on_try_again(self) -> None:
        if self.random_check.isChecked():
            self._choose_random_target()
        self.reset()

    @property
    def target_hz(self) -> float:
        return spell_midi(self.target_combo.currentData()).frequency()

    @property
    def tolerance(self) -> float:
        return config.PITCH_TOLERANCE_CENTS[self.difficulty_combo.currentData()]

    def reset(self) -> None:
        self.hold = NoteHold(
            target_hz=self.target_hz,
            required_s=config.TEST_NOTE_HOLD_S,
            tolerance_cents=self.tolerance,
            confirmation_s=config.STABLE_CONFIRMATION_S,
            grace_s=config.GRACE_PERIOD_S,
            hop_s=self.audio.hop_seconds,
        )
        self.display.reset()
        self.last_class = None
        self._passed_at = None
        self.target_label.setText(strings.TEST_TARGET_LABEL.format(note=self.target_combo.currentText()))
        self.pitch_meter.set_tolerance(self.tolerance)
        self._update(None)

    def _on_frames(self, frames: list) -> None:
        if not self.active or self.hold is None or self.message is not None:
            return
        for frame in frames:
            if self._passed_at is not None:
                if frame.time - self._passed_at >= config.TEST_RANDOM_NEXT_S:
                    self._choose_random_target()
                    self.reset()
                continue
            self.hold.feed(frame)
            self.display.feed(frame)
            self.last_class = frame.frame_class
            if self.hold.status is HoldStatus.PASSED and self.random_check.isChecked():
                self.hits += 1
                self._passed_at = frame.time
        self._update(smoothed_cents(self.display, self.target_hz))

    def _on_failed(self, problem: str) -> None:
        if self.active:
            self.message = strings.SETUP_INPUT_LOST if problem == InputProblem.LOST else strings.SETUP_INPUT_FAILED
            self.display.reset()
            self._update(None)

    def guide_text(self, cents: float | None) -> str:
        if self.message is not None:
            return self.message
        if self.hold.status is HoldStatus.PASSED:
            return strings.TEST_RANDOM_PASSED if self.random_check.isChecked() else strings.TEST_PASSED
        return guide_text(self.hold.status, self.last_class, cents, self.tolerance)

    def _update(self, cents: float | None) -> None:
        self.detected_label.setText(describe_detected(self.display))
        self.pitch_meter.set_cents(cents)
        self.hold_indicator.set_progress(self.hold.progress, self.hold.credit_s, config.TEST_NOTE_HOLD_S)
        self.guide_label.setText(self.guide_text(cents))
        enabled = self.message is None
        random_mode = self.random_check.isChecked()
        self.target_combo.setEnabled(enabled and not random_mode)
        self.random_check.setEnabled(enabled)
        self.difficulty_combo.setEnabled(enabled)
        self.try_again_button.setEnabled(enabled)
        self.hits_label.setVisible(random_mode)
        self.hits_label.setText(strings.TEST_HITS.format(count=self.hits))
