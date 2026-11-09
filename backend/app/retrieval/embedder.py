"""Builds the query embedder for the API process (search and RAG). Tests monkeypatch this."""

from __future__ import annotations

from app.core.config import Settings
from app.database.connection import AsyncSessionLocal
from app.embeddings.registry import embedding_configured, get_embedding_provider
from app.embeddings.service import EmbeddingService


def make_query_embedder(settings: Settings) -> EmbeddingService | None:
    """None when no embedding provider is configured: retrieval then runs keyword-only."""
    if not embedding_configured(settings):
        return None
    try:
        return EmbeddingService(AsyncSessionLocal, get_embedding_provider(settings), settings)
    except Exception:
        return None
