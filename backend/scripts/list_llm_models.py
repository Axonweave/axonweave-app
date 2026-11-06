"""List the models the configured provider key can use (D-38). Prints names, never the key.

Run inside the container:  docker compose exec backend python scripts/list_llm_models.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.diagnostics import NOT_CONFIGURED_HELP, list_models_report  # noqa: E402
from app.ai.errors import LLMError, LLMNotConfiguredError  # noqa: E402
from app.core.config import get_settings  # noqa: E402


def main() -> int:
    try:
        print(asyncio.run(list_models_report(get_settings())))
        return 0
    except LLMNotConfiguredError:
        print(NOT_CONFIGURED_HELP)
        return 2
    except LLMError as exc:
        print(f"FAILED: {exc.code}: {exc.user_message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
