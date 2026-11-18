"""Рендер mdlite.Block у різні формати: markdown-файл, .docx, HTML для GUI.

Один спільний прохід "розріж текст блоку на шматки за межами
bold/highlight/warning" (_split_spans) живить усі три рендери, щоб форматування
ніде не розійшлось між тим, що бачить користувач у вікні, і тим, що він
отримує в експортованому файлі.
"""

from pathlib import Path

from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.shared import RGBColor

from mdlite import Block

_HEADING_PREFIX = {1: "#", 2: "##", 3: "###"}

# Семантика розмітки -> ключ маркера в палітрі теми (gui.theme.MARKERS).
_SEMANTIC_MARKER = {"highlight": "yellow", "definition": "green", "warning": "rose"}


def _split_spans(block: Block) -> list[tuple[str, str | None]]:
    """[(шматок_тексту, тип_або_None)] у порядку зліва-направо.

    Типи в mdlite не перетинаються (кожен промпт дає Claude рівно один шар
    розмітки на діапазон), тож просто зливаємо всі межі й сортуємо.
    """
    cuts = {0, len(block.text)}
    spans: dict[tuple[int, int], str] = {}
    for kind, ranges in (
        ("bold", block.bold),
        ("highlight", block.highlight),
        ("definition", block.definition),
        ("warning", block.warning),
    ):
        for s, e in ranges:
            cuts.add(s)
            cuts.add(e)
            spans[(s, e)] = kind

    bounds = sorted(cuts)
    pieces: list[tuple[str, str | None]] = []
    for start, end in zip(bounds, bounds[1:]):
        if start >= end:
            continue
        kind = spans.get((start, end))
        pieces.append((block.text[start:end], kind))
    return pieces or [(block.text, None)]


def diagram_chains(edges: list[tuple[str, str]]) -> list[list[str]]:
    """Розкладає ребра діаграми на послідовні ланцюжки вузлів.

    Не повноцінний граф-лейаут — лекційні схеми майже завжди лінійні чи
    невеликі дерева, тож досить пройти від "коренів" (вузлів без вхідних
    ребер) і йти за стрілками; розгалуження дає кілька ланцюжків з однаковим
    префіксом. depth-запобіжник рятує від випадкового циклу в тексті Claude.
    """
    next_map: dict[str, list[str]] = {}
    has_incoming: set[str] = set()
    order: list[str] = []
    for a, b in edges:
        next_map.setdefault(a, []).append(b)
        has_incoming.add(b)
        for node in (a, b):
            if node not in order:
                order.append(node)

    roots = [n for n in order if n not in has_incoming] or order[:1]
    chains: list[list[str]] = []

    def walk(node: str, prefix: list[str], depth: int) -> None:
        path = prefix + [node]
        children = next_map.get(node, [])
        if not children or depth > 40:
            chains.append(path)
            return
        for child in children:
            walk(child, path, depth + 1)

    seen = set()
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        walk(root, [], 0)

    return chains or [order]


# --------------------------------------------------------------------- markdown


def blocks_to_markdown(blocks: list[Block]) -> str:
    lines = []
    for b in blocks:
        if b.kind == "table":
            lines.extend(_table_to_markdown(b.rows))
        elif b.kind == "diagram":
            for chain in diagram_chains(b.edges):
                lines.append(" → ".join(chain))
                lines.append("")
        else:
            text = _markup_text(b)
            if b.kind == "heading":
                lines.append(f"{_HEADING_PREFIX.get(b.level, '#')} {text}")
            elif b.kind == "bullet":
                lines.append("  " * (b.level - 1) + f"- {text}")
            elif b.kind == "number":
                lines.append("  " * (b.level - 1) + f"1. {text}")
            else:
                lines.append(text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _table_to_markdown(rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    out = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join("---" for _ in rows[0]) + " |"]
    for row in rows[1:]:
        out.append("| " + " | ".join(row) + " |")
    return out


def _markup_text(block: Block) -> str:
    out = []
    wrap = {"bold": "**", "highlight": "==", "definition": "++", "warning": "!!"}
    for piece, kind in _split_spans(block):
        mark = wrap.get(kind or "")
        out.append(f"{mark}{piece}{mark}" if mark else piece)
    return "".join(out)


# ------------------------------------------------------------------------ docx

_WARNING_RED = RGBColor(0xB0, 0x14, 0x14)
_LIST_STYLE = {"bullet": "List Bullet", "number": "List Number"}


def blocks_to_docx(blocks: list[Block], title: str, path: Path | str) -> None:
    doc = Document()
    doc.add_heading(title, level=0)

    for b in blocks:
        if b.kind == "table":
            _add_docx_table(doc, b.rows)
            continue
        if b.kind == "diagram":
            for chain in diagram_chains(b.edges):
                p = doc.add_paragraph()
                p.add_run(" → ".join(chain)).italic = True
            continue

        if b.kind == "heading":
            p = doc.add_heading("", level=min(b.level, 3))
        elif b.kind in _LIST_STYLE:
            style = f"{_LIST_STYLE[b.kind]} {b.level}" if b.level > 1 else _LIST_STYLE[b.kind]
            try:
                p = doc.add_paragraph(style=style)
            except KeyError:
                p = doc.add_paragraph(style=_LIST_STYLE[b.kind])
        else:
            p = doc.add_paragraph()

        for piece, kind in _split_spans(b):
            run = p.add_run(piece)
            if kind == "bold":
                run.bold = True
            elif kind == "highlight":
                run.font.highlight_color = WD_COLOR_INDEX.YELLOW
            elif kind == "definition":
                run.font.highlight_color = WD_COLOR_INDEX.BRIGHT_GREEN
            elif kind == "warning":
                run.bold = True
                run.font.color.rgb = _WARNING_RED
                run.font.highlight_color = WD_COLOR_INDEX.PINK

    doc.save(str(path))


def _add_docx_table(doc: Document, rows: list[list[str]]) -> None:
    if not rows:
        return
    ncols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=ncols)
    try:
        table.style = "Light Grid Accent 1"
    except KeyError:
        pass
    for r, row in enumerate(rows):
        for c in range(ncols):
            cell_text = row[c] if c < len(row) else ""
            cell = table.cell(r, c)
            cell.text = cell_text
            if r == 0:
                for p in cell.paragraphs:
                    for run in p.runs:
                        run.bold = True


# ------------------------------------------------------------------------ HTML
# Для рендеру в QTextEdit (gui/notes_panel.py). Кольори передаються ззовні,
# бо залежать від активної теми (dark/light).


def block_to_html(block: Block, colors: dict) -> str:
    if block.kind == "table":
        return _table_to_html(block.rows, colors)
    if block.kind == "diagram":
        return _diagram_to_html(block.edges, colors)

    inner = "".join(_html_span(piece, kind, colors) for piece, kind in _split_spans(block))
    if block.kind == "heading":
        # Справжній <h1-3>, а не стилізований <p> — щоб QTextDocument.toMarkdown()
        # (ручні правки студента, local_notes._richtext_to_markdown) розпізнавав
        # це як заголовок ("# ...."), а не губив рівень до жирного тексту.
        tag = f"h{min(block.level, 3)}"
        return (
            f'<{tag} style="font-family:\'Playfair Display\',serif; '
            f'color:{colors["heading"]}; margin:14px 0 6px 0;">{inner}</{tag}>'
        )
    if block.kind in ("bullet", "number"):
        indent = 18 * block.level
        marker = "•" if block.kind == "bullet" else "1."
        return (
            f'<p style="margin:2px 0 2px {indent}px; color:{colors["text"]};">'
            f"{marker} {inner}</p>"
        )
    return f'<p style="margin:6px 0; color:{colors["text"]};">{inner}</p>'


def _html_span(text: str, kind: str | None, colors: dict) -> str:
    """Хрома застосунку монохромна, а ось зміст конспекту має колір —
    маркер працює як справжній текстовиділювач на папері.

    Колір ніколи не несе сенс сам: у застереження лишається ▲, у терміна —
    жирність. Так розмітка читається і в чорно-білому друку, і людиною з
    дальтонізмом (WCAG 1.4.1).
    """
    text = _esc(text)
    if kind == "bold":
        return f'<b style="color:{colors["heading"]};">{text}</b>'

    marker = colors["markers"].get(_SEMANTIC_MARKER.get(kind, ""))
    if marker is None:
        return text

    prefix = "▲ " if kind == "warning" else ""
    weight = "600" if kind != "highlight" else "500"
    return (
        f'<span style="background-color:{marker["bg"]}; color:{marker["fg"]}; '
        f'font-weight:{weight};">&nbsp;{prefix}{text}&nbsp;</span>'
    )


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _table_to_html(rows: list[list[str]], colors: dict) -> str:
    if not rows:
        return ""
    border = colors.get("border", colors["text"])
    head, *body = rows
    thead = "".join(
        f'<th style="text-align:left; padding:6px 10px; border:1px solid {border}; '
        f'color:{colors["heading"]};">{_esc(cell)}</th>'
        for cell in head
    )
    trs = "".join(
        "<tr>"
        + "".join(
            f'<td style="padding:6px 10px; border:1px solid {border}; '
            f'color:{colors["text"]};">{_esc(cell)}</td>'
            for cell in row
        )
        + "</tr>"
        for row in body
    )
    return (
        f'<table cellspacing="0" style="border-collapse:collapse; margin:10px 0;">'
        f"<tr>{thead}</tr>{trs}</table>"
    )


def _diagram_to_html(edges: list[tuple[str, str]], colors: dict) -> str:
    # Жодних кольорових "чіпів" — вузол це напівжирний підкреслений текст,
    # стрілка між ними тьмяна, вся схема лишається чистим текстом.
    chains = diagram_chains(edges)
    rows = []
    for chain in chains:
        parts = []
        for idx, node in enumerate(chain):
            parts.append(
                f'<span style="font-weight:600; color:{colors["heading"]}; '
                f'text-decoration:underline;">{_esc(node)}</span>'
            )
            if idx < len(chain) - 1:
                parts.append(f'<span style="color:{colors["text_dim"]};">&nbsp;→&nbsp;</span>')
        rows.append(f'<p style="margin:6px 0;">{"".join(parts)}</p>')
    return "".join(rows)
