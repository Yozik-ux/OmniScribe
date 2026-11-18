"""Панель оформленого конспекту: рендерить mdlite.Block у HTML (ті самі
заголовки/списки/виділення, що раніше йшли в Google Docs) напряму в QTextEdit.

Редагований — студент може дописати чи виправити щось прямо тут. Ручні
правки (textChanged, коли це не наш власний setHtml/append) автозберігаються
з невеликою затримкою через сигнал `edited`; MainWindow слухає його й пише
в LocalNotesStore.save_notes_override.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from export import block_to_html
from gui.card import Card
from gui.editor_toolbar import EditorToolbar
from gui.theme import SPACE_LG, SPACE_SM, html_colors, palette
from mdlite import Block
from i18n import t

_AUTOSAVE_DELAY_MS = 900


class NotesPanel(Card):
    edited = Signal()

    def __init__(self, theme_name: str, parent=None) -> None:
        super().__init__(parent)
        self._theme_name = theme_name
        self._blocks: list[Block] = []
        self._programmatic = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_SM)

        # Шапка картки: назва лекції, під нею рядок метаданих, праворуч —
        # статус. Єдине місце картки, де з'являється колір (стан запису).
        header = QHBoxLayout()
        header.setSpacing(SPACE_SM)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title_label = QLabel(t("Конспект"))
        self.title_label.setObjectName("CardTitle")
        titles.addWidget(self.title_label)
        self.meta_label = QLabel("")
        self.meta_label.setObjectName("MetaText")
        titles.addWidget(self.meta_label)
        header.addLayout(titles, 1)

        self.state_pill = QLabel(t("ЧЕРНЕТКА"))
        self.state_pill.setObjectName("Pill")
        header.addWidget(self.state_pill, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        self.view = QTextEdit()
        self.view.setFrameShape(QTextEdit.Shape.NoFrame)
        self.view.setPlaceholderText(
            t("Конспект з'явиться тут, коли почнеться запис — або просто почни писати сам.")
        )
        self.view.setTabChangesFocus(False)

        rule = QFrame()
        rule.setObjectName("Divider")
        rule.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(rule)

        self.toolbar = EditorToolbar(self.view, theme_name)
        self.toolbar.findRequested.connect(self.open_find)
        layout.addWidget(self.toolbar)

        layout.addWidget(self._build_find_bar())
        layout.addWidget(self.view, 1)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(_AUTOSAVE_DELAY_MS)
        self._save_timer.timeout.connect(self.edited.emit)
        self.view.textChanged.connect(self._on_text_changed)

        self._apply_card_colors()

    def _build_find_bar(self) -> QFrame:
        """Рядок пошуку з'являється лише на Ctrl+F — у спокої його нема,
        щоб не з'їдати висоту конспекту."""
        bar = QFrame()
        bar.setVisible(False)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACE_SM)

        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText(t("Знайти в конспекті"))
        self.find_input.returnPressed.connect(self._find_next)
        self.find_input.textChanged.connect(lambda: self._set_find_status(""))
        row.addWidget(self.find_input, 1)

        self.find_status = QLabel("")
        self.find_status.setObjectName("MetaText")
        row.addWidget(self.find_status)

        next_btn = QPushButton(t("Далі"))
        next_btn.setObjectName("Ghost")
        next_btn.clicked.connect(self._find_next)
        row.addWidget(next_btn)

        close_btn = QPushButton(t("Закрити"))
        close_btn.setObjectName("Ghost")
        close_btn.clicked.connect(self.close_find)
        row.addWidget(close_btn)

        self._find_bar = bar
        return bar

    def open_find(self) -> None:
        self._find_bar.setVisible(True)
        self.find_input.setFocus()
        self.find_input.selectAll()

    def close_find(self) -> None:
        self._find_bar.setVisible(False)
        self.view.setFocus()

    def _find_next(self) -> None:
        needle = self.find_input.text()
        if not needle:
            return
        if self.view.find(needle):
            self._set_find_status("")
            return
        # Не знайшли далі — шукаємо з початку документа.
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.view.setTextCursor(cursor)
        self._set_find_status("" if self.view.find(needle) else t("Нічого не знайшлося"))

    def _set_find_status(self, text: str) -> None:
        self.find_status.setText(text)

    def _on_text_changed(self) -> None:
        if not self._programmatic:
            self._save_timer.start()

    def _apply_card_colors(self) -> None:
        c = palette(self._theme_name)
        self.set_colors(c["surface"], c["border_soft"])

    def set_theme(self, name: str) -> None:
        self._theme_name = name
        self._apply_card_colors()
        self.toolbar.set_theme(name)
        self._rerender()

    def append_blocks(self, blocks: list[Block]) -> None:
        self._blocks.extend(blocks)
        colors = html_colors(self._theme_name)
        self._programmatic = True
        for b in blocks:
            self.view.append(block_to_html(b, colors))
        self._programmatic = False
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

    def load_blocks(self, blocks: list[Block], session_title: str = "") -> None:
        """Повністю замінити вміст (перегляд іншої сесії зі списку)."""
        self._blocks = list(blocks)
        if session_title:
            self.title_label.setText(session_title)
        self._rerender()

    def set_raw_html(self, html: str, session_title: str = "") -> None:
        """Показати HTML як є — сесія, яку студент уже редагував вручну,
        не повинна перебудовуватись з blocks (це стерло б його правки)."""
        self._blocks = []
        if session_title:
            self.title_label.setText(session_title)
        self._programmatic = True
        self.view.setHtml(html)
        self._programmatic = False

    def set_header(self, title: str, meta: str, state: str = "idle") -> None:
        """state: 'live' (йде запис) | 'ok' (є конспект) | 'idle' (порожньо)."""
        self.title_label.setText(title)
        self.meta_label.setText(meta)

        label, obj = {
            "live": (t("ЗАПИС"), "PillLive"),
            "ok": (t("ЗБЕРЕЖЕНО"), "PillOk"),
        }.get(state, (t("ЧЕРНЕТКА"), "Pill"))
        self.state_pill.setText(label)
        self.state_pill.setObjectName(obj)
        self.state_pill.style().unpolish(self.state_pill)
        self.state_pill.style().polish(self.state_pill)

    def current_html(self) -> str:
        return self.view.toHtml()

    def clear(self) -> None:
        self._blocks = []
        self._programmatic = True
        self.view.clear()
        self._programmatic = False

    def current_blocks(self) -> list[Block]:
        return list(self._blocks)

    def _rerender(self) -> None:
        colors = html_colors(self._theme_name)
        html = "".join(block_to_html(b, colors) for b in self._blocks)
        self._programmatic = True
        self.view.setHtml(html)
        self._programmatic = False
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())
