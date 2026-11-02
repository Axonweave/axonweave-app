## What and why
<!-- One short paragraph. Link the task id from docs/TASKS.md, e.g. B3. -->

## Spec / acceptance criteria covered
<!-- Spec sections and the section-22 checkboxes this PR satisfies. -->

## Changes outside my owned area or in shared files
<!-- List them, or write "none". Shared files: backend/app/api/v1/router.py, backend/app/main.py, models/__init__.py, package.json, docker-compose.yml, .env.example -->

## Database
- [ ] No schema change
- [ ] New migration included; `alembic heads` shows exactly one head; upgrade and downgrade both tested

## Checklist
- [ ] Ownership/authorization checked in the backend; cross-user access test added (returns 404)
- [ ] Input validated on the backend; no secrets/tokens/passwords in logs or responses
- [ ] Backend tests pass / frontend tests pass / lint and typecheck pass
- [ ] Frontend API types regenerated from OpenAPI (if API changed)
- [ ] `.env.example` and docs updated if config or commands changed
- [ ] No fake data, no non-functional buttons, nothing from spec section 23 implemented

## How I verified it
<!-- Commands run, manual steps, screenshots for UI. -->

## Not done / known gaps
