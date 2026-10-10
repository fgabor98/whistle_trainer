"""Sound output: one QAudioSink that mixes scheduled sounds.

The sink is fed continuously (silence when nothing is scheduled) from a short
timer, so the output position advances steadily. A sound scheduled for a
monotonic time is placed at the output sample that will be heard then:
sample n plays at now + (n - processed) / rate, where processed is the number
of samples the sink has consumed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QIODevice, QObject, Qt, QTimer
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices

from whistle_trainer import config
from whistle_trainer.audio.devices import DeviceInfo

_BUFFER_S = 0.040
_PUMP_INTERVAL_MS = 5

_OUTPUT_TYPES = {
    QAudioFormat.SampleFormat.Float: (np.float32, 1.0),
    QAudioFormat.SampleFormat.Int16: (np.int16, 32767.0),
    QAudioFormat.SampleFormat.Int32: (np.int32, 2147483647.0),
}


@dataclass
class ScheduledSound:
    start: int  # output sample index
    samples: np.ndarray

    @property
    def end(self) -> int:
        return self.start + len(self.samples)


def mix(sounds: list[ScheduledSound], start: int, count: int) -> np.ndarray:
    """The output samples [start, start + count) with every overlapping sound added."""
    out = np.zeros(count, dtype=np.float32)
    for sound in sounds:
        begin, end = max(sound.start, start), min(sound.end, start + count)
        if begin < end:
            out[begin - start:end - start] += sound.samples[begin - sound.start:end - sound.start]
    return np.clip(out, -1.0, 1.0)


def output_index(at: float, now: float, processed: int, written: int, rate: int) -> int:
    """Output sample index heard at monotonic time `at`; never earlier than what is not yet written."""
    return max(written, processed + round((at - now) * rate))


def encode(samples: np.ndarray, sample_format: QAudioFormat.SampleFormat, channels: int) -> bytes:
    dtype, scale = _OUTPUT_TYPES[sample_format]
    data = samples if dtype is np.float32 else np.round(samples * scale)
    return np.repeat(data.astype(dtype), channels).tobytes()


class Playback(QObject):
    def __init__(self, parent: QObject | None = None, clock=time.monotonic):
        super().__init__(parent)
        self.clock = clock
        self.rate = config.SAMPLE_RATE
        self._sink: QAudioSink | None = None
        self._io: QIODevice | None = None
        self._format = QAudioFormat()
        self._written = 0
        self._sounds: list[ScheduledSound] = []
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(_PUMP_INTERVAL_MS)
        self._timer.timeout.connect(self._pump)

    @property
    def running(self) -> bool:
        return self._sink is not None

    def start(self, device: DeviceInfo | None) -> bool:
        """Open the output device (the system default if None). Returns False if it cannot be opened."""
        if self.running:
            return True
        qt_device = device.device if device is not None and device.device is not None \
            else QMediaDevices.defaultAudioOutput()
        if qt_device.isNull():
            return False
        audio_format = QAudioFormat()
        audio_format.setSampleRate(config.SAMPLE_RATE)
        audio_format.setChannelCount(1)
        audio_format.setSampleFormat(QAudioFormat.SampleFormat.Float)
        if not qt_device.isFormatSupported(audio_format):
            audio_format = qt_device.preferredFormat()
        if audio_format.sampleFormat() not in _OUTPUT_TYPES:
            return False
        self._format = audio_format
        self.rate = audio_format.sampleRate()
        self._sink = QAudioSink(qt_device, audio_format, self)
        self._sink.setBufferSize(audio_format.bytesForDuration(round(_BUFFER_S * 1_000_000)))
        self._io = self._sink.start()
        if self._io is None:
            self.stop()
            return False
        self._written = 0
        self._pump()
        self._timer.start()
        return True

    def stop(self) -> None:
        self._timer.stop()
        self._sounds.clear()
        if self._sink is not None:
            self._sink.stop()
            self._sink.deleteLater()
        self._sink = self._io = None

    def clear(self) -> None:
        """Remove every scheduled sound; whatever is already in the device buffer still plays."""
        self._sounds.clear()

    def schedule(self, samples: np.ndarray, at: float | None = None) -> None:
        """Play samples (mono, at self.rate) at a monotonic time, or as soon as possible."""
        if self._sink is None:
            return
        processed = round(self._sink.processedUSecs() * self.rate / 1_000_000)
        now = self.clock()
        start = output_index(now if at is None else at, now, processed, self._written, self.rate)
        self._sounds.append(ScheduledSound(start, np.asarray(samples, dtype=np.float32)))

    def _pump(self) -> None:
        if self._sink is None or self._io is None:
            return
        bytes_per_frame = self._format.bytesPerFrame()
        count = self._sink.bytesFree() // bytes_per_frame
        if count <= 0:
            return
        chunk = mix(self._sounds, self._written, count)
        self._io.write(encode(chunk, self._format.sampleFormat(), self._format.channelCount()))
        self._written += count
        self._sounds = [s for s in self._sounds if s.end > self._written]
