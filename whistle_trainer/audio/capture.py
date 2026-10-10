"""Microphone capture and analysis on a worker thread.

Audio is held only in memory and discarded after analysis.
"""

from __future__ import annotations

from enum import StrEnum

import numpy as np
from PySide6.QtCore import QIODevice, QObject, QThread, Signal, Slot
from PySide6.QtMultimedia import QAudioDevice, QAudioFormat, QAudioSource, QMediaDevices, QtAudio

from whistle_trainer import config
from whistle_trainer.audio.devices import DeviceInfo, device_id
from whistle_trainer.pitch.analyzer import Analyzer

# Requested capture buffer; PipeWire may choose a different size.
_BUFFER_S = 0.020


class InputProblem(StrEnum):
    START_FAILED = "start_failed"
    LOST = "lost"


_SAMPLE_TYPES = {
    QAudioFormat.SampleFormat.UInt8: (np.uint8, 128.0, 128.0),
    QAudioFormat.SampleFormat.Int16: (np.int16, 0.0, 32768.0),
    QAudioFormat.SampleFormat.Int32: (np.int32, 0.0, 2147483648.0),
    QAudioFormat.SampleFormat.Float: (np.float32, 0.0, 1.0),
}


def to_mono_float(data: bytes, sample_format: QAudioFormat.SampleFormat, channels: int) -> np.ndarray:
    """Interleaved samples of any supported format as mono floats from -1 to 1."""
    dtype, offset, scale = _SAMPLE_TYPES[sample_format]
    samples = np.frombuffer(data, dtype=dtype)
    samples = samples[: len(samples) - len(samples) % channels]
    mono = samples.reshape(-1, channels).astype(np.float64).mean(axis=1)
    return (mono - offset) / scale


class _CaptureWorker(QObject):
    frames_ready = Signal(list)
    started = Signal()
    stopped = Signal()
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._source: QAudioSource | None = None
        self._io: QIODevice | None = None
        self._analyzer: Analyzer | None = None
        self._format = QAudioFormat()

    @Slot(object, float)
    def start(self, device: QAudioDevice, threshold_db: float) -> None:
        self.stop()
        audio_format = QAudioFormat()
        audio_format.setSampleRate(config.SAMPLE_RATE)
        audio_format.setChannelCount(1)
        audio_format.setSampleFormat(QAudioFormat.SampleFormat.Float)
        if not device.isFormatSupported(audio_format):
            audio_format = device.preferredFormat()
        if audio_format.sampleFormat() not in _SAMPLE_TYPES:
            self.failed.emit(InputProblem.START_FAILED)
            return
        self._format = audio_format
        self._analyzer = Analyzer(audio_format.sampleRate(), threshold_db)
        self._source = QAudioSource(device, audio_format, self)
        self._source.setBufferSize(audio_format.bytesForDuration(round(_BUFFER_S * 1_000_000)))
        self._source.stateChanged.connect(self._on_state_changed)
        self._io = self._source.start()
        if self._io is None or self._source.error() != QtAudio.Error.NoError:
            self._release()
            self.failed.emit(InputProblem.START_FAILED)
            return
        self._io.readyRead.connect(self._read)
        self.started.emit()

    @Slot()
    def stop(self) -> None:
        if self._source is not None:
            self._release()
            self.stopped.emit()

    @Slot(float)
    def set_threshold(self, threshold_db: float) -> None:
        if self._analyzer is not None:
            self._analyzer.activity_threshold_db = threshold_db

    def _release(self) -> None:
        source, self._source, self._io = self._source, None, None
        if source is not None:
            source.stateChanged.disconnect(self._on_state_changed)
            source.stop()
            source.deleteLater()

    @Slot()
    def _read(self) -> None:
        if self._io is None or self._analyzer is None:
            return
        data = bytes(self._io.readAll().data())
        samples = to_mono_float(data, self._format.sampleFormat(), self._format.channelCount())
        frames = self._analyzer.feed(samples)
        if frames:
            self.frames_ready.emit(frames)

    @Slot(QtAudio.State)
    def _on_state_changed(self, state: QtAudio.State) -> None:
        if self._source is not None and state == QtAudio.State.StoppedState \
                and self._source.error() != QtAudio.Error.NoError:
            self._release()
            self.failed.emit(InputProblem.LOST)


class AudioInput(QObject):
    """Starts and stops capture; delivers analysis frames on the main thread.

    Frames are emitted in small batches as lists of AnalysisFrame. Frame times
    are seconds since capture started. Capture is never restarted automatically
    after a failure.
    """

    frames_ready = Signal(list)
    failed = Signal(str)  # InputProblem
    running_changed = Signal(bool)

    _start_requested = Signal(object, float)
    _stop_requested = Signal()
    _threshold_requested = Signal(float)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.running = False
        self.device_id: str | None = None
        self._thread = QThread()
        self._thread.setObjectName("audio-capture")
        self._worker = _CaptureWorker()
        self._worker.moveToThread(self._thread)
        self._start_requested.connect(self._worker.start)
        self._stop_requested.connect(self._worker.stop)
        self._threshold_requested.connect(self._worker.set_threshold)
        self._worker.frames_ready.connect(self.frames_ready)
        self._worker.started.connect(lambda: self._set_running(True))
        self._worker.stopped.connect(lambda: self._set_running(False))
        self._worker.failed.connect(self._on_failed)
        self._media = QMediaDevices(self)
        self._media.audioInputsChanged.connect(self._check_device_present)
        self._thread.start()

    @property
    def hop_seconds(self) -> float:
        return config.ANALYSIS_HOP_S

    def start(self, device: DeviceInfo, threshold_db: float) -> None:
        self.device_id = device.id
        self._start_requested.emit(device.device, threshold_db)

    def stop(self) -> None:
        self.device_id = None
        self._stop_requested.emit()

    def set_activity_threshold(self, threshold_db: float) -> None:
        self._threshold_requested.emit(threshold_db)

    def shutdown(self) -> None:
        self.stop()
        self._thread.quit()
        self._thread.wait()

    def _set_running(self, running: bool) -> None:
        if running != self.running:
            self.running = running
            self.running_changed.emit(running)

    def _on_failed(self, problem: str) -> None:
        self.device_id = None
        self._set_running(False)
        self.failed.emit(problem)

    def _check_device_present(self) -> None:
        if self.device_id is not None and all(device_id(d) != self.device_id for d in QMediaDevices.audioInputs()):
            self._stop_requested.emit()
            self._on_failed(InputProblem.LOST)
