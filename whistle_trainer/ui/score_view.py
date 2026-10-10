"""Score display: one scrolling treble staff drawn with the Bravura music font."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from whistle_trainer.music.model import Song
from whistle_trainer.ui.score_layout import PartLayout, ScoreLayout, layout_song

FONT_PATH = Path(__file__).resolve().parent.parent / "resources" / "fonts" / "Bravura.otf"
_font_family: str | None = None

# SMuFL code points.
G_CLEF = ""
NOTEHEADS = {"whole": "", "half": ""}
NOTEHEAD_BLACK = ""
RESTS = {None: "", "whole": "", "half": "", "quarter": "", "eighth": "",
         "16th": "", "32nd": ""}
FLAGS_UP = {"eighth": "", "16th": "", "32nd": ""}
FLAGS_DOWN = {"eighth": "", "16th": "", "32nd": ""}
ACCIDENTALS = {-2: "", -1: "", 0: "", 1: "", 2: ""}
AUGMENTATION_DOT = ""
TIME_SIG_DIGITS = ""

STEM_LENGTH = 3.5
STEM_THICKNESS = 0.12
STAFF_LINE_THICKNESS = 0.13
LEDGER_EXTENSION = 0.4
CHECK_MARK = "✓"


def music_font_family() -> str:
    global _font_family
    if _font_family is None:
        font_id = QFontDatabase.addApplicationFont(str(FONT_PATH))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        _font_family = families[0] if families else "Bravura"
    return _font_family


class ScoreView(QWidget):
    """Shows the song with the current event highlighted and completed events checked.

    The view scrolls so that the current event stays about a third from the left.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.song: Song | None = None
        self.layout_data: ScoreLayout | None = None
        self.current: int | None = None
        self.completed: set[int] = set()
        self.show_note_names = True
        self.scroll = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(300)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._set_scroll)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(160)

    def sizeHint(self) -> QSize:
        return QSize(800, 240)

    # State

    def set_song(self, song: Song, show_note_names: bool = True) -> None:
        self.song = song
        self.layout_data = layout_song(song)
        self.show_note_names = show_note_names
        self.completed = set()
        self.current = None
        self.scroll = 0.0
        self.update()

    def set_completed(self, completed: set[int]) -> None:
        self.completed = set(completed)
        self.update()

    def set_current(self, index: int | None, animate: bool = True) -> None:
        self.current = index
        target = self._scroll_target()
        self._animation.stop()
        if animate and self.isVisible():
            self._animation.setStartValue(float(self.scroll))
            self._animation.setEndValue(float(target))
            self._animation.start()
        else:
            self._set_scroll(target)
        self.update()

    def _set_scroll(self, value: float) -> None:
        self.scroll = float(value)
        self.update()

    def _scroll_target(self) -> float:
        if self.layout_data is None or self.current is None or self.current >= len(self.layout_data.events):
            return self.scroll
        center = self.x_for(self.layout_data.events[self.current].center) + self.scroll
        return max(0.0, center - self.width() / 3)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._set_scroll(self._scroll_target())

    # Geometry

    @property
    def space(self) -> float:
        """Pixels per staff space."""
        return min(max(self.height() / 17.0, 7.0), 16.0)

    def _bottom_line_y(self) -> float:
        # Room for notes up to three ledger lines above the staff, and names below it;
        # the 17 spaces of content are centered vertically.
        return self.space * 9.0 + max(0.0, (self.height() - 17 * self.space) / 2)

    def y_for(self, position: float) -> float:
        return self._bottom_line_y() - position * self.space / 2

    def x_for(self, x: float) -> float:
        return self.space * (x + 1.0) - self.scroll

    # Painting

    def paintEvent(self, _event) -> None:
        if self.layout_data is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        text = palette.color(QPalette.ColorRole.Text)
        done = QColor(text)
        done.setAlpha(120)
        highlight = palette.color(QPalette.ColorRole.Highlight)
        sp = self.space
        music = QFont(music_font_family())
        music.setPixelSize(max(1, round(4 * sp)))
        painter.setFont(music)

        layout = self.layout_data
        if self.current is not None and self.current < len(layout.events):
            event = layout.events[self.current]
            band = QColor(highlight)
            band.setAlpha(60)
            painter.fillRect(QRectF(self.x_for(event.left), self.y_for(14), (event.right - event.left) * sp,
                                    self.y_for(-6) - self.y_for(14)), band)

        painter.setPen(QPen(text, STAFF_LINE_THICKNESS * sp))
        right = min(self.width(), self.x_for(layout.width))
        for line in range(5):
            y = self.y_for(line * 2)
            painter.drawLine(QPointF(max(0.0, self.x_for(0)), y), QPointF(right, y))
        for x in layout.barlines[:-1]:
            painter.drawLine(QPointF(self.x_for(x), self.y_for(0)), QPointF(self.x_for(x), self.y_for(8)))
        self._draw_final_barline(painter, text, layout.barlines[-1])

        painter.setPen(text)
        painter.drawText(QPointF(self.x_for(0.8), self.y_for(2)), G_CLEF)
        for i, (alter, position) in enumerate(layout.key_signature):
            painter.drawText(QPointF(self.x_for(layout.key_x + i * 1.1), self.y_for(position)), ACCIDENTALS[alter])
        beats, beat_type = layout.time_signature
        for value, position in ((beats, 6), (beat_type, 2)):
            digits = "".join(TIME_SIG_DIGITS[int(d)] for d in str(value))
            painter.drawText(QPointF(self.x_for(layout.time_x), self.y_for(position)), digits)

        visible = (self.scroll / sp - 6, (self.scroll + self.width()) / sp + 2)
        for part in layout.parts:
            if not visible[0] <= part.x <= visible[1]:
                continue
            index = part.event_index
            color = highlight if index == self.current else done if index in self.completed else text
            self._draw_part(painter, part, color)

        label_font = QFont(self.font())
        label_font.setPixelSize(max(1, round(sp * 1.3)))
        for index, event in enumerate(layout.events):
            if not visible[0] <= event.left <= visible[1]:
                continue
            if self.show_note_names and event.label:
                label_font.setBold(index == self.current)
                painter.setFont(label_font)
                painter.setPen(highlight if index == self.current else done if index in self.completed else text)
                rect = QRectF(self.x_for(event.left) - sp, self.y_for(-6), (event.right - event.left + 2) * sp, 2 * sp)
                painter.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, event.label)
            if index in self.completed:
                label_font.setBold(False)
                painter.setFont(label_font)
                painter.setPen(done)
                rect = QRectF(self.x_for(event.left), self.y_for(16), (event.right - event.left) * sp, 2 * sp)
                painter.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, CHECK_MARK)

    def _draw_final_barline(self, painter: QPainter, color: QColor, x: float) -> None:
        sp = self.space
        top, bottom = self.y_for(8), self.y_for(0)
        painter.setPen(QPen(color, 0.16 * sp))
        painter.drawLine(QPointF(self.x_for(x - 0.9), top), QPointF(self.x_for(x - 0.9), bottom))
        painter.fillRect(QRectF(self.x_for(x - 0.5), top, 0.5 * sp, bottom - top), color)

    def _draw_part(self, painter: QPainter, part: PartLayout, color: QColor) -> None:
        sp = self.space
        painter.setPen(color)
        x = self.x_for(part.x)
        if part.position is None:
            position = 6 if part.note_type in (None, "whole") else 4
            painter.drawText(QPointF(x, self.y_for(position)), RESTS[part.note_type])
            return

        position = part.position
        y = self.y_for(position)
        painter.setPen(QPen(color, STAFF_LINE_THICKNESS * sp))
        ledger_left, ledger_right = x - LEDGER_EXTENSION * sp, x + (part.head_width + LEDGER_EXTENSION) * sp
        for ledger in range(-2, position - 1, -2):
            painter.drawLine(QPointF(ledger_left, self.y_for(ledger)), QPointF(ledger_right, self.y_for(ledger)))
        for ledger in range(10, position + 1, 2):
            painter.drawLine(QPointF(ledger_left, self.y_for(ledger)), QPointF(ledger_right, self.y_for(ledger)))

        painter.setPen(color)
        if part.accidental is not None:
            painter.drawText(QPointF(x - 1.3 * sp, y), ACCIDENTALS[part.accidental])
        painter.drawText(QPointF(x, y), NOTEHEADS.get(part.note_type, NOTEHEAD_BLACK))
        if part.dots:
            dot_y = self.y_for(position + 1) if position % 2 == 0 else y
            for dot in range(part.dots):
                painter.drawText(QPointF(x + (part.head_width + 0.4 + dot * 0.6) * sp, dot_y), AUGMENTATION_DOT)

        if part.note_type != "whole":
            if part.stem_up:
                stem_x = x + (part.head_width - STEM_THICKNESS / 2) * sp
                start, end = y - 0.168 * sp, y - STEM_LENGTH * sp
            else:
                stem_x = x + STEM_THICKNESS / 2 * sp
                start, end = y + 0.168 * sp, y + STEM_LENGTH * sp
            painter.setPen(QPen(color, STEM_THICKNESS * sp))
            painter.drawLine(QPointF(stem_x, start), QPointF(stem_x, end))
            flags = FLAGS_UP if part.stem_up else FLAGS_DOWN
            if part.note_type in flags:
                painter.setPen(color)
                painter.drawText(QPointF(stem_x - STEM_THICKNESS / 2 * sp, end), flags[part.note_type])

        if part.tied_to_next:
            self._draw_tie(painter, part, color)

    def _draw_tie(self, painter: QPainter, part: PartLayout, color: QColor) -> None:
        layout = self.layout_data
        parts = layout.events[part.event_index].parts
        following = parts[parts.index(part) + 1]
        sp = self.space
        direction = 1 if part.stem_up else -1  # away from the stem
        y = self.y_for(part.position) + direction * 0.7 * sp
        start = QPointF(self.x_for(part.x + part.head_width) + 0.1 * sp, y)
        end = QPointF(self.x_for(following.x) - 0.1 * sp, y)
        height = direction * min(1.0, 0.25 + (end.x() - start.x()) / sp * 0.05) * sp
        path = QPainterPath(start)
        path.cubicTo(QPointF(start.x() + (end.x() - start.x()) * 0.25, y + height),
                     QPointF(start.x() + (end.x() - start.x()) * 0.75, y + height), end)
        path.cubicTo(QPointF(start.x() + (end.x() - start.x()) * 0.75, y + height * 0.7),
                     QPointF(start.x() + (end.x() - start.x()) * 0.25, y + height * 0.7), start)
        painter.setPen(QPen(color, 0.1 * sp))
        painter.setBrush(color)
        painter.drawPath(path)
        painter.setBrush(Qt.BrushStyle.NoBrush)
