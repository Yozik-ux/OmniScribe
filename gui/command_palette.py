"""Командна палітра (Ctrl+K) — усе керування застосунком з клавіатури.

Зроблено за зразком Raycast: один рядок пошуку, нечіткий збіг по назві й
ключових словах, стрілки/Enter для вибору, підказка шорткату праворуч.
Кожна дія тут — та сама, що й у кнопках інтерфейсу, тому палітра не живе
окремим життям і не розходиться з рештою UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.theme import SPACE_SM, palette
from i18n import t

_ROW_HEIGHT = 56
_MAX_ROWS = 7


@dataclass
class Command:
    title: str
    subtitle: str
    run: Callable[[], None]
    shortcut: str = ""
    keywords: tuple[str, ...] = field(default_factory=tuple)
    enabled: bool = True

    def matches(self, query: str) -> bool:
        if not query:
            return True
        haystack = " ".join((self.title, self.subtitle, *self.keywords)).lower()
        return _subsequence(query.lower(), haystack)


def _subsequence(needle: str, haystack: str) -> bool:
    """Нечіткий збіг: усі символи запиту йдуть по порядку ("нвс" -> "нова сесія")."""
    it = iter(haystack)
    return all(ch in it for ch in needle if not ch.isspace())


class CommandPalette(QDialog):
    def __init__(self, commands: list[Command], theme_name: str, parent=None) -> None:
        super().__init__(parent)
        self._commands = [c for c in commands if c.enabled]
        self._theme_name = theme_name

        self.setObjectName("Palette")
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setFixedWidth(620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, SPACE_SM)
        layout.setSpacing(0)

        self.input = QLineEdit()
        self.input.setObjectName("PaletteInput")
        self.input.setPlaceholderText(t("Що зробити?"))
        self.input.textChanged.connect(self._refilter)
        self.input.installEventFilter(self)
        layout.addWidget(self.input)

        self.list = QListWidget()
        self.list.setObjectName("PaletteList")
        self.list.setFrameShape(QListWidget.Shape.NoFrame)
        self.list.itemActivated.connect(self._run_item)
        self.list.itemClicked.connect(self._run_item)
        layout.addWidget(self.list)

        self._refilter("")

    # ------------------------------------------------------------- клавіатура

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 — Qt override
        if obj is self.input and event.type() == event.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.list.currentRow()
                delta = 1 if key == Qt.Key.Key_Down else -1
                self.list.setCurrentRow(
                    max(0, min(self.list.count() - 1, row + delta))
                )
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self.list.currentItem()
                if item:
                    self._run_item(item)
                return True
        return super().eventFilter(obj, event)

    # ---------------------------------------------------------------- список

    def _refilter(self, query: str) -> None:
        self.list.clear()
        c = palette(self._theme_name)
        for command in self._commands:
            if not command.matches(query):
                continue
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, command)
            item.setSizeHint(QSize(0, _ROW_HEIGHT))
            self.list.addItem(item)
            self.list.setItemWidget(item, self._row_widget(command, c))

        if self.list.count():
            self.list.setCurrentRow(0)
        self._resize_to_rows()

    def _row_widget(self, command: Command, c: dict) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = QLabel(command.title)
        title.setStyleSheet(f"color: {c['heading']}; font-size: 10.5pt; font-weight: 500;")
        texts.addWidget(title)
        if command.subtitle:
            subtitle = QLabel(command.subtitle)
            subtitle.setStyleSheet(f"color: {c['text_faint']}; font-size: 9pt;")
            texts.addWidget(subtitle)
        layout.addLayout(texts, 1)

        if command.shortcut:
            kbd = QLabel(command.shortcut)
            kbd.setObjectName("Kbd")
            layout.addWidget(kbd, 0, Qt.AlignmentFlag.AlignVCenter)

        return row

    def _resize_to_rows(self) -> None:
        rows = min(self.list.count(), _MAX_ROWS)
        self.list.setFixedHeight(max(_ROW_HEIGHT, rows * (_ROW_HEIGHT + 4) + 8))
        self.adjustSize()

    def _run_item(self, item: QListWidgetItem) -> None:
        command: Command = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        command.run()

    def open_centered(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            geo = parent.geometry()
            self.move(
                geo.x() + (geo.width() - self.width()) // 2,
                geo.y() + max(80, geo.height() // 6),
            )
        self.input.clear()
        self.input.setFocus()
        self.show()
