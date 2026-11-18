"""Головне вікно OmniScribe.

Структура (щільність — за зразком Linear, статуси кольором — за Vercel):
    TopBar    логотип · мікрофон · запис/пауза · тема · налаштування
    Sidebar   нова сесія · пошук · список сесій з метаданими · квота плану
    Workspace картка "чує зараз" + картка конспекту з шапкою сесії
    StatusBar підказка шорткатів

Усе, що можна зробити мишею, доступне і з клавіатури — команди зібрані в
одному місці (`_commands`) і живлять водночас шорткати й палітру Ctrl+K,
тому вони не розходяться між собою.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

import audio_io
import i18n
from accounts import AccountStore
from billing import BillingStore
from config import Config
from gui.auth_dialog import AuthDialog
from gui.brand import BrandWidget
from gui.command_palette import Command, CommandPalette
from gui.live_panel import LivePanel
from gui.notes_panel import NotesPanel
from gui.plans_dialog import PlansDialog
from gui.session_list import META_ROLE, SessionDelegate
from gui.settings_dialog import SettingsDialog
from gui.theme import (
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    apply_density,
    build_qss,
    load_theme_name,
    palette,
    preference,
    save_preference,
    save_theme_name,
)
from gui.toast import Toast
from gui.workers import TranscriptionPipeline
from i18n import t
from local_notes import LocalNotesStore, default_db_path
from paths import base_dir

ASSETS_DIR = base_dir() / "assets"


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self.theme_name = load_theme_name()
        self.notes_builder = None
        self.pipeline: TranscriptionPipeline | None = None
        self.store = LocalNotesStore()
        self.billing = BillingStore(default_db_path())
        self.accounts = AccountStore(default_db_path())
        self.active_session_id = self.store.session_id
        self.viewed_session_id = self.active_session_id
        self.recording = False
        self._refreshing_sessions = False
        self._palette: CommandPalette | None = None
        self.live_panel_shown = preference("live_panel", "1") == "1"

        self.billing.add_session()

        self.setWindowTitle("OmniScribe")
        self.resize(1360, 860)
        self.setMinimumSize(1040, 640)
        self._apply_window_icon()

        self._build_ui()
        self._refresh_devices()
        self._refresh_sessions()
        self._refresh_quota()
        self._refresh_account()
        self._update_record_controls()
        self._refresh_session_header()
        self._install_shortcuts()
        self.apply_theme(self.theme_name)

    # ------------------------------------------------------------------- UI

    def _apply_window_icon(self) -> None:
        icon_path = ASSETS_DIR / "logo.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _update_brand_logo(self) -> None:
        name = "logo_white.png" if self.theme_name == "dark" else "logo_black.png"
        logo_path = ASSETS_DIR / name
        if logo_path.exists():
            self.brand.set_logo(str(logo_path))

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_topbar())

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self._build_sidebar())
        body_layout.addWidget(self._build_workspace(), 1)
        root.addWidget(body, 1)

        self.status = QStatusBar()
        self.status.setSizeGripEnabled(False)
        self.setStatusBar(self.status)
        self.status.showMessage(t("Ctrl+K — усі команди · Ctrl+R — запис · Ctrl+N — нова сесія"))

        # Службові перемикачі живуть унизу праворуч: вони потрібні зрідка,
        # тож не мають ділити верхній рядок із записом — головною дією.
        for glyph, tip, handler in (
            ("⌘", t("Команди  ·  Ctrl+K"), self._open_palette),
            ("☾", t("Тема  ·  Ctrl+D"), self._toggle_theme),
            ("⚙", t("Налаштування  ·  Ctrl+,"), self._open_settings),
        ):
            button = QPushButton(glyph)
            button.setObjectName("BottomIcon")
            button.setFixedSize(28, 28)
            button.setToolTip(tip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(handler)
            self.status.addPermanentWidget(button)
            if glyph == "☾":
                self.theme_btn = button

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(100)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(SPACE_LG, SPACE_SM, SPACE_LG, SPACE_SM)
        layout.setSpacing(SPACE_MD)

        self.brand = BrandWidget()
        layout.addWidget(self.brand)
        layout.addStretch(1)

        mic_label = QLabel(t("Мікрофон"))
        mic_label.setObjectName("FieldLabel")
        layout.addWidget(mic_label)
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(230)
        layout.addWidget(self.device_combo)

        refresh_btn = QPushButton("↻")
        refresh_btn.setObjectName("Ghost")
        refresh_btn.setFixedWidth(36)
        refresh_btn.setToolTip(t("Оновити список пристроїв"))
        refresh_btn.clicked.connect(self._refresh_devices)
        layout.addWidget(refresh_btn)

        layout.addSpacing(SPACE_SM)

        # Запис: у спокої одна кнопка, під час запису — дві. Вимкнених
        # кнопок немає взагалі: сіра «Пауза», яку не можна натиснути,
        # займає місце й нічого не повідомляє.
        self.record_btn = QPushButton(t("Записати"))
        self.record_btn.setObjectName("Tonal")
        self.record_btn.setToolTip(t("Почати запис  ·  Ctrl+R"))
        self.record_btn.clicked.connect(self._toggle_record)
        layout.addWidget(self.record_btn)

        self.pause_btn = QPushButton(t("Пауза"))
        self.pause_btn.setObjectName("Tonal")
        self.pause_btn.setToolTip(t("Пауза  ·  Ctrl+Space"))
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.pause_btn.setVisible(False)
        layout.addWidget(self.pause_btn)

        layout.addSpacing(SPACE_SM)

        self.account_btn = QPushButton()
        self.account_btn.setObjectName("Avatar")
        self.account_btn.setFixedSize(34, 34)
        self.account_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.account_btn.clicked.connect(self._open_account_menu)
        layout.addWidget(self.account_btn)

        return bar

    def _build_sidebar(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("Sidebar")
        panel.setFixedWidth(282)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        layout.setSpacing(SPACE_SM)

        new_btn = QPushButton(t("+  Нова сесія"))
        new_btn.setObjectName("Tonal")
        new_btn.setToolTip(t("Нова сесія  ·  Ctrl+N"))
        new_btn.clicked.connect(self._new_session)
        layout.addWidget(new_btn)

        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText(t("Пошук сесій…   Ctrl+L"))
        self.search.textChanged.connect(self._refresh_sessions)
        layout.addWidget(self.search)

        header = QHBoxLayout()
        label = QLabel(t("Сесії"))
        label.setObjectName("SectionLabel")
        header.addWidget(label)
        header.addStretch(1)
        self.sessions_count = QLabel("")
        self.sessions_count.setObjectName("SectionLabel")
        header.addWidget(self.sessions_count)
        layout.addLayout(header)

        self.sessions_list = QListWidget()
        self.sessions_list.setFrameShape(QListWidget.Shape.NoFrame)
        self.sessions_list.setMouseTracking(True)
        self.session_delegate = SessionDelegate(self.theme_name, self.sessions_list)
        self.sessions_list.setItemDelegate(self.session_delegate)
        self.sessions_list.setToolTip(t("Подвійний клік — перейменувати лекцію"))
        self.sessions_list.itemClicked.connect(self._on_session_selected)
        self.sessions_list.itemChanged.connect(self._on_session_renamed)
        layout.addWidget(self.sessions_list, 1)

        layout.addWidget(_divider())

        export_row = QHBoxLayout()
        export_row.setSpacing(SPACE_SM)
        export_md = QPushButton(t("Markdown"))
        export_md.setObjectName("Ghost")
        export_md.setToolTip(t("Експорт .md  ·  Ctrl+E"))
        export_md.clicked.connect(lambda: self._export("md"))
        export_row.addWidget(export_md)
        export_docx = QPushButton(t("Word"))
        export_docx.setObjectName("Ghost")
        export_docx.setToolTip(t("Експорт .docx  ·  Ctrl+Shift+E"))
        export_docx.clicked.connect(lambda: self._export("docx"))
        export_row.addWidget(export_docx)
        layout.addLayout(export_row)

        layout.addWidget(_divider())
        layout.addWidget(self._build_quota_block())

        return panel

    def _build_quota_block(self) -> QWidget:
        block = QWidget()
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, SPACE_SM, 0, 0)
        layout.setSpacing(6)

        top = QHBoxLayout()
        self.plan_pill = QLabel("FREE")
        self.plan_pill.setObjectName("Pill")
        top.addWidget(self.plan_pill)
        top.addStretch(1)
        upgrade = QPushButton(t("Змінити"))
        upgrade.setObjectName("Ghost")
        upgrade.setToolTip(t("Плани  ·  Ctrl+P"))
        upgrade.clicked.connect(self._open_plans)
        top.addWidget(upgrade)
        layout.addLayout(top)

        self.quota_bar = QProgressBar()
        self.quota_bar.setObjectName("Quota")
        self.quota_bar.setTextVisible(False)
        self.quota_bar.setRange(0, 100)
        layout.addWidget(self.quota_bar)

        self.quota_label = QLabel("")
        self.quota_label.setObjectName("MetaText")
        layout.addWidget(self.quota_label)

        return block

    def _build_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QHBoxLayout(workspace)
        layout.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        layout.setSpacing(SPACE_LG)

        self.live_panel = LivePanel(self.theme_name)
        self.live_panel.closeRequested.connect(lambda: self.toggle_live_panel(False))
        self.notes_panel = NotesPanel(self.theme_name)
        self.notes_panel.edited.connect(self._save_notes_override)

        layout.addWidget(self.live_panel, 2)
        layout.addWidget(self.notes_panel, 3)
        self.live_panel.setVisible(self.live_panel_shown)
        return workspace

    # ------------------------------------------------------------ шорткати

    def _commands(self) -> list[Command]:
        return [
            Command(
                t("Почати запис") if not self.recording else t("Зупинити запис"),
                "Мікрофон → конспект у реальному часі",
                self._toggle_record,
                "Ctrl+R",
                ("record", "запис", "мікрофон"),
            ),
            Command(
                t("Пауза / продовжити"),
                t("Призупинити потік, не закриваючи сесію"),
                self._toggle_pause,
                "Ctrl+Space",
                ("pause", "пауза"),
                enabled=self.recording,
            ),
            Command(
                t("Нова сесія"),
                t("Почати нову лекцію з власною назвою"),
                self._new_session,
                "Ctrl+N",
                ("new", "нова", "лекція", "сесія"),
            ),
            Command(
                t("Перейменувати лекцію"),
                t("Змінити назву поточної сесії"),
                self._rename_current_session,
                "F2",
                ("rename", "назва", "перейменувати"),
            ),
            Command(
                t("Експорт у Markdown"),
                t("Зберегти конспект як .md"),
                lambda: self._export("md"),
                "Ctrl+E",
                ("export", "markdown", "експорт"),
            ),
            Command(
                t("Експорт у Word"),
                t("Зберегти конспект як .docx"),
                lambda: self._export("docx"),
                "Ctrl+Shift+E",
                ("export", "word", "docx", "експорт"),
            ),
            Command(
                "Плани й підписка",
                f'{t("Зараз")}: {self.billing.plan().name} · {self.billing.usage().label}',
                self._open_plans,
                "Ctrl+P",
                ("plan", "підписка", "оплата", "тариф", "квота"),
            ),
            Command(
                t("Налаштування"),
                t("Ключі API, моделі, пресети конспектування"),
                self._open_settings,
                "Ctrl+,",
                ("settings", "налаштування", "ключі", "модель"),
            ),
            Command(
                t("Перемкнути тему"),
                t("Темна ↔ світла"),
                self._toggle_theme,
                "Ctrl+D",
                ("theme", "тема", "темна", "світла"),
            ),
            Command(
                t("Показати панель «Чує зараз»") if not self.live_panel_shown
                else t("Сховати панель «Чує зараз»"),
                t("Більше місця конспекту"),
                self.toggle_live_panel,
                "Ctrl+Shift+L",
                ("panel", "панель", "чує", "live"),
            ),
            Command(
                t("Оновити список мікрофонів"),
                t("Перечитати доступні пристрої запису"),
                self._refresh_devices,
                "",
                ("device", "мікрофон", "пристрій"),
            ),
            Command(
                t("Скинути лічильник квоти"),
                t("Демо: обнулити використані хвилини цього місяця"),
                self._reset_quota,
                "",
                ("quota", "квота", "скинути", "demo"),
            ),
        ]

    def _install_shortcuts(self) -> None:
        pairs = [
            ("Ctrl+K", self._open_palette),
            ("Ctrl+R", self._toggle_record),
            ("Ctrl+Space", self._toggle_pause),
            ("Ctrl+N", self._new_session),
            ("F2", self._rename_current_session),
            ("Ctrl+E", lambda: self._export("md")),
            ("Ctrl+Shift+E", lambda: self._export("docx")),
            ("Ctrl+P", self._open_plans),
            ("Ctrl+,", self._open_settings),
            ("Ctrl+D", self._toggle_theme),
            ("Ctrl+L", self.search.setFocus),
            ("Ctrl+Shift+L", self.toggle_live_panel),
        ]
        for keys, handler in pairs:
            QShortcut(QKeySequence(keys), self, activated=handler)

    def _open_palette(self) -> None:
        self._palette = CommandPalette(self._commands(), self.theme_name, self)
        self._palette.open_centered()

    # --------------------------------------------------------------- devices

    def _refresh_devices(self) -> None:
        self.device_combo.clear()
        self._devices = audio_io.list_input_devices()
        if not self._devices:
            self.device_combo.addItem(t("Мікрофон не знайдено"))
            self.device_combo.setEnabled(False)
            self.record_btn.setEnabled(False)
            return
        self.device_combo.setEnabled(True)
        self.record_btn.setEnabled(True)
        default = audio_io.default_input_device()
        for i, d in enumerate(self._devices):
            self.device_combo.addItem(f"{d.name}", userData=d)
            if default and d.index == default.index:
                self.device_combo.setCurrentIndex(i)

    # ------------------------------------------------------------- recording

    def _toggle_record(self) -> None:
        if self.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        missing = self.cfg.missing_keys()
        if missing:
            QMessageBox.critical(
                self, t("Немає ключів API"), t("Додай у налаштуваннях") + ": " + ", ".join(missing)
            )
            return

        usage = self.billing.usage()
        if usage.exhausted:
            self.toast(
                f"Квота {self.billing.plan().name} вичерпана — {usage.label}", "warn"
            )
            self._open_plans()
            return

        device = self.device_combo.currentData()
        if device is None:
            return

        if self.notes_builder is None:
            from notes_ai import NoteBuilder

            self.notes_builder = NoteBuilder(
                groq_api_key=self.cfg.groq_api_key,
                anthropic_api_key=self.cfg.anthropic_api_key,
                model=self.cfg.model,
                effort=self.cfg.effort,
                whisper_model=self.cfg.whisper_model,
                language=self.cfg.language,
                preset=self.cfg.preset,
            )

        self.pipeline = TranscriptionPipeline(self.notes_builder, self.store, self.cfg.queue_max)
        self.pipeline.heard.connect(self.live_panel.append_line)
        self.pipeline.noteBlocks.connect(self._on_note_blocks)
        self.pipeline.usageSeconds.connect(self._on_usage_seconds)
        self.pipeline.statusChanged.connect(self.status.showMessage)
        self.pipeline.start(device)

        self.recording = True
        self.pause_btn.setText(t("Пауза"))
        self.device_combo.setEnabled(False)
        self.live_panel.set_live(True)
        self._update_record_controls()
        self._refresh_session_header()
        self.toast(f'{t("Запис почався")} · {device.name}', "ok")

    def _stop_recording(self) -> None:
        if self.pipeline:
            self.pipeline.stop()
            self.pipeline = None
        self.recording = False
        self.device_combo.setEnabled(True)
        self.live_panel.set_live(False)
        self._update_record_controls()
        self.status.showMessage(t("Запис зупинено"))
        self._refresh_sessions()
        self._refresh_session_header()
        self.toast(t("Запис зупинено, конспект збережено"), "ok")

    def _toggle_pause(self) -> None:
        if not self.pipeline:
            return
        paused = self.pause_btn.text() == t("Пауза")
        if paused:
            self.pipeline.pause()
            self.pause_btn.setText(t("Продовжити"))
        else:
            self.pipeline.resume()
            self.pause_btn.setText(t("Пауза"))
        self.live_panel.set_live(not paused)
        self._update_record_controls()

    def _update_record_controls(self) -> None:
        """Крапка — єдиний кольоровий елемент у верхньому рядку: червона в
        записі, бліда в спокої, прозора на паузі."""
        c = palette(self.theme_name)
        paused = self.recording and self.pause_btn.text() == t("Продовжити")

        self.record_btn.setText(t("Стоп") if self.recording else t("Записати"))
        self.record_btn.setToolTip(
            t("Зупинити запис  ·  Ctrl+R") if self.recording else t("Почати запис  ·  Ctrl+R")
        )
        dot = c["text_faint"] if not self.recording else (c["text_dim"] if paused else c["status_live"])
        self.record_btn.setIcon(_dot_icon(dot))
        self.record_btn.setIconSize(QSize(8, 8))
        self.pause_btn.setVisible(self.recording)

    def _on_note_blocks(self, blocks) -> None:
        words = sum(len(b.text.split()) for b in blocks if b.text)
        if words:
            self.store.add_session_stats(self.active_session_id, words=words)
        if self.viewed_session_id == self.active_session_id:
            self.notes_panel.append_blocks(blocks)
            self._refresh_session_header()

    def _on_usage_seconds(self, seconds: float) -> None:
        self.billing.add_seconds(seconds)
        self.store.add_session_stats(self.active_session_id, seconds=seconds)
        self._refresh_quota()

        usage = self.billing.usage()
        if usage.exhausted and self.recording:
            self._stop_recording()
            self.toast(t("Місячна квота вичерпана — запис зупинено"), "err")
            self._open_plans()

    def _save_notes_override(self) -> None:
        self.store.save_notes_override(self.viewed_session_id, self.notes_panel.current_html())

    # ------------------------------------------------------------------ квота

    def _refresh_quota(self) -> None:
        plan = self.billing.plan()
        usage = self.billing.usage()

        self.plan_pill.setText(plan.name.upper())
        self.quota_label.setText(usage.label)
        self.quota_bar.setValue(usage.percent if plan.minutes_month else 100)

        state = "full" if usage.exhausted else ("warn" if usage.percent >= 80 else "ok")
        self.quota_bar.setProperty("state", state)
        self.quota_bar.style().unpolish(self.quota_bar)
        self.quota_bar.style().polish(self.quota_bar)

        self.plan_pill.setObjectName("PillWarn" if usage.exhausted else "Pill")
        self.plan_pill.style().unpolish(self.plan_pill)
        self.plan_pill.style().polish(self.plan_pill)

    # ---------------------------------------------------------------- акаунт

    def _refresh_account(self) -> None:
        account = self.accounts.current()
        self.account_btn.setText(account.initials if account else "+")
        self.account_btn.setToolTip(
            f"{account.name} · {account.email}" if account else t("Увійти або створити акаунт")
        )

    def _open_account_menu(self) -> None:
        account = self.accounts.current()
        menu = QMenu(self)

        if account is None:
            menu.addAction(t("Увійти"), lambda: self._authenticate(signup=False))
            menu.addAction(t("Створити акаунт"), lambda: self._authenticate(signup=True))
            menu.addSeparator()
            hint = menu.addAction(t("Без акаунта все працює локально"))
            hint.setEnabled(False)
        else:
            head = menu.addAction(f"{account.name} · {account.email}")
            head.setEnabled(False)
            menu.addSeparator()
            menu.addAction(f'{t("План")} {self.billing.plan().name}', self._open_plans)
            menu.addAction(t("Вийти"), self._sign_out)

        menu.exec(self.account_btn.mapToGlobal(self.account_btn.rect().bottomLeft()))

    def _authenticate(self, signup: bool) -> bool:
        dialog = AuthDialog(self.accounts, self.theme_name, self, signup=signup)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.account is None:
            return False
        self._refresh_account()
        self.toast(f'{t("Вітаємо")}, {dialog.account.name.split()[0]}', "ok")
        return True

    def _sign_out(self) -> None:
        self.accounts.sign_out()
        self._refresh_account()
        self.toast(t("Ви вийшли з акаунта"), "info")

    def _open_plans(self) -> None:
        # Платний план прив'язується до особи, тож без акаунта оплата не має
        # сенсу — пропонуємо створити його до, а не після форми оплати.
        if self.accounts.current() is None and self.billing.plan_id() == "free":
            self.toast(t("Щоб змінити план, потрібен акаунт"), "warn")
            if not self._authenticate(signup=True):
                return

        dialog = PlansDialog(self.billing.plan_id(), self.theme_name, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.chosen_plan:
            self.billing.set_plan(dialog.chosen_plan)
            plan = self.billing.plan()
            self.cfg.model = plan.model
            self.notes_builder = None
            self._refresh_quota()
            self.toast(f'{t("План")} {plan.name} {t("активовано")} · {t("модель")} {plan.model}', "ok")

    def _reset_quota(self) -> None:
        self.billing.reset_usage()
        self._refresh_quota()
        self.toast(t("Лічильник квоти обнулено (демо)"), "info")

    # ----------------------------------------------------------------- sessions

    def _refresh_sessions(self) -> None:
        query = self.search.text().strip().lower() if hasattr(self, "search") else ""
        self._refreshing_sessions = True
        self.sessions_list.clear()

        rows = self.store.list_sessions()
        shown = 0
        for row in rows:
            if query and query not in row.title.lower():
                continue
            item = QListWidgetItem(row.title)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setData(Qt.ItemDataRole.UserRole, row.id)
            item.setData(META_ROLE, row.meta_label)
            self.sessions_list.addItem(item)
            if row.id == self.viewed_session_id:
                self.sessions_list.setCurrentItem(item)
            shown += 1

        self.sessions_count.setText(str(shown) if not query else f"{shown} / {len(rows)}")
        self._refreshing_sessions = False

    def _on_session_renamed(self, item: QListWidgetItem) -> None:
        if self._refreshing_sessions:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        new_title = item.text().strip()
        if not new_title:
            item.setText(self.store.session_title(sid))
            return
        self.store.rename_session(sid, new_title)
        self._refresh_session_header()
        self.toast(t("Назву оновлено"), "ok")

    def _rename_current_session(self) -> None:
        sid = self.viewed_session_id
        title, ok = QInputDialog.getText(
            self, t("Назва лекції"), t("Як називається лекція?"), text=self.store.session_title(sid)
        )
        if ok and title.strip():
            self.store.rename_session(sid, title.strip())
            self._refresh_sessions()
            self._refresh_session_header()
            self.toast(t("Назву оновлено"), "ok")

    def _on_session_selected(self, item: QListWidgetItem) -> None:
        sid = item.data(Qt.ItemDataRole.UserRole)
        if sid == self.viewed_session_id:
            return
        self.viewed_session_id = sid
        override = self.store.load_notes_override(sid)
        if override:
            self.notes_panel.set_raw_html(override)
        else:
            stored = self.store.load_blocks(sid)
            blocks = [b.to_block() for b in stored if not b.pending]
            self.notes_panel.load_blocks(blocks)
        self._refresh_session_header()

    def _new_session(self) -> None:
        if self.recording:
            self._stop_recording()

        from datetime import datetime

        suggested = f'{t("Лекція")} {datetime.now():%d.%m.%Y %H:%M}'
        title, ok = QInputDialog.getText(self, t("Нова сесія"), t("Назва лекції:"), text=suggested)
        if not ok:
            return

        self.store = LocalNotesStore(session_title=title.strip() or suggested)
        self.billing.add_session()
        self.active_session_id = self.store.session_id
        self.viewed_session_id = self.active_session_id
        self.notes_builder = None
        self.live_panel.clear()
        self.notes_panel.clear()
        self._refresh_sessions()
        self._refresh_session_header()
        self.toast(f'{t("Сесія")} «{self.store.title}» {t("створена")}', "ok")

    def _refresh_session_header(self) -> None:
        sid = self.viewed_session_id
        seconds, words = self.store.session_stats(sid)
        parts = []
        if seconds >= 30:
            parts.append(f'{int(round(seconds / 60))} {t("хв мовлення")}')
        if words:
            parts.append(f'{words:,} {t("слів")}'.replace(",", " "))
        parts.append(self.cfg.model)

        is_active = sid == self.active_session_id
        state = "live" if (self.recording and is_active) else ("ok" if words else "idle")
        self.notes_panel.set_header(
            self.store.session_title(sid) or "Конспект", "  ·  ".join(parts), state
        )

    # ------------------------------------------------------------------ export

    def _export(self, fmt: str) -> None:
        if fmt == "docx" and not self.billing.has_feature("docx"):
            self.toast(t("Експорт у Word доступний з плану Pro"), "warn")
            self._open_plans()
            return

        sid = self.viewed_session_id
        title = self.store.session_title(sid) or t("Конспект")
        safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip()
        suggested = f"{safe_name or 'конспект'}.{fmt}"

        if fmt == "md":
            path, _ = QFileDialog.getSaveFileName(
                self, t("Експорт у Markdown"), suggested, "Markdown (*.md)"
            )
            if not path:
                return
            Path(path).write_text(self.store.export_markdown(sid), encoding="utf-8")
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, t("Експорт у Word"), suggested, "Word (*.docx)"
            )
            if not path:
                return
            self.store.export_docx(path, sid)

        self.status.showMessage(f'{t("Збережено")}: {path}')
        self.toast(f'{t("Збережено")} {Path(path).name}', "ok")

    # ------------------------------------------------------------------ тости

    def toast(self, text: str, kind: str = "ok") -> None:
        Toast(self, text, kind, self.theme_name).pop()

    # ---------------------------------------------------------------- settings

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.cfg, self.theme_name, self.accounts, self)
        dialog.appearanceChanged.connect(self._apply_appearance)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        self._apply_appearance()
        if accepted:
            self.notes_builder = None
            self._refresh_session_header()
            self.toast(t("Налаштування збережено"), "ok")

    # -------------------------------------------------------------- вигляд

    def toggle_live_panel(self, shown: bool | None = None) -> None:
        self.live_panel_shown = (not self.live_panel_shown) if shown is None else shown
        save_preference("live_panel", "1" if self.live_panel_shown else "0")
        self.live_panel.setVisible(self.live_panel_shown)

    def _apply_appearance(self) -> None:
        """Мова, щільність і кегль вшиті у віджети при створенні, тож
        змінити їх наживо означає перебудувати інтерфейс. Стан (база,
        білінг, конвеєр) живе поза віджетами й перебудову переживає; вміст
        панелей переносимо руками, щоб не зникло те, що людина щойно бачила.
        """
        i18n.set_language(preference("language", i18n.DEFAULT))
        apply_density(preference("density", "comfortable"))

        notes_html = self.notes_panel.current_html()
        heard = self.live_panel.view.toPlainText()
        self.theme_name = preference("theme", self.theme_name)

        if self.pipeline is not None:
            self.pipeline.heard.disconnect()
            self.pipeline.noteBlocks.disconnect()
            self.pipeline.statusChanged.disconnect()

        self._build_ui()
        self._refresh_devices()
        self._refresh_sessions()
        self._refresh_quota()
        self._refresh_account()
        self._update_record_controls()
        self._refresh_session_header()
        self.apply_theme(self.theme_name)

        self.notes_panel.set_raw_html(notes_html)
        for line in heard.splitlines():
            self.live_panel.append_line(line)
        self.live_panel.set_live(self.recording)

        if self.pipeline is not None:
            self.pipeline.heard.connect(self.live_panel.append_line)
            self.pipeline.noteBlocks.connect(self._on_note_blocks)
            self.pipeline.statusChanged.connect(self.status.showMessage)

    # -------------------------------------------------------------------- theme

    def _toggle_theme(self) -> None:
        self.apply_theme("light" if self.theme_name == "dark" else "dark")

    def apply_theme(self, name: str) -> None:
        from PySide6.QtWidgets import QApplication

        self.theme_name = name
        save_theme_name(name)
        if hasattr(self, "theme_btn"):
            self.theme_btn.setText("☀" if name == "dark" else "☾")

        QApplication.instance().setStyleSheet(build_qss(name))
        self.live_panel.set_theme(name)
        self.notes_panel.set_theme(name)
        self.session_delegate.set_theme(name)
        self.sessions_list.viewport().update()
        self._update_record_controls()
        self._update_brand_logo()
        self._refresh_quota()

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt override
        if self.pipeline:
            self.pipeline.stop()
        self.store.close()
        self.billing.close()
        self.accounts.close()
        super().closeEvent(event)


def _divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFrameShape(QFrame.Shape.HLine)
    return line


def _dot_icon(color: str, size: int = 16) -> QIcon:
    """Кружечок як іконка кнопки: QSS не вміє пофарбувати частину тексту,
    а малювати його віджетом заради 8 пікселів — зайва складність."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(2, 2, size - 4, size - 4)
    painter.end()
    return QIcon(pixmap)
