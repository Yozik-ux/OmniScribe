"""Панель форматування конспекту.

Набір — як у текстовому процесорі (стиль абзацу, накреслення, маркери,
списки, відступи, таблиця, пошук), подача — як у Linear: 26-піксельні
прозорі кнопки, що проявляються лише на ховері, згруповані волосяними
роздільниками. Колір є тільки у квадратиках маркерів: вони показують
результат дії, а не прикрашають панель.

Заголовки ставляться через QTextBlockFormat.setHeadingLevel, а не просто
більшим шрифтом — тоді QTextDocument.toMarkdown() (ним іде експорт ручних
правок у local_notes) бачить справжній рівень і віддає "## ", а не жирний
рядок.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QKeySequence,
    QTextCharFormat,
    QTextCursor,
    QTextListFormat,
    QTextTableFormat,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QMenu,
    QTextEdit,
    QToolButton,
    QWidget,
)

from gui.theme import markers, palette
from i18n import t

_BTN = QSize(28, 26)

# (ключ стилю, підпис у списку, рівень заголовка)
_BLOCK_STYLES = (
    ("body", "Текст", 0),
    ("h1", "Заголовок 1", 1),
    ("h2", "Заголовок 2", 2),
    ("h3", "Заголовок 3", 3),
)
_HEADING_PT = {1: 19.0, 2: 15.0, 3: 12.5}
_BODY_PT = 10.5


class EditorToolbar(QWidget):
    """Керує переданим QTextEdit. Сигнал `findRequested` просить панель
    пошуку — вона живе в NotesPanel, бо то не форматування."""

    findRequested = Signal()

    def __init__(self, view: QTextEdit, theme_name: str, parent=None) -> None:
        super().__init__(parent)
        self.view = view
        self._theme_name = theme_name
        self._syncing = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._add(layout, "↶", t("Скасувати"), "Ctrl+Z", self.view.undo)
        self._add(layout, "↷", t("Повторити"), "Ctrl+Shift+Z", self.view.redo)
        layout.addWidget(_divider())

        self.block_style = QComboBox()
        self.block_style.setObjectName("BlockStyle")
        for key, label, _ in _BLOCK_STYLES:
            self.block_style.addItem(t(label), key)
        self.block_style.setToolTip(t("Стиль абзацу  ·  Ctrl+Alt+1…3"))
        self.block_style.activated.connect(self._apply_block_style)
        layout.addWidget(self.block_style)
        layout.addWidget(_divider())

        self.bold_btn = self._add(
            layout, "B", t("Жирний"), "Ctrl+B", self._toggle_bold, checkable=True, weight=QFont.Weight.Bold
        )
        self.italic_btn = self._add(
            layout, "I", t("Курсив"), "Ctrl+I", self._toggle_italic, checkable=True, italic=True
        )
        self.underline_btn = self._add(
            layout, "U", t("Підкреслений"), "Ctrl+U", self._toggle_underline, checkable=True, underline=True
        )
        self.strike_btn = self._add(
            layout, "S", t("Закреслений"), "Ctrl+Shift+S", self._toggle_strike, checkable=True, strike=True
        )
        layout.addWidget(_divider())

        # Смужка під "A" забарвлена в активний маркер — кнопка одночасно
        # підказує дію і показує, який колір ляже наступним (як у Docs).
        self.marker_btn = self._add(layout, "A", t("Колір тексту і маркер"), "Ctrl+Shift+H", None)
        self.marker_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.marker_btn.setMenu(self._build_color_menu())
        self._last_marker = "yellow"
        self._paint_marker_button()
        layout.addWidget(_divider())

        self._add(layout, "•", t("Маркований список"), "Ctrl+Shift+8", lambda: self._list(QTextListFormat.Style.ListDisc))
        self._add(layout, "1.", t("Нумерований список"), "Ctrl+Shift+7", lambda: self._list(QTextListFormat.Style.ListDecimal))
        self._add(layout, "⇤", t("Зменшити відступ"), "Ctrl+[", lambda: self._indent(-1))
        self._add(layout, "⇥", t("Збільшити відступ"), "Ctrl+]", lambda: self._indent(1))
        layout.addWidget(_divider())

        self._add(layout, "⊞", t("Вставити таблицю 3×2"), "", self._insert_table)
        self._add(layout, "—", t("Горизонтальна лінія"), "", self._insert_rule)
        layout.addWidget(_divider())

        self._add(layout, "⌫", t("Прибрати форматування"), "Ctrl+\\", self._clear_format)
        self._add(layout, "⌕", t("Знайти в конспекті"), "Ctrl+F", self.findRequested.emit)

        layout.addStretch(1)

        self.view.currentCharFormatChanged.connect(self._sync_from_format)
        self.view.cursorPositionChanged.connect(self._sync_block_style)
        self._install_shortcuts()

    # ------------------------------------------------------------- побудова

    def _add(
        self,
        layout: QHBoxLayout,
        glyph: str,
        tip: str,
        shortcut: str,
        handler,
        *,
        checkable: bool = False,
        weight: QFont.Weight = QFont.Weight.Medium,
        italic: bool = False,
        underline: bool = False,
        strike: bool = False,
    ) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("Tool")
        btn.setText(glyph)
        btn.setFixedSize(_BTN)
        btn.setCheckable(checkable)
        btn.setToolTip(f"{tip}  ·  {shortcut}" if shortcut else tip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        font = QFont(btn.font())
        font.setWeight(weight)
        font.setItalic(italic)
        font.setUnderline(underline)
        font.setStrikeOut(strike)
        btn.setFont(font)

        if handler is not None:
            btn.clicked.connect(handler)
        layout.addWidget(btn)
        return btn

    def _build_color_menu(self) -> QMenu:
        menu = QMenu(self)
        c = palette(self._theme_name)

        head = QAction(t("Маркер"), menu)
        head.setEnabled(False)
        menu.addAction(head)
        for key, spec in markers(self._theme_name).items():
            action = QAction(f"  {t(spec['name'])}", menu)
            action.setData(("marker", key))
            action.triggered.connect(lambda _=False, k=key: self._apply_marker(k))
            menu.addAction(action)

        clear = QAction("  " + t("Без маркера"), menu)
        clear.triggered.connect(lambda: self._apply_marker(None))
        menu.addAction(clear)

        menu.addSeparator()
        text_head = QAction(t("Колір тексту"), menu)
        text_head.setEnabled(False)
        menu.addAction(text_head)
        for label, color in (
            ("  " + t("Звичайний"), c["text"]),
            ("  " + t("Приглушений"), c["text_dim"]),
            ("  " + t("Контрастний"), c["heading"]),
        ):
            action = QAction(label, menu)
            action.triggered.connect(lambda _=False, col=color: self._apply_text_color(col))
            menu.addAction(action)

        return menu

    def _install_shortcuts(self) -> None:
        pairs = [
            ("Ctrl+B", self._toggle_bold),
            ("Ctrl+I", self._toggle_italic),
            ("Ctrl+U", self._toggle_underline),
            ("Ctrl+Shift+S", self._toggle_strike),
            ("Ctrl+Shift+H", lambda: self._apply_marker("yellow")),
            ("Ctrl+Shift+G", lambda: self._apply_marker("green")),
            ("Ctrl+Shift+8", lambda: self._list(QTextListFormat.Style.ListDisc)),
            ("Ctrl+Shift+7", lambda: self._list(QTextListFormat.Style.ListDecimal)),
            ("Ctrl+]", lambda: self._indent(1)),
            ("Ctrl+[", lambda: self._indent(-1)),
            ("Ctrl+\\", self._clear_format),
            ("Ctrl+Alt+0", lambda: self._set_heading(0)),
            ("Ctrl+Alt+1", lambda: self._set_heading(1)),
            ("Ctrl+Alt+2", lambda: self._set_heading(2)),
            ("Ctrl+Alt+3", lambda: self._set_heading(3)),
        ]
        for keys, handler in pairs:
            action = QAction(self.view)
            action.setShortcut(QKeySequence(keys))
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(handler)
            self.view.addAction(action)

    # ----------------------------------------------------------- накреслення

    def _merge(self, fmt: QTextCharFormat) -> None:
        cursor = self.view.textCursor()
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        self.view.mergeCurrentCharFormat(fmt)
        self.view.setFocus()

    def _toggle_bold(self) -> None:
        fmt = QTextCharFormat()
        on = self.view.fontWeight() <= QFont.Weight.Normal
        fmt.setFontWeight(QFont.Weight.Bold if on else QFont.Weight.Normal)
        self._merge(fmt)

    def _toggle_italic(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self.view.fontItalic())
        self._merge(fmt)

    def _toggle_underline(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not self.view.fontUnderline())
        self._merge(fmt)

    def _toggle_strike(self) -> None:
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(not self.view.currentCharFormat().fontStrikeOut())
        self._merge(fmt)

    def _apply_marker(self, key: str | None) -> None:
        fmt = QTextCharFormat()
        if key is None:
            fmt.setBackground(Qt.GlobalColor.transparent)
            fmt.setForeground(QColor(palette(self._theme_name)["text"]))
        else:
            spec = markers(self._theme_name)[key]
            fmt.setBackground(QColor(spec["bg"]))
            fmt.setForeground(QColor(spec["fg"]))
            self._last_marker = key
            self._paint_marker_button()
        self._merge(fmt)

    def _paint_marker_button(self) -> None:
        spec = markers(self._theme_name)[self._last_marker]
        self.marker_btn.setStyleSheet(
            f"QToolButton#Tool {{ border-bottom: 3px solid {spec['bg']}; "
            f"border-bottom-left-radius: 0; border-bottom-right-radius: 0; }}"
        )

    def _apply_text_color(self, color: str) -> None:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        self._merge(fmt)

    def _clear_format(self) -> None:
        cursor = self.view.textCursor()
        plain = QTextCharFormat()
        plain.setForeground(QColor(palette(self._theme_name)["text"]))
        plain.setFontPointSize(_BODY_PT)
        if cursor.hasSelection():
            cursor.setCharFormat(plain)
        self.view.setCurrentCharFormat(plain)
        self._set_heading(0)

    # -------------------------------------------------------------- абзаци

    def _apply_block_style(self, index: int) -> None:
        self._set_heading(_BLOCK_STYLES[index][2])

    def _set_heading(self, level: int) -> None:
        cursor = self.view.textCursor()
        cursor.beginEditBlock()

        block_fmt = cursor.blockFormat()
        block_fmt.setHeadingLevel(level)
        block_fmt.setTopMargin(10 if level else 2)
        block_fmt.setBottomMargin(4 if level else 2)
        cursor.setBlockFormat(block_fmt)

        char_fmt = QTextCharFormat()
        if level:
            char_fmt.setFontFamilies(["Playfair Display", "serif"])
            char_fmt.setFontPointSize(_HEADING_PT[level])
            char_fmt.setFontWeight(QFont.Weight.DemiBold)
            char_fmt.setForeground(QColor(palette(self._theme_name)["heading"]))
        else:
            char_fmt.setFontFamilies(["Inter", "sans-serif"])
            char_fmt.setFontPointSize(_BODY_PT)
            char_fmt.setFontWeight(QFont.Weight.Normal)
            char_fmt.setForeground(QColor(palette(self._theme_name)["text"]))

        select = QTextCursor(cursor)
        select.select(QTextCursor.SelectionType.BlockUnderCursor)
        select.mergeCharFormat(char_fmt)
        cursor.endEditBlock()

        self.view.setCurrentCharFormat(char_fmt)
        self._sync_block_style()
        self.view.setFocus()

    def _list(self, style: QTextListFormat.Style) -> None:
        cursor = self.view.textCursor()
        cursor.beginEditBlock()
        current = cursor.currentList()
        if current and current.format().style() == style:
            # Повторний клік по активному списку — знімаємо список.
            block_fmt = cursor.blockFormat()
            block_fmt.setObjectIndex(-1)
            block_fmt.setIndent(0)
            cursor.setBlockFormat(block_fmt)
        else:
            list_fmt = QTextListFormat()
            list_fmt.setStyle(style)
            list_fmt.setIndent(1)
            cursor.createList(list_fmt)
        cursor.endEditBlock()
        self.view.setFocus()

    def _indent(self, delta: int) -> None:
        cursor = self.view.textCursor()
        cursor.beginEditBlock()
        current = cursor.currentList()
        if current:
            fmt = current.format()
            fmt.setIndent(max(1, fmt.indent() + delta))
            cursor.createList(fmt)
        else:
            block_fmt = cursor.blockFormat()
            block_fmt.setIndent(max(0, block_fmt.indent() + delta))
            cursor.setBlockFormat(block_fmt)
        cursor.endEditBlock()
        self.view.setFocus()

    # ------------------------------------------------------------- вставка

    def _insert_at_cursor(self, insert) -> None:
        """Вставка ніколи не має з'їдати виділення: QTextCursor.insert*
        замінює виділений текст, тому спершу знімаємо його. І працюємо з
        курсором віджета, а не з копією — інакше курсор лишиться поза
        вставленим, і користувач друкуватиме не туди."""
        cursor = self.view.textCursor()
        if cursor.hasSelection():
            cursor.setPosition(cursor.selectionEnd())
        insert(cursor)
        self.view.setTextCursor(cursor)
        self.view.setFocus()

    def _insert_table(self) -> None:
        c = palette(self._theme_name)
        fmt = QTextTableFormat()
        fmt.setCellPadding(5)
        fmt.setCellSpacing(0)
        fmt.setBorder(1)
        fmt.setBorderBrush(QColor(c["border"]))
        fmt.setBorderStyle(QTextTableFormat.BorderStyle.BorderStyle_Solid)
        self._insert_at_cursor(lambda cursor: cursor.insertTable(3, 2, fmt))

    def _insert_rule(self) -> None:
        self._insert_at_cursor(lambda cursor: cursor.insertHtml("<hr>"))

    # --------------------------------------------------------- синхронізація

    def _sync_from_format(self, fmt: QTextCharFormat) -> None:
        if self._syncing:
            return
        self._syncing = True
        self.bold_btn.setChecked(fmt.fontWeight() > QFont.Weight.Normal)
        self.italic_btn.setChecked(fmt.fontItalic())
        self.underline_btn.setChecked(fmt.fontUnderline())
        self.strike_btn.setChecked(fmt.fontStrikeOut())
        self._syncing = False

    def _sync_block_style(self) -> None:
        level = self.view.textCursor().blockFormat().headingLevel()
        index = next((i for i, (_, _, lvl) in enumerate(_BLOCK_STYLES) if lvl == level), 0)
        self.block_style.setCurrentIndex(index)

    def set_theme(self, name: str) -> None:
        self._theme_name = name
        self.marker_btn.setMenu(self._build_color_menu())
        self._paint_marker_button()


def _divider() -> QFrame:
    line = QFrame()
    line.setObjectName("ToolDivider")
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFixedHeight(18)
    return line
