"""Панель "Чує зараз": сирий текст Whisper одразу, до того як Claude оформить
його в конспект — показує, що AI справді чує лектора в реальному часі.

Оформлена як картка (референс — сучасні SaaS-дашборди: плаваюча картка на
нейтральному тлі, легка межа + м'яка тінь замість жорстких ліній) з
індикатором "наживо" біля заголовка.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout

from gui.card import Card
from gui.theme import SPACE_LG, SPACE_SM, palette
from i18n import t


class LivePanel(Card):
    closeRequested = Signal()

    def __init__(self, theme_name: str, parent=None) -> None:
        super().__init__(parent)
        self._theme_name = theme_name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_SM)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.dot = QLabel()
        self.dot.setObjectName("LiveDotIdle")
        self.dot.setFixedSize(8, 8)
        header.addWidget(self.dot)
        title = QLabel(t("Чує зараз"))
        title.setObjectName("SectionLabel")
        header.addWidget(title)
        header.addStretch(1)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("BottomIcon")
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setToolTip(t("Сховати панель  ·  Ctrl+Shift+L"))
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.closeRequested.emit)
        header.addWidget(self.close_btn)

        layout.addLayout(header)

        self.view = QTextEdit()
        self.view.setReadOnly(True)
        self.view.setFrameShape(QTextEdit.Shape.NoFrame)
        self.view.setPlaceholderText(t("Натисни «Записати» — і тут з'явиться те, що чує модель."))
        layout.addWidget(self.view, 1)

        self._apply_text_style()

    def _apply_text_style(self) -> None:
        c = palette(self._theme_name)
        self.set_colors(c["surface"], c["border_soft"])
        self.view.setStyleSheet(
            f"QTextEdit {{ font-size: 12pt; font-style: italic; color: {c['text_dim']}; "
            f"line-height: 150%; }}"
        )

    def set_theme(self, name: str) -> None:
        self._theme_name = name
        self._apply_text_style()

    def set_live(self, live: bool) -> None:
        self.dot.setObjectName("LiveDot" if live else "LiveDotIdle")
        self.dot.style().unpolish(self.dot)
        self.dot.style().polish(self.dot)

    def append_line(self, text: str) -> None:
        self.view.append(text.strip())
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

    def clear(self) -> None:
        self.view.clear()
