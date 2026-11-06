"""Send one real request to the configured provider and print the reply and usage.

Run inside the container with your own key in .env (the key is never printed):
    docker compose exec backend python scripts/llm_smoke_test.py
    docker compose exec backend python scripts/llm_smoke_test.py --stream
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.diagnostics import (  # noqa: E402
    NOT_CONFIGURED_HELP,
    DiagnosticFailed,
    smoke_test_report,
)
from app.ai.errors import LLMError, LLMNotConfiguredError  # noqa: E402
from app.core.config import get_settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stream", action="store_true", help="use the streaming call")
    args = parser.parse_args()
    try:
        print(asyncio.run(smoke_test_report(get_settings(), stream=args.stream)))
        return 0
    except LLMNotConfiguredError:
        print(NOT_CONFIGURED_HELP)
        return 2
    except DiagnosticFailed as exc:  # partial report ending in the error code
        print(exc)
        return 1
    except LLMError as exc:
        print(f"FAILED: {exc.code}: {exc.user_message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
