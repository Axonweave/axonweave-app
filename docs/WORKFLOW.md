# Workflow

Rules for working in parallel on this repository. `CLAUDE.md` is the standing contract; this file
covers git and pull requests.

## Branches

- `main` is protected by convention: **never push to it directly** and never force-push a shared
  branch.
- One task per branch, named `<type>/<short-description>`, e.g. `feat/ui-dashboard-pages`,
  `fix/workspace-default`, `chore/phase1-closeout`.
- Branch from an up-to-date `main`. Rebase or merge `main` into your branch before opening the PR.

## Commits

- Small and frequent, Conventional Commits: `feat(auth): ...`, `fix(workspaces): ...`, `test: ...`,
  `docs: ...`, `chore: ...`, `ci: ...`.
- Never use `--no-verify`. If a hook fails, fix the cause.
- Never commit `.env`, keys, dumps or anything from `test-results/`. If a secret is ever committed,
  tell the team immediately so it is rotated; deleting the commit is not enough.

## Before opening a pull request

All of these must pass locally:

```bash
docker compose exec backend sh -c "ruff check . && ruff format --check ."
docker compose exec backend mypy app
docker compose exec backend pytest -m "not live"
docker compose exec backend alembic heads           # exactly one head
cd frontend && npm run lint && npx tsc --noEmit && npm run test
```

Use `-m "not live"`: tests marked `live` call the real AI provider, cost money and run only when you
choose (`pytest -m live tests/ai`). Likewise `scripts/run_ai_eval.py` and `scripts/llm_smoke_test.py` send
real requests; run them deliberately and never in CI. Never paste, commit or print a provider key.

For UI work also run the Playwright specs against the running stack. Regenerate the frontend API
types if backend schemas changed (`docs/SETUP.md`).

## Database migrations

- Every schema change is a new Alembic migration. **Never edit a migration that is merged to main.**
- After any rebase run `alembic heads`; there must be exactly one head. Two heads means a
  migration conflict that must be resolved with a merge migration before the PR.

## Pull requests

Use the template in `.github/pull_request_template.md`. State:

- the task (see `docs/TASKS_Phase1.md` or `docs/TASKS_Phase2.md`) and the spec acceptance items it satisfies
  (Phase 1 section 22, Phase 2 section 23 in `docs/PHASE2_ACCEPTANCE.md`);
- anything touched outside your owned area or in a shared file (list in `docs/TASKS_Phase1.md`);
- what was tested and what was **not**; do not tick an acceptance item that was not verified;
- for AI changes: whether the fake provider or a real one was used, and any change to quotas, limits, prompts
  or the privacy notice.

CI must be green. Reviewers check: ownership scoping on every query, 404 for non-owned resources,
no sensitive data in responses or logs, no placeholder controls.

## Shared files

Change minimally and mention in the PR: `backend/app/api/v1/router.py`, `backend/app/main.py`,
`backend/app/models/__init__.py`, `docker-compose.yml`, `.env.example`, `frontend/package.json`,
`README.md`.

## Claude Code sessions

Plan first for non-trivial work and wait for approval. One task per session; clear context between
tasks. If the spec is ambiguous or contradicts `docs/DECISIONS.md`, stop and ask.
