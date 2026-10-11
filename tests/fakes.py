"""Stand-ins for audio devices and capture in UI tests."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from whistle_trainer import config
from whistle_trainer.audio.devices import DeviceInfo

MIC = DeviceInfo("usb-mic", "USB Microphone", is_default=False)
BUILTIN = DeviceInfo("builtin-mic", "Built-in Microphone", is_default=True)
SPEAKERS = DeviceInfo("speakers", "Speakers", is_default=True)


class FakeDevices(QObject):
    changed = Signal()

    def __init__(self, inputs=(BUILTIN, MIC), outputs=(SPEAKERS,)):
        super().__init__()
        self._inputs = list(inputs)
        self._outputs = list(outputs)

    def inputs(self):
        return list(self._inputs)

    def outputs(self):
        return list(self._outputs)

    def set_inputs(self, inputs) -> None:
        self._inputs = list(inputs)
        self.changed.emit()


class FakeAudio(QObject):
    frames_ready = Signal(list)
    failed = Signal(str)
    running_changed = Signal(bool)

    hop_seconds = config.ANALYSIS_HOP_S

    def __init__(self):
        super().__init__()
        self.running = False
        self.device_id = None
        self.threshold_db = None
        self.starts: list[str] = []
        self.capture_offset: float | None = 0.0  # capture time equals the fake clock

    def start(self, device: DeviceInfo, threshold_db: float) -> None:
        self.device_id = device.id
        self.threshold_db = threshold_db
        self.starts.append(device.id)
        self._set_running(True)

    def stop(self) -> None:
        self.device_id = None
        self._set_running(False)

    def set_activity_threshold(self, threshold_db: float) -> None:
        self.threshold_db = threshold_db

    def fail(self, problem: str) -> None:
        self.device_id = None
        self._set_running(False)
        self.failed.emit(problem)

    def send(self, frames, batch: int = 5) -> None:
        for i in range(0, len(frames), batch):
            self.frames_ready.emit(frames[i:i + batch])

    def _set_running(self, running: bool) -> None:
        if running != self.running:
            self.running = running
            self.running_changed.emit(running)


class FakePlayback:
    rate = config.SAMPLE_RATE

    def __init__(self):
        self.running = False
        self.device = None
        self.scheduled: list[tuple[float, object]] = []  # (time, samples)

    def start(self, device) -> bool:
        self.running, self.device = True, device
        return True

    def stop(self) -> None:
        self.running = False
        self.scheduled.clear()

    def clear(self) -> None:
        self.scheduled.clear()

    def schedule(self, samples, at=None) -> None:
        self.scheduled.append((at, samples))


class FakeClock:
    def __init__(self, now: float = 0.0):
        self.now = now

    def __call__(self) -> float:
        return self.now
