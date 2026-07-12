# SUPERLEARN-SPEC — Super-Learner integration for the CCAF study hub

**Status: APPROVED by David 2026-07-12.** AGENT-3 executes from this document.

Sources read: `BecomeASuperLearner_Part1.pdf` / `_Part2.pdf` (Ch2, 16-17, 27, 33, 34 — no text layer, read via rendered page images), `Copy of Study System Spreadsheet.xlsx` (all 7 phase sheets, formulas decoded), `Levels of Learning.md` (Ackoff), `SuperHuman Life.md`, `Personal Learning Systems.docx`, `What-How.docx`. See also the rebuilt reference spreadsheet at `learning-system.xlsx` (repo root) — its Phase 5 tab is the working reference model for §5 below.

---

## 0. Design philosophy (why this shapes the phases the way it does)

Ackoff's ladder (`Levels of Learning.md`): **data → information → knowledge → understanding → wisdom.** Knowledge answers "how"; understanding answers "why"; wisdom is knowing whether the goal was worth pursuing at all. David's own framing: *"I want to be able to talk about WHY I know the answers."* That's the **understanding** rung — it's the design target for Phase 4 (teach-back) specifically, and it's why teach-back outranks every other net-new feature in value.

`What-How.docx` / `Personal Learning Systems.docx` add one more frame worth keeping in view: **effectiveness (doing the right thing) beats efficiency (doing the thing right)**, and every learning cycle should open with "what" before "how." That's the spine for Phase 1 (what to study, in priority order) and Phase 7 (was this the right thing to have studied).

The existing app already does quite a lot of Phase 1/3/6/7 work implicitly through its domain/scenario data model — the phases mostly need **surfacing and framing**, not new engines. Phase 5 is the one phase that needs a real engine change. Phase 4 is entirely AGENT-4's build.

---

## 1. Phase 1 — Break it Down

**What the method prescribes:**
Decompose the subject into a hierarchy — the spreadsheet's literal columns are Groups → Sections → Subsections → Pages → Details. Before deep-reading any unit, **pre-read** it: skim at 5-8× your normal reading speed, looking only for titles, sub-headings, proper nouns, and numbers — nothing else — to build a rough "mental map" of structure (Ch16). This is explicitly the 80/20 rule: ~20% of the details (titles/structure) buy ~80% of the orientation you need before a real read. Ch34 ("Dense Materials / Textbooks") says pre-reading matters **more**, not less, as material gets denser — exactly the CCAF playbooks' situation — and recommends manufacturing "intense interest" (imagine a real scenario where you'd need this) before the real read, plus using any existing diagrams as temporary markers.

The spreadsheet also computes a **Priority Score** per section (`Importance / Challenge × mastery factor`) so you study the highest-value, hardest, least-mastered material first — "(Higher score = Higher Priority)."

**Feature mapping — existing vs. new:**
- **Existing:** the app's data model already *is* this hierarchy — `BANK.questions` grouped by `domain` (5 domains, weighted %) and `scenario` (6 scenarios), each linked to a playbook doc (`DOMAIN_DOC`) and specific principle anchors (`STUDYMAP`). Progress tab's domain/scenario mastery bars, sorted weakest-first, are already a working diagnostic view of where you're behind.
- **New:** a "Phase 1: Break it Down" view that relabels/re-surfaces that existing aggregation explicitly as the decomposition step — domain/scenario tree, weight %, current mastery, sorted by priority — plus a "Pre-read" CTA per domain that opens its playbook doc in the existing Study tab (reader + TTS already built). **No new data plumbing** — this is a rendering/framing pass over `agg()`/`accOf()`, which already exist in `showProgress()`.
- **The spreadsheet's priority formula is correct as written — do not invert it.** `Priority = Importance / Challenge × (1 + %Mastered)`. This *intentionally* rewards higher mastery: it's part of the spaced-repetition framework, not a diagnostic ranking. Already-mastered material still needs quick, high-priority review passes to lock in long-term retention (interleaving reinforcement of what you know alongside acquisition of what you don't) — that's a different job from the Progress tab's weakest-first view, which answers "where am I behind" rather than "what belongs in today's session." `learning-system.xlsx`'s Phase 1 tab uses this exact formula, unmodified from the original sheet. If AGENT-3 builds a "Phase 1" priority view in the app, port the formula as-is: `Importance/Challenge × (1 + %Mastered)`, not an inverted version.

---

## 2. Phase 2 — Lock it In

**What the method prescribes:**
Not a technique — a commitment ritual. State a goal (what / minutes-per-day / days-per-week / weeks), name the reward, name the obstacles, then pick ≥2 "locking mechanisms" from a menu (Focusmate, accountability partner, habit tracker, public commitment, self-betting, anti-incentives, fail-safes, etc.) and generate a shareable commitment message. `SuperHuman Life.md` shows this isn't theoretical for David — it's literally the structure of his own "Tetraud" accountability-pod program (small groups, rotating roles, weekly commitment check-ins).

**Feature mapping — existing vs. new:**
- **Existing:** none. The app has no goal-setting surface today.
- **New (lowest engineering risk — pure UI + localStorage, no engine work):** a one-time "Phase 2: Lock it In" card (first Practice visit, or from a Learning Path nav) capturing goal / cadence / reward / obstacle into a new `ccaf-goal-v1` key, a checklist of the spreadsheet's locking mechanisms, and the same commitment-message template pre-filled from the answers, with a copy-to-clipboard button. No send integration — David copy/pastes it himself (matches how this repo already treats "David does the actual send" elsewhere).
- **Priority: build last.** Nothing else depends on it, and it's the smallest, least risky piece of scope if AGENT-3 runs short on room.

---

## 3. Phase 3 — Map it Out

**What the method prescribes:**
Ch27: mind mapping is "drawing out a neural network of new ideas, concepts, and details" — a non-linear visual structure, better than an outline because it can show connections *across* branches, not just within one. Same underlying hierarchy as Phase 1, re-rendered as a connected map instead of a list.

**Feature mapping — existing vs. new:**
- **Existing:** the app already encodes a many-to-many concept graph — every question links to its domain playbook, its scenario doc, and specific principle anchors (`studyLinksHTML()`, `STUDYMAP[q.id].principles`). That *is* the mind-map's edge set; it's just not drawn as one.
- **New (v1, recommended scope):** a "Phase 3: Map it Out" view — a collapsible tree grouped by domain → scenario → principle, styled to read as a map (not a flat list), reusing existing `STUDYMAP`/`DOMAIN_DOC`/`SCEN_DOC` JSON with zero new data work. Clicking a node reuses the existing `wireStudyLinks()` navigation.
- **New (stretch goal, skip unless there's room):** an actual visual radial/force node-graph (SVG, no new library needed — the dataset is small enough for a static radial layout). Not worth the complexity budget in Wave 2 unless the tree view ships early and there's time left.
- **Priority: second after Phase 5.** This is the second-most "real" build in the set.

---

## 4. Phase 4 — Make it Simple

**What the method prescribes:**
The Feynman Technique, explicitly named in `SuperHuman Life.md` ("deepen your understanding of your topic using the FEYNMAN TECHNIQUE"). The spreadsheet's own tab operationalizes it: state the topic, ask 3 big questions about it, list up to 7 key points, supply analogies/metaphors/examples, then explain it as if teaching a student — explain in plain language, find the gap, go back to the source, simplify again.

**Feature mapping — existing vs. new:**
- **This phase is entirely AGENT-4's assignment (Teach-back mode)** — not built here, not built by AGENT-3. Included for completeness of the 7-phase framing only.
- **Existing plumbing AGENT-4 should reuse:** the tutor's Anthropic-backed conversation loop (`openTutor`/`submitTutor`), the tutor thread UI (`renderTutorThread`), and TTS (`speak()`), plus each question's official explanation + matched `STUDYMAP` principle as the grading reference.
- **Grading contract to hand AGENT-4** (spelled out here so AGENT-3's phase scaffold has something concrete to link to): tutor system prompt receives (a) the official explanation, (b) the matched principle title/id, (c) the user's spoken/typed explanation; returns a structured verdict — what was covered, what was missed, any misconception to correct — rendered as a compact card and read aloud via existing `speak()`.
- AGENT-3's only job re: Phase 4 is labeling the step in the Learning Path scaffold and linking it to wherever AGENT-4 mounts the teach-back entry point (likely the existing "🎤 Ask" button surface on answered questions).

---

## 5. Phase 5 — Make it Stick (the engine change)

### 5.1 What the method actually prescribes

Ch33 ("Long Term Storage: Maintaining Memories"): forgetting is exponential (Ebbinghaus), spaced repetition is "one of the most powerful secrets in the SuperLearner's toolkit," and the book explicitly recommends **Anki** — i.e., an SM-2-family scheduler is the intended tool, which the app already has. Its four practical rules: (1) material you already know well needs no spaced repetition, (2) multi-modal encoding (image + word + sound) needs fewer repetitions, (3) unstructured/unfamiliar material needs ~7 or more, with diminishing return per rep, (4) use real spaced-repetition software, not manual tracking.

The spreadsheet's Phase 5 tab is where "back-loaded / level-loaded / front-loaded" lives, and I decoded its formulas directly rather than going by the tab labels alone. Here's what they actually compute:

- The sheet defines an **X-multiple curve** across 8 "intervals" (calendar checkpoints), one curve per experience level:
  - **Beginner / Back-loaded:** `[1.0, 1.25, 1.6, 2.0, 3.0, 3.0, 2.5, 2.0]`
  - **Intermediate / Level-loaded:** flat `2.04375` × 8 (the mean of the other two curves — steady pace)
  - **Advanced / Front-loaded:** `[2.0, 2.5, 3.0, 3.0, 2.0, 1.6, 1.25, 1.0]` (exact mirror of Beginner)
  - All three sum to the same total (`X Factor` = 16.35), so the same total amount of material gets scheduled either way — only the *shape* of introduction changes.
- **Critical finding:** the calendar-date formulas for all three curves are algebraically identical (`EndDate − unit×(10−i)` for Back-loaded reduces to exactly `StartDate + unit×i`, same as the other two). **The loading strategies do NOT change *when* you study or how per-card intervals grow.** They change **how many brand-new items get introduced at each checkpoint.** Back-loaded ramps new-item introduction up through the middle of the study window; Front-loaded front-loads it and tapers; Level-loaded is a flat, constant rate.
- The sheet reserves the **last 2 of 10 equal time-slices as pure review/buffer** (no new items introduced) — confirmed by its own "Total Card Creation Days / Total Review Days / Buffer Days" columns. So the study window splits ~80% new-item introduction (the 8 checkpoints above) / ~20% pure review before the target date.

This means the honest "SM-2 scheduling parameter" here is a **new-card daily intake cap**, not a per-card interval multiplier. (I tried modeling it as a per-card compounding interval multiplier first — chaining the X-values geometrically the way SM-2 chains EF — and it blows up to ~180 days by the 8th repetition for a single card, which is obviously not what a 12-17 day study window intends. The spreadsheet's own numbers rule that reading out.)

The rebuilt `learning-system.xlsx` → **Phase 5 - Make it Stick** tab implements this exact model as a live, formula-driven reference: an Experience-level dropdown drives a `CHOOSE`/`MATCH`-selected active curve, which feeds an 8-checkpoint new-card intake schedule. Verified: all three curves total exactly 166 cards (the current bank size) by checkpoint 8, matching `BANK.questions.length`.

### 5.2 Concrete implementation for AGENT-3

**Preserve completely, untouched:** `srDefault()`, `gradeCard()`, the existing `ef`/`iv`/`reps`/`due`/`lapses` math (`quiz-template.html:348-366`). This feature does not touch per-card grading at all — it only gates which **never-seen** cards are allowed to enter the queue on a given day. Cards that have already been started continue on their normal SM-2 schedule, completely unaffected.

**New localStorage key:** `ccaf-loading-v1` = `{ level: 'beginner' | 'intermediate' | 'advanced', examDate: '<ISO date>' | null, studyStart: '<ISO date>' | null }`. `studyStart` is set automatically the first time the user saves a plan (today's date). Default `level`: `'intermediate'`.

**Curves (paste directly):**
```js
const LOADING_CURVES = {
  beginner:     [1.0, 1.25, 1.6, 2.0, 3.0, 3.0, 2.5, 2.0],
  intermediate: [2.04375, 2.04375, 2.04375, 2.04375, 2.04375, 2.04375, 2.04375, 2.04375],
  advanced:     [2.0, 2.5, 3.0, 3.0, 2.0, 1.6, 1.25, 1.0],
};
const X_FACTOR = 16.35; // sum of any curve above — normalizing constant
```

**New-card cap for "today," given `prefs = loadingPrefs()`:**
```js
function newCardCapToday(prefs, totalNew) {
  if (!prefs.examDate || !prefs.studyStart) return Infinity; // no plan set = today's unconstrained behavior
  const curve = LOADING_CURVES[prefs.level];
  const totalDays = Math.max(1, (Date.parse(prefs.examDate) - Date.parse(prefs.studyStart)) / DAY);
  const sliceLen = totalDays / 10;                 // 10 equal slices; last 2 are pure review (no new cards)
  const daysIn = (Date.now() - Date.parse(prefs.studyStart)) / DAY;
  const checkpoint = Math.min(8, Math.max(1, Math.ceil(daysIn / sliceLen)));
  let cumulative = 0;
  for (let i = 0; i < checkpoint; i++) cumulative += curve[i];
  const cap = Math.round(totalNew * cumulative / X_FACTOR);
  return checkpoint === 8 ? totalNew : cap;          // guarantee full bank scheduled by checkpoint 8
}
```

**Gate `isDue()` for new (never-started) cards only** — existing logic (`quiz-template.html:374`) currently treats *every* unstarted card as always-due. Change it to:
```js
function isDue(qid) {
  const c = cardOf(qid);
  if (c && c.sr) return (c.sr.due || 0) <= Date.now();   // started cards: unchanged, normal SM-2
  const prefs = loadingPrefs();
  const cap = newCardCapToday(prefs, BANK.questions.length);
  const admitted = admissionOrder().slice(0, cap);        // top `cap` never-started cards, priority-ordered — see below
  return admitted.includes(qid);
}
```
**Admission order for new cards:** don't use raw bank order — order by domain Importance/Challenge (the same ratio Phase 1's priority formula uses), highest first. Note the `%Mastered` term from Phase 1's formula doesn't apply here: every candidate is by definition never-started (0% mastered), so it contributes nothing to this particular ranking — this is a different, narrower use of the same underlying signal, not a reintroduction of a mastery-based sort. `admissionOrder()` should return `BANK.questions` filtered to never-started cards, sorted by domain Importance/Challenge descending.

**UI:** a small "Study Plan" control (Review intro screen or Progress tab) — Experience-level choice with plain-language labels ("Back-loaded — ease in, ramp through the middle" / "Level-loaded — steady pace" / "Front-loaded — hit it hard early, coast into review"), and an exam-date picker. If no plan is set, behavior is exactly what it is today (unconstrained) — the feature is opt-in, not a forced change.

---

## 6. Phase 6 — Make it Real

**What the method prescribes:** the spreadsheet's Phase 6 tab is just a 5-10 point "application strategy" — once foundational knowledge is built, write concrete steps for applying it for real.

**Feature mapping — existing vs. new:**
- **Existing:** the repo already has this — `exercises/exercise-1-2-agent-and-claude-code.md` and `exercises/exercise-3-4-extraction-and-research.md` are the "build exercises" the HANDOFF doc references as the Phase 6 seed. They currently have **no UI entry point at all** — confirmed, nothing in `quiz-template.html` references the `exercises/` directory.
- **New (small lift):** add both files to the Study tab's doc list (`DOCS.items`) tagged as "Exercises," so they render through the existing doc-reader/TTS pipeline for free, surfaced as the "Phase 6: Make it Real" step.

---

## 7. Phase 7 — Make it Yours

**What the method prescribes:** the spreadsheet's Phase 7 tab is a ~20-question reflection (did you hit the goal, what would you change, what habit mattered, who would benefit from what you now know, teach someone else, etc.) — final personalization/ownership pass.

**Feature mapping — existing vs. new:**
- **Existing:** per-question notes (`getNote`/`setNote`, the `note` field already in `ccaf-stats-v1`) are already a "make it yours" seed — free-text personalization on any question.
- **New (small lift, low risk):** a short end-of-study reflection form — the spreadsheet's ~10 strongest questions, not all 20 boilerplate blanks — surfaced once the user's best exam-sim score crosses `PASS_PCT`, or accessible any time from Progress. Store as free text in a new `ccaf-reflection-v1` key. Pure journaling, no tutor/grading involvement.
- **Priority: build last, alongside Phase 2.**

---

## 8. Build-order recommendation for AGENT-3

1. **Phase 5** (the real engine work — this is the phase DISPATCH explicitly calls out)
2. **Phase 3** tree view (second-most substantial, reuses existing data)
3. **Phase 1** framing pass (cheap — relabels existing Progress aggregation)
4. **Phase 6** exercises doc-list entry (trivial)
5. **Phase 2** and **Phase 7** (pure UI + localStorage, no dependencies, do last if room is tight)
6. **Phase 4** — not AGENT-3's; hand off the grading contract above to AGENT-4

**Suggested IA:** a single new "Learning Path" view presenting the 7 phases as a stepper/checklist, each card linking into the *existing* Study/Practice/Progress tabs rather than replacing them — this is the smallest-blast-radius reading of "the 7-phase framing **over** the existing tabs," and it means nothing about the current Study/Practice/Progress structure needs to change.
