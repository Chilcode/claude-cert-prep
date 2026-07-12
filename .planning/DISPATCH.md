# DISPATCH.md — CCAF Study Tool build board

**Orchestrator:** Opus 4.8 (David's PM session). **Executors:** separate Claude Code instances, one per Agent ID below.
**How this works:** David starts a fresh Claude Code instance per agent and pastes a one-line bootstrap (see §Bootstrap). Each agent reads *only its own section* here, executes it, and **appends to its Status Log entry** as it goes. The orchestrator reads this file, gates/unblocks agents, and coordinates rotation. Nobody pastes agent output back into the PM chat — this file is the channel.

---

## Roster & state

| Agent | Task | Model | Owns (writes) | State |
|-------|------|-------|---------------|-------|
| **AGENT-1** | Learning-science spec + rebuild the Study System spreadsheet | Sonnet 5 | `.planning/SUPERLEARN-SPEC.md`, new `.xlsx` | 🟢 READY — start now |
| **AGENT-2** | De-scratchpad build + size/zoom fix + review shuffle + tutor prompt-caching | Sonnet 5 | `build/quiz-template.html`, `build/build_hub.py`, `index.html` | 🟢 READY — start now |
| **AGENT-3** | 7-phase "Learning Path" scaffold + Phase-5 loading-strategy scheduler | Sonnet 5 | `build/quiz-template.html` | 🔴 BLOCKED — needs AGENT-1 spec APPROVED **and** AGENT-2 merged |
| **AGENT-4** | Teach-back / Feynman "explain *why*" mode | Sonnet 5 | `build/quiz-template.html` | 🔴 BLOCKED — needs AGENT-2 merged; serialize *after* AGENT-3 (same file) |

State values: `READY` · `IN PROGRESS` · `NEEDS-REVIEW` (waiting on David/orchestrator) · `BLOCKED` · `ROTATE` (near context limit — see §Rotation) · `DONE`.

---

## Global rules (every agent)

1. **Source of truth = `build/quiz-template.html`.** NEVER hand-edit `index.html` — it is generated. Edit the template → run the build → the build writes `index.html`.
2. **Build = `python build/build_hub.py`.** Requires `pip install markdown`. After every build, **`node --check`** the inline JS (extract or use the build's check) before considering it shippable.
3. **One writer per file.** Only ONE agent edits `build/quiz-template.html` at a time. In Wave 1 that's AGENT-2 only (AGENT-1 never touches it). Wave 2 is AGENT-3 then AGENT-4, serialized.
4. **Preserve:** dyslexia-font default; localStorage keys `ccaf-stats-v1` (per-card r/w/sr/note) and `ccaf-font-v1`; the existing tutor + TTS plumbing.
5. **Push** (only when David says ship): `gh.exe auth token` inline-URL form — the WSL credential manager fails from an agent shell. If push fails, leave the commit local and log it; David will push.
6. **Log as you go.** Append to your Status Log entry (§Status Log) at each milestone and before you stop. If you hit a decision that needs David, set state `NEEDS-REVIEW` and stop.
7. Paths (Windows instances): repo `C:\Users\david.rios\Dev\claude-cert-prep`; materials `C:\Users\david.rios\Dev\learning\CCAF\`. (WSL: `/mnt/c/Users/david.rios/Dev/...`.)

---

## AGENT-1 — Learning-science spec + spreadsheet copy  (Sonnet 5, read-only on code)

**Context:** Also read `.planning/SUPERLEARNER-HANDOFF.md` (full 7-phase background). You are the merged "Session A + spreadsheet build."

**Read (use the `pdf-reading` skill for PDFs, `spreadsheet` skill for xlsx) — from `...\learning\CCAF\`:**
- `BecomeASuperLearner_Part1.pdf`, `_Part2.pdf` — **only these two, not the full book.**
- `Copy of Study System Spreadsheet.xlsx` — all 7 phase sheets.
- `Levels of Learning.md` (Ackoff: data→information→knowledge→**understanding**→**wisdom**; the goal is *understanding*/"why" + *wisdom*), `SuperHuman Life.md`, `Personal Learning Systems.docx`, `What-How.docx`.

**Deliver:**
1. `.planning/SUPERLEARN-SPEC.md` — for each of the 7 phases: (a) what the method actually prescribes, (b) the concrete study-hub feature that implements it (existing vs. new), (c) Phase-5 loading strategies (back-/level-/front-loaded) expressed as **actual SM-2 scheduling parameters**. Implementation-ready — AGENT-3 executes from it.
2. A **rebuilt copy of the Study System spreadsheet** (new `.xlsx` in the repo, e.g. `learning-system.xlsx`) with clean tabs incl. **Levels of Learning**, **Personal Learning Systems**, **SuperHuman Life** — David's "build a copy" ask.

**Gate:** Show David the spec inline BEFORE writing the file (his standing rule). Set state `NEEDS-REVIEW` when the spec draft is ready; do not unblock AGENT-3 yourself. No code edits.

---

## AGENT-2 — De-scratchpad build + three fixes  (Sonnet 5, sole template writer in Wave 1)

Work in `build/quiz-template.html`; rebuild after each change; `node --check`; ship incrementally.

**Step 0 — de-scratchpad the build (prerequisite, do first).** `build/build_hub.py` has hardcoded paths to a dead temp dir (`/tmp/.../50551102-.../scratchpad`) for the template input, fontcache, and output artifact. Repoint every `SCRATCH`-relative path into `build/` (template = `build/quiz-template.html`; fontcache = `build/fontcache`; standalone output = repo-root `index.html`) so the build runs from a fresh clone. Confirm `python build/build_hub.py` regenerates `index.html` cleanly.

**Fix 1 — size/zoom regression** ("small/medium/large/XL does nothing; still have to zoom"). Commit `d10b9a1` "true zoom sizing" regressed. Find `applyFont()` — it sets CSS vars `--serif`/`--sans` (font *families*) but does **not** appear to apply a size/scale. Trace the S/M/L/XL control → its saved pref in `ccaf-font-v1` → confirm nothing reads it as a scale. Fix: apply the chosen size as a real scale (e.g. a `--doc-scale` var / root font-size the doc/question typography inherits from) and wire the control + persistence to it. Verify by actually changing the setting and seeing text resize with no browser zoom.

**Fix 2 — review shuffle.** Answer options are **already** shuffled (`order: shuffle([0,1,2,3])`), and exam shuffles within-scenario — but `startReview()` builds the due-card queue in **schedule order, unshuffled**. Fix: shuffle the final review queue with the existing `shuffle()` util **while preserving the due-card filter** (only cards actually due). Do not disturb exam/drill.

**Fix 3 — tutor prompt-caching.** The voice tutor (commit `d1c117d`) calls Claude with study-doc/question context. Correct the model David had: caching is **not** an account toggle — it's per-request `cache_control` on the *stable prefix*. Find the tutor's Anthropic request; put the stable context (system prompt + study-doc/question grounding) first with a `cache_control: {type:"ephemeral"}` breakpoint (or top-level `cache_control:{type:"ephemeral"}` to auto-cache the last cacheable block), keep the volatile user question last. Verify caching actually engages by logging `usage.cache_read_input_tokens` (>0 on the 2nd+ turn of a tutoring session). Caveats to note in your log: min cacheable prefix is ~4096 tokens on Opus 4.8 / ~2048 on Sonnet — if the grounding is smaller it silently won't cache (harmless). Do NOT change the tutor's model. If the call is browser-direct, the `anthropic-dangerous-direct-browser-access` header must already be present (tutor works today); caching is unaffected.

Ship order: Step 0 → Fix 2 (smallest) → Fix 1 → Fix 3. Set `NEEDS-REVIEW` when all three build clean and pass `node --check`; David pushes.

---

## AGENT-3 — 7-phase Learning Path scaffold + loading strategies  (BLOCKED)

Unblocks when AGENT-1's spec is APPROVED and AGENT-2 is merged. Read `.planning/SUPERLEARNER-HANDOFF.md` + `.planning/SUPERLEARN-SPEC.md`. Implement the 7-phase "Learning Path" framing over the existing Study/Practice/Progress tabs, and add the Phase-5 loading-strategy chooser (back/level/front-loaded) into Review's SM-2 scheduler. Template + rebuild + `node --check`; ship incrementally.

## AGENT-4 — Teach-back / Feynman mode  (BLOCKED)

Unblocks when AGENT-2 is merged; run *after* AGENT-3 (both write the template). Add a "Teach-back" mode: on a question, instead of picking, David explains *out loud* why the answer is correct (reuse the voice-input + Anthropic-tutor plumbing); the tutor grades the explanation against the official explanation + the answer-physics principle and names what was missed. Implements Phase 4 "Make it Simple" + Ackoff "understanding." Template + rebuild + `node --check`.

---

## Rotation protocol (context-window handoff)

Sonnet 5 / Opus 4.8 have **1M-token** windows, so this should be rare — but if any agent senses it's filling up (roughly ≥70–80% of its usable window, or after very heavy PDF/file reads):

1. Append to your Status Log: `⚠️ ROTATE-REQUEST` + (a) what's DONE, (b) the exact NEXT step, (c) files touched / uncommitted, (d) a self-contained RESUME note a fresh instance can act on with no other context. Set state `ROTATE`.
2. Tell David (in that instance) you're rotating. David pings the orchestrator; the orchestrator verifies the RESUME note is complete and gives David the go + the same bootstrap to relaunch.
3. David closes that instance, opens a fresh one, pastes the same bootstrap (same Agent ID). The new instance reads its ROTATE/RESUME note, flips state back to `IN PROGRESS`, and continues.

---

## Bootstrap (David pastes this into each fresh instance; swap the ID)

> You are **AGENT-2** on the CCAF study tool. Open `C:\Users\david.rios\Dev\claude-cert-prep\.planning\DISPATCH.md`, read it fully, find the **AGENT-2** section, and execute it exactly. Follow the Global Rules. Append progress to your Status Log entry as you work, set `NEEDS-REVIEW` if you need me, and follow the Rotation Protocol if you near your context limit. Do not edit other agents' sections.

---

## Orchestrator queue (PM ↔ agents)
- _(empty — orchestrator appends approvals/unblocks here)_

---

## Status Log (agents append; newest at bottom of each block)

### AGENT-1
- _queued_
- IN PROGRESS: Starting. Read DISPATCH.md AGENT-1 section + roster. About to read SUPERLEARNER-HANDOFF.md, then source materials (Part1/Part2 PDFs, spreadsheet, Levels of Learning.md, SuperHuman Life.md, Personal Learning Systems.docx, What-How.docx). No code edits planned (read-only on code per role).

### AGENT-2
- _queued_
- IN PROGRESS: Step 0 done. `build_hub.py` de-scratchpadded — `BUILD = Path(__file__).resolve().parent`, `KIT = BUILD.parent` (also fixes the hardcoded absolute repo path, so it now runs from any clone location, not just David's machine). `font_faces()` cache → `build/fontcache`; template read → `build/quiz-template.html`; artifact output → `build/ccaf-practice.html`. Standalone `index.html` write unchanged (repo-root). Added `build/fontcache/` and `build/ccaf-practice.html` to `.gitignore` (cache + claude.ai-only artifact, not the deployed site). Ran `python build/build_hub.py` in a scratch venv (system Python is externally-managed, no `markdown` pkg installed) — clean run, and `index.html` output is **byte-identical** to the previously committed version (`git diff --stat index.html` empty), confirming the rebuild is deterministic. Baseline `node --check` on extracted inline JS passes. Moving to Fix 2 (review shuffle) next per ship order.
- IN PROGRESS: Fix 2 done. `startReview()` (build/quiz-template.html) — `const queue = [...seen, ...fresh].slice(0, 30)` → `const queue = shuffle([...seen, ...fresh].slice(0, 30))`. The `.slice(0,30)` cap still runs on the due-sorted `[...seen, ...fresh]` array first, so which cards are selected (most-overdue-first priority, only actually-due cards) is unchanged — `shuffle()` only randomizes presentation order of the selected set. Exam/drill untouched. Rebuilt + `node --check` clean. Moving to Fix 1 (size/zoom) next.

### AGENT-3
- _blocked_

### AGENT-4
- _blocked_
