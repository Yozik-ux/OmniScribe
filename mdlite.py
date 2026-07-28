"""Розбір відповіді Claude у структуру, яку розуміє Google Docs API.

Google Docs не знає про markdown: insertText вставляє рівно ті символи, що дав.
Тому "**термін**" опинявся в документі буквально зі зірочками. Тут ми
перетворюємо обмежений набір розмітки в (чистий_текст + діапазони стилів),
а docs_writer уже накладає updateTextStyle / createParagraphBullets.

Підмножина розмітки навмисно вузька — рівно те, що дозволено промптом:
    "## Заголовок"    -> heading
    "- пункт"         -> bullet
    "1. пункт"        -> number
    звичайний рядок   -> para
    "**жирний**"      -> діапазон bold усередині будь-якого з них
"""

import re
from dataclasses import dataclass, field

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
_BULLET_RE = re.compile(r"^\s{0,4}[-*•]\s+(.*)$")
_NUMBER_RE = re.compile(r"^\s{0,4}\d+[.)]\s+(.*)$")


@dataclass
class Block:
    kind: str  # "heading" | "bullet" | "number" | "para"
    text: str
    bold: list[tuple[int, int]] = field(default_factory=list)  # (start, end) у символах


def _extract_bold(line: str) -> tuple[str, list[tuple[int, int]]]:
    """Витягує **жирний**, повертає чистий текст і діапазони."""
    out: list[str] = []
    spans: list[tuple[int, int]] = []
    pos = 0
    for m in _BOLD_RE.finditer(line):
        out.append(line[pos : m.start()])
        start = sum(len(p) for p in out)
        inner = m.group(1).strip()
        out.append(inner)
        spans.append((start, start + len(inner)))
        pos = m.end()
    out.append(line[pos:])
    return "".join(out), spans


def _strip_stray_markup(text: str) -> str:
    """Прибирає недопарені зірочки/підкреслення, щоб вони не текли в документ."""
    return text.replace("**", "").replace("__", "").strip()


def parse(md: str) -> list[Block]:
    blocks: list[Block] = []

    for raw in (md or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue

        kind = "para"
        body = line

        m = _HEADING_RE.match(line)
        if m:
            kind, body = "heading", m.group(1)
        else:
            m = _BULLET_RE.match(line)
            if m:
                kind, body = "bullet", m.group(1)
            else:
                m = _NUMBER_RE.match(line)
                if m:
                    kind, body = "number", m.group(1)

        text, spans = _extract_bold(body)
        text = _strip_stray_markup(text)
        if not text:
            continue

        # У заголовку жирний зайвий — стиль заголовка вже виділяє його.
        if kind == "heading":
            spans = []

        # Захист від зсуву діапазонів, якщо _strip_stray_markup щось прибрав.
        spans = [(s, e) for s, e in spans if 0 <= s < e <= len(text)]

        blocks.append(Block(kind=kind, text=text, bold=spans))

    return blocks
