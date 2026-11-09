import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator

from app.core.config import Settings, get_settings
from app.core.dependencies import ActiveUser, DbSession
from app.core.rate_limit import RateLimiter, get_rate_limiter
from app.database.connection import AsyncSessionLocal
from app.embeddings.registry import embedding_configured, get_embedding_provider
from app.embeddings.service import EmbeddingService
from app.retrieval.scope import ScopeKind, ScopeResolver
from app.retrieval.searcher import QueryEmbedder, Searcher

router = APIRouter(prefix="/search", tags=["search"])


class SearchScope(BaseModel):
    kind: ScopeKind = "all"
    id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _id_matches_kind(self) -> "SearchScope":
        if (self.kind == "all") != (self.id is None):
            raise ValueError("scope id is required for every scope kind except 'all'")
        return self


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    scope: SearchScope = Field(default_factory=SearchScope)
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid"
    limit: int = Field(default=8, ge=1, le=20)

    @model_validator(mode="after")
    def _not_blank(self) -> "SearchRequest":
        if not self.query.strip():
            raise ValueError("query must not be blank")
        return self


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    page_number: int | None
    slide_number: int | None
    section_heading: str | None
    snippet: str
    score: float


class SearchData(BaseModel):
    results: list[SearchHit]
    mode_used: Literal["keyword", "semantic", "hybrid"]
    degraded: bool


class SearchResponse(BaseModel):
    success: bool = True
    data: SearchData


def get_query_embedder(
    settings: Annotated[Settings, Depends(get_settings)],
) -> QueryEmbedder | None:
    """None when no embedding provider is configured: search then answers keyword-only."""
    if not embedding_configured(settings):
        return None
    try:
        return EmbeddingService(AsyncSessionLocal, get_embedding_provider(settings), settings)
    except Exception:
        return None


@router.post("", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    current_user: ActiveUser,
    db: DbSession,
    settings: Annotated[Settings, Depends(get_settings)],
    embedder: Annotated[QueryEmbedder | None, Depends(get_query_embedder)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> SearchResponse:
    await limiter.check(
        f"search:{current_user.id}", settings.search_requests_per_minute_per_user, 60
    )
    scope = await ScopeResolver(db).resolve(current_user.id, body.scope.kind, body.scope.id)
    result = await Searcher(db, settings, embedder).search(
        scope, body.query, mode=body.mode, top_k=body.limit
    )
    return SearchResponse(
        data=SearchData(
            results=[
                SearchHit(
                    chunk_id=h.chunk_id,
                    document_id=h.document_id,
                    document_name=h.document_name,
                    page_number=h.page_number,
                    slide_number=h.slide_number,
                    section_heading=h.section_heading,
                    snippet=h.content[:500],
                    score=round(h.score, 4),
                )
                for h in result.hits
            ],
            mode_used=result.mode_used,
            degraded=result.degraded,
        )
    )
