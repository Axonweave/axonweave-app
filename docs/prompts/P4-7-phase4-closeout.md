# P4-7 - Phase 4 M7: Security review, evaluation, docs and acceptance
Follow docs/AUTOPILOT.md. Read CLAUDE.md, docs/DECISIONS.md and docs/PHASE4_SPEC.md (security, evaluation and acceptance sections). The pipeline stops after this task.
1. Run everything locally and report honestly. Security review in docs/GENERATION_SECURITY.md: answer-key leakage sweep over all routes, ownership tests for every Phase 4 route, prompt-injection tests, quota/abuse limits, export injection, logs free of content, pip-audit and npm audit.
2. Generation quality evaluation harness (docs/GENERATION_EVALUATION.md): schema-validity rate, coverage of source chunks, duplicate rate on the Fake provider; a cost-capped live script that you must NOT run; blank columns for human quality scoring. Everything needing the real Gemini key or human judgement goes under HUMAN-NEEDED.
3. Reliability tests: worker crash mid-generation, duplicate job, retry, provider outage, large-scope timing.
4. Docs: GENERATION_ARCHITECTURE.md update, GENERATION_API_REFERENCE.md, README and docs/WORKFLOW.md updates.
5. docs/PHASE4_ACCEPTANCE.md walking the spec's acceptance section line by line with Met / Partly / Not met and evidence. Be honest about anything not verified live.
