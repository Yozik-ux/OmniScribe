"""Список сесій зі щільністю, як у Linear: назва + рядок метаданих під нею,
активний елемент позначений вузькою вертикальною смужкою зліва.

Малюється делегатом, а не QSS, бо QSS не вміє два різні стилі тексту в
одному рядку списку. Редагування назви (подвійний клік) лишається
стандартним — делегат не чіпає createEditor.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from gui.theme import palette

META_ROLE = Qt.ItemDataRole.UserRole + 1

_ROW_HEIGHT = 54
_PAD_X = 14
_RAIL_W = 3


class SessionDelegate(QStyledItemDelegate):
    def __init__(self, theme_name: str, parent=None) -> None:
        super().__init__(parent)
        self._c = palette(theme_name)

    def set_theme(self, theme_name: str) -> None:
        self._c = palette(theme_name)

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 — Qt override
        return QSize(option.rect.width(), _ROW_HEIGHT)

    def paint(self, painter: QPainter, option, index) -> None:
        c = self._c
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect: QRect = option.rect.adjusted(2, 1, -2, -1)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if selected:
            painter.fillRect(rect, QColor(c["accent_soft"]))
            painter.fillRect(QRect(rect.x(), rect.y(), _RAIL_W, rect.height()), QColor(c["rail"]))
        elif hovered:
            painter.fillRect(rect, QColor(c["surface_raised"]))

        title = index.data(Qt.ItemDataRole.DisplayRole) or ""
        meta = index.data(META_ROLE) or ""

        title_font = QFont(option.font)
        title_font.setPointSizeF(10.5)
        title_font.setWeight(QFont.Weight.Medium if selected else QFont.Weight.Normal)
        painter.setFont(title_font)
        painter.setPen(QColor(c["heading"] if selected else c["text"]))
        painter.drawText(
            QRect(rect.x() + _PAD_X, rect.y() + 8, rect.width() - _PAD_X * 2, 20),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            title_font_elided(painter, title, rect.width() - _PAD_X * 2),
        )

        meta_font = QFont(option.font)
        meta_font.setPointSizeF(8.5)
        painter.setFont(meta_font)
        painter.setPen(QColor(c["text_faint"]))
        painter.drawText(
            QRect(rect.x() + _PAD_X, rect.y() + 28, rect.width() - _PAD_X * 2, 18),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            meta,
        )
        painter.restore()


def title_font_elided(painter: QPainter, text: str, width: int) -> str:
    metrics = painter.fontMetrics()
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, width)
