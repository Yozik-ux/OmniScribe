"""Перемикач для бінарних налаштувань.

Чому не QCheckBox: у монохромній темі залитий квадратик без галочки читається
як «біла пляма», а не як «увімкнено» — стан неоднозначний. Перемикач показує
стан позицією повзунка, а не кольором, тож лишається зрозумілим і в чорно-
білому, і для людини з дальтонізмом.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from gui.theme import palette

_W, _H, _PAD = 40, 22, 3


class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, theme_name: str, checked: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._c = palette(theme_name)
        self._checked = checked
        self._offset = 1.0 if checked else 0.0

        self.setFixedSize(_W, _H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # положення повзунка 0..1 — анімується, не зберігається
    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def isChecked(self) -> bool:  # noqa: N802 — тримаємо API як у QCheckBox
        return self._checked

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        if checked == self._checked:
            return
        self._checked = checked
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def mousePressEvent(self, event) -> None:  # noqa: N802 — Qt override
        self.setChecked(not self._checked)
        self.toggled.emit(self._checked)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt override
        c = self._c
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        track = QColor(c["accent"] if self._checked else c["surface_alt"])
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0, 0, _W, _H), _H / 2, _H / 2)

        if not self._checked:
            painter.setPen(QColor(c["border"]))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(0.5, 0.5, _W - 1, _H - 1), _H / 2, _H / 2)
            painter.setPen(Qt.PenStyle.NoPen)

        knob = _H - _PAD * 2
        x = _PAD + self._offset * (_W - knob - _PAD * 2)
        painter.setBrush(QColor(c["accent_text"] if self._checked else c["text_dim"]))
        painter.drawEllipse(QRectF(x, _PAD, knob, knob))
        painter.end()
