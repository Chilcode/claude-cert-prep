# DISPATCH.md — CCAF Study Tool build board

**Orchestrator:** Opus 4.8 (David's PM session). **Executors:** separate Claude Code instances, one per Agent ID below.
**How this works:** David starts a fresh Claude Code instance per agent and pastes a one-line bootstrap (see §Bootstrap). Each agent reads *only its own section* here, executes it, and **appends to its Status Log entry** as it goes. The orchestrator reads this file, gates/unblocks agents, and coordinates rotation. Nobody pastes agent output back into the PM chat — this file is the channel.

---

## Roster & state

| Agent | Task | Model | Owns (writes) | State |
|-------|------|-------|---------------|-------|
| **AGENT-1** | Learning-science spec + rebuild the Study System spreadsheet | Sonnet 5 | `.planning/SUPERLEARN-SPEC.md`, new `.xlsx` | ✅ DONE — spec approved + written, spreadsheet built. AGENT-3 still needs orchestrator to flip its own BLOCKED gate |
| **AGENT-2** | De-scratchpad build + size/zoom fix + review shuffle + tutor prompt-caching | Sonnet 5 | `build/quiz-template.html`, `build/build_hub.py`, `index.html` | 🟢 MERGED — committed `0e1a0b6`; 3 fixes verified in deployed index.html. **Push to live Pages held** pending David's in-browser check of the size fix. |
| **AGENT-3** | 7-phase "Learning Path" scaffold + Phase-5 loading-strategy scheduler | Sonnet 5 | `build/quiz-template.html` | 🟢 READY — gates cleared (spec APPROVED + AGENT-2 merged). Launch when David is ready. |
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
- 2026-07-12 — AGENT-1 spec + `learning-system.xlsx` reviewed & committed (`cae3ec9`). Flagged to David: the Phase-1 mastery-direction inversion (spec §1).
- 2026-07-12 — AGENT-2 committed (`0e1a0b6`): rescued source-of-truth now version-controlled; all 3 fixes verified present in deployed `index.html`. **Push to GitHub Pages held** pending David's in-browser check of the size fix (Firefox — original bug was CSS `zoom`, unsupported there).
- 2026-07-12 — AGENT-3 gates cleared (spec APPROVED + AGENT-2 merged) → flipped to READY. AGENT-4 stays BLOCKED (runs after AGENT-3; same file).

---

## Status Log (agents append; newest at bottom of each block)

### AGENT-1
- _queued_
- IN PROGRESS: Starting. Read DISPATCH.md AGENT-1 section + roster. About to read SUPERLEARNER-HANDOFF.md, then source materials (Part1/Part2 PDFs, spreadsheet, Levels of Learning.md, SuperHuman Life.md, Personal Learning Systems.docx, What-How.docx). No code edits planned (read-only on code per role).
- NEEDS-REVIEW: Spec draft complete, shown to David inline in chat (not yet written to `.planning/SUPERLEARN-SPEC.md` per the show-before-write gate). Key findings: (1) Part1/2 PDFs have no OCR text layer — read via rendered page images instead (Ch2,16-17,27,33,34). (2) Decoded the spreadsheet's Phase-5 X-multiple formulas directly — proved the three loading-strategy calendar dates are algebraically identical, so the real mechanic is new-card daily intake pacing, not per-card SM-2 interval growth (ruled out a compounding-interval design that blew up to ~180 days by rep 8). Spec proposes: preserve gradeCard()/ef/iv untouched, gate isDue() for never-started cards only via a new ccaf-loading-v1 pref + newCardCapToday(), admission ordered by Phase-1 priority (domain weight × mastery gap). Full phase-by-phase existing-vs-new mapping done for all 7 phases; Phase 4 flagged as entirely AGENT-4's build (wrote the grading contract for them to consume). Build-order recommendation: Phase5 → Phase3(tree view) → Phase1(framing) → Phase6(exercises doc-list) → Phase2/7(low-risk, last). Waiting on David's approve before writing spec file.
- Spreadsheet deliverable DONE: `learning-system.xlsx` written to repo root (not gated — dispatch's show-before-write gate only named the spec file). 10 tabs: Phase 1-7 (rebuilt as clean, reusable templates — same mechanics as the original, decluttered from ~1000 unused rows to ~30-40, formulas intact) + 3 new reference tabs (Levels of Learning, Personal Learning Systems, SuperHuman Life). Phase 1 keeps a Priority-score formula but deliberately inverts the original sheet's mastery direction (flagged in spec §1) so it rewards low-mastery/high-importance instead of the original's backwards weighting. Phase 5 tab is the reference model for the spec's loading-strategy design — full 8-checkpoint new-card intake schedule with a Beginner/Intermediate/Advanced dropdown (data validation) driving a CHOOSE/MATCH-selected active curve. SuperHuman Life tab deliberately omits David's actual groupmates' names/schedule (concepts — Hero/Coach/Helper/Advisor roles, Feynman Technique reference — only; this repo is public). Verification: found and fixed two real formula bugs during build (dead code clobbering a cell with a text label; a wrong cell reference making the whole intake schedule evaluate to 0) — caught via the `formulas` package actually calculating the workbook (0 errors across 414 evaluated cells) since no LibreOffice available in this sandbox for visual rendering; also hand-simulated the 3 loading curves in Python and confirmed the spreadsheet's computed values match exactly (e.g. Beginner checkpoint-1 = 10 cards, all three curves total exactly 166 by checkpoint 8). File is untracked (not committed — David commits/pushes per Global Rule 5).
- ✅ DONE: David approved the spec inline in chat ("Go ahead, write the superlearnspec.md!"). Wrote `.planning/SUPERLEARN-SPEC.md` verbatim from the approved draft, with two small tightenings on the way in: (1) status header changed from DRAFT to "APPROVED by David 2026-07-12," (2) cleaned up a dangling unused `startedCount` variable in the §5.2 `isDue()` code sketch that was dead pseudocode in the draft, and added one line clarifying `admissionOrder()`'s contract (never-started cards filtered from `BANK.questions`, sorted by Phase-1 priority) since AGENT-3 needs to implement that function from the spec. No other content changes from what David reviewed. Both AGENT-1 deliverables (spec file + `learning-system.xlsx`) are now complete. Per the Gate instruction I am NOT flipping AGENT-3's row myself — that's the orchestrator's call once AGENT-2's merge also lands. Setting my own state → **DONE**. No code touched at any point this session.

### AGENT-2
- _queued_
- IN PROGRESS: Step 0 done. `build_hub.py` de-scratchpadded — `BUILD = Path(__file__).resolve().parent`, `KIT = BUILD.parent` (also fixes the hardcoded absolute repo path, so it now runs from any clone location, not just David's machine). `font_faces()` cache → `build/fontcache`; template read → `build/quiz-template.html`; artifact output → `build/ccaf-practice.html`. Standalone `index.html` write unchanged (repo-root). Added `build/fontcache/` and `build/ccaf-practice.html` to `.gitignore` (cache + claude.ai-only artifact, not the deployed site). Ran `python build/build_hub.py` in a scratch venv (system Python is externally-managed, no `markdown` pkg installed) — clean run, and `index.html` output is **byte-identical** to the previously committed version (`git diff --stat index.html` empty), confirming the rebuild is deterministic. Baseline `node --check` on extracted inline JS passes. Moving to Fix 2 (review shuffle) next per ship order.
- IN PROGRESS: Fix 2 done. `startReview()` (build/quiz-template.html) — `const queue = [...seen, ...fresh].slice(0, 30)` → `const queue = shuffle([...seen, ...fresh].slice(0, 30))`. The `.slice(0,30)` cap still runs on the due-sorted `[...seen, ...fresh]` array first, so which cards are selected (most-overdue-first priority, only actually-due cards) is unchanged — `shuffle()` only randomizes presentation order of the selected set. Exam/drill untouched. Rebuilt + `node --check` clean. Moving to Fix 1 (size/zoom) next.
- IN PROGRESS: Fix 1 done. Root cause: `applyDisplay()` (the "applyFont()" of the ticket — renamed at some point) sets `--serif`/`--sans` correctly but the size control wrote `document.body.style.zoom = String(p.scale||1)` — CSS `zoom` is non-standard and doesn't work in all browsers (notably Firefox pre-126), which is exactly "does nothing, still have to zoom." Found the CSS already had unused scaffolding from the d10b9a1 "true zoom sizing" commit: `:root{--fscale:1}` + `calc(Npx * var(--fscale))` on `article.doc`, `.stem`, `.opt`, `.verdict .ex`, `.tmsg`, `details.miss summary/.body` — i.e. doc/question/tutor typography — but nothing ever called `setProperty('--fscale', ...)`. Fix: replaced the dead `body.style.zoom` line with `r.style.setProperty('--fscale', String(p.scale || 1))`. S/M/L/XL/Huge select + `ccaf-font-v1` persistence (`scale` key) untouched — same read/write path, now actually wired to something CSS uses. Verified logic in isolation (Node, stubbed `documentElement.style`/`localStorage`): selecting each size option now sets `--fscale` to the matching value (1.5, 0.9, etc.) — confirms the wiring end-to-end at the JS level; couldn't do a full rendered-browser check in this shell (no GUI browser available here), so **David should eyeball it in an actual browser before/instead of relying solely on this** — change Size dropdown, confirm doc/question text visibly grows/shrinks with no ctrl+scroll zoom. Rebuilt + `node --check` clean. Moving to Fix 3 (tutor prompt-caching) next.
- IN PROGRESS: Fix 3 done — with a finding worth flagging. Read `submitTutor()` (the Anthropic request) and `tutorSystem()` (the grounding builder). **The structural fix the ticket described was already in place**: `tutorSystem()` builds the stable prefix (tutor persona + full study-doc/question grounding) as the `system` block, sent as `system: [{ type:'text', text: tutorSystem(), cache_control: { type:'ephemeral' } }]`, with the running `TUTOR.messages` (volatile user/assistant turns) after it — exactly "stable context first with an ephemeral breakpoint, volatile question last." `anthropic-dangerous-direct-browser-access` header confirmed present. Didn't touch the model (`claude-haiku-4-5`, untouched per instruction). So the actual gap was the **verification** the ticket asked for, which was genuinely missing: nothing logged `usage`. Added, right after the response is parsed in `submitTutor()`: `console.log('[tutor cache] cache_read_input_tokens=… cache_creation_input_tokens=… input_tokens=…')`. David/orchestrator: to verify, open DevTools console during a tutoring session on the *same* doc/question — turn 1 should show `cache_creation_input_tokens>0, cache_read_input_tokens=0`, turn 2+ should flip to `cache_read_input_tokens>0`. Caveat from the ticket, corrected for the actual model in use: tutor calls **Haiku 4.5**, not Opus/Sonnet — Anthropic's minimum cacheable prefix is model-dependent (larger for Haiku-tier than Sonnet-tier per Anthropic's docs, exact figure not re-verified here); a short question-only grounding block (stem + 4 options, no full doc text) may land under that floor and silently miss the cache — harmless, just won't show `cache_read_input_tokens>0`. Doc-context tutoring (`c.kind === 'doc'`, full doc text embedded) is comfortably above any such floor. Rebuilt + `node --check` clean.

**All three fixes + Step 0 done, ship order followed (0 → Fix2 → Fix1 → Fix3).** Final state: `build/build_hub.py` and `build/quiz-template.html` de-scratchpadded and portable; review queue shuffled (due-filter preserved); size control wired to `--fscale` (zoom-property fallback removed); tutor cache verified-loggable (cache wiring itself pre-existed, correct). `.gitignore` +2 lines (`build/fontcache/`, `build/ccaf-practice.html`). Final `python build/build_hub.py` clean, final `node --check` on extracted inline JS clean, `index.html` regenerated and matches all 3 fixes (grepped each). Files touched: `build/build_hub.py`, `build/quiz-template.html`, `.gitignore`, `index.html` (generated). `build/` itself was never git-tracked before this session (that's *why* Step 0's de-scratchpad was needed) — still untracked, ready for `git add build/build_hub.py build/quiz-template.html`. Did not push (Global rule 5 — David pushes). Setting state → **NEEDS-REVIEW**.

### AGENT-3
- _blocked_

### AGENT-4
- _blocked_
