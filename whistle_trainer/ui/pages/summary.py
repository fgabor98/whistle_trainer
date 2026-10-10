"""Summary page shown when a song or section is finished."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from whistle_trainer import strings
from whistle_trainer.config import Mode
from whistle_trainer.music.model import Song
from whistle_trainer.ui.pages.library import format_length

HARDEST_SHOWN = 3


@dataclass
class SessionSummary:
    song: Song  # as practiced, transposed
    mode: Mode
    start: int  # first event of the practiced range
    end: int  # one past the last event
    active_seconds: float
    retries: dict[int, int] = field(default_factory=dict)
    song_completed: bool = False  # every event is now completed in this mode

    @property
    def whole_song(self) -> bool:
        return self.start == 0 and self.end == len(self.song.events)

    def measure_number(self, index: int) -> str:
        return self.song.measures[self.song.events[index].parts[0].measure_index].number

    def range_text(self) -> str:
        if self.whole_song:
            return strings.SUMMARY_WHOLE_SONG
        first, last = self.measure_number(self.start), self.measure_number(self.end - 1)
        if self.end == len(self.song.events):
            return strings.SUMMARY_FROM_MEASURE.format(start=first)
        if first == last:
            return strings.SUMMARY_MEASURE.format(start=first)
        return strings.SUMMARY_MEASURES.format(start=first, end=last)

    def hardest(self) -> list[tuple[int, int]]:
        """(event index, retries) of the events with the most retries, most first."""
        ranked = sorted((item for item in self.retries.items() if item[1] > 0), key=lambda item: (-item[1], item[0]))
        return ranked[:HARDEST_SHOWN]

    def hardest_measure(self) -> tuple[int, int] | None:
        """(measure index, retries) of the measure with the most retries in total."""
        per_measure: dict[int, int] = {}
        for index, count in self.retries.items():
            measure = self.song.events[index].parts[0].measure_index
            per_measure[measure] = per_measure.get(measure, 0) + count
        if not per_measure or max(per_measure.values()) == 0:
            return None
        return max(per_measure.items(), key=lambda item: (item[1], -item[0]))

    def measure_range(self, measure_index: int) -> tuple[int, int]:
        """Events that start in a measure, as (start, end exclusive)."""
        indexes = [e.index for e in self.song.events if e.parts[0].measure_index == measure_index]
        return indexes[0], indexes[-1] + 1


class SummaryPage(QWidget):
    repeat_requested = Signal()
    restart_requested = Signal()
    library_requested = Signal()
    section_requested = Signal(int, int)  # start, end exclusive

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.summary: SessionSummary | None = None
        self._section: tuple[int, int] | None = None

        self.heading = QLabel()
        font = self.heading.font()
        font.setPointSizeF(font.pointSizeF() * 2)
        font.setBold(True)
        self.heading.setFont(font)
        self.heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.completed_label = QLabel()
        self.completed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mode_value = QLabel()
        self.range_value = QLabel()
        self.time_value = QLabel()
        self.retries_value = QLabel()
        form = QFormLayout()
        form.addRow(strings.SUMMARY_MODE, self.mode_value)
        form.addRow(strings.SUMMARY_PRACTICED, self.range_value)
        form.addRow(strings.SUMMARY_TIME, self.time_value)
        form.addRow(strings.SUMMARY_RETRIES, self.retries_value)
        self.hardest_label = QLabel()
        self.hardest_label.setWordWrap(True)

        self.section_button = QPushButton()
        self.section_button.clicked.connect(lambda: self.section_requested.emit(*self._section))
        self.repeat_button = QPushButton(strings.SUMMARY_REPEAT)
        self.repeat_button.clicked.connect(self.repeat_requested)
        self.restart_button = QPushButton(strings.SUMMARY_RESTART)
        self.restart_button.clicked.connect(self.restart_requested)
        self.library_button = QPushButton(strings.SUMMARY_LIBRARY)
        self.library_button.clicked.connect(self.library_requested)
        buttons = QHBoxLayout()
        buttons.addStretch()
        for button in (self.section_button, self.repeat_button, self.restart_button, self.library_button):
            buttons.addWidget(button)
        buttons.addStretch()

        center = QVBoxLayout()
        center.addStretch()
        center.addWidget(self.heading)
        center.addWidget(self.completed_label)
        center.addSpacing(16)
        center.addLayout(form)
        center.addSpacing(8)
        center.addWidget(self.hardest_label)
        center.addSpacing(16)
        center.addLayout(buttons)
        center.addStretch()
        layout = QHBoxLayout(self)
        layout.addStretch()
        layout.addLayout(center)
        layout.addStretch()

    def title(self) -> str:
        return strings.PAGE_SUMMARY.format(title=self.summary.song.title) if self.summary else ""

    def show_summary(self, summary: SessionSummary) -> None:
        self.summary = summary
        self.heading.setText(strings.SUMMARY_SONG_COMPLETE if summary.whole_song else strings.SUMMARY_SECTION_COMPLETE)
        mode_name = strings.MODE_NAMES[summary.mode]
        self.completed_label.setText(strings.SUMMARY_SONG_DONE_IN_MODE.format(mode=mode_name.lower())
                                     if summary.song_completed else "")
        self.completed_label.setVisible(summary.song_completed)
        self.mode_value.setText(mode_name)
        self.range_value.setText(summary.range_text())
        self.time_value.setText(format_length(summary.active_seconds))
        self.retries_value.setText(str(sum(summary.retries.values())))

        hardest = summary.hardest()
        if hardest:
            lines = [strings.SUMMARY_HARDEST_ITEM.format(
                note=summary.song.events[i].pitch.name if summary.song.events[i].pitch else strings.PRACTICE_TARGET_REST,
                measure=summary.measure_number(i), count=count) for i, count in hardest]
            self.hardest_label.setText(strings.SUMMARY_HARDEST + "\n• " + "\n• ".join(lines))
        else:
            self.hardest_label.setText(strings.SUMMARY_NO_RETRIES)

        measure = summary.hardest_measure()
        self._section = summary.measure_range(measure[0]) if measure else None
        self.section_button.setVisible(self._section is not None)
        if measure:
            number = summary.song.measures[measure[0]].number
            self.section_button.setText(strings.SUMMARY_PRACTICE_MEASURE.format(measure=number))
