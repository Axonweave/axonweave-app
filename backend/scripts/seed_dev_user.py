"""Create one ready-to-use login for local development (idempotent).

  docker compose exec -T backend python scripts/seed_dev_user.py

The account is already verified and has its default "Personal" workspace, exactly like a normal
sign-up followed by email verification. Docker Compose runs this once at start-up (service
`dev-user`). It refuses to run unless APP_ENV is `development`, so the fixed password can never
exist on a production database.
"""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import AppEnv, get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.database.connection import AsyncSessionLocal  # noqa: E402
from app.modules.auth.schemas import TERMS_VERSION  # noqa: E402
from app.repositories.user_repository import UserRepository  # noqa: E402
from app.repositories.workspace_repository import WorkspaceRepository  # noqa: E402

DEV_EMAIL = "dev@example.com"
# Development only: main() refuses any APP_ENV other than development.
DEV_PASSWORD = "DevPassword2026!"  # noqa: S105
DEV_NAME = "Dev User"


async def main() -> int:
    if get_settings().app_env != AppEnv.development:
        print("seed_dev_user: refused, APP_ENV is not development", file=sys.stderr)
        return 1

    async with AsyncSessionLocal() as db:
        users = UserRepository(db)
        if await users.email_exists(DEV_EMAIL):
            print(f"seed_dev_user: {DEV_EMAIL} already exists")
            return 0

        now = datetime.now(UTC)
        user = await users.create(
            email=DEV_EMAIL,
            password_hash=hash_password(DEV_PASSWORD),
            terms_accepted_at=now,
            terms_version=TERMS_VERSION,
        )
        user.is_verified = True
        user.email_verified_at = now
        user.status = "active"
        await users.create_profile(user_id=user.id, full_name=DEV_NAME)
        await users.create_preferences(user_id=user.id)
        await WorkspaceRepository(db).create(
            user_id=user.id,
            name="Personal",
            workspace_type="personal_learning",
            is_default=True,
            description="Your default personal workspace.",
        )
        await db.commit()
        print(f"seed_dev_user: created {DEV_EMAIL}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
