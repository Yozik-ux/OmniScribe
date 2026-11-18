"""Картка з заокругленими кутами, намальована вручну в paintEvent.

QSS-фон на підкласах QWidget (навіть з WA_StyledBackground) у деяких
Qt-білдах заливає лише верхню смугу картки замість усієї площі — тому
замість боротьби зі стилями малюємо фон/межу самі. Надійно працює
незалежно від платформи.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

RADIUS = 18


class Card(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._bg = QColor("#19191c")
        self._border = QColor("#333338")

    def set_colors(self, bg: str, border: str) -> None:
        self._bg = QColor(bg)
        self._border = QColor(border)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 — Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(self._border, 1))
        painter.setBrush(self._bg)
        painter.drawRoundedRect(rect, RADIUS, RADIUS)
        painter.end()
        super().paintEvent(event)
