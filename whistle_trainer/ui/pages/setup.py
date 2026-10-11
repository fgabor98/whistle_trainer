"""Audio setup page: device selection, level calibration, and range measurement."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from whistle_trainer import config, strings
from whistle_trainer.audio.capture import InputProblem
from whistle_trainer.audio.devices import DeviceInfo
from whistle_trainer.music.transpose import spell_midi
from whistle_trainer.pitch.calibration import LevelCalibration, LevelStep, Pause, RangeMeasurement, SetupProblem
from whistle_trainer.pitch.display import NoteDisplay
from whistle_trainer.storage.settings import Calibration, SettingsStore
from whistle_trainer.ui.meters import LevelMeter


def describe_detected(display: NoteDisplay) -> str:
    note = display.current
    if note is None:
        return strings.DETECTED_NONE
    return strings.DETECTED_NOTE.format(note=note.pitch.name, cents=note.cents)


def fill_device_combo(combo: QComboBox, devices: list[DeviceInfo], saved_id: str | None,
                      saved_name: str | None) -> None:
    """List devices, keeping a saved but disconnected device visible and selected."""
    combo.clear()
    for device in devices:
        name = strings.SETUP_SYSTEM_DEFAULT.format(name=device.name) if device.is_default else device.name
        combo.addItem(name, device.id)
    if saved_id is not None and all(d.id != saved_id for d in devices):
        combo.addItem(strings.SETUP_UNAVAILABLE.format(name=saved_name or saved_id), saved_id)
    wanted = saved_id or next((d.id for d in devices if d.is_default), None)
    index = combo.findData(wanted) if wanted is not None else -1
    combo.setCurrentIndex(index if index >= 0 else 0)


class SetupPage(QWidget):
    test_input_requested = Signal()

    def __init__(self, devices, audio, settings: SettingsStore, parent: QWidget | None = None):
        super().__init__(parent)
        self.devices = devices
        self.audio = audio
        self.store = settings
        self.active = False
        self.display = NoteDisplay()
        self.calibration: LevelCalibration | None = None
        self.range_low: RangeMeasurement | None = None
        self.range_pause: Pause | None = None
        self.range_high: RangeMeasurement | None = None
        self.message: str | None = None

        self.input_combo = QComboBox()
        self.input_combo.activated.connect(self._on_input_chosen)
        self.output_combo = QComboBox()
        self.output_combo.activated.connect(self._on_output_chosen)
        self.level_meter = LevelMeter()
        self.detected_label = QLabel(strings.DETECTED_NONE)

        form = QFormLayout()
        form.addRow(strings.SETUP_INPUT, self.input_combo)
        form.addRow(strings.SETUP_OUTPUT, self.output_combo)
        form.addRow(strings.SETUP_ACTIVITY, self.level_meter)
        form.addRow(strings.SETUP_DETECTED, self.detected_label)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.hide()

        self.start_button = QPushButton(strings.SETUP_START)
        self.start_button.clicked.connect(self.start_setup)
        self.range_button = QPushButton(strings.SETUP_MEASURE_RANGE)
        self.range_button.clicked.connect(self.start_range)
        self.test_button = QPushButton(strings.SETUP_TEST_INPUT)
        self.test_button.clicked.connect(self.test_input_requested)
        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.range_button)
        buttons.addWidget(self.test_button)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addSpacing(12)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress)
        layout.addLayout(buttons)
        layout.addStretch()

        devices.changed.connect(self._on_devices_changed)
        audio.frames_ready.connect(self._on_frames)
        audio.failed.connect(self._on_failed)

    # Page lifecycle

    def activate(self) -> None:
        self.active = True
        self.message = None
        self._fill_devices()
        self._start_capture()
        self._update()

    def deactivate(self) -> None:
        self.active = False
        self._cancel_measurements()
        self.audio.stop()

    # Devices

    @property
    def settings(self):
        return self.store.settings

    def _fill_devices(self) -> None:
        fill_device_combo(self.input_combo, self.devices.inputs(),
                          self.settings.input_device, self.settings.input_device_name)
        fill_device_combo(self.output_combo, self.devices.outputs(),
                          self.settings.output_device, self.settings.output_device_name)

    def selected_input(self) -> DeviceInfo | None:
        wanted = self.input_combo.currentData()
        return next((d for d in self.devices.inputs() if d.id == wanted), None)

    def _saved_calibration(self) -> Calibration | None:
        return self.settings.calibrations.get(self.input_combo.currentData())

    def _start_capture(self) -> None:
        device = self.selected_input()
        calibration = self._saved_calibration()
        self.level_meter.set_threshold(calibration.activity_threshold_db if calibration else None)
        if device is None:
            self.audio.stop()
            return
        if not (self.audio.running and self.audio.device_id == device.id):
            threshold = calibration.activity_threshold_db if calibration else config.UNCALIBRATED_THRESHOLD_DB
            self.audio.start(device, threshold)

    def _on_input_chosen(self, _index: int) -> None:
        device = self.selected_input()
        self._cancel_measurements()
        self.message = None
        if device is not None:
            self.settings.input_device, self.settings.input_device_name = device.id, device.name
            self.store.save()
        self.display.reset()
        self.audio.stop()
        self._start_capture()
        self._update()

    def _on_output_chosen(self, _index: int) -> None:
        wanted = self.output_combo.currentData()
        device = next((d for d in self.devices.outputs() if d.id == wanted), None)
        if device is not None:
            self.settings.output_device, self.settings.output_device_name = device.id, device.name
            self.store.save()

    def _on_devices_changed(self) -> None:
        if not self.active:
            return
        # Keep the current choice; never switch inputs or start listening automatically.
        current_input = self.input_combo.currentData()
        saved = self.settings.input_device
        name = self.settings.input_device_name
        if current_input is not None and current_input != saved:
            saved = current_input
            name = self.input_combo.currentText()
        fill_device_combo(self.input_combo, self.devices.inputs(), saved, name)
        fill_device_combo(self.output_combo, self.devices.outputs(),
                          self.settings.output_device, self.settings.output_device_name)
        self._update()

    def _on_failed(self, problem: str) -> None:
        if not self.active:
            return
        self._cancel_measurements()
        self.message = strings.SETUP_INPUT_LOST if problem == InputProblem.LOST else strings.SETUP_INPUT_FAILED
        self.level_meter.set_level(LevelMeter.MIN_DB)
        self.display.reset()
        self._update()

    # Measurements

    def start_setup(self) -> None:
        self.message = None
        self._cancel_measurements()
        self._start_capture()
        self.calibration = LevelCalibration(self.audio.hop_seconds)
        self._update()

    def start_range(self) -> None:
        self.message = None
        self._cancel_measurements()
        self._start_capture()
        self.range_low = RangeMeasurement(self.audio.hop_seconds)
        self._update()

    def measuring(self) -> bool:
        return self.calibration is not None or self.range_low is not None

    def _cancel_measurements(self) -> None:
        self.calibration = self.range_low = self.range_pause = self.range_high = None
        self.progress.hide()

    def _on_frames(self, frames: list) -> None:
        if not self.active:
            return
        for frame in frames:
            self.display.feed(frame)
            if self.calibration is not None:
                if self.calibration.feed(frame) is LevelStep.DONE:
                    self._finish_calibration()
            elif self.range_high is not None:
                if self.range_high.feed(frame):
                    self._finish_range()
            elif self.range_pause is not None:
                if self.range_pause.feed(frame):
                    self.range_high = RangeMeasurement(self.audio.hop_seconds)
            elif self.range_low is not None:
                if self.range_low.feed(frame):
                    if self.range_low.midi is None:
                        self._finish_range()
                    else:
                        self.range_pause = Pause(config.SETUP_RANGE_PAUSE_S)
        self.level_meter.set_level(frames[-1].level_db)
        self.detected_label.setText(describe_detected(self.display))
        self._update()

    def _finish_calibration(self) -> None:
        result = self.calibration.result
        self.calibration = None
        if result.problem is SetupProblem.NO_STEADY_WHISTLE:
            self.message = strings.SETUP_NO_STEADY_WHISTLE
        elif result.problem is SetupProblem.TOO_QUIET:
            self.message = strings.SETUP_TOO_QUIET.format(whistle=result.whistle_level_db, noise=result.noise_floor_db)
        else:
            device = self.selected_input()
            previous = self._saved_calibration()
            self.settings.calibrations[device.id] = Calibration(
                noise_floor_db=result.noise_floor_db,
                whistle_level_db=result.whistle_level_db,
                activity_threshold_db=result.activity_threshold_db,
                practice_low_midi=previous.practice_low_midi if previous else None,
                practice_high_midi=previous.practice_high_midi if previous else None,
            )
            self.settings.input_device, self.settings.input_device_name = device.id, device.name
            self.store.save()
            self.audio.set_activity_threshold(result.activity_threshold_db)
            self.level_meter.set_threshold(result.activity_threshold_db)
            self.message = strings.SETUP_DONE.format(
                noise=result.noise_floor_db, whistle=result.whistle_level_db,
                threshold=result.activity_threshold_db,
            )

    def _finish_range(self) -> None:
        low = self.range_low.midi if self.range_low else None
        high = self.range_high.midi if self.range_high else None
        self.range_low = self.range_pause = self.range_high = None
        calibration = self._saved_calibration()
        if low is None or high is None or high <= low or calibration is None:
            self.message = strings.SETUP_RANGE_FAILED
            return
        calibration.practice_low_midi, calibration.practice_high_midi = low, high
        self.store.save()
        self.message = strings.SETUP_RANGE_DONE.format(low=spell_midi(low).name, high=spell_midi(high).name)

    # Display

    def _status_text(self) -> str:
        if self.calibration is not None:
            if self.calibration.step is LevelStep.SILENCE:
                return strings.SETUP_STEP_SILENCE
            return strings.SETUP_STEP_WHISTLE
        if self.range_high is not None:
            return strings.SETUP_RANGE_HIGH
        if self.range_pause is not None:
            return strings.SETUP_RANGE_PAUSE.format(low=spell_midi(self.range_low.midi).name)
        if self.range_low is not None:
            return strings.SETUP_RANGE_LOW
        if self.message is not None:
            return self.message
        if self.input_combo.count() == 0:
            return strings.SETUP_NO_INPUTS
        if self.selected_input() is None:
            return strings.SETUP_INPUT_MISSING.format(
                name=self.settings.input_device_name or self.input_combo.currentData()
            )
        calibration = self._saved_calibration()
        if calibration is None:
            return strings.SETUP_INTRO
        text = strings.SETUP_ALREADY_DONE
        if calibration.practice_low_midi is not None and calibration.practice_high_midi is not None:
            text += " " + strings.SETUP_RANGE_SAVED.format(
                low=spell_midi(calibration.practice_low_midi).name,
                high=spell_midi(calibration.practice_high_midi).name,
            )
        return text

    def _update(self) -> None:
        self.status_label.setText(self._status_text())
        measuring = self.measuring()
        if measuring:
            measurement = self.calibration or self.range_high or self.range_pause or self.range_low
            self.progress.setValue(round(measurement.progress() * 1000))
        self.progress.setVisible(measuring)
        available = self.selected_input() is not None
        calibrated = self._saved_calibration() is not None
        self.start_button.setText(strings.SETUP_REPEAT if calibrated else strings.SETUP_START)
        self.start_button.setEnabled(available and not measuring)
        self.range_button.setEnabled(available and calibrated and not measuring)
        self.test_button.setEnabled(available and calibrated and not measuring)
        self.input_combo.setEnabled(not measuring)
