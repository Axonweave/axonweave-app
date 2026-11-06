"""Storage key builder. Keys are never derived from user input (D-64).

Only UUID objects, an integer version and an extension from a fixed allowlist go in. The original
filename is a display value in the database and never becomes part of a key.
"""

import re
import uuid

# Detected file types the pipeline supports (D-71); the extension comes from the validated type.
ALLOWED_EXTENSIONS = frozenset({"pdf", "pptx", "docx", "txt", "md", "png", "jpg", "jpeg"})

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_KEY_RE = re.compile(
    rf"^users/{_UUID}/documents/{_UUID}/v[1-9][0-9]*/original\.(?:pdf|pptx|docx|txt|md|png|jpg|jpeg)$"
)


def build_original_key(
    user_id: uuid.UUID, document_id: uuid.UUID, version: int, extension: str
) -> str:
    if not isinstance(user_id, uuid.UUID) or not isinstance(document_id, uuid.UUID):
        raise TypeError("user_id and document_id must be UUID objects")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("version must be a positive integer")
    ext = extension.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("unsupported file extension")
    return f"users/{user_id}/documents/{document_id}/v{version}/original.{ext}"


def is_valid_original_key(key: str) -> bool:
    """True for keys this module could have produced (defence in depth before delete or read)."""
    return bool(_KEY_RE.match(key))
