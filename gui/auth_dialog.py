"""Вхід і реєстрація.

Одне вікно з двома режимами, а не дві схожі форми: різниця між ними —
лише поле імені, тож перемикач угорі дешевший і для коду, і для людини.

Помилка показується під полями одним рядком і ніколи не вигадує причину:
текст приходить з accounts.validate / sign_in, де він і формулюється.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from accounts import Account, AccountStore
from gui.theme import SPACE_LG, SPACE_SM, palette
from i18n import t


class AuthDialog(QDialog):
    """Після exec() == Accepted акаунт лежить у .account."""

    def __init__(self, store: AccountStore, theme_name: str, parent=None, signup: bool = False) -> None:
        super().__init__(parent)
        self.store = store
        self.account: Account | None = None
        self._signup = signup

        c = palette(theme_name)
        self.setWindowTitle(t("Акаунт OmniScribe"))
        self.setMinimumWidth(400)

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE_LG + 4, SPACE_LG, SPACE_LG + 4, SPACE_LG)
        root.setSpacing(SPACE_SM)

        self.title = QLabel()
        self.title.setStyleSheet(
            f"font-family: 'Playfair Display', serif; font-size: 19pt; "
            f"font-weight: 600; color: {c['heading']};"
        )
        root.addWidget(self.title)

        self.subtitle = QLabel()
        self.subtitle.setObjectName("MetaText")
        self.subtitle.setWordWrap(True)
        root.addWidget(self.subtitle)

        root.addSpacing(SPACE_SM)

        self.name = QLineEdit()
        self.name.setPlaceholderText(t("Ім'я та прізвище"))
        root.addWidget(self.name)

        self.email = QLineEdit()
        self.email.setPlaceholderText(t("Пошта"))
        root.addWidget(self.email)

        self.password = QLineEdit()
        self.password.setPlaceholderText(t("Пароль"))
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.returnPressed.connect(self._submit)
        root.addWidget(self.password)

        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setStyleSheet(f"color: {c['status_err']}; font-size: 9.5pt;")
        self.error.setVisible(False)
        root.addWidget(self.error)

        root.addSpacing(SPACE_SM)

        self.submit_btn = QPushButton()
        self.submit_btn.setObjectName("Primary")
        self.submit_btn.clicked.connect(self._submit)
        root.addWidget(self.submit_btn)

        switch_row = QHBoxLayout()
        switch_row.setSpacing(4)
        self.switch_hint = QLabel()
        self.switch_hint.setObjectName("MetaText")
        switch_row.addWidget(self.switch_hint)
        self.switch_btn = QPushButton()
        self.switch_btn.setObjectName("Link")
        self.switch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.switch_btn.clicked.connect(self._toggle_mode)
        switch_row.addWidget(self.switch_btn)
        switch_row.addStretch(1)
        root.addLayout(switch_row)

        note = QLabel(t("Акаунт зберігається лише на цьому комп'ютері — сервера поки немає."))
        note.setObjectName("MetaText")
        note.setWordWrap(True)
        root.addWidget(note)

        self._apply_mode()

    # ------------------------------------------------------------------ режим

    def _apply_mode(self) -> None:
        if self._signup:
            self.title.setText(t("Створити акаунт"))
            self.subtitle.setText(t("Потрібен для оплати плану й синхронізації між пристроями."))
            self.submit_btn.setText(t("Створити акаунт"))
            self.switch_hint.setText(t("Уже є акаунт?"))
            self.switch_btn.setText(t("Увійти"))
        else:
            self.title.setText(t("Вхід"))
            self.subtitle.setText(t("Конспекти лишаються на цьому комп'ютері в будь-якому разі."))
            self.submit_btn.setText(t("Увійти"))
            self.switch_hint.setText(t("Ще немає акаунта?"))
            self.switch_btn.setText(t("Зареєструватися"))

        self.name.setVisible(self._signup)
        self.error.setVisible(False)
        (self.name if self._signup else self.email).setFocus()

    def _toggle_mode(self) -> None:
        self._signup = not self._signup
        self._apply_mode()

    # -------------------------------------------------------------- submit

    def _submit(self) -> None:
        email = self.email.text()
        password = self.password.text()

        if self._signup:
            account, error = self.store.sign_up(email, self.name.text(), password)
        else:
            account, error = self.store.sign_in(email, password)

        if error:
            self.error.setText(error)
            self.error.setVisible(True)
            return

        self.account = account
        self.accept()
