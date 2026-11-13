"""Draft helpers (Phase 7 M7.9, spec 31). Pure functions, no model call.

A citation in a draft is the marker `{{cite:<paper id>}}`. The marker is what is stored, so a
citation stays connected to its paper however the text is edited; it is turned into an in-text
citation and a reference list only when the draft is previewed or exported.

The evidence check is lexical and deliberately conservative: a sentence counts as supported by a
cited paper when it shares at least two topic terms with one of that paper's analysed claims. It
finds citations that do not match their sentence and claim-like sentences with no citation; it does
not prove a statement true.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field

from app.research.citations import Meta, format_citation, in_text, sort_key
from app.research.claims import LoadedPaper
from app.research.comparison import terms_of

SECTION_HEADINGS: dict[str, str] = {
    "title": "Research title",
    "abstract": "Abstract",
    "introduction": "Introduction",
    "background": "Background",
    "literature_review": "Literature review",
    "problem_statement": "Problem statement",
    "objectives": "Research objectives",
    "research_questions": "Research questions",
    "methodology": "Methodology",
    "proposed_approach": "Proposed approach",
    "results": "Results",
    "discussion": "Discussion",
    "limitations": "Limitations",
    "conclusion": "Conclusion",
    "future_work": "Future work",
    "references": "References",
}

# Which analysed sections of the papers are useful evidence for a draft section.
SECTION_EVIDENCE: dict[str, tuple[str, ...]] = {
    "abstract": ("research_problem", "objectives", "methodology", "results", "contributions"),
    "introduction": ("research_problem", "objectives", "contributions"),
    "background": ("research_problem", "methodology", "contributions"),
    "literature_review": ("methodology", "results", "contributions", "limitations"),
    "problem_statement": ("research_problem", "limitations", "future_work"),
    "objectives": ("objectives", "research_problem"),
    "research_questions": ("objectives", "research_problem", "future_work"),
    "methodology": ("methodology", "dataset", "evaluation"),
    "proposed_approach": ("methodology", "contributions", "limitations"),
    "results": ("results", "evaluation", "dataset"),
    "discussion": ("results", "limitations", "contributions"),
    "limitations": ("limitations",),
    "conclusion": ("contributions", "results", "future_work"),
    "future_work": ("future_work", "limitations"),
}

CITE = re.compile(
    r"\{\{cite:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12})\}\}"
)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\[{(\"“])")
_CUES = (
    "show",
    "demonstrat",
    "found that",
    "finds that",
    "outperform",
    "improv",
    "achiev",
    "reduc",
    "increas",
    "decreas",
    "significant",
    "evidence",
    "report",
    "propos",
    "indicate",
    "reveal",
    "confirm",
    "prove",
    "study",
    "studies",
    "research has",
    "according to",
)
_NUMBER = re.compile(r"\d")
MIN_SHARED_TERMS = 2
MAX_SENTENCE_CHARS = 400


def cited_ids(content: str) -> list[uuid.UUID]:
    """Paper ids cited in the text, in order of first appearance, each once."""
    seen: dict[uuid.UUID, None] = {}
    for m in CITE.finditer(content):
        seen.setdefault(uuid.UUID(m.group(1)), None)
    return list(seen)


def marker(paper_id: uuid.UUID) -> str:
    return "{{cite:" + str(paper_id) + "}}"


def strip_markers(text: str) -> str:
    return " ".join(CITE.sub(" ", text).split())


def split_sentences(content: str) -> list[str]:
    """Sentences of the body text. Headings, blank lines and list bullets' markers are skipped."""
    out: list[str] = []
    for line in content.splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        text = re.sub(r"^([-*+]|\d+[.)])\s+", "", text)
        for part in _SENTENCE_END.split(text):
            part = part.strip()
            if part:
                out.append(part)
    return out


def is_claim_like(sentence: str) -> bool:
    low = strip_markers(sentence).casefold()
    return bool(_NUMBER.search(low)) or any(c in low for c in _CUES)


@dataclass
class SentenceCheck:
    text: str
    status: str
    paper_ids: list[uuid.UUID] = field(default_factory=list)


STATUSES = (
    "supported_single",
    "supported_multiple",
    "citation_mismatch",
    "cannot_verify",
    "invalid_reference",
    "unsupported",
    "unmarked",
)


def check_sentences(
    content: str,
    project_paper_ids: set[uuid.UUID],
    analysed: Mapping[uuid.UUID, LoadedPaper],
) -> list[SentenceCheck]:
    """Classify each sentence of the draft.

    supported_single / supported_multiple: every citation is a project paper and at least one (or
    two distinct) cited paper's analysis shares topic terms with the sentence.
    citation_mismatch: cited papers are analysed but none matches the sentence.
    cannot_verify: cited papers exist but have no completed analysis.
    invalid_reference: a marker that is not a paper of this project.
    unsupported: no citation, but the sentence reads like a finding (a number or a reporting verb).
    unmarked: no citation and not claim-like (interpretation, transition or plain prose).
    """
    results: list[SentenceCheck] = []
    for raw in split_sentences(content):
        ids = cited_ids(raw)
        shown = strip_markers(raw)[:MAX_SENTENCE_CHARS]
        if not ids:
            status = "unsupported" if is_claim_like(raw) else "unmarked"
            results.append(SentenceCheck(shown, status))
            continue
        if any(i not in project_paper_ids for i in ids):
            results.append(SentenceCheck(shown, "invalid_reference", ids))
            continue
        terms = terms_of(strip_markers(raw))
        matching: list[uuid.UUID] = []
        verifiable = False
        for pid in ids:
            paper = analysed.get(pid)
            if paper is None:
                continue
            verifiable = True
            if any(len(terms & terms_of(c.text)) >= MIN_SHARED_TERMS for c in paper.claims):
                matching.append(pid)
        if not verifiable:
            status = "cannot_verify"
        elif len(matching) >= 2:
            status = "supported_multiple"
        elif matching:
            status = "supported_single"
        else:
            status = "citation_mismatch"
        results.append(SentenceCheck(shown, status, ids))
    return results


def summarise(checks: list[SentenceCheck]) -> dict[str, int]:
    counts = dict.fromkeys(STATUSES, 0)
    for c in checks:
        counts[c.status] += 1
    return counts


_REF_HEADING = re.compile(r"^#{1,6}\s*references\s*$", re.IGNORECASE)
_ANY_HEADING = re.compile(r"^#{1,6}\s")


def _drop_references_section(content: str) -> str:
    out: list[str] = []
    skipping = False
    for line in content.splitlines():
        if _REF_HEADING.match(line.strip()):
            skipping = True
            continue
        if skipping and _ANY_HEADING.match(line.strip()):
            skipping = False
        if not skipping:
            out.append(line)
    return "\n".join(out).rstrip()


@dataclass
class Rendered:
    markdown: str
    cited: list[uuid.UUID]
    invalid: list[uuid.UUID]


def render_markdown(
    title: str, content: str, metas: Mapping[uuid.UUID, Meta], style: str
) -> Rendered:
    """The draft with every citation marker resolved and a generated reference list. Markers of
    papers that are not in `metas` stay out of the text as "[unknown reference]" and are reported
    in `invalid` (the exporter refuses to export while any exist)."""
    ids = cited_ids(content)
    invalid = [i for i in ids if i not in metas]
    valid = [i for i in ids if i in metas]
    if style == "ieee":
        numbers = {pid: n for n, pid in enumerate(valid, start=1)}
    else:
        numbers = {}

    def replace(m: re.Match[str]) -> str:
        pid = uuid.UUID(m.group(1))
        if pid not in metas:
            return "[unknown reference]"
        return in_text(style, metas[pid], numbers.get(pid))

    body = CITE.sub(replace, _drop_references_section(content))
    if style == "ieee":
        ordered = valid
    else:
        ordered = sorted(valid, key=lambda pid: sort_key(metas[pid]))
    lines = []
    for n, pid in enumerate(ordered, start=1):
        text = format_citation(style, metas[pid])
        lines.append(f"[{n}] {text}" if style == "ieee" else text)
    parts = [f"# {title}", "", body.strip()]
    if lines:
        parts += ["", "## References", "", "\n\n".join(lines)]
    return Rendered("\n".join(parts).strip() + "\n", valid, invalid)
