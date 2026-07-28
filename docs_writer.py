"""Запис конспекту в Google Docs зі справжнім форматуванням.

Дві проблеми, які тут вирішуються:

1. insertText вставляє текст буквально — тому markdown від Claude перетворюємо
   на batchUpdate: insertText + updateTextStyle (жирний) + createParagraphBullets
   (списки) + updateParagraphStyle (заголовки).

2. Студент редагує документ у реальному часі, тобто індекси символів "їдуть"
   між нашими запитами. Тому кожен ще-не-готовий фрагмент обгортається в
   NamedRange: Google сам переносить його межі при правках, і ми потім знаходимо
   потрібне місце навіть якщо студент вище дописав три абзаци.
"""

import threading
import time
from datetime import datetime

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from mdlite import Block

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

PENDING_PREFIX = "▸ "
GREY = {"color": {"rgbColor": {"red": 0.53, "green": 0.53, "blue": 0.53}}}
BLACK = {"color": {"rgbColor": {"red": 0.0, "green": 0.0, "blue": 0.0}}}

RETRY_STATUSES = {429, 500, 502, 503, 504}


def u16len(text: str) -> int:
    """Довжина в UTF-16 code units — саме ними Google Docs міряє індекси."""
    return len(text.encode("utf-16-le")) // 2


class DocsWriter:
    def __init__(self, credentials_file: str, document_id: str = "", share_with: str = "") -> None:
        creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
        self.docs = build("docs", "v1", credentials=creds, cache_discovery=False)
        self._drive = None
        self._creds = creds
        self._lock = threading.Lock()
        self._counter = 0

        if document_id:
            self.doc_id = document_id
            self.created = False
        else:
            self.doc_id = self._create_document(share_with)
            self.created = True

    @property
    def url(self) -> str:
        return f"https://docs.google.com/document/d/{self.doc_id}/edit"

    # ------------------------------------------------------------- lifecycle

    def _drive_service(self):
        if self._drive is None:
            self._drive = build("drive", "v3", credentials=self._creds, cache_discovery=False)
        return self._drive

    def _create_document(self, share_with: str) -> str:
        title = f"Конспект — {datetime.now():%d.%m.%Y %H:%M}"
        doc = self._exec(lambda: self.docs.documents().create(body={"title": title}))
        doc_id = doc["documentId"]

        if share_with:
            try:
                self._exec(
                    lambda: self._drive_service()
                    .permissions()
                    .create(
                        fileId=doc_id,
                        body={"type": "user", "role": "writer", "emailAddress": share_with},
                        sendNotificationEmail=False,
                        fields="id",
                    )
                )
                print(f"🔗 Документ розшарено на {share_with}", flush=True)
            except Exception as exc:  # noqa: BLE001 — сесія має жити далі
                print(
                    f"⚠️ Не вдалося розшарити документ ({exc}).\n"
                    f"   Увімкни Drive API в проєкті або задай CONSPEKT_DOCUMENT_ID вручну.",
                    flush=True,
                )
        return doc_id

    def write_session_header(self) -> None:
        """Шапка сесії, щоб кілька лекцій в одному документі не злипались."""
        stamp = datetime.now().strftime("%d.%m.%Y, %H:%M")
        self.commit(None, [Block("heading", f"Лекція {stamp}")])

    # ------------------------------------------------------------ публічне API

    def insert_pending(self, raw_text: str) -> str | None:
        """Одразу показати сирий транскрипт (сірим курсивом) і зарезервувати місце.

        Повертає ім'я NamedRange, яке потім передається в commit().
        """
        text = PENDING_PREFIX + raw_text.strip()
        with self._lock:
            try:
                snap = self._snapshot(with_named_ranges=False)
                start = snap["insert_at"]
                payload = ("" if snap["last_empty"] else "\n") + text + "\n"
                length = u16len(payload)

                self._counter += 1
                name = f"cnspkt{self._counter}"

                requests = [
                    {"insertText": {"location": {"index": start}, "text": payload}},
                    {
                        "createNamedRange": {
                            "name": name,
                            "range": {"startIndex": start, "endIndex": start + length},
                        }
                    },
                    {
                        "updateParagraphStyle": {
                            "range": {"startIndex": start, "endIndex": start + length},
                            "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                            "fields": "namedStyleType",
                        }
                    },
                    {
                        "updateTextStyle": {
                            "range": {"startIndex": start, "endIndex": start + length},
                            "textStyle": {"italic": True, "bold": False, "foregroundColor": GREY},
                            "fields": "italic,bold,foregroundColor",
                        }
                    },
                ]
                self._batch(requests)
                return name
            except Exception as exc:  # noqa: BLE001
                print(f"❌ Не вдалося вставити чернетку: {exc}", flush=True)
                return None

    def commit(self, pending_name: str | None, blocks: list[Block]) -> bool:
        """Замінити чернетку відформатованим конспектом.

        Якщо NamedRange зник (студент видалив абзац) — дописуємо в кінець.
        """
        if not blocks:
            return False

        with self._lock:
            try:
                snap = self._snapshot(with_named_ranges=bool(pending_name))
                requests: list[dict] = []
                target = None

                if pending_name:
                    found = self._find_range(snap["named_ranges"], pending_name)
                    if found:
                        rng_id, rng = found
                        target = rng["startIndex"]
                        requests.append({"deleteNamedRange": {"namedRangeId": rng_id}})
                        if rng["endIndex"] > rng["startIndex"]:
                            requests.append(
                                {
                                    "deleteContentRange": {
                                        "range": {
                                            "startIndex": rng["startIndex"],
                                            "endIndex": rng["endIndex"],
                                        }
                                    }
                                }
                            )

                if target is None:
                    target = snap["insert_at"]
                    prefix = "" if snap["last_empty"] else "\n"
                else:
                    prefix = ""

                requests.extend(self._render(target, prefix, blocks))
                self._batch(requests)
                return True
            except Exception as exc:  # noqa: BLE001
                print(f"❌ Не вдалося записати в документ: {exc}", flush=True)
                return False

    # ------------------------------------------------------------ рендер блоків

    def _render(self, start: int, prefix: str, blocks: list[Block]) -> list[dict]:
        """Складає insertText + усі стилі. Індекси — відносно start, у UTF-16."""
        payload = prefix
        # (початок, кінець, блок) у UTF-16 одиницях відносно start
        spans: list[tuple[int, int, Block]] = []

        offset = u16len(prefix)
        for block in blocks:
            line = block.text + "\n"
            length = u16len(line)
            spans.append((offset, offset + length, block))
            payload += line
            offset += length

        total = u16len(payload)
        requests: list[dict] = [
            {"insertText": {"location": {"index": start}, "text": payload}}
        ]

        # 1. Стилі абзаців. NORMAL_TEXT спершу — інакше успадкуємо заголовок
        #    від абзацу, у який вставляємось.
        requests.append(
            {
                "updateParagraphStyle": {
                    "range": {"startIndex": start, "endIndex": start + total},
                    "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"},
                    "fields": "namedStyleType",
                }
            }
        )
        for s, e, block in spans:
            if block.kind == "heading":
                requests.append(
                    {
                        "updateParagraphStyle": {
                            "range": {"startIndex": start + s, "endIndex": start + e},
                            "paragraphStyle": {"namedStyleType": "HEADING_3"},
                            "fields": "namedStyleType",
                        }
                    }
                )

        # 2. Скидаємо сірий курсив чернетки, яку щойно замінили.
        requests.append(
            {
                "updateTextStyle": {
                    "range": {"startIndex": start, "endIndex": start + total},
                    "textStyle": {"bold": False, "italic": False, "foregroundColor": BLACK},
                    "fields": "bold,italic,foregroundColor",
                }
            }
        )

        # 3. Жирні терміни.
        for s, _e, block in spans:
            for b_start, b_end in block.bold:
                abs_start = start + s + u16len(block.text[:b_start])
                abs_end = start + s + u16len(block.text[:b_end])
                if abs_end > abs_start:
                    requests.append(
                        {
                            "updateTextStyle": {
                                "range": {"startIndex": abs_start, "endIndex": abs_end},
                                "textStyle": {"bold": True},
                                "fields": "bold",
                            }
                        }
                    )

        # 4. Списки — суміжні пункти одного типу групуємо в один запит.
        for kind, preset in (
            ("bullet", "BULLET_DISC_CIRCLE_SQUARE"),
            ("number", "NUMBERED_DECIMAL_ALPHA_ROMAN"),
        ):
            for group_start, group_end in self._group(spans, kind):
                requests.append(
                    {
                        "createParagraphBullets": {
                            "range": {
                                "startIndex": start + group_start,
                                "endIndex": start + group_end,
                            },
                            "bulletPreset": preset,
                        }
                    }
                )

        return requests

    @staticmethod
    def _group(spans: list[tuple[int, int, Block]], kind: str) -> list[tuple[int, int]]:
        groups: list[tuple[int, int]] = []
        run: tuple[int, int] | None = None
        for s, e, block in spans:
            if block.kind == kind:
                run = (run[0], e) if run else (s, e)
            elif run:
                groups.append(run)
                run = None
        if run:
            groups.append(run)
        return groups

    # ------------------------------------------------------------------- низький рівень

    def _snapshot(self, with_named_ranges: bool) -> dict:
        fields = "body.content,namedRanges" if with_named_ranges else "body.content"
        try:
            doc = self._exec(
                lambda: self.docs.documents().get(documentId=self.doc_id, fields=fields)
            )
        except HttpError as exc:
            if exc.resp is not None and exc.resp.status == 400:
                # Якщо часткова відповідь не сподобалась — беремо документ повністю.
                doc = self._exec(lambda: self.docs.documents().get(documentId=self.doc_id))
            else:
                raise

        content = doc.get("body", {}).get("content", []) or []
        end_index = max((el.get("endIndex", 1) for el in content), default=1)

        last_empty = True
        if content:
            para = content[-1].get("paragraph")
            if para:
                text = "".join(
                    el.get("textRun", {}).get("content", "") for el in para.get("elements", [])
                )
                last_empty = not text.strip()

        return {
            # Останній "\n" тіла документа не можна перекривати — вставляємо перед ним.
            "insert_at": max(1, end_index - 1),
            "last_empty": last_empty,
            "named_ranges": doc.get("namedRanges", {}) or {},
        }

    @staticmethod
    def _find_range(named_ranges: dict, name: str) -> tuple[str, dict] | None:
        entry = named_ranges.get(name)
        if not entry:
            return None
        for nr in entry.get("namedRanges", []):
            ranges = nr.get("ranges") or []
            if ranges:
                rng = ranges[0]
                if "startIndex" in rng and "endIndex" in rng:
                    return nr["namedRangeId"], rng
        return None

    def _batch(self, requests: list[dict]) -> None:
        if not requests:
            return
        self._exec(
            lambda: self.docs.documents().batchUpdate(
                documentId=self.doc_id, body={"requests": requests}
            )
        )

    @staticmethod
    def _exec(make_request, attempts: int = 4):
        """Виконати запит з backoff на 429/5xx — квоти Docs API не безмежні."""
        delay = 1.0
        for attempt in range(attempts):
            try:
                return make_request().execute()
            except HttpError as exc:
                status = exc.resp.status if exc.resp is not None else 0
                if status in RETRY_STATUSES and attempt < attempts - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        raise RuntimeError("недосяжний стан у _exec")
