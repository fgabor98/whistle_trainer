"""Test input page: whistle one target note with live pitch guidance."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from whistle_trainer import config, strings
from whistle_trainer.assessment.frames import FrameClass
from whistle_trainer.assessment.hold import HoldStatus, NoteHold
from whistle_trainer.audio.capture import InputProblem
from whistle_trainer.audio.devices import DeviceInfo
from whistle_trainer.config import Difficulty
from whistle_trainer.music.transpose import spell_midi
from whistle_trainer.pitch.display import NoteDisplay
from whistle_trainer.storage.settings import SettingsStore
from whistle_trainer.ui.meters import HoldIndicator, PitchMeter
from whistle_trainer.ui.pages.setup import describe_detected

# Selectable targets: C5 to C7.
TARGET_MIDI = range(72, 97)
DEFAULT_TARGET_MIDI = 83  # B5


class TestInputPage(QWidget):
    __test__ = False  # not a pytest test class

    def __init__(self, devices, audio, settings: SettingsStore, parent: QWidget | None = None):
        super().__init__(parent)
        self.devices = devices
        self.audio = audio
        self.store = settings
        self.active = False
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
        form = QFormLayout()
        form.addRow(strings.TEST_TARGET, self.target_combo)
        form.addRow(strings.TEST_DIFFICULTY, self.difficulty_combo)

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
        self.try_again_button.clicked.connect(self.reset)
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
        self.target_label.setText(strings.TEST_TARGET_LABEL.format(note=self.target_combo.currentText()))
        self.pitch_meter.set_tolerance(self.tolerance)
        self._update(None)

    def _on_frames(self, frames: list) -> None:
        if not self.active or self.hold is None or self.message is not None:
            return
        for frame in frames:
            self.hold.feed(frame)
            self.display.feed(frame)
            self.last_class = frame.frame_class
        self._update(self._smoothed_cents())

    def _on_failed(self, problem: str) -> None:
        if self.active:
            self.message = strings.SETUP_INPUT_LOST if problem == InputProblem.LOST else strings.SETUP_INPUT_FAILED
            self.display.reset()
            self._update(None)

    def _smoothed_cents(self) -> float | None:
        note = self.display.current
        return None if note is None else 1200 * math.log2(note.frequency / self.target_hz)

    def guide_text(self, cents: float | None) -> str:
        if self.message is not None:
            return self.message
        status = self.hold.status
        if status is HoldStatus.PASSED:
            return strings.TEST_PASSED
        if status is HoldStatus.INTERRUPTED:
            return strings.GUIDE_KEEP_GOING
        if status in (HoldStatus.CONFIRMING, HoldStatus.HOLDING):
            return strings.GUIDE_HOLD
        if self.last_class is FrameClass.UNCLEAR:
            return strings.GUIDE_NO_CLEAR_PITCH
        if self.last_class is FrameClass.PITCHED and cents is not None:
            if cents > self.tolerance:
                return strings.GUIDE_WHISTLE_LOWER
            if cents < -self.tolerance:
                return strings.GUIDE_WHISTLE_HIGHER
            return strings.GUIDE_HOLD
        return strings.GUIDE_START_WHEN_READY

    def _update(self, cents: float | None) -> None:
        self.detected_label.setText(describe_detected(self.display))
        self.pitch_meter.set_cents(cents)
        self.hold_indicator.set_progress(
            self.hold.credit_frames / self.hold.required_frames, self.hold.credit_s, config.TEST_NOTE_HOLD_S
        )
        self.guide_label.setText(self.guide_text(cents))
        enabled = self.message is None
        self.target_combo.setEnabled(enabled)
        self.difficulty_combo.setEnabled(enabled)
        self.try_again_button.setEnabled(enabled)
