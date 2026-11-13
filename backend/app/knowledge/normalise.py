"""Concept-name normalisation: the key for exact matching and duplicate detection (spec 9.6)."""

from __future__ import annotations

import re
import unicodedata

_SPACE = re.compile(r"\s+")
_EDGE = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)


def normalise_name(name: str) -> str:
    """NFKC, case-folded, whitespace collapsed, punctuation trimmed from both ends.
    "Back-propagation " and "back-propagation" match; "Backpropagation" does not (that is what
    aliases and the duplicate review are for, never a silent merge)."""
    text = unicodedata.normalize("NFKC", name).casefold()
    text = _SPACE.sub(" ", text).strip()
    return _EDGE.sub("", text)[:200]


def normalise_passage(text: str) -> str:
    """Whitespace/case/quote-insensitive form used to check a quote against its source."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    folded = folded.replace("‘", "'").replace("’", "'")
    folded = folded.replace("“", '"').replace("”", '"')
    return _SPACE.sub(" ", folded).strip()
