# AI evaluation (spec 18)

A working connection does not prove a useful tutor. This document describes how answer quality,
latency and cost are evaluated, and records the first run. **Answer quality has not been scored yet.**
The scoring columns in the results file are blank on purpose: correctness and hallucination need a
human reviewer, not the tool that produced the answers.

## What exists

| Item | Where |
|------|-------|
| Question set, 40 items | `docs/ai_eval/questions.yaml` |
| Runner with hard caps | `backend/scripts/run_ai_eval.py` (tested in `backend/tests/ai/test_ai_eval_script.py`, fake provider, no cost) |
| Results of the first live run | `docs/ai_eval/results/2026-11-06_gemini-3.5-flash-lite_n15.csv` |

### The question set (spec 18.1)

Forty items over the seven subjects: computer science (6), mathematics (6), artificial intelligence (6),
cloud computing (5), cybersecurity (5), database systems (5), programming (7).
Every kind in the spec appears: simple, complex, multi-step, follow-up (two turns sent as one
conversation, so context retention can be judged), ambiguous, incorrect assumption (`false_premise`) and
requires-uncertainty. Each item has a `reviewer_hint`: a short note on what a good answer should do. The hints
were written from general knowledge, are not an answer key, are never sent to the model, and must be checked
by the reviewer.

### The runner

- Uses the same path the app uses: the configured provider and default model, the production
  `academic_tutor` system prompt (key and version are recorded), the configured output-token and
  timeout settings, and the previous turns as context for follow-ups.
- **Two hard caps** stop it: `--max-requests` (default 15; every turn is one request) and
  `--max-total-tokens` (default 60,000, input plus output as reported by the provider). It makes one
  attempt per request with no retries, so the request cap is a true upper bound on billed calls.
- It streams, so it records time to first token as well as total time.
- With a budget smaller than the whole set it chooses items deterministically, spreading across
  question kinds and subjects, and never cuts a follow-up item in half. `--dry-run` shows the selection and sends nothing.
- A failed turn is recorded with its error code (never provider text) and its follow-up turns are skipped.
- Console output has ids, timings and token counts only. Answers go to the results file only. The key is never printed.
- Cost: from the pricing registry (D-39). With no verified price the cost is the word `unknown`, never 0.

### Results file columns

Filled by the runner: run id and time (UTC), provider, model id, prompt key and version, question id, subject, kind,
turn, question, answer, status, error code, finish reason, time to first token, total latency, input and output tokens,
usage source, estimated cost and currency.

**Blank, for the reviewer:** `correctness`, `relevance`, `clarity`, `hallucination`, `instruction_following`,
`context_retention`, `reviewer_notes`. Suggested scale: 0 to 2 per metric (0 wrong or missing, 1 partly,
2 good), and for `hallucination` count or note each invented claim. Use the same scale for every provider.

Spec 18.2 also lists *latency*, *cost* and *reliability*; those are measured by the runner (latency, cost) and
by the status column (reliability).

## How to run

The backend container mounts `backend/` only, so copy the questions in and the results out:

```bash
docker compose cp docs/ai_eval/questions.yaml backend:/tmp/questions.yaml
docker compose exec backend python scripts/run_ai_eval.py --questions /tmp/questions.yaml --dry-run
docker compose exec backend python scripts/run_ai_eval.py --questions /tmp/questions.yaml \
    --out /tmp/results.csv --max-requests 15 --max-total-tokens 60000
docker compose cp backend:/tmp/results.csv docs/ai_eval/results/<date>_<model>_n<requests>.csv
```

Requires `LLM_PROVIDER`, `LLM_DEFAULT_MODEL` and the provider key in your local `.env`. It sends real requests
and costs money. To try another model for one run without editing `.env`, pass
`docker compose exec -e LLM_DEFAULT_MODEL=<id> backend ...`.

To compare providers or models (spec 18.3), run the same question file with the same caps and settings for each and
score them in the same session. Do not choose a provider from a few impressive answers.

## Run 1: 2026-11-06, provider `gemini`, model `gemini-3.5-flash-lite`, prompt `academic_tutor` v1

Run id `8981665b4daa`. Cap 15 requests, 60,000 tokens. 13 of the 40 items were selected
(`cs-01, cs-02, cs-06, ma-03, ma-06, ai-03, ai-04, cc-03, cy-03, cy-04, db-01, db-03, pr-06`),
covering all seven subjects and all seven question kinds.

| Measure | Result |
|---------|--------|
| Requests sent | 15 of cap 15 |
| Succeeded / failed / skipped | 15 / 0 / 0 |
| Finish reason | `stop` for all 15 (none truncated) |
| Total latency | median 4.10 s, mean 3.99 s, max 5.58 s |
| Time to first token | median 0.71 s, max 1.51 s |
| Tokens (provider reported) | 4,602 input + 13,506 output = 18,108 (cap 60,000) |
| Estimated cost | **unknown**: there is no verified price for this model in the pricing registry |

| Question | Kind | Turn | First token (s) | Total (s) | Input tokens | Output tokens |
|---|---|---|---|---|---|---|
| cs-01 | simple | 1 | 0.79 | 2.87 | 161 | 696 |
| cs-02 | complex | 1 | 0.70 | 5.02 | 162 | 1200 |
| cs-06 | ambiguous | 1 | 1.51 | 4.71 | 156 | 938 |
| ma-03 | complex | 1 | 0.71 | 3.87 | 169 | 1066 |
| ma-06 | uncertainty | 1 | 1.11 | 4.05 | 156 | 780 |
| ai-03 | follow_up | 1 | 1.36 | 4.13 | 160 | 869 |
| ai-03 | follow_up | 2 | 0.67 | 4.41 | 1040 | 871 |
| ai-04 | false_premise | 1 | 0.70 | 4.10 | 171 | 861 |
| cc-03 | multi_step | 1 | 0.87 | 5.58 | 170 | 1234 |
| cy-03 | follow_up | 1 | 0.55 | 4.63 | 160 | 1247 |
| cy-03 | follow_up | 2 | 1.03 | 4.98 | 1417 | 1120 |
| cy-04 | false_premise | 1 | 0.58 | 3.72 | 168 | 847 |
| db-01 | simple | 1 | 0.69 | 3.60 | 160 | 904 |
| db-03 | multi_step | 1 | 0.58 | 2.90 | 196 | 649 |
| pr-06 | ambiguous | 1 | 0.72 | 1.29 | 156 | 224 |

Observations from the numbers only (no judgement of answer content):

- Answers are long: about 3,900 characters on average and 650 to 1,250 output tokens for most questions, even
  for simple ones. The `output_tokens` figure is what the provider reports and may include model reasoning tokens;
  the runner does not separate them. Output tokens dominate the cost of a conversation, so a short-answer
  instruction in the prompt or a lower `LLM_MAX_OUTPUT_TOKENS` should be considered once quality is scored.
- Follow-up turns cost more input because the first answer is sent back as context (160 to 1,040 and 1,417 input tokens).
- Token use per request averaged about 1,200 (18,108 over 15 requests). At the default quotas (50 messages and
  200,000 tokens a day) 50 messages of this size use about 60,000 tokens, so the message quota would be reached
  first for short chats. Long conversations send more history as input (see above), so the token quota could be
  reached first for them. Re-check both defaults against real usage.
- Latency is acceptable for a tutor (first token under 1.6 s in every request). Based on 15 requests from one machine at one
  time of day, so it is not a load or percentile result.

### What this run does not tell us

- **Whether the answers are correct, relevant, clear or free of hallucination.** That is the reviewer's job. Nothing in this repository claims
  the answers were good.
- Cost in money (unverified price). Once the provider's published price for this model is verified and added to the
  pricing registry (D-39, with a date and source), re-run to get costs.
- Behaviour on the other 27 items, or anything beyond 15 requests.
- Comparison with any other model or provider.

## Manual review procedure (spec 18.3)

1. Open the CSV in a spreadsheet (UTF-8; the file has a BOM so Excel reads it correctly).
2. For each row, read `question` and `answer` with the `reviewer_hint` from `questions.yaml` next to it.
3. Fill the seven scoring columns; for follow-up second turns, score `context_retention`.
4. Record reviewer name and date in `reviewer_notes` of the first row.
5. Summarise per subject and per kind. Watch for patterns: do false-premise items get challenged? do ambiguous
   items get a clarifying question? does the model express uncertainty on open questions?
6. Record decisions (model choice, prompt changes) in `docs/DECISIONS.md`.

## Automated quality tests (spec 18.4)

All run on the fake provider with no cost; see `docs/AI_TESTING.md`: API response validation, streaming completion, message
persistence, context construction, provider failure handling, usage recording, ownership validation and prompt
version selection. The live provider tests are optional and marked `live`.
