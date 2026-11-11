"""Study export rendering (spec 14, D-100): pure functions from a material to file bytes.

Nothing here touches the database, storage or the network. Content is untrusted (it came from a
model and from user edits), so:
- CSV cells that a spreadsheet could read as a formula are neutralised (`csv_safe`);
- the PDF is drawn from plain text only (no HTML or Markdown is ever interpreted) after control
  characters are removed;
- Markdown output escapes HTML and link syntax; DOCX gets plain paragraphs (XML is escaped).
Quiz and question-bank exports are built from the public view and never carry answer keys,
explanations or rubrics (D-94, spec 21.4).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Any

FORMATS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "summary": ("pdf", "docx", "md"),
    "study_guide": ("pdf", "docx", "md"),
    "flashcards": ("csv", "pdf"),
    "quiz": ("pdf",),
    "glossary": ("csv", "pdf"),
    "formula_sheet": ("pdf",),
    "question_bank": ("csv", "pdf"),
}
CONTENT_TYPES = {
    "pdf": "application/pdf",
    "csv": "text/csv; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_EXPORT_BYTES = 20 * 1024 * 1024

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f  ‪-‮⁦-⁩]")
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r", "\n")


def clean_text(value: object) -> str:
    """Printable text only: control and bidirectional-override characters are removed."""
    return _CONTROL.sub("", "" if value is None else str(value))


def csv_safe(value: object) -> str:
    """Neutralise spreadsheet formula injection: a cell that starts with `=`, `+`, `-`, `@`, tab,
    CR or LF (also after leading spaces) gets a leading apostrophe so it is read as text."""
    text = clean_text(value) if not isinstance(value, str) else _CONTROL.sub("", value)
    probe = text.lstrip(" ")
    if probe.startswith(_FORMULA_START) or text.startswith(_FORMULA_START):
        return "'" + text
    return text


def md_escape(value: object) -> str:
    text = clean_text(value)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for ch in ("\\", "`", "*", "_", "[", "]", "#"):
        text = text.replace(ch, "\\" + ch)
    return text


@dataclass(frozen=True)
class Block:
    kind: str  # "title" | "h1" | "h2" | "p" | "bullet"
    text: str


@dataclass(frozen=True)
class ExportInput:
    resource_type: str
    title: str
    payload: dict[str, Any]
    cards: list[dict[str, Any]]  # flashcards: front/back/explanation/card_type/difficulty
    questions: list[dict[str, Any]]  # quiz: public view only


def _heading(items: list[Block], text: str, level: str = "h1") -> None:
    if text:
        items.append(Block(level, text))


def _para(items: list[Block], text: object) -> None:
    value = clean_text(text).strip()
    if value:
        items.append(Block("p", value))


def _bullets(items: list[Block], values: object) -> None:
    for v in values if isinstance(values, list) else []:
        text = clean_text(v).strip()
        if text:
            items.append(Block("bullet", text))


def _question_blocks(items: list[Block], questions: list[dict[str, Any]]) -> None:
    for i, q in enumerate(questions, start=1):
        meta = " / ".join(
            clean_text(x)
            for x in (q.get("question_type"), q.get("difficulty"), q.get("topic"))
            if x
        )
        items.append(Block("h2", f"Question {i}" + (f" ({meta})" if meta else "")))
        _para(items, q.get("question"))
        for opt in q.get("options") or []:
            items.append(
                Block("bullet", f"{clean_text(opt.get('id'))}. {clean_text(opt.get('text'))}")
            )


def to_blocks(data: ExportInput) -> list[Block]:
    p, kind = data.payload, data.resource_type
    out: list[Block] = [Block("title", clean_text(data.title) or "Study material")]
    if kind == "summary":
        for s in p.get("sections", []):
            _heading(out, clean_text(s.get("heading")))
            _para(out, s.get("body"))
            _bullets(out, s.get("bullets"))
    elif kind == "study_guide":
        _para(out, p.get("overview"))
        if p.get("learning_objectives"):
            _heading(out, "Learning objectives")
            _bullets(out, [o.get("text") for o in p["learning_objectives"]])
        if p.get("prerequisites"):
            _heading(out, "Prerequisites")
            _bullets(out, p["prerequisites"])
        for s in p.get("sections", []):
            _heading(out, clean_text(s.get("heading")), "h1" if s.get("level", 1) == 1 else "h2")
            _para(out, s.get("body"))
            _bullets(out, s.get("bullets"))
        if p.get("key_takeaways"):
            _heading(out, "Key takeaways")
            _bullets(out, p["key_takeaways"])
        if p.get("practice_questions"):
            _heading(out, "Practice questions")
            _bullets(out, [q.get("question") for q in p["practice_questions"]])
    elif kind == "glossary":
        for t in p.get("terms", []):
            _heading(out, clean_text(t.get("term")), "h2")
            _para(out, t.get("definition"))
            _para(out, t.get("explanation"))
            if t.get("example"):
                _para(out, "Example: " + clean_text(t["example"]))
    elif kind == "formula_sheet":
        _para(
            out, "Formulas are unverified: check them against your source before relying on them."
        )
        for f in p.get("formulas", []):
            _heading(out, clean_text(f.get("name")), "h2")
            _para(out, clean_text(f.get("expression")))  # LaTeX source as plain text
            _para(out, f.get("explanation"))
            _bullets(
                out,
                [
                    f"{clean_text(v.get('symbol'))}: {clean_text(v.get('meaning'))}"
                    + (f" ({clean_text(v['unit'])})" if v.get("unit") else "")
                    for v in f.get("variables", [])
                ],
            )
            if f.get("conditions"):
                _para(out, "Conditions: " + clean_text(f["conditions"]))
            if f.get("needs_review"):
                _para(out, "Needs review.")
    elif kind == "flashcards":
        for i, c in enumerate(data.cards, start=1):
            _heading(out, f"Card {i}", "h2")
            _para(out, "Front: " + clean_text(c.get("front")))
            _para(out, "Back: " + clean_text(c.get("back")))
            if c.get("explanation"):
                _para(out, "Explanation: " + clean_text(c["explanation"]))
    elif kind == "quiz":
        _para(out, p.get("description"))
        _question_blocks(out, data.questions)
    elif kind == "question_bank":
        _question_blocks(out, p.get("questions", []))
    return out


def render_csv(data: ExportInput) -> bytes:
    """Flashcards, glossary and question bank. Every cell goes through `csv_safe`."""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n")
    p = data.payload
    if data.resource_type == "flashcards":
        writer.writerow(["front", "back", "explanation", "card_type", "difficulty"])
        for c in data.cards:
            writer.writerow(
                csv_safe(c.get(k))
                for k in ("front", "back", "explanation", "card_type", "difficulty")
            )
    elif data.resource_type == "glossary":
        writer.writerow(["term", "definition", "explanation", "example", "topic", "related_terms"])
        for t in p.get("terms", []):
            row = [
                csv_safe(t.get(k))
                for k in ("term", "definition", "explanation", "example", "topic")
            ]
            row.append(csv_safe("; ".join(clean_text(r) for r in t.get("related_terms", []))))
            writer.writerow(row)
    elif data.resource_type == "question_bank":
        writer.writerow(["question", "question_type", "difficulty", "topic", "options"])
        for q in p.get("questions", []):
            options = " | ".join(
                f"{clean_text(o.get('id'))}: {clean_text(o.get('text'))}"
                for o in q.get("options", [])
            )
            writer.writerow(
                [
                    csv_safe(q.get("question")),
                    csv_safe(q.get("question_type")),
                    csv_safe(q.get("difficulty")),
                    csv_safe(q.get("topic")),
                    csv_safe(options),
                ]
            )
    else:
        raise ValueError("unsupported")
    return buf.getvalue().encode("utf-8")


def render_markdown(data: ExportInput) -> bytes:
    lines: list[str] = []
    for b in to_blocks(data):
        text = md_escape(b.text)
        if b.kind == "title":
            lines += [f"# {text}", ""]
        elif b.kind == "h1":
            lines += [f"## {text}", ""]
        elif b.kind == "h2":
            lines += [f"### {text}", ""]
        elif b.kind == "bullet":
            lines.append(f"- {text}")
        else:
            lines += [text, ""]
    return ("\n".join(lines).strip() + "\n").encode("utf-8")


def render_docx(data: ExportInput) -> bytes:
    from docx import Document

    doc = Document()
    for b in to_blocks(data):
        text = clean_text(b.text)
        if b.kind == "title":
            doc.add_heading(text, level=0)
        elif b.kind == "h1":
            doc.add_heading(text, level=1)
        elif b.kind == "h2":
            doc.add_heading(text, level=2)
        elif b.kind == "bullet":
            doc.add_paragraph(text, style="List Bullet")
        else:
            doc.add_paragraph(text)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


_STYLE = {"title": 20.0, "h1": 15.0, "h2": 12.5, "p": 10.5, "bullet": 10.5}


def _latin(text: str) -> str:
    """The built-in PDF font is Latin-1; anything else is shown as `?` rather than dropped."""
    return clean_text(text).encode("latin-1", "replace").decode("latin-1")


def render_pdf(data: ExportInput) -> bytes:
    """Plain-text PDF drawn directly (no HTML engine, no links, no embedded content)."""
    import pymupdf

    doc = pymupdf.open()
    width, height, margin = 595.0, 842.0, 54.0
    state = {"page": doc.new_page(width=width, height=height), "y": margin}

    def write(text: str, size: float, *, indent: float = 0.0, bold: bool = False) -> None:
        font = "hebo" if bold else "helv"
        max_w = width - 2 * margin - indent
        words, line = _latin(text).replace("\n", " ").split(" "), ""
        lines: list[str] = []
        for w in words:
            while pymupdf.get_text_length(w, fontname=font, fontsize=size) > max_w:
                cut = max(1, int(len(w) * max_w / pymupdf.get_text_length(w, font, size)))
                if line:
                    lines.append(line)
                    line = ""
                lines.append(w[:cut])
                w = w[cut:]
            probe = f"{line} {w}".strip()
            if pymupdf.get_text_length(probe, fontname=font, fontsize=size) <= max_w:
                line = probe
            else:
                lines.append(line)
                line = w
        lines.append(line)
        for ln in lines:
            if state["y"] + size * 1.3 > height - margin:
                state["page"] = doc.new_page(width=width, height=height)
                state["y"] = margin
            state["y"] += size * 1.3
            state["page"].insert_text(
                (margin + indent, state["y"]), ln, fontsize=size, fontname=font
            )
        state["y"] += size * 0.45

    for b in to_blocks(data):
        if b.kind == "bullet":
            write("- " + b.text, _STYLE["bullet"], indent=12)
        else:
            write(b.text, _STYLE[b.kind], bold=b.kind != "p")
    out = doc.tobytes()
    doc.close()
    return bytes(out)


def render(fmt: str, data: ExportInput) -> bytes:
    if fmt not in FORMATS_BY_TYPE.get(data.resource_type, ()):
        raise ValueError("unsupported")
    content = {
        "pdf": render_pdf,
        "csv": render_csv,
        "md": render_markdown,
        "docx": render_docx,
    }[fmt](data)
    if len(content) > MAX_EXPORT_BYTES:
        raise ValueError("too large")
    return content
