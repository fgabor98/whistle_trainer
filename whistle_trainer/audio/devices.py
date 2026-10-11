"""Audio input and output devices, as provided by PipeWire/PulseAudio through Qt."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal
from PySide6.QtMultimedia import QAudioDevice, QMediaDevices


@dataclass(frozen=True)
class DeviceInfo:
    id: str  # stable across sessions (the PipeWire/PulseAudio node name)
    name: str
    is_default: bool
    device: QAudioDevice | None = None


def device_id(device: QAudioDevice) -> str:
    return bytes(device.id().data()).decode("utf-8", errors="replace")


def _info(device: QAudioDevice) -> DeviceInfo:
    return DeviceInfo(device_id(device), device.description(), device.isDefault(), device)


class AudioDevices(QObject):
    """Current devices; emits changed when one is connected or disconnected."""

    changed = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._media = QMediaDevices(self)
        self._media.audioInputsChanged.connect(self.changed)
        self._media.audioOutputsChanged.connect(self.changed)

    def inputs(self) -> list[DeviceInfo]:
        return [_info(d) for d in QMediaDevices.audioInputs()]

    def outputs(self) -> list[DeviceInfo]:
        return [_info(d) for d in QMediaDevices.audioOutputs()]
