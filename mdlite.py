"""Розбір відповіді Claude у структуру, яку розуміє Google Docs API.

Google Docs не знає про markdown: insertText вставляє рівно ті символи, що дав.
Тому "**термін**" опинявся в документі буквально зі зірочками. Тут ми
перетворюємо обмежений набір розмітки в (чистий_текст + діапазони стилів),
а docs_writer уже накладає updateTextStyle / createParagraphBullets.

Підмножина розмітки навмисно вузька — рівно те, що дозволено промптом:
    "# / ## / ### Заголовок" -> heading, рівень 1-3 (кількість #)
    "- пункт"                -> bullet, рівень вкладеності за відступом
    "  - пункт"               -> bullet рівня 2 (2 пробіли відступу)
    "1. пункт"                -> number, вкладеність так само відступом
    звичайний рядок           -> para
    "**жирний**"              -> діапазон bold усередині будь-якого з них
    "==важливе=="             -> діапазон highlight (жовтий маркер)
    "++означення++"           -> діапазон definition (зелений маркер)
    "!!попередження!!"        -> діапазон warning (рожевий маркер)
    "| a | b |\n| - | - |"    -> table, рядки клітинок (GFM-таблиця)
    "@@diagram ... @@"        -> diagram, список ребер "Вузол -> Вузол"

Docs — лінійний документ: намалювати довільні стрілки чи рамки з рукописних
конспектів неможливо. Вкладеність списків (рівень) — це заміна дерева/мапи
думок: ієрархія через відступ замість стрілок на папері. Таблиця і діаграма —
єдині виключення: вони вже структуровані самі по собі, тому несуть власні
поля (rows/edges) замість одного рядка тексту.
"""

import re
from dataclasses import dataclass, field

_MARK_RE = re.compile(
    r"\*\*(?P<bold>.+?)\*\*|==(?P<highlight>.+?)==|"
    r"\+\+(?P<definition>.+?)\+\+|!!(?P<warning>.+?)!!",
    re.DOTALL,
)
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^( {0,8})[-*•]\s+(.*)$")
_NUMBER_RE = re.compile(r"^( {0,8})\d+[.)]\s+(.*)$")
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_DIAGRAM_START = "@@diagram"
_DIAGRAM_END = "@@"
_EDGE_RE = re.compile(r"^\s*(.+?)\s*->\s*(.+?)\s*$")

_MAX_LEVEL = 3
_INDENT_PER_LEVEL = 2  # пробілів відступу на один рівень вкладеності списку
_MAX_DIAGRAM_LINES = 60  # запобіжник: один поганий фрагмент не захопить парсер


@dataclass
class Block:
    kind: str  # "heading" | "bullet" | "number" | "para" | "table" | "diagram"
    text: str = ""
    level: int = 1  # для heading: 1-3 (H1-H3); для bullet/number: вкладеність 1-3
    bold: list[tuple[int, int]] = field(default_factory=list)  # (start, end) у символах
    highlight: list[tuple[int, int]] = field(default_factory=list)
    warning: list[tuple[int, int]] = field(default_factory=list)
    definition: list[tuple[int, int]] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)  # kind == "table"
    edges: list[tuple[str, str]] = field(default_factory=list)  # kind == "diagram"


MARK_KINDS = ("bold", "highlight", "definition", "warning")


def _extract_marks(line: str) -> tuple[str, dict[str, list[tuple[int, int]]]]:
    """Витягує розмітку, повертає (чистий текст, діапазони за типом).

    Один прохід зліва направо — тому позиції різних типів не зсувають одна
    одну. Словник замість кортежу з чотирьох списків: додати новий маркер
    тепер означає рядок у регулярці, а не зміну сигнатури всюди.
    """
    out: list[str] = []
    spans: dict[str, list[tuple[int, int]]] = {kind: [] for kind in MARK_KINDS}

    pos = 0
    for m in _MARK_RE.finditer(line):
        out.append(line[pos : m.start()])
        start = sum(len(p) for p in out)

        kind = next(k for k in MARK_KINDS if m.group(k) is not None)
        inner = m.group(kind).strip()
        out.append(inner)
        spans[kind].append((start, start + len(inner)))
        pos = m.end()

    out.append(line[pos:])
    return "".join(out), spans


def _strip_stray_markup(text: str) -> str:
    """Прибирає недопарені зірочки/підкреслення/розмітку, щоб вони не текли в документ."""
    for marker in ("**", "__", "==", "++", "!!"):
        text = text.replace(marker, "")
    return text.strip()


def _split_table_row(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [_strip_stray_markup(_extract_marks(cell)[0]) for cell in inner.split("|")]


def parse(md: str) -> list[Block]:
    lines = (md or "").splitlines()
    blocks: list[Block] = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i].rstrip()
        stripped = line.strip()

        if stripped == _DIAGRAM_START:
            edges: list[tuple[str, str]] = []
            i += 1
            limit = i + _MAX_DIAGRAM_LINES
            while i < n and lines[i].strip() != _DIAGRAM_END and i < limit:
                m = _EDGE_RE.match(lines[i])
                if m:
                    edges.append((m.group(1).strip(), m.group(2).strip()))
                i += 1
            if i < n and lines[i].strip() == _DIAGRAM_END:
                i += 1
            if edges:
                blocks.append(Block(kind="diagram", edges=edges))
            continue

        if (
            _TABLE_ROW_RE.match(line)
            and i + 1 < n
            and _TABLE_SEP_RE.match(lines[i + 1].strip())
        ):
            rows = [_split_table_row(line)]
            i += 2  # пропускаємо рядок-роздільник "| --- | --- |"
            while i < n and _TABLE_ROW_RE.match(lines[i].rstrip()):
                rows.append(_split_table_row(lines[i].rstrip()))
                i += 1
            blocks.append(Block(kind="table", rows=rows))
            continue

        if not stripped:
            i += 1
            continue

        kind = "para"
        body = line
        level = 1

        m = _HEADING_RE.match(line)
        if m:
            kind, level, body = "heading", min(len(m.group(1)), _MAX_LEVEL), m.group(2)
        else:
            m = _BULLET_RE.match(line)
            if m:
                kind, body = "bullet", m.group(2)
                level = min(_MAX_LEVEL, 1 + len(m.group(1)) // _INDENT_PER_LEVEL)
            else:
                m = _NUMBER_RE.match(line)
                if m:
                    kind, body = "number", m.group(2)
                    level = min(_MAX_LEVEL, 1 + len(m.group(1)) // _INDENT_PER_LEVEL)

        text, spans = _extract_marks(body)
        text = _strip_stray_markup(text)
        i += 1
        if not text:
            continue

        # У заголовку додаткові виділення зайві — стиль заголовка вже виділяє його.
        if kind == "heading":
            spans = {k: [] for k in MARK_KINDS}

        # Захист від зсуву діапазонів, якщо _strip_stray_markup щось прибрав.
        spans = {
            k: [(s, e) for s, e in v if 0 <= s < e <= len(text)] for k, v in spans.items()
        }

        blocks.append(Block(kind=kind, text=text, level=level, **spans))

    return blocks
