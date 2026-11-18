"""Плани користування + демо-оплата.

ДЕМО, і це написано просто у вікні: жоден платіж не проводиться, реквізити
картки нікуди не йдуть і ніде не зберігаються — поле приймає лише тестовий
номер 4242 4242 4242 4242. Це заготовка екрана підписки, щоб було видно, як
воно виглядатиме, коли білінг з'явиться по-справжньому.

Композиція за зразком Stripe/Vercel: три картки в ряд, однакова сітка,
поточний план обведено, ціна — найбільший елемент картки.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from billing import PLANS, Plan
from gui.card import Card
from gui.theme import SPACE_LG, SPACE_MD, SPACE_SM, palette
from i18n import t

_TEST_CARD = "4242424242424242"


class PlansDialog(QDialog):
    """Повертає id обраного плану через .chosen_plan (None — нічого не змінили)."""

    def __init__(self, current_plan_id: str, theme_name: str, parent=None) -> None:
        super().__init__(parent)
        self._theme = theme_name
        self._current = current_plan_id
        self.chosen_plan: str | None = None

        c = palette(theme_name)
        self.setWindowTitle(t("Плани OmniScribe"))
        self.setMinimumWidth(920)

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE_LG + 8, SPACE_LG + 4, SPACE_LG + 8, SPACE_LG)
        root.setSpacing(SPACE_SM)

        title = QLabel(t("Плани"))
        title.setStyleSheet(
            f"font-family: 'Playfair Display', serif; font-size: 24pt; "
            f"font-weight: 600; color: {c['heading']};"
        )
        root.addWidget(title)

        subtitle = QLabel(
            t(
                "Квота рахується за хвилинами запису. Зміна плану діє одразу, "
                "конспекти лишаються локальними в будь-якому плані."
            )
        )
        subtitle.setObjectName("MetaText")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        root.addSpacing(SPACE_MD)

        cards = QHBoxLayout()
        cards.setSpacing(SPACE_MD)
        for plan in PLANS.values():
            cards.addWidget(self._plan_card(plan, c), 1)
        root.addLayout(cards, 1)

        root.addSpacing(SPACE_SM)
        note = QLabel(t("Демо-режим: оплата не проводиться, дані картки нікуди не надсилаються."))
        note.setObjectName("MetaText")
        root.addWidget(note)

    def _plan_card(self, plan: Plan, c: dict) -> QWidget:
        is_current = plan.id == self._current
        card = Card()
        card.set_colors(c["surface"], c["accent"] if is_current else c["border_soft"])

        layout = QVBoxLayout(card)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_SM)

        header = QHBoxLayout()
        name = QLabel(plan.name)
        name.setStyleSheet(f"color: {c['heading']}; font-size: 13pt; font-weight: 600;")
        header.addWidget(name)
        header.addStretch(1)
        if is_current:
            pill = QLabel(t("ПОТОЧНИЙ"))
            pill.setObjectName("PillOk")
            header.addWidget(pill)
        layout.addLayout(header)

        tagline = QLabel(plan.tagline)
        tagline.setObjectName("MetaText")
        layout.addWidget(tagline)

        layout.addSpacing(SPACE_SM)
        price_row = QHBoxLayout()
        price_row.setSpacing(6)
        # Число — Playfair, валюта й період — Inter: у Playfair немає гліфа ₴,
        # і підміна шрифту посеред рядка ламає кегль.
        amount = QLabel(str(plan.price_uah))
        amount.setStyleSheet(
            f"font-family: 'Playfair Display', serif; font-size: 32pt; "
            f"font-weight: 600; color: {c['heading']}; background: transparent;"
        )
        price_row.addWidget(amount)
        per = QLabel("₴ " + t("/ міс"))
        per.setStyleSheet(
            f"color: {c['text_dim']}; font-size: 10pt; background: transparent;"
        )
        price_row.addWidget(per, 0, Qt.AlignmentFlag.AlignBottom)
        price_row.addStretch(1)
        layout.addLayout(price_row)

        limit = QLabel(plan.limit_label)
        limit.setObjectName("MetaText")
        layout.addWidget(limit)

        divider = QFrame()
        divider.setObjectName("Divider")
        layout.addWidget(divider)

        for feature in plan.features:
            layout.addWidget(_feature_row(feature, True, c))
        for feature in plan.locked:
            layout.addWidget(_feature_row(feature, False, c))

        layout.addStretch(1)

        button = QPushButton(t("Поточний план") if is_current else f'{t("Обрати")} {plan.name}')
        button.setEnabled(not is_current)
        if not is_current:
            button.setObjectName("Primary")
        button.clicked.connect(lambda _=False, p=plan: self._choose(p))
        layout.addWidget(button)

        return card

    def _choose(self, plan: Plan) -> None:
        if plan.price_uah == 0:
            self.chosen_plan = plan.id
            self.accept()
            return

        checkout = CheckoutDialog(plan, self._theme, self)
        if checkout.exec() == QDialog.DialogCode.Accepted:
            self.chosen_plan = plan.id
            self.accept()


def _feature_row(text: str, available: bool, c: dict) -> QWidget:
    row = QWidget()
    # Без цього рядок бере суцільний фон сторінки і виглядає як сіра плашка
    # поверх картки (QWidget успадковує QSS-правило фону вікна).
    row.setStyleSheet("background: transparent;")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 1, 0, 1)
    layout.setSpacing(8)

    mark = QLabel("✓" if available else "✕")
    mark.setFixedWidth(12)
    mark.setStyleSheet(
        f"color: {c['status_ok'] if available else c['text_faint']}; font-size: 9.5pt;"
    )
    layout.addWidget(mark)

    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(
        f"color: {c['text'] if available else c['text_faint']}; font-size: 9.5pt;"
    )
    layout.addWidget(label, 1)
    return row


class CheckoutDialog(QDialog):
    """Демо-форма оплати. Нічого не надсилає й не зберігає."""

    def __init__(self, plan: Plan, theme_name: str, parent=None) -> None:
        super().__init__(parent)
        c = palette(theme_name)
        self.plan = plan
        self.setWindowTitle(f"Підписка {plan.name} — демо")
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        root.setSpacing(SPACE_SM)

        banner = QLabel(t("ДЕМО — платіж не проводиться"))
        banner.setObjectName("PillWarn")
        root.addWidget(banner, 0, Qt.AlignmentFlag.AlignLeft)

        title = QLabel(f"{plan.name} · {plan.price_label} / міс")
        title.setStyleSheet(f"color: {c['heading']}; font-size: 15pt; font-weight: 600;")
        root.addWidget(title)

        sub = QLabel(f'{plan.limit_label} · {t("модель")} {plan.model}')
        sub.setObjectName("MetaText")
        root.addWidget(sub)

        root.addSpacing(SPACE_SM)

        form = QGridLayout()
        form.setHorizontalSpacing(SPACE_SM)
        form.setVerticalSpacing(SPACE_SM)

        self.card = QLineEdit()
        self.card.setPlaceholderText("4242 4242 4242 4242")
        self.card.setMaxLength(19)
        self.card.textChanged.connect(self._format_card)
        form.addWidget(_field_label(t("Номер тестової картки"), c), 0, 0, 1, 2)
        form.addWidget(self.card, 1, 0, 1, 2)

        self.expiry = QLineEdit()
        self.expiry.setPlaceholderText("12 / 29")
        form.addWidget(_field_label(t("Термін дії"), c), 2, 0)
        form.addWidget(self.expiry, 3, 0)

        self.cvc = QLineEdit()
        self.cvc.setPlaceholderText("123")
        self.cvc.setMaxLength(4)
        form.addWidget(_field_label("CVC", c), 2, 1)
        form.addWidget(self.cvc, 3, 1)

        root.addLayout(form)
        root.addSpacing(SPACE_SM)

        self.hint = QLabel(t("Приймається лише тестовий номер 4242 4242 4242 4242."))
        self.hint.setObjectName("MetaText")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        buttons = QHBoxLayout()
        cancel = QPushButton(t("Скасувати"))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        buttons.addStretch(1)
        self.pay = QPushButton(f'{t("Оформити за")} {plan.price_label}')
        self.pay.setObjectName("Primary")
        self.pay.clicked.connect(self._submit)
        buttons.addWidget(self.pay)
        root.addLayout(buttons)

    def _format_card(self, text: str) -> None:
        digits = "".join(ch for ch in text if ch.isdigit())[:16]
        grouped = " ".join(digits[i : i + 4] for i in range(0, len(digits), 4))
        if grouped != text:
            self.card.blockSignals(True)
            self.card.setText(grouped)
            self.card.setCursorPosition(len(grouped))
            self.card.blockSignals(False)

    def _submit(self) -> None:
        digits = "".join(ch for ch in self.card.text() if ch.isdigit())
        if digits != _TEST_CARD:
            self.hint.setText(t("Це демо — введи тестовий номер 4242 4242 4242 4242."))
            self.hint.setObjectName("PillWarn")
            self.hint.style().unpolish(self.hint)
            self.hint.style().polish(self.hint)
            return

        self.pay.setEnabled(False)
        self.pay.setText(t("Обробка…"))
        QTimer.singleShot(900, self.accept)


def _field_label(text: str, c: dict) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {c['text_dim']}; font-size: 9pt;")
    return label
