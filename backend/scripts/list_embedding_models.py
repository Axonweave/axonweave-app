"""List the embedding models the configured key can use (D-69). Prints names, never the key.

Run inside the container:  docker compose exec backend python scripts/list_embedding_models.py
Set EMBEDDING_PROVIDER (and GEMINI_API_KEY for gemini) first.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.embeddings.errors import EmbeddingError, EmbeddingNotConfiguredError  # noqa: E402
from app.embeddings.registry import get_embedding_provider  # noqa: E402

HELP = (
    "No embedding provider is configured. Set EMBEDDING_PROVIDER=gemini (and GEMINI_API_KEY) in "
    "your local .env, make sure docker-compose.yml passes them to the backend, then restart it."
)


async def report() -> str:
    settings = get_settings()
    if not settings.embedding_provider:
        raise EmbeddingNotConfiguredError()
    provider = get_embedding_provider(settings)
    try:
        models = await provider.list_models()
    finally:
        await provider.aclose()
    lines = [
        f"Provider: {provider.name}",
        f"Embedding models available to the configured key: {len(models)}",
        f"Column dimension (fixed in the schema): {settings.embedding_dimensions}",
        "",
    ]
    for m in sorted(models, key=lambda x: x.provider_model_id):
        mark = "  <- EMBEDDING_MODEL" if m.provider_model_id == settings.embedding_model else ""
        lines.append(
            f"{m.provider_model_id}  |  {m.display_name or '-'}  |  "
            f"methods: {','.join(m.supported_methods) or '-'}  |  "
            f"input limit: {m.input_token_limit or '?'}{mark}"
        )
    return "\n".join(lines)


def main() -> int:
    try:
        print(asyncio.run(report()))
        return 0
    except EmbeddingNotConfiguredError:
        print(HELP)
        return 2
    except EmbeddingError as exc:
        print(f"FAILED: {exc.code}: {exc.user_message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
