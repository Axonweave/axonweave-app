"""Pure tests for normalisation and chunking: no database, no parser libraries."""

import pytest

from app.ingestion.chunker import (
    CHARS_PER_TOKEN,
    ChunkSettings,
    chunk_blocks,
    estimate_tokens,
)
from app.ingestion.extractors.base import Block
from app.ingestion.normalise import normalise_blocks, normalise_text, word_count

CFG = ChunkSettings(target_tokens=100, overlap_tokens=40, max_tokens=150)


def sentence(n: int) -> str:
    return f"Sentence number {n} talks about topic {n} in a reasonably plain way."


def para(count: int, start: int = 0) -> str:
    return " ".join(sentence(i) for i in range(start, start + count))


class TestNormalise:
    def test_cleans_whitespace_controls_and_ligatures(self):
        raw = "Hello  world\x00 \x07of ﬁne\r\ntext​  here"
        assert normalise_text(raw) == "Hello world of fine\ntext here"

    def test_rejoins_hyphenated_line_breaks_only_between_lowercase(self):
        assert normalise_text("photo-\nsynthesis") == "photosynthesis"
        assert normalise_text("well-\nKnown") == "well-\nKnown"

    def test_collapses_blank_runs(self):
        assert normalise_text("a\n\n\n\n\nb") == "a\n\nb"

    def test_drops_empty_blocks_and_sets_section_headings(self):
        blocks = [
            Block("  ", page=1),
            Block("Intro", page=1, kind="heading", level=1),
            Block("Body one", page=1),
            Block("Methods", page=2, kind="heading", level=1),
            Block("Body two", page=2),
        ]
        out = normalise_blocks(blocks)
        assert [b.heading for b in out] == ["Intro", "Intro", "Methods", "Methods"]

    def test_heading_does_not_leak_across_slides(self):
        blocks = [
            Block("Slide one title", slide=1, kind="heading"),
            Block("Slide one body", slide=1),
            Block("Slide two body without a title", slide=2),
        ]
        out = normalise_blocks(blocks)
        assert out[1].heading == "Slide one title"
        assert out[2].heading is None

    def test_repeated_running_headers_and_page_numbers_are_removed(self):
        blocks = []
        for page in range(1, 7):
            blocks.append(Block("ACME Corp Confidential", page=page))
            blocks.append(Block(f"Real content for page {page} is here.", page=page))
            blocks.append(Block(str(page), page=page))
        out = normalise_blocks(blocks, page_count=6)
        texts = [b.text for b in out]
        assert not any("Confidential" in t for t in texts)
        assert len(out) == 6  # one real block per page survives

    def test_short_documents_keep_everything(self):
        blocks = [Block("Header", page=p) for p in (1, 2)]
        assert len(normalise_blocks(blocks, page_count=2)) == 2

    def test_word_count(self):
        assert word_count([Block("one two three"), Block("four")]) == 4


class TestChunker:
    def test_settings_are_validated(self):
        with pytest.raises(ValueError):
            ChunkSettings(target_tokens=100, overlap_tokens=100, max_tokens=150)
        with pytest.raises(ValueError):
            ChunkSettings(target_tokens=200, overlap_tokens=10, max_tokens=150)

    def test_small_document_is_one_chunk(self):
        chunks = chunk_blocks([Block("A short note about plants and light.", page=1)], CFG)
        assert len(chunks) == 1 and chunks[0].page == 1

    def test_chunks_respect_the_maximum_size(self):
        blocks = [Block(para(6, i * 6), page=1 + i // 3) for i in range(30)]
        chunks = chunk_blocks(blocks, CFG)
        assert len(chunks) > 5
        assert all(c.token_count <= CFG.max_tokens for c in chunks)
        assert all(c.text.strip() for c in chunks)

    def test_oversize_paragraph_is_split_on_sentences(self):
        chunks = chunk_blocks([Block(para(80), page=1)], CFG)
        assert len(chunks) > 2
        for c in chunks:
            assert c.token_count <= CFG.max_tokens
            assert c.text.rstrip().endswith(".")  # never cut mid-sentence

    def test_giant_token_without_spaces_is_still_cut(self):
        chunks = chunk_blocks([Block("x" * 5000, page=1)], CFG)
        assert len(chunks) >= 2
        assert all(c.token_count <= CFG.max_tokens for c in chunks)

    def test_overlap_carries_the_end_of_the_previous_chunk(self):
        chunks = chunk_blocks([Block(para(60), page=1)], CFG)
        assert len(chunks) >= 2
        shared = 0
        for prev, nxt in zip(chunks, chunks[1:], strict=False):
            last_sentence = prev.text.rstrip().split(". ")[-1]
            if last_sentence in nxt.text:
                shared += 1
        assert shared >= 1

    def test_no_overlap_when_disabled(self):
        cfg = ChunkSettings(target_tokens=100, overlap_tokens=0, max_tokens=150)
        chunks = chunk_blocks([Block(para(60), page=1)], cfg)
        joined = " ".join(c.text for c in chunks)
        assert joined.count(sentence(0)) == 1

    def test_slides_never_share_a_chunk_and_keep_their_number(self):
        blocks = []
        for n in range(1, 5):
            blocks += [
                Block(f"Title {n}", slide=n, kind="heading", heading=f"Title {n}"),
                Block("A bullet that is long enough to count as content.", slide=n),
            ]
        chunks = chunk_blocks(blocks, CFG)
        assert [c.slide for c in chunks] == [1, 2, 3, 4]
        assert all(c.heading == f"Title {c.slide}" for c in chunks)

    def test_new_heading_starts_a_new_chunk_once_there_is_enough_text(self):
        blocks = [
            Block("Alpha", page=1, kind="heading", heading="Alpha"),
            Block(para(8), page=1, heading="Alpha"),
            Block("Beta", page=2, kind="heading", heading="Beta"),
            Block(para(8, 20), page=2, heading="Beta"),
        ]
        chunks = chunk_blocks(blocks, CFG)
        assert chunks[0].heading == "Alpha"
        assert any(c.heading == "Beta" and c.page == 2 for c in chunks)
        assert not any(
            "Beta" in c.text and "Alpha" in c.text.split("Beta")[0][:6] for c in chunks[1:]
        )

    def test_table_is_kept_whole_when_it_fits(self):
        table = "\n".join(f"row {i} | value {i}" for i in range(8))
        chunks = chunk_blocks([Block(table, page=1, kind="table")], CFG)
        assert len(chunks) == 1 and chunks[0].text == table

    def test_oversize_table_is_split_by_rows(self):
        table = "\n".join(f"row {i} | value {i} | more cells here" for i in range(120))
        chunks = chunk_blocks([Block(table, page=1, kind="table")], CFG)
        assert len(chunks) > 1
        for c in chunks:
            assert all(line.startswith("row ") for line in c.text.split("\n"))

    def test_provenance_and_bboxes_are_recorded(self):
        blocks = [
            Block("First paragraph with enough text to keep.", page=3, bbox=(1.0, 2.0, 3.0, 4.0)),
            Block("Second paragraph with enough text to keep.", page=3, bbox=(5.0, 6.0, 7.0, 8.0)),
        ]
        (chunk,) = chunk_blocks(blocks, CFG)
        assert chunk.page == 3
        assert chunk.bboxes == [
            {"page": 3, "bbox": [1.0, 2.0, 3.0, 4.0]},
            {"page": 3, "bbox": [5.0, 6.0, 7.0, 8.0]},
        ]

    def test_ocr_flag_only_when_every_block_came_from_ocr(self):
        ocr = chunk_blocks([Block("recognised text from a scan page", page=1, from_ocr=True)], CFG)
        mixed = chunk_blocks(
            [
                Block("recognised text from a scan", page=1, from_ocr=True),
                Block("digital text here ok", page=1),
            ],
            CFG,
        )
        assert ocr[0].from_ocr is True and mixed[0].from_ocr is False

    def test_deterministic(self):
        blocks = [Block(para(40), page=1)]
        a = [c.text for c in chunk_blocks(blocks, CFG)]
        b = [c.text for c in chunk_blocks([Block(para(40), page=1)], CFG)]
        assert a == b

    def test_empty_input(self):
        assert chunk_blocks([], CFG) == []

    def test_token_estimate_is_conservative(self):
        assert estimate_tokens("a" * (CHARS_PER_TOKEN * 10)) == 10
        assert estimate_tokens("") == 0
