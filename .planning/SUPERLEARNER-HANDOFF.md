# Super-Learner integration — handoff for fresh sessions

**Why this file:** the session that built the study hub got very long. This is the PM brief so a *fresh* Claude Code session can pick up each build cleanly. Run the sessions **in order** — Session A gates B and C.

## The tool (what already exists)
- Repo: `C:\Users\david.rios\Dev\claude-cert-prep` · Live: https://chilcode.github.io/claude-cert-prep/ · also a claude.ai artifact.
- Single-file app: `quiz-template.html` (in the session scratchpad) → built by `build_hub.py` → `index.html`. **Edit the template + rebuild; never hand-edit index.html.** Build injects `bank.json`, the 14 study docs, `study-map.json`, and embedded dyslexia fonts via `/*__…__*/` placeholders.
- Three tabs: **Study** (14 docs, TTS read-along), **Practice** (Review = SM-2 spaced repetition, Drill, Exam sim), **Progress** (mastery scoreboard + missed review). Plus a voice tutor, per-question notes, study-guide deep-links, dyslexia-friendly fonts + zoom.
- Data lives in `localStorage` (`ccaf-stats-v1` per-card r/w/sr/note; `ccaf-font-v1`).

## Source materials (`C:\Users\david.rios\Dev\learning\CCAF\`)
- `BecomeASuperLearner_Part1.pdf`, `_Part2.pdf` — the method (David: read Part 1 & 2 only, not the whole book).
- `SuperLearnerSyllabus.pdf`, `SuperHuman Life.md` — supporting.
- `Copy of Study System Spreadsheet.xlsx` — **the 7-phase study system to build into the tool.**
- `What-How.docx`, `Personal Learning Systems.docx` — design docs; figure out where they fit.
- `Levels of Learning.md` — Ackoff's data→information→knowledge→**understanding**→**wisdom**. Load-bearing: the goal is *understanding* (answers to WHY) and *wisdom* (effectiveness), not just recall. David said it directly: *"I want to be able to talk about WHY I know the answers."*

## The 7-phase Study System (from the spreadsheet)
1. **Break it Down** — decompose the subject. (Tool seed: Progress tab's domain/scenario map.)
2. **Lock it In** — encode/commit. (Seed: spaced repetition.)
3. **Map it Out** — connect concepts. (Seed: study-guide deep-links per question.)
4. **Make it Simple** — Feynman/teach-back; explain plainly.
5. **Make it Stick** — spaced repetition with loading strategies: Beginner "Back-Loaded", Intermediate "Level-Loaded", Advanced "Front-Loaded" review schedules. (Seed: SM-2; scheduling variant not yet built.)
6. **Make it Real** — apply. (Seed: the 4 build exercises.)
7. **Make it Yours** — personalize/own. (Seed: notes.)

The tool already touches 1, 2, 3, 6, 7 partially. The gaps are: an explicit **phase framing/guided path**, **Phase 4 teach-back**, and **Phase 5 loading-strategy scheduler**. The single highest-value new feature (serves "talk about why") is **teach-back**.

---

## Session A — SPEC (read + design, no code). RUN FIRST.
> Paste into a fresh tab:

I'm building a super-learning layer into my CCAF cert study tool at `C:\Users\david.rios\Dev\claude-cert-prep` (live: https://chilcode.github.io/claude-cert-prep/). Read `.planning/SUPERLEARNER-HANDOFF.md` for full context. Use the pdf-reading skill to read **only Part 1 and Part 2** of `C:\Users\david.rios\Dev\learning\CCAF\BecomeASuperLearner_Part1.pdf` and `_Part2.pdf`, plus `Copy of Study System Spreadsheet.xlsx` (all 7 phase sheets), `What-How.docx`, `Personal Learning Systems.docx`, and `Levels of Learning.md`. Then write `.planning/SUPERLEARN-SPEC.md`: for each of the 7 phases, (a) what the method actually says to do, (b) the concrete feature in the study hub that implements it, mapping to what already exists vs. what's new, and (c) the Phase-5 loading strategies (back/level/front-loaded) as actual SM-2 scheduling parameters. Keep it implementation-ready — a build session should be able to execute from it. Don't touch code. Show me the spec before writing the file.

## Session B — BUILD the phase scaffold + loading strategies.
> After A is approved, paste into a fresh tab:

Read `.planning/SUPERLEARNER-HANDOFF.md` and `.planning/SUPERLEARN-SPEC.md` in `C:\Users\david.rios\Dev\claude-cert-prep`. Implement the 7-phase "Learning Path" framing over the existing Study/Practice/Progress tabs, and add the Phase-5 loading-strategy chooser (back/level/front-loaded) to Review's SM-2 scheduler. Edit `quiz-template.html`, rebuild with `build_hub.py`, syntax-check the inline JS with `node --check`, republish the artifact, and push to GitHub (fonts + placeholders already wired — follow the existing build/push pattern in the repo history). Ship incrementally.

## Session C — BUILD teach-back / Feynman mode (the "why" feature).
> Independent of B; paste into a fresh tab:

Read `.planning/SUPERLEARNER-HANDOFF.md` in `C:\Users\david.rios\Dev\claude-cert-prep`. Add a "Teach-back" mode to the study hub: on a question, instead of picking, I explain OUT LOUD why the answer is what it is (reuse the existing voice-input + Anthropic-tutor plumbing — see the tutor code in `quiz-template.html`), and the tutor grades my explanation against the official explanation and the answer-physics principle, then tells me what I missed. This implements Phase 4 "Make it Simple" and Ackoff's "understanding" level. Edit the template, rebuild, syntax-check, republish, push.

---

**Guardrails for all build sessions:** template + rebuild only; `node --check` the inline JS before shipping; keep the dyslexia-font default and localStorage keys intact; push via `gh.exe auth token` inline-URL (WSL credential manager fails from the agent shell).
