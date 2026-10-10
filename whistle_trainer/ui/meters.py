"""Level meter, pitch meter, and hold indicator."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPolygonF
from PySide6.QtWidgets import QProgressBar, QSizePolicy, QWidget

from whistle_trainer import strings


def _highlight(widget: QWidget, alpha: int = 255) -> QColor:
    color = QColor(widget.palette().color(QPalette.ColorRole.Highlight))
    color.setAlpha(alpha)
    return color


class LevelMeter(QWidget):
    """Input level from -80 to 0 dBFS with a marker for the activity threshold."""

    MIN_DB = -80.0

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.level_db = self.MIN_DB
        self.threshold_db: float | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(300, self.fontMetrics().height() + 12)

    def set_level(self, level_db: float) -> None:
        self.level_db = level_db
        self.update()

    def set_threshold(self, threshold_db: float | None) -> None:
        self.threshold_db = threshold_db
        self.update()

    def _x(self, db: float, bar: QRectF) -> float:
        fraction = (min(max(db, self.MIN_DB), 0.0) - self.MIN_DB) / -self.MIN_DB
        return bar.left() + fraction * bar.width()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        label = strings.LEVEL_DB.format(level=self.level_db)
        label_width = self.fontMetrics().horizontalAdvance("−120 dB") + 8
        bar = QRectF(0.5, 3.5, self.width() - label_width - 1, self.height() - 7)

        painter.setPen(palette.color(QPalette.ColorRole.Mid))
        painter.setBrush(palette.color(QPalette.ColorRole.Base))
        painter.drawRoundedRect(bar, 3, 3)
        filled = QRectF(bar.left(), bar.top(), self._x(self.level_db, bar) - bar.left(), bar.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_highlight(self))
        painter.drawRoundedRect(filled, 3, 3)

        if self.threshold_db is not None:
            x = self._x(self.threshold_db, bar)
            painter.setPen(palette.color(QPalette.ColorRole.Text))
            painter.drawLine(QPointF(x, 0), QPointF(x, self.height()))

        painter.setPen(palette.color(QPalette.ColorRole.Text))
        text_rect = QRectF(bar.right() + 8, 0, label_width - 8, self.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, label)


class PitchMeter(QWidget):
    """Deviation from the target from -100 to +100 cents, with the tolerance band shaded.

    Pitches outside the scale are shown as an arrow at the matching edge.
    """

    RANGE_CENTS = 100.0

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.cents: float | None = None
        self.tolerance_cents = 40.0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(400, 56)

    def set_cents(self, cents: float | None) -> None:
        self.cents = cents
        self.update()

    def set_tolerance(self, tolerance_cents: float) -> None:
        self.tolerance_cents = tolerance_cents
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        margin = 14.0
        scale = QRectF(margin, 8, self.width() - 2 * margin, self.height() - 16)
        center_y = scale.center().y()

        def x_for(cents: float) -> float:
            clamped = min(max(cents, -self.RANGE_CENTS), self.RANGE_CENTS)
            return scale.center().x() + clamped / self.RANGE_CENTS * scale.width() / 2

        band = QRectF(QPointF(x_for(-self.tolerance_cents), scale.top()),
                      QPointF(x_for(self.tolerance_cents), scale.bottom()))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_highlight(self, 60))
        painter.drawRoundedRect(band, 4, 4)

        painter.setPen(palette.color(QPalette.ColorRole.Mid))
        painter.drawLine(QPointF(scale.left(), center_y), QPointF(scale.right(), center_y))
        for cents in (-100, -50, 0, 50, 100):
            tick = 10 if cents == 0 else 5
            painter.drawLine(QPointF(x_for(cents), center_y - tick), QPointF(x_for(cents), center_y + tick))

        if self.cents is None:
            return
        x = x_for(self.cents)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(palette.color(QPalette.ColorRole.Text))
        if abs(self.cents) > self.RANGE_CENTS:
            direction = 1 if self.cents > 0 else -1
            tip = x + direction * (margin - 2)
            painter.drawPolygon(QPolygonF([
                QPointF(tip, center_y),
                QPointF(x - direction * 2, center_y - 9),
                QPointF(x - direction * 2, center_y + 9),
            ]))
        else:
            painter.drawPolygon(QPolygonF([
                QPointF(x, center_y + 2),
                QPointF(x - 7, scale.top() - 4),
                QPointF(x + 7, scale.top() - 4),
            ]))
            painter.drawRect(QRectF(x - 1.5, center_y, 3, scale.bottom() - center_y))


class HoldIndicator(QProgressBar):
    """Hold progress with the credited time as text."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setRange(0, 1000)
        self.setTextVisible(True)
        self.set_progress(0.0, 0.0, 1.0)

    def set_progress(self, fraction: float, seconds: float, required: float,
                     label: str = strings.HOLD_LABEL) -> None:
        self.setValue(round(min(max(fraction, 0.0), 1.0) * 1000))
        self.setFormat(label.format(seconds=seconds, required=required))
