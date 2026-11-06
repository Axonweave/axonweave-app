# Axonweave autopilot kit
Copy into the repo root (keeps the folder layout): docs/AUTOPILOT.md, docs/prompts/*, scripts/autopilot.mjs.
Then follow the steps given in chat. Commands:
  node scripts/autopilot.mjs --status
  node scripts/autopilot.mjs --dry-run
  node scripts/autopilot.mjs --stop-after P3-4
  node scripts/autopilot.mjs            (runs P3-2 .. P3-7, pauses; run again for Phase 4)
  node scripts/autopilot.mjs --reset P3-3   (after fixing a blocked task)
Flags: --no-merge (open PRs, never merge), --yolo (skip permission prompts: containers/VMs only), --from, --only, --max-sessions, --max-turns.
Env: AUTOPILOT_MODEL to choose the model.
