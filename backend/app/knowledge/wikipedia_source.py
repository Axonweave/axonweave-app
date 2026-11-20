"""Wikipedia as a web source for the subject graph (D-145).

A fixed-host, read-only fetch that runs only in the Celery worker. The subject name goes to the
Wikipedia search API as a query parameter; the pages found come back as `WebSource` objects, so the
ordinary extraction and quote verification (D-126) run over real article text.

Safety: the host is a constant (never built from user input); page URLs are built from API titles
with percent-encoding; responses are size-capped while streaming; every call has a timeout; page
text is untrusted data and is only ever put in a prompt as data. Nothing here logs the subject
name, queries or text (counts and error types only).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import quote

import httpx
import structlog

from app.ai.types import WebSource

logger = structlog.get_logger(__name__)

API_URL = "https://en.wikipedia.org/w/api.php"
PAGE_URL = "https://en.wikipedia.org/wiki/"
TIMEOUT_SECONDS = 15.0
MAX_RESPONSE_BYTES = 2_000_000
MAX_QUERY_CHARS = 200
MAX_PAGE_CHARS = 20_000  # per article: the lead plus the first sections, within the token budget
MIN_PAGE_CHARS = 200  # a stub is not worth a passage
RETRY_STATUSES = frozenset({429, 503})
MAX_RETRY_WAIT_SECONDS = 5.0
REQUEST_GAP_SECONDS = 0.25  # polite pacing between the requests of one run
DEFAULT_USER_AGENT = "AxonweaveStudyApp/1.0 (knowledge graph; read-only)"

_HEADING = re.compile(r"^=+\s*(.+?)\s*=+$", re.MULTILINE)
_SKIP_SECTIONS = frozenset(
    {
        "references",
        "external links",
        "see also",
        "notes",
        "further reading",
        "bibliography",
        "citations",
        "sources",
    }
)
_WHITESPACE = re.compile(r"[ \t]+")


class WikipediaUnavailableError(Exception):
    """The Wikipedia API could not be reached or answered with something unusable."""


_WORDS = re.compile(r"[^\W_]+", re.UNICODE)
_STEM = 5  # words match on their first letters: "system" ~ "systems", "design" ~ "designing"


def _stems(text: str) -> set[str]:
    return {w.lower()[:_STEM] for w in _WORDS.findall(text) if len(w) >= 3}


def related_titles(query: str, titles: list[str]) -> list[str]:
    """Search hits whose title shares a word with the subject name, in order. Wikipedia's search
    also matches words deep inside an article (a "Photosynthesis" search returns "Food"), which
    would put an off-topic article in the graph. If no title qualifies, the order is kept as is."""
    wanted = _stems(query)
    kept = [t for t in titles if "(disambiguation)" not in t and wanted & _stems(t)]
    return kept or [t for t in titles if "(disambiguation)" not in t]


def page_url(title: str) -> str:
    return PAGE_URL + quote(title.replace(" ", "_"), safe="_()',-.")


def split_sections(text: str, limit: int = MAX_PAGE_CHARS) -> tuple[str, ...]:
    """Plain-text article -> passages: the lead, then each section, without the reference-style
    sections, within `limit` characters in all."""
    parts = _HEADING.split(text)
    # parts = [lead, heading1, body1, heading2, body2, ...]
    sections: list[str] = [parts[0]]
    for i in range(1, len(parts) - 1, 2):
        if parts[i].strip().lower() in _SKIP_SECTIONS:
            continue
        sections.append(f"{parts[i].strip()}\n{parts[i + 1]}")
    out: list[str] = []
    used = 0
    for section in sections:
        cleaned = "\n".join(
            _WHITESPACE.sub(" ", line).strip() for line in section.splitlines() if line.strip()
        )
        if not cleaned:
            continue
        if used + len(cleaned) > limit:
            cleaned = cleaned[: max(0, limit - used)]
        if cleaned:
            out.append(cleaned)
            used += len(cleaned)
        if used >= limit:
            break
    return tuple(out)


async def _get_json(client: httpx.AsyncClient, params: dict[str, Any]) -> dict[str, Any]:
    """One GET with a hard size cap, retried once when the API says slow down (429/503, honouring
    a short Retry-After). Any failure becomes WikipediaUnavailableError."""
    for attempt in (1, 2):
        try:
            async with client.stream("GET", API_URL, params=params) as response:
                status = response.status_code
                wait = _retry_after(response)
                body = bytearray()
                if status == 200:
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise WikipediaUnavailableError
        except WikipediaUnavailableError:
            raise
        except httpx.HTTPError as exc:
            logger.warning("wikipedia_request_failed", error_type=type(exc).__name__)
            raise WikipediaUnavailableError from None
        if status in RETRY_STATUSES and attempt == 1:
            await asyncio.sleep(wait)
            continue
        if status != 200:
            logger.warning("wikipedia_bad_status", status=status)
            raise WikipediaUnavailableError
        try:
            data = httpx.Response(200, content=bytes(body)).json()
        except ValueError:
            raise WikipediaUnavailableError from None
        if not isinstance(data, dict):
            raise WikipediaUnavailableError
        return data
    raise WikipediaUnavailableError  # unreachable: the second attempt returns or raises


def _retry_after(response: httpx.Response) -> float:
    try:
        seconds = float(response.headers.get("retry-after", "1"))
    except ValueError:
        seconds = 1.0
    return min(max(seconds, 0.5), MAX_RETRY_WAIT_SECONDS)


async def fetch_wikipedia_sources(
    topic: str,
    max_pages: int,
    *,
    user_agent: str = DEFAULT_USER_AGENT,
    transport: httpx.AsyncBaseTransport | None = None,
    request_gap: float = REQUEST_GAP_SECONDS,
) -> tuple[WebSource, ...]:
    """Search Wikipedia for `topic` and return up to `max_pages` articles as sources. Empty when
    nothing usable was found; raises WikipediaUnavailableError when the API cannot be used."""
    query = " ".join(topic.split())[:MAX_QUERY_CHARS]
    if not query or max_pages < 1:
        return ()
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    sources: list[WebSource] = []
    async with httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(TIMEOUT_SECONDS),
        follow_redirects=False,
        transport=transport,
    ) as client:
        found = await _get_json(
            client,
            {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": min(max_pages * 2, 10),  # spare hits for stubs and disambiguation
                "srnamespace": 0,
                "format": "json",
                "formatversion": 2,
            },
        )
        hits = (found.get("query") or {}).get("search") or []
        titles = [str(h.get("title") or "").strip() for h in hits if isinstance(h, dict)]
        seen: set[str] = set()
        for title in related_titles(query, [t for t in titles if t]):
            if len(sources) >= max_pages:
                break
            if title in seen:
                continue
            seen.add(title)
            await asyncio.sleep(request_gap)
            try:
                page = await _get_json(
                    client,
                    {
                        "action": "query",
                        "prop": "extracts",
                        "explaintext": 1,
                        "titles": title,
                        "redirects": 1,
                        "format": "json",
                        "formatversion": 2,
                    },
                )
            except WikipediaUnavailableError:
                if sources:
                    break  # keep the articles already read rather than lose the run
                raise
            pages = (page.get("query") or {}).get("pages") or []
            extract = (
                str(pages[0].get("extract") or "") if pages and isinstance(pages[0], dict) else ""
            )
            if len(extract) < MIN_PAGE_CHARS or "may refer to" in extract[:300]:
                continue  # missing, a stub or a disambiguation page
            segments = split_sections(extract)
            if segments:
                sources.append(WebSource(page_url(title), f"{title} - Wikipedia", segments))
    logger.info("wikipedia_sources_fetched", count=len(sources))
    return tuple(sources)
