"""Fixtures generated in code (D-76): no real or copyrighted documents are stored in git.

These need the worker libraries (PyMuPDF, python-pptx, python-docx, Pillow); tests that use them
skip when a library is missing. OCR tests also need the `tesseract` binary.
"""

import io
import shutil

import pytest

LOREM = [
    "Photosynthesis converts light energy into chemical energy stored in glucose molecules.",
    "The Calvin cycle fixes carbon dioxide into sugars using ATP and NADPH from light reactions.",
    "Chlorophyll absorbs mostly blue and red wavelengths and reflects green light.",
    "Stomata regulate gas exchange and water loss in the leaves of vascular plants.",
]


def need(module: str) -> None:
    pytest.importorskip(module)


def need_tesseract() -> None:
    if shutil.which("tesseract") is None:
        pytest.skip("tesseract is not installed")


def paragraph(n: int) -> str:
    return " ".join(LOREM[(n + i) % len(LOREM)] for i in range(3))


def make_text_pdf(pages: list[list[tuple[str, float]]]) -> bytes:
    """Each page is a list of (text, font size); larger text becomes a heading."""
    need("pymupdf")
    import pymupdf

    doc = pymupdf.open()
    for items in pages:
        page = doc.new_page()
        y = 60.0
        for text, size in items:
            height = max(size * 2.0, size * 1.6 * (len(text) // 70 + 1))
            page.insert_textbox(pymupdf.Rect(60, y, 540, y + height), text, fontsize=size)
            y += height + 8
    data = doc.tobytes()
    doc.close()
    return data


def make_blank_pdf(pages: int = 1) -> bytes:
    need("pymupdf")
    import pymupdf

    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def make_encrypted_pdf() -> bytes:
    need("pymupdf")
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret page")
    data = doc.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner-pw", user_pw="user-pw"
    )
    doc.close()
    return data


def text_image_png(text: str, size: int = 56, width: int = 1400, height: int = 300) -> bytes:
    need("PIL")
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (width, height), "white")
    font = ImageFont.load_default(size=size)
    ImageDraw.Draw(image).text((30, 40), text, fill="black", font=font)
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def make_scanned_pdf(text: str) -> bytes:
    """A page that is only an image of text: it has no text layer, so OCR is required."""
    need("pymupdf")
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=842, height=300)
    page.insert_image(pymupdf.Rect(0, 0, 842, 180), stream=text_image_png(text))
    data = doc.tobytes()
    doc.close()
    return data


def make_pptx_file(slides: list[tuple[str, str, str]]) -> bytes:
    """Each slide is (title, body, notes)."""
    need("pptx")
    from pptx import Presentation

    prs = Presentation()
    for title, body, notes in slides:
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        slide.shapes.title.text = title
        slide.placeholders[1].text = body
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def make_docx_file(
    heading: str, paragraphs: list[str], table: list[list[str]] | None = None
) -> bytes:
    need("docx")
    import docx

    document = docx.Document()
    document.add_heading(heading, level=1)
    for text in paragraphs:
        document.add_paragraph(text)
    document.add_paragraph("first item", style="List Bullet")
    if table:
        t = document.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, cell in enumerate(row):
                t.cell(r, c).text = cell
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()
