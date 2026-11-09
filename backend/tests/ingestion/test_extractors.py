"""Extractor tests on fixtures generated in code. Skipped when a worker library is missing."""

import pytest

from app.ingestion.extractors import extract
from app.ingestion.extractors.base import ExtractionError, ExtractionLimits
from tests.ingestion import fixtures as fx

LIMITS = ExtractionLimits(
    max_pages=50,
    max_chars=1_000_000,
    ocr_enabled=True,
    ocr_dpi=200,
    ocr_languages="eng",
    image_max_pixels=50_000_000,
    ocr_timeout_seconds=60,
)


def limits(**changes: object) -> ExtractionLimits:
    from dataclasses import replace

    return replace(LIMITS, **changes)  # type: ignore[arg-type]


class TestPdf:
    def test_pages_blocks_and_headings(self):
        data = fx.make_text_pdf(
            [
                [("Plant Biology", 24), (fx.paragraph(0), 11), (fx.paragraph(1), 11)],
                [("Light Reactions", 20), (fx.paragraph(2), 11)],
            ]
        )
        result = extract("pdf", data, LIMITS)
        assert result.method == "pymupdf" and result.page_count == 2 and not result.ocr_used
        headings = [b.text for b in result.blocks if b.kind == "heading"]
        assert "Plant Biology" in headings and "Light Reactions" in headings
        assert {b.page for b in result.blocks} == {1, 2}
        assert all(b.bbox is not None for b in result.blocks)
        assert any("Calvin" in b.text for b in result.blocks)

    def test_encrypted_pdf_is_refused(self):
        with pytest.raises(ExtractionError) as exc:
            extract("pdf", fx.make_encrypted_pdf(), LIMITS)
        assert exc.value.code == "FILE_ENCRYPTED"

    def test_corrupt_pdf_is_refused(self):
        fx.need("pymupdf")
        with pytest.raises(ExtractionError) as exc:
            extract("pdf", b"%PDF-1.4\nthis is not a real pdf body", LIMITS)
        assert exc.value.code == "FILE_CORRUPT"

    def test_page_limit(self):
        data = fx.make_text_pdf([[(fx.paragraph(i), 11)] for i in range(3)])
        with pytest.raises(ExtractionError) as exc:
            extract("pdf", data, limits(max_pages=2))
        assert exc.value.code == "TOO_MANY_PAGES"

    def test_character_budget_truncates_with_a_warning(self):
        data = fx.make_text_pdf([[(fx.paragraph(i), 11)] for i in range(4)])
        result = extract("pdf", data, limits(max_chars=200))
        assert "TEXT_TRUNCATED" in result.warnings
        assert sum(len(b.text) for b in result.blocks) <= 200

    def test_blank_pdf_without_ocr_has_no_text(self):
        with pytest.raises(ExtractionError) as exc:
            extract("pdf", fx.make_blank_pdf(), limits(ocr_enabled=False))
        assert exc.value.code == "NO_TEXT_FOUND"

    def test_scanned_pdf_uses_ocr_only_for_pages_without_text(self):
        fx.need_tesseract()
        digital = fx.make_text_pdf([[(fx.paragraph(0), 11)]])
        assert extract("pdf", digital, LIMITS).ocr_used is False
        result = extract("pdf", fx.make_scanned_pdf("Mitochondria produce ATP"), LIMITS)
        assert result.ocr_used is True
        assert "OCR_USED" in result.warnings
        assert result.ocr_mean_confidence is not None and result.ocr_mean_confidence > 40
        text = " ".join(b.text for b in result.blocks).lower()
        assert "mitochondria" in text and all(b.from_ocr and b.page == 1 for b in result.blocks)

    def test_scanned_pdf_with_ocr_disabled_warns_instead_of_guessing(self):
        data = fx.make_scanned_pdf("Mitochondria produce ATP")
        with pytest.raises(ExtractionError) as exc:
            extract("pdf", data, limits(ocr_enabled=False))
        assert exc.value.code == "NO_TEXT_FOUND"


class TestOffice:
    def test_pptx_slides_titles_tables_and_notes(self):
        data = fx.make_pptx_file(
            [
                ("Cell Structure", "Nucleus and membrane details", "Remember the organelles"),
                ("Energy", "Mitochondria produce ATP", ""),
            ]
        )
        result = extract("pptx", data, LIMITS)
        assert result.slide_count == 2 and result.method == "python-pptx"
        by_slide = {}
        for b in result.blocks:
            by_slide.setdefault(b.slide, []).append(b)
        assert by_slide[1][0].kind == "heading" and by_slide[1][0].text == "Cell Structure"
        assert any(b.kind == "notes" and "organelles" in b.text for b in by_slide[1])
        assert any("Mitochondria" in b.text for b in by_slide[2])

    def test_pptx_slide_limit(self):
        data = fx.make_pptx_file([(f"S{i}", "body text here", "") for i in range(3)])
        with pytest.raises(ExtractionError) as exc:
            extract("pptx", data, limits(max_pages=2))
        assert exc.value.code == "TOO_MANY_PAGES"

    def test_docx_headings_lists_and_tables(self):
        data = fx.make_docx_file(
            "Genetics", [fx.paragraph(0)], table=[["Allele", "Trait"], ["A", "Tall"]]
        )
        result = extract("docx", data, LIMITS)
        kinds = [b.kind for b in result.blocks]
        assert kinds[0] == "heading" and "list" in kinds and "table" in kinds
        table = next(b for b in result.blocks if b.kind == "table")
        assert "Allele | Trait" in table.text and "A | Tall" in table.text

    def test_corrupt_office_files(self):
        fx.need("docx")
        fx.need("pptx")
        for kind in ("docx", "pptx"):
            with pytest.raises(ExtractionError) as exc:
                extract(kind, b"PK\x03\x04 garbage that is not a zip", LIMITS)
            assert exc.value.code == "FILE_CORRUPT"


class TestPlainAndImages:
    def test_text_paragraphs(self):
        result = extract("txt", b"First paragraph.\nstill first.\n\nSecond paragraph.", LIMITS)
        assert [b.text for b in result.blocks] == [
            "First paragraph.\nstill first.",
            "Second paragraph.",
        ]

    def test_markdown_headings_and_code_fences(self):
        md = b"# Title\n\nIntro text.\n\n## Part\n\n```\ncode line 1\n\ncode line 2\n```\n"
        result = extract("md", md, LIMITS)
        assert [(b.kind, b.level) for b in result.blocks[:3]] == [
            ("heading", 1),
            ("paragraph", 0),
            ("heading", 2),
        ]
        assert "code line 1\n\ncode line 2" in result.blocks[3].text  # fence kept whole

    def test_invalid_utf8_is_replaced_not_crashed(self):
        result = extract("txt", b"caf\xe9 au lait is fine", LIMITS)
        assert "au lait" in result.blocks[0].text

    def test_whitespace_only_text_has_no_text(self):
        with pytest.raises(ExtractionError) as exc:
            extract("txt", b"  \n \n\t\n", LIMITS)
        assert exc.value.code == "NO_TEXT_FOUND"

    def test_image_ocr(self):
        fx.need_tesseract()
        result = extract("png", fx.text_image_png("Chloroplast"), LIMITS)
        assert result.ocr_used and "OCR_USED" in result.warnings
        assert "chloroplast" in " ".join(b.text for b in result.blocks).lower()

    def test_image_without_ocr_is_refused(self):
        fx.need("PIL")
        with pytest.raises(ExtractionError) as exc:
            extract("png", fx.text_image_png("Chloroplast"), limits(ocr_enabled=False))
        assert exc.value.code == "OCR_UNAVAILABLE"

    def test_blank_image_has_no_text(self):
        fx.need_tesseract()
        data = fx.text_image_png("")
        with pytest.raises(ExtractionError) as exc:
            extract("png", data, LIMITS)
        assert exc.value.code == "NO_TEXT_FOUND"

    def test_pixel_limit_blocks_decompression_bombs(self):
        fx.need_tesseract()
        data = fx.text_image_png("hello", width=400, height=200)
        with pytest.raises(ExtractionError) as exc:
            extract("png", data, limits(image_max_pixels=1000))
        assert exc.value.code == "FILE_CORRUPT"

    def test_unsupported_type(self):
        with pytest.raises(ExtractionError) as exc:
            extract("exe", b"MZ", LIMITS)
        assert exc.value.code == "UNSUPPORTED_FILE_TYPE"
