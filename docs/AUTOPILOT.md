# Autopilot protocol (read this first in every unattended task)

You are running UNATTENDED inside an automated pipeline (`scripts/autopilot.mjs`). Nobody will answer questions. A script around you creates the branch, pushes, opens the pull request, waits for CI, and merges. Your job is to do the task completely, test it honestly, and commit.

## 1. How you behave
- Never ask for approval or clarification. Where a task prompt says "plan first and wait for approval", instead write a short plan to `docs/autopilot/<TASK_ID>-plan.md`, commit it, and proceed.
- You are already on the correct branch. Do NOT create, switch, rebase or delete branches. Do NOT push, merge, force anything, or run `git reset --hard` / `git clean`. Only commit locally (the script pushes).
- Commit small and often with Conventional Commits (`feat(documents): ...`). Commit after every meaningful sub-step so work survives a restart.
- Keep `docs/autopilot/<TASK_ID>-progress.md` as a checklist of sub-steps and tick them as you go. If you find this file already exists, you are RESUMING: read it, read `git log main..HEAD`, check what is actually done, and continue. Do not redo finished work.

## 2. Making decisions yourself
Order of authority: `CLAUDE.md` > `docs/DECISIONS.md` > the task prompt > the phase spec in `docs/` > your own judgement.
- If still ambiguous, choose the safest, simplest, most reversible option that does not contradict the above.
- Record every non-trivial choice in `docs/AUTOPILOT_LOG.md` as one line: `TASK_ID | question | choice | reason`.
- If a choice is a lasting design rule, also add it to `docs/DECISIONS.md` with the next free number.
- Never change an out-of-scope item from the phase spec into scope.

## 3. Quality gates (all must pass before you finish)
Run the checks that apply to what you touched, and fix failures properly:
- Backend: `ruff check`, `ruff format --check`, `mypy app`, the full pytest suite, migration upgrade AND downgrade, exactly one Alembic head.
- Frontend: lint, typecheck, build, Vitest; Playwright when the task asks for it.
- `docker compose up` still works and services are healthy when infra changed.
- NEVER weaken, delete or skip tests to get green. No `|| true`, no `xfail` to hide a real bug. If a test is wrong, fix the test and say why in the summary.
- Add the tests the task prompt asks for, including cross-user (ownership) tests that return 404.

## 4. Safety rules
- Never read, print or commit `.env`, API keys, tokens, `testdata-private/`, `*.pem`, `*.key`, or large binaries. Never put a secret in a log, a test or a doc.
- Do NOT call the real Gemini API or any paid external service. `RUN_LIVE_LLM_TESTS` is unset: skip live checks and list them under HUMAN-NEEDED.
- Use the Fake providers and generated fixtures for all tests.
- Follow every security rule in `CLAUDE.md` (ownership checks, 404 for non-owned, no content in logs, untrusted LLM output, answer keys never in responses, etc.).

## 5. When you cannot finish
Stop and create `docs/autopilot/<TASK_ID>-BLOCKED.md` (what is blocking, what you tried, what a human must do), commit it, and finish. Blocking reasons ONLY:
- a secret, credential or paid action is required;
- a prerequisite from an earlier phase or milestone is missing or broken in a way you cannot safely fix within this task;
- a destructive, irreversible action would be required;
- tests still fail after 3 genuine, different fix attempts;
- the task would require implementing something the phase spec marks as out of scope.
Anything else: decide and continue.

## 6. Things only a human can do
Some parts need a person (real lecture files, human scoring of answer quality, looking at the UI in a browser, live Gemini checks, deployment, choosing legal/privacy wording). Do the automatable part, build the scaffolding, and list the rest under **HUMAN-NEEDED** in your summary. Never fabricate results for them. Never claim an acceptance item is "Met" without evidence you actually ran.

## 7. Your final deliverable
Write `docs/autopilot/<TASK_ID>.md` and commit it as your LAST commit. It becomes the pull request description, so keep it clear:
```
# <TASK_ID> - <title>
## What was built
## Decisions made (with reasons)
## Verified (exact command -> result)
## NOT verified / limitations
## HUMAN-NEEDED
```
The presence of this file tells the pipeline you finished. Do not create it until the work is done and the gates pass.
