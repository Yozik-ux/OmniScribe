"""Тости: коротке підтвердження дії в нижньому правому куті.

Тактильні, як у Family.co: виїжджають знизу з пружинкою (OutBack), гаснуть
самі. Колір є лише в крапці статусу (успіх / застереження / помилка) —
решта лишається монохромною.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel

from gui.card import Card
from gui.theme import SPACE_MD, SPACE_SM, palette

_LIFETIME_MS = 3200
_SLIDE_MS = 320
_FADE_MS = 220
_MARGIN = 20

_DOT_ROLE = {
    "ok": "status_ok",
    "warn": "status_warn",
    "err": "status_err",
    "info": "text_dim",
}


class Toast(Card):
    def __init__(self, parent, text: str, kind: str = "ok", theme_name: str = "dark") -> None:
        super().__init__(parent)
        c = palette(theme_name)
        self.set_colors(c["surface_raised"], c["border"])

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_SM + 2, SPACE_MD, SPACE_SM + 2)
        layout.setSpacing(SPACE_SM)

        dot = QLabel()
        dot.setFixedSize(7, 7)
        dot.setStyleSheet(
            f"background-color: {c[_DOT_ROLE.get(kind, 'text_dim')]}; border-radius: 3px;"
        )
        layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)

        label = QLabel(text)
        label.setStyleSheet(f"color: {c['text']}; font-size: 10pt;")
        layout.addWidget(label)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self.adjustSize()
        self._slide = QPropertyAnimation(self, b"pos", self)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)

    def pop(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return

        end = QPoint(
            parent.width() - self.width() - _MARGIN,
            parent.height() - self.height() - _MARGIN - 24,
        )
        self.move(end + QPoint(0, 18))
        self.show()
        self.raise_()

        self._slide.stop()
        self._slide.setDuration(_SLIDE_MS)
        self._slide.setEasingCurve(QEasingCurve.Type.OutBack)
        self._slide.setStartValue(self.pos())
        self._slide.setEndValue(end)
        self._slide.start()

        self._fade.stop()
        self._fade.setDuration(_FADE_MS)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()

        QTimer.singleShot(_LIFETIME_MS, self._dismiss)

    def _dismiss(self) -> None:
        self._fade.stop()
        self._fade.setDuration(_FADE_MS)
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self.deleteLater)
        self._fade.start()
