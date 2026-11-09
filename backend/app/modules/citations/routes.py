import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.dependencies import ActiveUser, DbSession
from app.modules.ai.schemas import CitationOut, CitationResponse
from app.modules.citations.service import CitationService

router = APIRouter(tags=["citations"])


def _regions(raw: object) -> list["Region"]:
    """Stored block rectangles, defensively validated (they come from our own extractor)."""
    out: list[Region] = []
    for item in raw if isinstance(raw, list) else []:
        try:
            page, box = int(item["page"]), [float(v) for v in item["bbox"]]
        except (KeyError, TypeError, ValueError):
            continue
        if page >= 1 and len(box) == 4:
            out.append(Region(page=page, bbox=box))
    return out


class Region(BaseModel):
    page: int
    bbox: list[float]  # x0, y0, x1, y1 in PDF points, origin top-left


class SourcePassageOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    chunk_index: int
    page_number: int | None
    slide_number: int | None
    section_heading: str | None
    content: str
    regions: list[Region] = []


class SourcePassageResponse(BaseModel):
    success: bool = True
    data: SourcePassageOut


@router.get("/citations/{citation_id}", response_model=CitationResponse)
async def get_citation(
    citation_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> CitationResponse:
    row = await CitationService(db).get(user_id=current_user.id, citation_id=citation_id)
    return CitationResponse(data=CitationOut.model_validate(row))


@router.get("/documents/{document_id}/sources/{chunk_id}", response_model=SourcePassageResponse)
async def get_source_passage(
    document_id: uuid.UUID, chunk_id: uuid.UUID, current_user: ActiveUser, db: DbSession
) -> SourcePassageResponse:
    chunk, name = await CitationService(db).source_passage(
        user_id=current_user.id, document_id=document_id, chunk_id=chunk_id
    )
    return SourcePassageResponse(
        data=SourcePassageOut(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_name=name,
            chunk_index=chunk.chunk_index,
            page_number=chunk.page_number,
            slide_number=chunk.slide_number,
            section_heading=chunk.section_heading,
            content=chunk.content,
            regions=_regions(chunk.bboxes),
        )
    )
