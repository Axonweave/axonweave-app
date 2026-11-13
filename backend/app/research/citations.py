"""Citation formatting and metadata validation (Phase 7 M7.8, spec 30). Pure functions.

A standards-based implementation of five styles for a journal or conference article, written here
because the application has no citation library and a model must never format citations or invent
metadata (spec 30.1). Missing details are left out, never filled in; the validator reports them.
Output is plain text. Author names are read as "Family, Given" or "Given Family"; name particles
("van der") and organisations are not specially handled, so the validator asks the researcher to
check single-word names.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Any

STYLES = ("apa", "ieee", "mla", "chicago", "harvard")
STYLE_LABELS = {
    "apa": "APA 7",
    "ieee": "IEEE",
    "mla": "MLA 9",
    "chicago": "Chicago (author-date)",
    "harvard": "Harvard",
}

_DOI = re.compile(r"^10\.\d{4,9}/\S+$")
_PAGES = re.compile(r"^[A-Za-z]?\d+\s*[-–—]\s*[A-Za-z]?\d+$|^[A-Za-z]?\d+$")
_SPLIT_GIVEN = re.compile(r"[\s]+")


@dataclass(frozen=True)
class Meta:
    authors: tuple[str, ...]
    title: str
    year: int | None = None
    venue: str | None = None
    publisher: str | None = None
    doi: str | None = None
    url: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    accessed: date | None = None
    verified: bool = False

    def snapshot(self) -> dict[str, Any]:
        out = asdict(self)
        out["authors"] = list(self.authors)
        out["accessed"] = self.accessed.isoformat() if self.accessed else None
        return out

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> Meta:
        accessed = data.get("accessed")
        return cls(
            authors=tuple(data.get("authors") or ()),
            title=data.get("title") or "",
            year=data.get("year"),
            venue=data.get("venue"),
            publisher=data.get("publisher"),
            doi=data.get("doi"),
            url=data.get("url"),
            volume=data.get("volume"),
            issue=data.get("issue"),
            pages=data.get("pages"),
            accessed=date.fromisoformat(accessed) if accessed else None,
            verified=bool(data.get("verified")),
        )


@dataclass(frozen=True)
class Name:
    family: str
    given: tuple[str, ...]  # given names as written

    @property
    def initials(self) -> list[str]:
        return [g[0].upper() for g in self.given if g]


def parse_name(raw: str) -> Name:
    text = " ".join(raw.split())
    if "," in text:
        family, _, given = text.partition(",")
        return Name(family.strip(), tuple(p for p in _SPLIT_GIVEN.split(given.strip()) if p))
    parts = text.split(" ")
    return Name(parts[-1], tuple(parts[:-1]))


def _names(meta: Meta) -> list[Name]:
    return [parse_name(a) for a in meta.authors if a.strip()]


def _doi_url(doi: str) -> str:
    return f"https://doi.org/{doi}"


def _join(items: Sequence[str], last: str) -> str:
    if len(items) <= 1:
        return "".join(items)
    if len(items) == 2:
        return f"{items[0]} {last} {items[1]}"
    return ", ".join(items[:-1]) + f", {last} {items[-1]}"


def _end(text: str) -> str:
    return text if text.endswith((".", "?", "!")) else text + "."


def _pages(p: str) -> str:
    return re.sub(r"\s*[-–—]\s*", "–", p.strip())


def _locator(meta: Meta, *, paren_issue: bool = True) -> str:
    out = meta.volume or ""
    if meta.issue:
        out += f"({meta.issue})" if paren_issue else f", no. {meta.issue}"
    return out


def _initials(n: Name, dots: str = ". ") -> str:
    return dots.join(n.initials) + "." if n.initials else ""


def _family_initials(n: Name) -> str:
    ini = _initials(n)
    return f"{n.family}, {ini}" if ini else n.family


def _apa(meta: Meta) -> str:
    names = _names(meta)
    shown = [_family_initials(n) for n in names]
    if len(shown) > 20:
        who = ", ".join(shown[:19]) + ", … " + shown[-1]
    elif len(shown) > 1:
        who = ", ".join(shown[:-1]) + ", & " + shown[-1]
    else:
        who = "".join(shown)
    year = f"({meta.year})" if meta.year else "(n.d.)"
    if who:
        parts = [_end(who), f"{year}.", _end(meta.title)]
    else:  # APA moves the title to the author position when there is no author
        parts = [_end(meta.title), f"{year}."]
    if meta.venue:
        src = meta.venue
        loc = _locator(meta)
        if loc:
            src += f", {loc}"
        if meta.pages:
            src += f", {_pages(meta.pages)}"
        parts.append(_end(src))
    elif meta.publisher:
        parts.append(_end(meta.publisher))
    link = _doi_url(meta.doi) if meta.doi else meta.url
    if link:
        parts.append(link)
    return " ".join(parts)


def _page_label(pages: str) -> str:
    return ("pp. " if re.search(r"[-–—]", pages) else "p. ") + _pages(pages)


def _ieee(meta: Meta) -> str:
    names = _names(meta)
    fmt = [f"{_initials(n)} {n.family}" if n.initials else n.family for n in names]
    if len(fmt) > 6:
        who = fmt[0] + " et al."
    elif len(fmt) > 2:
        who = ", ".join(fmt[:-1]) + ", and " + fmt[-1]
    else:
        who = " and ".join(fmt)
    prefix = f"{who}, " if who else ""
    bits: list[str] = []
    if meta.venue:
        bits.append(meta.venue)
    if meta.volume:
        bits.append(f"vol. {meta.volume}")
    if meta.issue:
        bits.append(f"no. {meta.issue}")
    if meta.pages:
        bits.append(_page_label(meta.pages))
    if meta.year:
        bits.append(str(meta.year))
    if meta.doi:
        bits.append(f"doi: {meta.doi}")
    elif meta.url:
        bits.append(f"[Online]. Available: {meta.url}")
    if not bits:
        return f"{prefix}“{_end(meta.title)}”"
    return f"{prefix}“{meta.title},” {', '.join(bits)}."


def _mla(meta: Meta) -> str:
    names = _names(meta)
    if len(names) == 1:
        who = _mla_first(names[0])
    elif len(names) == 2:
        who = f"{_mla_first(names[0])}, and {' '.join((*names[1].given, names[1].family))}"
    elif names:
        who = f"{_mla_first(names[0])}, et al"
    else:
        who = ""
    parts = [_end(who)] if who else []
    parts.append(f"“{_end(meta.title)}”")
    tail: list[str] = []
    if meta.venue:
        tail.append(meta.venue)
    if meta.volume:
        tail.append(f"vol. {meta.volume}")
    if meta.issue:
        tail.append(f"no. {meta.issue}")
    if meta.year:
        tail.append(str(meta.year))
    if meta.pages:
        tail.append(_page_label(meta.pages))
    if tail:
        parts.append(_end(", ".join(tail)))
    link = _doi_url(meta.doi) if meta.doi else meta.url
    if link:
        parts.append(_end(link))
    return " ".join(parts)


def _mla_first(n: Name) -> str:
    return f"{n.family}, {' '.join(n.given)}" if n.given else n.family


def _chicago(meta: Meta) -> str:
    names = _names(meta)
    shown = [_mla_first(names[0])] if names else []
    shown += [" ".join((*n.given, n.family)) for n in names[1:10]]
    if len(names) > 10:
        who = ", ".join(shown) + ", et al."
    else:
        who = _join(shown, "and") if len(shown) > 2 else " and ".join(shown)
    parts = [_end(who)] if who else []
    parts.append(f"{meta.year}." if meta.year else "n.d.")
    parts.append(f"“{_end(meta.title)}”")
    if meta.venue:
        src = meta.venue
        if meta.volume:
            src += f" {meta.volume}"
        if meta.issue:
            src += f" ({meta.issue})"
        if meta.pages:
            src += f": {_pages(meta.pages)}"
        parts.append(_end(src))
    link = _doi_url(meta.doi) if meta.doi else meta.url
    if link:
        parts.append(_end(link))
    return " ".join(parts)


def _harvard(meta: Meta) -> str:
    names = _names(meta)
    shown = [f"{n.family}, {''.join(i + '.' for i in n.initials)}".rstrip(", ") for n in names]
    who = ", ".join(shown[:-1]) + f" and {shown[-1]}" if len(shown) > 1 else "".join(shown)
    year = f"({meta.year})" if meta.year else "(n.d.)"
    out = f"{who} {year}" if who else year
    out += f" ‘{meta.title}’"
    if meta.venue:
        src = f", {meta.venue}"
        loc = _locator(meta)
        if loc:
            src += f", {loc}"
        if meta.pages:
            src += ", " + _page_label(meta.pages)
        out += src
    out += "."
    if meta.doi:
        out += f" doi:{meta.doi}."
    elif meta.url:
        out += f" Available at: {meta.url}"
        if meta.accessed:
            out += f" (Accessed: {meta.accessed.strftime('%d %B %Y').lstrip('0')})"
        out += "."
    return out


_FORMATTERS = {"apa": _apa, "ieee": _ieee, "mla": _mla, "chicago": _chicago, "harvard": _harvard}


def format_citation(style: str, meta: Meta) -> str:
    return " ".join(_FORMATTERS[style](meta).split())


def _short_title(title: str) -> str:
    words = title.split()
    return " ".join(words[:4]) + ("…" if len(words) > 4 else "")


def in_text(style: str, meta: Meta, number: int | None = None) -> str:
    """The in-text form: author-year for APA/Chicago/Harvard, author for MLA, number for IEEE."""
    if style == "ieee":
        return f"[{number if number is not None else 'n'}]"
    names = _names(meta)
    year = str(meta.year) if meta.year else "n.d."
    if not names:
        label = f"“{_short_title(meta.title)}”"
        return f"({label})" if style == "mla" else f"({label}, {year})"
    fams = [n.family for n in names]
    if style == "apa":
        who = (
            fams[0]
            if len(fams) == 1
            else f"{fams[0]} & {fams[1]}"
            if len(fams) == 2
            else f"{fams[0]} et al."
        )
        return f"({who}, {year})"
    if style == "harvard":
        who = (
            fams[0]
            if len(fams) == 1
            else f"{fams[0]} and {fams[1]}"
            if len(fams) == 2
            else f"{fams[0]} et al."
        )
        return f"({who}, {year})"
    if style == "chicago":
        who = (
            fams[0]
            if len(fams) == 1
            else f"{fams[0]} and {fams[1]}"
            if len(fams) == 2
            else f"{fams[0]} et al."
        )
        return f"({who} {year})"
    who = (
        fams[0]
        if len(fams) == 1
        else f"{fams[0]} and {fams[1]}"
        if len(fams) == 2
        else f"{fams[0]} et al."
    )
    return f"({who})"


@dataclass(frozen=True)
class Issue:
    field: str
    severity: str  # missing | warning | info
    code: str
    message: str


def validate(meta: Meta, *, today: date | None = None) -> list[Issue]:
    """Metadata completeness and sanity. Nothing is guessed: each finding names what to fix."""
    today = today or datetime.now(UTC).date()
    out: list[Issue] = []
    names = _names(meta)
    if not names:
        out.append(Issue("authors", "missing", "MISSING_AUTHORS", "No authors are recorded."))
    seen: set[str] = set()
    for raw in meta.authors:
        name = parse_name(raw)
        key = (name.family + "|" + " ".join(name.given)).casefold()
        if key in seen:
            out.append(Issue("authors", "warning", "DUPLICATE_AUTHOR", f"“{raw}” is listed twice."))
        seen.add(key)
        if not name.given:
            out.append(
                Issue(
                    "authors",
                    "warning",
                    "INCOMPLETE_AUTHOR",
                    f"“{raw}” has no given name; check it is complete (and not an organisation).",
                )
            )
    if len(meta.title.strip()) < 3:
        out.append(Issue("title", "missing", "MISSING_TITLE", "The title is missing or too short."))
    if meta.year is None:
        out.append(Issue("year", "missing", "MISSING_YEAR", "No publication year is recorded."))
    elif meta.year < 1000 or meta.year > today.year + 1:
        out.append(Issue("year", "warning", "INVALID_YEAR", f"The year {meta.year} looks wrong."))
    if not meta.venue:
        out.append(
            Issue("venue", "missing", "MISSING_VENUE", "No journal or conference is recorded.")
        )
    if meta.doi:
        if not _DOI.match(meta.doi):
            out.append(
                Issue("doi", "warning", "INVALID_DOI", "The DOI is not in the form 10.xxxx/…")
            )
    elif not meta.url:
        out.append(Issue("doi", "info", "MISSING_DOI", "No DOI or URL is recorded."))
    if meta.pages:
        if not _PAGES.match(meta.pages.strip()):
            out.append(
                Issue(
                    "pages", "warning", "INVALID_PAGES", "The page information is not a page range."
                )
            )
        else:
            parts = re.split(r"\s*[-–—]\s*", meta.pages.strip())
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                if int(parts[1]) < int(parts[0]):
                    out.append(
                        Issue(
                            "pages",
                            "warning",
                            "INVALID_PAGES",
                            "The last page is before the first.",
                        )
                    )
    elif meta.venue:
        out.append(Issue("pages", "info", "MISSING_PAGES", "No page information is recorded."))
    if meta.venue and not meta.volume:
        out.append(Issue("volume", "info", "MISSING_VOLUME", "No volume is recorded."))
    if not meta.verified:
        out.append(
            Issue(
                "metadata",
                "info",
                "UNVERIFIED_METADATA",
                "You have not marked this paper's metadata as checked.",
            )
        )
    return out


def sort_key(meta: Meta) -> tuple[str, str, int]:
    names = _names(meta)
    lead = names[0].family.casefold() if names else meta.title.casefold()
    return (lead, meta.title.casefold(), meta.year or 0)
