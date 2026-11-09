"""Format extractors. Parser libraries are imported lazily inside each extractor so importing this
package never needs them; only the worker image installs them (D-70)."""

from app.ingestion.extractors.base import (
    NO_TEXT_FOUND,
    UNSUPPORTED_FILE_TYPE,
    Extraction,
    ExtractionError,
    ExtractionLimits,
)


def extract(file_type: str, data: bytes, limits: ExtractionLimits) -> Extraction:
    if file_type == "pdf":
        from app.ingestion.extractors.pdf import extract_pdf

        result = extract_pdf(data, limits)
    elif file_type == "docx":
        from app.ingestion.extractors.office import extract_docx

        result = extract_docx(data, limits)
    elif file_type == "pptx":
        from app.ingestion.extractors.office import extract_pptx

        result = extract_pptx(data, limits)
    elif file_type in ("txt", "md"):
        from app.ingestion.extractors.plain import extract_text

        result = extract_text(data, limits, markdown=file_type == "md")
    elif file_type in ("png", "jpg"):
        from app.ingestion.extractors.plain import extract_image

        result = extract_image(data, limits)
    else:
        raise ExtractionError(UNSUPPORTED_FILE_TYPE)
    if not any(block.text.strip() for block in result.blocks):
        raise ExtractionError(NO_TEXT_FOUND, "No text could be extracted from the document.")
    return result
