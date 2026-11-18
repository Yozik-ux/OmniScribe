"""Фірмовий знак у шапці.

У спокої видно лише літеру "O" — вона і є логотип. При наведенні вона
трохи відходить ліворуч, звільняючи місце, і з-під неї виїжджає "mniScribe":
разом читається як одне слово. Рух має причину (знак розступається, щоб
впустити напис), тому це не декоративна анімація заради анімації.

Зсув анімується через Qt-властивість `nudge`: QPropertyAnimation не вміє
рухати віджет усередині layout напряму, але вміє крутити число, а сеттер
перекладає його у відступи.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

_DURATION_MS = 280
_LOGO_HEIGHT_PX = 52
_NUDGE_PX = 9  # наскільки знак відходить ліворуч на ховері


class BrandWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._nudge = 0.0

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(_NUDGE_PX, 0, 0, 0)
        self._layout.setSpacing(4)

        self.logo_label = QLabel()
        self.logo_label.setFixedHeight(_LOGO_HEIGHT_PX)
        self._layout.addWidget(self.logo_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self.rest_label = QLabel("mniScribe")
        self.rest_label.setObjectName("BrandRest")
        self.rest_label.setMaximumWidth(0)
        self._layout.addWidget(self.rest_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self._layout.addStretch(1)

        self._opacity = QGraphicsOpacityEffect(self.rest_label)
        self._opacity.setOpacity(0.0)
        self.rest_label.setGraphicsEffect(self._opacity)

        self._anim_width = _anim(self, self.rest_label, b"maximumWidth")
        self._anim_opacity = _anim(self, self._opacity, b"opacity")
        self._anim_nudge = _anim(self, self, b"nudge")

    # Відступ зліва: 0 — знак зсунутий ліворуч (ховер), _NUDGE_PX — спокій.
    def _get_nudge(self) -> float:
        return self._nudge

    def _set_nudge(self, value: float) -> None:
        self._nudge = value
        self._layout.setContentsMargins(int(value), 0, 0, 0)

    nudge = Property(float, _get_nudge, _set_nudge)

    def set_logo(self, path: str) -> None:
        pix = QPixmap(path).scaledToHeight(
            _LOGO_HEIGHT_PX, Qt.TransformationMode.SmoothTransformation
        )
        self.logo_label.setPixmap(pix)
        self.logo_label.setFixedWidth(pix.width())

    def enterEvent(self, event) -> None:  # noqa: N802 — Qt override
        self._animate(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 — Qt override
        self._animate(False)
        super().leaveEvent(event)

    def _animate(self, show: bool) -> None:
        _run(self._anim_nudge, self._nudge, 0.0 if show else float(_NUDGE_PX))
        _run(
            self._anim_width,
            self.rest_label.maximumWidth(),
            self.rest_label.sizeHint().width() + 2 if show else 0,
        )
        _run(self._anim_opacity, self._opacity.opacity(), 1.0 if show else 0.0)


def _anim(parent: QWidget, target, prop: bytes) -> QPropertyAnimation:
    anim = QPropertyAnimation(target, prop, parent)
    anim.setDuration(_DURATION_MS)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    return anim


def _run(anim: QPropertyAnimation, start, end) -> None:
    anim.stop()
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.start()
