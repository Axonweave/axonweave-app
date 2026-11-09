"""Upload/processing timing check against the RUNNING stack (Phase 3 M7). Prints counts and
seconds only, never document text. Creates a throwaway user, uploads many small files and one
large file over HTTP to the API, waits for the real worker, deletes the documents (queues object
cleanup) and then the user.

  docker compose exec backend python scripts/load_check.py [small_files] [large_mib]
"""

import asyncio
import secrets
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.core.config import AppEnv, get_settings  # noqa: E402
from app.core.security import generate_token, hash_password, hash_token  # noqa: E402
from app.database.connection import AsyncSessionLocal  # noqa: E402
from app.models.session_model import Session  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.user_preferences import UserPreferences  # noqa: E402
from app.models.user_profile import UserProfile  # noqa: E402
from app.models.workspace import Workspace  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"


async def make_user() -> tuple[uuid.UUID, uuid.UUID, str, str]:
    async with AsyncSessionLocal() as db:
        now = datetime.now(UTC)
        user = User(
            email=f"load-{secrets.token_hex(4)}@example.com",
            password_hash=hash_password(secrets.token_urlsafe(16)),
            status="active",
            is_verified=True,
            email_verified_at=now,
            terms_accepted_at=now,
            terms_version="1.0",
        )
        db.add(user)
        await db.flush()
        db.add(UserProfile(user_id=user.id, full_name="Load check"))
        db.add(UserPreferences(user_id=user.id))
        ws = Workspace(
            user_id=user.id, name="Load", workspace_type="personal_learning", is_default=True
        )
        db.add(ws)
        token, csrf = generate_token(), generate_token()
        db.add(
            Session(
                user_id=user.id,
                session_token_hash=hash_token(token),
                expires_at=now + timedelta(hours=1),
                created_at=now,
                last_used_at=now,
            )
        )
        await db.commit()
        return user.id, ws.id, token, csrf


async def wait_done(client: httpx.AsyncClient, ids: list[str], timeout: float) -> dict[str, int]:
    start = time.monotonic()
    counts: dict[str, int] = {}
    while time.monotonic() - start < timeout:
        counts = {}
        for doc_id in ids:
            r = await client.get(f"{BASE}/documents/{doc_id}/status")
            st = r.json()["data"]["processing_status"] if r.status_code == 200 else "error"
            counts[st] = counts.get(st, 0) + 1
        if all(k in ("completed", "failed", "cancelled") for k in counts):
            break
        await asyncio.sleep(2)
    return counts


async def main(small: int, large_mib: int) -> int:
    if get_settings().app_env == AppEnv.production:
        print("Refusing: production.")
        return 2
    user_id, ws_id, token, csrf = await make_user()
    ids: list[str] = []
    try:
        async with httpx.AsyncClient(
            cookies={"aw_session": token, "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
            timeout=120,
        ) as client:
            t0, rejected, sent = time.monotonic(), 0, 0
            for batch_start in range(0, small, 3):
                files = [
                    (
                        "files",
                        (
                            f"small-{i}.txt",
                            f"Note {i}: photosynthesis in chloroplasts.".encode(),
                            "text/plain",
                        ),
                    )
                    for i in range(batch_start, min(batch_start + 3, small))
                ]
                r = await client.post(
                    f"{BASE}/documents/upload", files=files, data={"workspace_id": str(ws_id)}
                )
                sent += len(files)
                if r.status_code in (200, 201):
                    body = r.json()["data"]
                    ids += [d["id"] for d in body["documents"]]
                    rejected += len(body.get("rejected", []))
                else:
                    rejected += len(files)
                    print(f"batch http={r.status_code}")
            t_up = time.monotonic() - t0
            counts = await wait_done(client, ids, 300)
            print(f"small files: sent={sent} accepted={len(ids)} rejected={rejected}")
            print(f"  upload {t_up:.1f}s; all done after {time.monotonic() - t0:.1f}s; {counts}")

            body = (b"x" * 1023 + bytes([10])) * 1024 * large_mib
            t1 = time.monotonic()
            r = await client.post(
                f"{BASE}/documents/upload",
                files=[("files", ("large.txt", body, "text/plain"))],
                data={"workspace_id": str(ws_id)},
            )
            t_large = time.monotonic() - t1
            print(f"large file {large_mib} MiB: http={r.status_code} upload {t_large:.1f}s")
            if r.status_code in (200, 201):
                data = r.json()["data"]
                new_ids = [d["id"] for d in data["documents"]]
                ids += new_ids
                if new_ids:
                    c = await wait_done(client, new_ids, 300)
                    print(f"  processing result: {c}")
                for rej in data.get("rejected", []):
                    print(f"  rejected: {rej.get('code')}")
            elif r.status_code != 413:
                print(f"  error code: {r.json().get('error', {}).get('code')}")
            else:
                print("  rejected with 413 (over the size limit)")
            for doc_id in ids:
                await client.delete(f"{BASE}/documents/{doc_id}")
        return 0
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
        print("cleanup: user removed")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 18
    mib = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    raise SystemExit(asyncio.run(main(n, mib)))
