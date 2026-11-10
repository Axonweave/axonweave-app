#!/usr/bin/env node
// Axonweave autopilot: runs each task prompt in a fresh `claude -p` session,
// then pushes, opens a PR, waits for CI and squash-merges only if CI is green.
// Usage: node scripts/autopilot.mjs [--dry-run] [--only P3-2] [--stop-after P3-4]
//        [--from P3-3] [--no-merge] [--yolo] [--max-sessions 3] [--status] [--reset P3-2]
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const TASKS = [
  ["P3-2", "P3-2-documents-upload-api.md", "Documents upload API"],
  ["P3-3", "P3-3-ingestion-pipeline.md", "Ingestion pipeline"],
  ["P3-4", "P3-4-embeddings-retrieval.md", "Embeddings and retrieval"],
  ["P3-5", "P3-5-rag-citations.md", "RAG and citations"],
  ["P3-6", "P3-6-ui-documents-rag.md", "Documents and RAG UI"],
  ["P3-7", "P3-7-phase3-closeout.md", "Phase 3 closeout", { pauseAfter: true }],
  ["P4-0", "P4-0-generation-engine.md", "Generation engine"],
  ["P4-1", "P4-1-summaries.md", "Summaries"],
  ["P4-2", "P4-2-flashcards.md", "Flashcards"],
  ["P4-3", "P4-3-quiz-engine.md", "Quiz engine"],
  ["P4-4", "P4-4-guides-glossary-formulas-bank.md", "Guides, glossary, formulas, question bank"],
  ["P4-5", "P4-5-library-versioning-export.md", "Library, versioning and export"],
  ["P4-6", "P4-6-ui-generation-library.md", "Generation and library UI"],
  ["P4-7", "P4-7-ui-quiz-export-preferences.md", "Quiz, export and preferences UI"],
  ["P4-8", "P4-8-phase4-closeout.md", "Phase 4 closeout", { pauseAfter: true }],
].map(([id, file, title, o = {}]) => ({ id, file, title, ...o }));

const args = process.argv.slice(2);
const flag = (n) => args.includes(n);
const val = (n, d) => (args.includes(n) ? args[args.indexOf(n) + 1] : d);
const DRY = flag("--dry-run");
const NO_MERGE = flag("--no-merge");
const YOLO = flag("--yolo");
const MAX_SESSIONS = Number(val("--max-sessions", 3));
const MAX_CI_FIXES = 2;
const MAIN = val("--main", "main");
const MAX_TURNS = val("--max-turns", "400");
const ROOT = process.cwd();
const STATE_DIR = path.join(ROOT, ".autopilot");
const STATE_FILE = path.join(STATE_DIR, "state.json");
const isWin = process.platform === "win32";

const log = (...a) => console.log(`[${new Date().toISOString().slice(11, 19)}]`, ...a);
const die = (m) => { console.error("\nSTOPPED: " + m); process.exit(1); };

function run(cmd, cmdArgs, opts = {}) {
  const r = spawnSync(cmd, cmdArgs, {
    cwd: ROOT, encoding: "utf8", shell: isWin, maxBuffer: 64 * 1024 * 1024, ...opts,
  });
  return { code: r.status ?? 1, out: (r.stdout || "") + (r.stderr || ""), stdout: r.stdout || "" };
}
const git = (...a) => run("git", a);
const gh = (...a) => run("gh", a);

function loadState() {
  try { return JSON.parse(fs.readFileSync(STATE_FILE, "utf8")); } catch { return { tasks: {} }; }
}
function saveState(s) {
  fs.mkdirSync(STATE_DIR, { recursive: true });
  fs.writeFileSync(STATE_FILE, JSON.stringify(s, null, 2));
}

function preflight() {
  for (const [c, a] of [["git", ["--version"]], ["gh", ["--version"]], ["claude", ["--version"]], ["node", ["--version"]]]) {
    if (run(c, a).code !== 0) die(`'${c}' not found on PATH.`);
  }
  if (gh("auth", "status").code !== 0) die("Run `gh auth login` first.");
  for (const t of TASKS) {
    if (!fs.existsSync(path.join(ROOT, "docs/prompts", t.file))) die(`Missing docs/prompts/${t.file}`);
  }
  for (const f of ["CLAUDE.md", "docs/AUTOPILOT.md", "docs/DECISIONS.md"]) {
    if (!fs.existsSync(path.join(ROOT, f))) die(`Missing ${f}`);
  }
  if (TASKS.some((t) => t.id.startsWith("P4")) && !fs.existsSync(path.join(ROOT, "docs/PHASE4_SPEC.md"))) {
    log("WARNING: docs/PHASE4_SPEC.md is missing; Phase 4 tasks will block until you add it.");
  }
  if (!fs.existsSync(path.join(ROOT, "docs/PHASE3_SPEC.md"))) die("Missing docs/PHASE3_SPEC.md");
  if (TASKS.some((t) => t.id.startsWith("P4")) && !fs.existsSync(path.join(ROOT, "docs/TASKS_Phase4.md"))) die("Missing docs/TASKS_Phase4.md");
}

const q = (a) => (isWin && /[ ()&|<>^]/.test(a) ? `"${a}"` : a);

function claudeArgs() {
  const a = ["-p", "--output-format", "text", "--max-turns", MAX_TURNS];
  if (YOLO) {
    a.push("--dangerously-skip-permissions");
  } else {
    a.push("--permission-mode", "acceptEdits");
    a.push("--allowedTools", "Bash", "Read", "Edit", "Write", "Glob", "Grep", "WebSearch");
    a.push("--disallowedTools",
      "Bash(git push:*)", "Bash(git reset --hard:*)", "Bash(git clean:*)", "Bash(git checkout main:*)",
      "Bash(git branch -D:*)", "Bash(gh pr merge:*)", "Bash(rm -rf /:*)", "Bash(rm -rf ~:*)");
  }
  if (process.env.AUTOPILOT_MODEL) a.push("--model", process.env.AUTOPILOT_MODEL);
  return a.map(q);
}

function sessionPrompt(task, resuming) {
  return [
    `You are running unattended in the Axonweave autopilot pipeline. TASK_ID = ${task.id}.`,
    `Read CLAUDE.md and docs/AUTOPILOT.md first, then do exactly what docs/prompts/${task.file} says.`,
    resuming
      ? `This is a RESUMED run: docs/autopilot/${task.id}-progress.md and earlier commits may exist. Verify what is really done and continue.`
      : `Start by writing docs/autopilot/${task.id}-plan.md and docs/autopilot/${task.id}-progress.md.`,
    `You are on branch autopilot/${task.id.toLowerCase()}. Do not push, merge or change branches; the pipeline does that.`,
    `Finish by committing docs/autopilot/${task.id}.md (the PR description), or docs/autopilot/${task.id}-BLOCKED.md if blocked.`,
  ].join("\n");
}

function exists(p) { return fs.existsSync(path.join(ROOT, p)); }

function ensureClean() {
  const s = git("status", "--porcelain");
  if (s.stdout.trim()) {
    // Commit leftover work so nothing is lost, then continue.
    git("add", "-A");
    git("commit", "-m", "chore(autopilot): save uncommitted work from interrupted session");
  }
}

function prepareBranch(task) {
  const branch = `autopilot/${task.id.toLowerCase()}`;
  const have = git("rev-parse", "--verify", branch).code === 0;
  if (have) {
    if (git("checkout", branch).code !== 0) die(`Cannot checkout ${branch}. Clean your working tree.`);
    return { branch, resuming: true };
  }
  if (git("checkout", MAIN).code !== 0) die(`Cannot checkout ${MAIN}. Commit or stash your changes.`);
  if (git("pull", "--ff-only", "origin", MAIN).code !== 0) die(`Cannot fast-forward ${MAIN}.`);
  if (git("checkout", "-b", branch).code !== 0) die(`Cannot create ${branch}.`);
  return { branch, resuming: false };
}

function runClaude(task, resuming) {
  const prompt = sessionPrompt(task, resuming);
  if (DRY) { log(`[dry-run] claude ${claudeArgs().join(" ")}  <<< ${prompt.split("\n")[0]}`); return 0; }
  fs.mkdirSync(path.join(STATE_DIR, "logs"), { recursive: true });
  const logFile = path.join(STATE_DIR, "logs", `${task.id}-${Date.now()}.log`);
  log(`claude session started (log: ${logFile})`);
  const r = spawnSync("claude", claudeArgs(), {
    cwd: ROOT, input: prompt, encoding: "utf8", shell: isWin, maxBuffer: 256 * 1024 * 1024,
  });
  fs.writeFileSync(logFile, (r.stdout || "") + "\n--- stderr ---\n" + (r.stderr || ""));
  if (r.status !== 0) log(`claude exited with code ${r.status}`);
  return r.status ?? 1;
}

function waitForChecks(pr) {
  // `gh pr checks --watch --fail-fast` exits non-zero if any check fails.
  // Give GitHub a moment to register the workflow runs first.
  spawnSync(isWin ? "timeout" : "sleep", isWin ? ["/t", "20", "/nobreak"] : ["20"], { shell: isWin });
  const noChecks = gh("pr", "checks", pr, "--required");
  if (/no checks reported|no required checks/i.test(noChecks.out)) {
    log("No checks reported. Treating as NOT green for safety.");
    return { green: false, out: noChecks.out };
  }
  const r = gh("pr", "checks", pr, "--watch", "--fail-fast");
  return { green: r.code === 0, out: r.out };
}

function ciFixSession(task, failure) {
  const prompt = [
    `TASK_ID = ${task.id}. CI failed on the open PR for branch autopilot/${task.id.toLowerCase()}.`,
    `Read docs/AUTOPILOT.md. Reproduce and fix the failures properly without weakening tests. Commit the fix. Do not push.`,
    `CI output (tail):\n${failure.slice(-6000)}`,
    `You can fetch full logs with: gh run list --branch autopilot/${task.id.toLowerCase()} --limit 1  then  gh run view <id> --log-failed`,
  ].join("\n");
  if (DRY) return;
  spawnSync("claude", claudeArgs(), { cwd: ROOT, input: prompt, encoding: "utf8", shell: isWin, maxBuffer: 256 * 1024 * 1024 });
}

function finishTask(task, st, branch) {
  const doneFile = `docs/autopilot/${task.id}.md`;
  if (DRY) { log(`[dry-run] would push ${branch}, open PR, wait for CI, squash-merge`); return "dry"; }

  if (git("push", "-u", "origin", branch).code !== 0) die("git push failed.");
  let pr = gh("pr", "list", "--head", branch, "--json", "number", "--jq", ".[0].number").stdout.trim();
  if (!pr) {
    const created = gh("pr", "create", "--base", MAIN, "--head", branch,
      "--title", `${task.id}: ${task.title}`, "--body-file", doneFile);
    if (created.code !== 0) die("gh pr create failed:\n" + created.out);
    pr = gh("pr", "list", "--head", branch, "--json", "number", "--jq", ".[0].number").stdout.trim();
  }
  st.pr = pr;

  for (let attempt = 0; attempt <= MAX_CI_FIXES; attempt++) {
    log(`PR #${pr}: waiting for CI (attempt ${attempt + 1})`);
    const res = waitForChecks(pr);
    if (res.green) break;
    if (attempt === MAX_CI_FIXES) return `CI still failing on PR #${pr} after ${MAX_CI_FIXES} fix sessions`;
    log("CI failed; starting a fix session");
    ciFixSession(task, res.out);
    if (git("push", "origin", branch).code !== 0) return "push of CI fix failed";
  }

  if (NO_MERGE) return "no-merge";
  const m = gh("pr", "merge", pr, "--squash", "--delete-branch");
  if (m.code !== 0) return `merge failed: ${m.out.trim().slice(0, 400)}`;
  git("checkout", MAIN); git("pull", "--ff-only", "origin", MAIN);
  return "merged";
}

function main() {
  if (flag("--status")) {
    const s = loadState();
    for (const t of TASKS) console.log(t.id.padEnd(5), (s.tasks[t.id]?.status || "pending").padEnd(10), t.title);
    return;
  }
  if (flag("--reset")) {
    const s = loadState(); delete s.tasks[val("--reset")]; saveState(s); return log("reset", val("--reset"));
  }
  preflight();
  const state = loadState();
  const only = val("--only");
  const from = val("--from");
  const stopAfter = val("--stop-after");
  let started = !from;

  for (const task of TASKS) {
    if (only && task.id !== only) continue;
    if (!started && task.id === from) started = true;
    if (!started) continue;
    const st = (state.tasks[task.id] ||= { status: "pending", sessions: 0 });
    if (st.status === "merged") { log(`${task.id} already merged, skipping`); continue; }
    if (st.status === "blocked" || st.status === "paused") {
      die(`${task.id} is ${st.status}. Fix it (see docs/autopilot/${task.id}-BLOCKED.md), then run with --reset ${task.id}.`);
    }

    log(`=== ${task.id}: ${task.title} ===`);
    const { branch, resuming } = prepareBranch(task);
    let resumedRun = resuming;

    while (!exists(`docs/autopilot/${task.id}.md`) && !exists(`docs/autopilot/${task.id}-BLOCKED.md`)) {
      if (st.sessions >= MAX_SESSIONS) {
        st.status = "blocked"; saveState(state);
        die(`${task.id}: no completion file after ${MAX_SESSIONS} sessions. Look at .autopilot/logs and the branch ${branch}.`);
      }
      st.sessions++; st.status = "running"; saveState(state);
      runClaude(task, resumedRun); ensureClean(); resumedRun = true;
      if (DRY) break;
    }

    if (exists(`docs/autopilot/${task.id}-BLOCKED.md`)) {
      st.status = "blocked"; saveState(state);
      die(`${task.id} reported BLOCKED. Read docs/autopilot/${task.id}-BLOCKED.md on branch ${branch}.`);
    }

    const result = finishTask(task, st, branch);
    if (result !== "merged" && result !== "dry" && result !== "no-merge") {
      st.status = "blocked"; saveState(state); die(`${task.id}: ${result}`);
    }
    st.status = result === "merged" ? "merged" : st.status; saveState(state);
    log(`${task.id}: ${result}`);

    if (task.pauseAfter && !DRY) {
      st.status = "merged"; saveState(state);
      log(`Phase checkpoint after ${task.id}. Review docs/PHASE*_ACCEPTANCE.md, then run again to continue.`);
      return;
    }
    if (stopAfter === task.id) return log(`stopped after ${task.id} as requested`);
  }
  log("Done.");
}
main();
