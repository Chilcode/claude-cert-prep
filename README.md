# Claude Certified Architect – Foundations — Study Kit

Built 2026-07-11 from the official exam guide (v0.2, 2026-06-30). Everything in this kit is grounded in that guide — no invented features, no out-of-scope material.

## The exam in one paragraph

60 multiple-choice questions, 120 minutes (2 min/question), pass at 720/1000. You get **4 scenarios drawn from a bank of 6 that are published in the guide** — so you can prep every scenario in advance. Domain weights: Agentic Architecture 27%, Claude Code Config 20%, Prompt Engineering & Structured Output 20%, Tool Design & MCP 18%, Context & Reliability 15%. One correct answer + three distractors that are "plausible to a candidate with incomplete knowledge" — meaning every wrong answer is a named anti-pattern or a real technique aimed at the wrong problem.

## Study order

1. **`playbook/00-answer-physics.md`** ← START HERE. The exam's answer-selection doctrine reverse-engineered from the 12 official sample questions. Seven principles for how correct answers behave + the distractor taxonomy. This is the highest-yield 30 minutes in the kit.
2. **`scenarios/01–06`** — one per exam scenario: how you'd actually build the thing from scratch (architecture, build order, code), then the decision points the exam tests, then a failure-modes drill. Read the two Agent SDK-heavy ones first (01 customer support, 03 multi-agent research) — that's where your gap is and it's 27% of the exam.
3. **`playbook/domain-1..5`** — every task statement decoded into decision rules + a "memorize cold" list (exact flags, paths, config keys, enum values). Use these as reference + final-week flashcards.
4. **`exercises/`** — the guide's 4 official prep exercises turned into evening-sized builds with paste-ready code and "break it on purpose" experiments. Do Exercise 1 (agentic loop + hooks) before anything else: it makes stop_reason, tool_use, and programmatic enforcement physical instead of theoretical.
5. **`questions/bank.json`** — ~60 adversarially-verified practice questions in exam style (interactive quiz app link below). Drill AFTER reading the playbook; use wrong answers to route you back to the relevant domain file.

## The study hub (read it OR listen to it)

**Live site: https://chilcode.github.io/claude-cert-prep/** (also on claude.ai: https://claude.ai/code/artifact/0e5ebe8b-91b4-4d67-a551-dfaa1f70ded8)

Everything in one navigable app — works on your phone:

- **Study tab** — all 14 docs rendered in the browser with **read-aloud**: open a doc, hit "Listen to this doc" and it reads while highlighting and scrolling each paragraph so you can follow along. Double-click any paragraph to start listening from there. `R` restarts.
- **Practice tab** — **Drill** (filter by scenario/domain, instant feedback with the decision rule behind every answer, "missed only" replay) and **Exam simulation** (4 random scenarios × 10 questions, 80-minute clock, answer-to-advance like the real platform, per-domain scorecard). Every question, its options, and its explanation can be read aloud — turn on "Read questions aloud automatically" in Audio settings, or press `R` on any question. Answer positions shuffle every run; stats persist in the browser.
- **Ask the tutor (voice)** — every study doc and every answered question has a **🎤 Ask** button. Tap it, ask your question out loud like you would in class, and a Claude tutor answers in your chosen voice, grounded in that exact doc or question. Follow-ups keep the thread; "Resume reading" picks the doc back up where you paused. Add your **Anthropic API key** under Audio → Tutor (stored only in your browser, sent only to Anthropic; runs on Claude Haiku, ~a cent per question). Voice input needs Chrome or Edge; other browsers fall back to a text box. GitHub Pages site only — the claude.ai copy can't reach the API.
- **Review (spaced repetition)** — the daily driver, on the Practice tab. Anki-style SM-2 scheduling: answer, then grade **Again / Hard / Good / Easy** (keys 1–4) and each card comes back on a schedule set by how well you knew it. "Again" cards re-appear the same session. A due-count shows how many are waiting.
- **Notes** — every question has a note field (in Review, Drill, and the missed list). Jot a memory hook or why you missed it; it sticks to the card.
- **Progress tab** — a scoreboard: due/mastered/learning/not-started tiles, lifetime accuracy, best exam sim; **mastery bars per domain and per scenario** (weakest first); a "study next" panel; and a full **missed-questions** review.
- **Study-guide deep-links** — every question (in results, misses, and the scoreboard) links to its **domain playbook**, its **scenario walkthrough**, and the exact **principle in "Start Here"** it drills — clicking scrolls to and highlights that heading. The question→principle map (`questions/study-map.json`) tags all 60.
- **Reading — dyslexia-friendly by default** — the whole app defaults to a dyslexia-friendly font with roomier letter/line spacing (Reading settings on the Practice tab). Pick from **OpenDyslexic** and **Atkinson Hyperlegible** (both embedded, no network), Verdana, Tahoma, Comic Sans, or the original serif — plus a **S/M/L/XL** size control. Applies everywhere: docs, questions, notes, tutor.
- **Voices**: two engines, switchable under Audio on the Practice tab.
  - **System voices** (free, unlimited) — best quality in **Microsoft Edge** (desktop or Android): pick a voice with "Natural" in the name.
  - **ElevenLabs** (your account) — paste your API key (stored only in your browser, never in this repo), hit "Load my voices," and the whole hub reads in your ElevenLabs voices. Audio is cached locally so re-listens are free; first listens cost credits (~500–700/question on Flash, 10–25K per full doc — use system voices for long docs). Works on the GitHub Pages site only; the claude.ai artifact copy blocks external APIs. Tip: create a TTS-restricted key in the ElevenLabs dashboard.

**Real-exam tip:** the exam is online-proctored — before booking, ask the test provider about accessibility accommodations (screen reader support and/or extended time). Reading accommodations on a 60-question / 120-minute reading-heavy exam are exactly what those policies exist for.

## Weight-adjusted priorities

- **Agent SDK mechanics are the fattest target (D1, 27%)**: agentic loop terminates on `stop_reason == "end_turn"`, continues on `"tool_use"` — never text parsing, never iteration caps. Subagents inherit NOTHING; context is passed explicitly in prompts. Coordinator needs `Task` in `allowedTools`. Parallel subagents = multiple Task calls in ONE response.
- **The money rule**: anything financial/compliance → hooks and programmatic gates, never prompt instructions ("non-zero failure rate" is the guide's own phrase).
- **The scoping rule**: team-shared → project scope (`.claude/commands/`, `.mcp.json`, project CLAUDE.md); personal → user scope (`~/.claude/...`). This one rule answers several questions per exam.
- **The API-matching rule**: anyone waiting on the result → synchronous API; nobody waiting → Batches API (50% cheaper, ≤24h, no SLA, no multi-turn tool calling).

## Sources

- Exam guide PDF: `C:\Users\david.rios\Downloads\Claude+Certified+Architect+-+Foundations+-+Exam+Guide.pdf`
- Out of scope (don't waste time): fine-tuning, auth/billing, streaming, vision, computer use, prompt-caching internals, pricing math, cloud-provider config.
