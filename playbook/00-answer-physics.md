# 00 — Answer Physics

**What this is:** The exam's answer-selection doctrine, reverse-engineered from the 12 official sample questions and their explanations. Every claim below points at a specific sample question (Q1–Q12) or a task statement in the guide. If you internalize this one file, you can pick correct answers even on questions where you're fuzzy on the underlying tech — because the exam rewards *judgment patterns*, and there are only about seven of them.

**Exam mechanics you exploit:** 60 questions, 120 min (2 min each), 1 correct + 3 distractors, 720/1000 to pass. Distractors are "plausible to a candidate with incomplete knowledge." Translation: every wrong answer is a *named anti-pattern* or a *real technique applied to the wrong problem*. The guide literally lists the anti-patterns in its task statements. You're not being tested on trivia — you're being tested on whether you reach for the crane when a screwdriver fixes it, and whether you reach for a screwdriver when the requirement is load-bearing.

---

## 1. How correct answers behave

Seven principles. Every one of the 12 sample answers is an instance of at least one.

### P1. Fix the root cause the evidence points at — not a symptom, not a neighbor

The stem always tells you what's actually broken. The correct answer touches *that thing*.

- **Q2** — Agent picks `get_customer` when it should pick `lookup_order`. Stem says both tools have *minimal descriptions* ("Retrieves customer information" / "Retrieves order details"). Root cause is stated in the stem. Winner: **expand the tool descriptions** (input formats, example queries, edge cases, boundaries). The guide is explicit: "Tool descriptions are the primary mechanism LLMs use for tool selection."
- **Q3** — 55% first-contact resolution; agent escalates easy cases and grinds on hard ones. Root cause: *unclear decision boundaries*. Winner: **explicit escalation criteria + few-shot examples in the system prompt**. Not confidence scores, not sentiment, not a classifier.
- **Q12** — 14-file review is inconsistent, misses bugs, contradicts itself. Root cause: *attention dilution*, not context size. Winner: **restructure into per-file passes + one cross-file integration pass**.

**Test:** Re-read the stem. What specific defect is described or shown in the logs? The correct answer modifies exactly that component. Any answer that modifies a *different* component is wrong even if it's a real best practice.

### P2. "Most effective FIRST step" = lowest effort, highest leverage, at the root cause

When the stem says *first step* or *most effective way to improve*, the exam wants the cheapest intervention that addresses the root cause — almost always words (descriptions, criteria, examples) before infrastructure (classifiers, routers, layers).

- **Q2** — Rewriting descriptions beats few-shot examples ("token overhead without fixing the underlying issue"), beats a routing layer ("over-engineered"), beats consolidating tools ("requires more effort than a 'first step' warrants"). Note: consolidation is called *a valid architectural choice* — it loses only because the question asked for a first step. Read the ask.
- **Q3** — Prompt criteria beat a trained classifier because "prompt optimization hasn't been tried" yet. The exam's escalation ladder: **fix the prompt → fix the tool descriptions → restructure the workflow → add infrastructure**. You may only skip rungs when determinism is required (see P3).

### P3. When money, compliance, or ordering is at stake → deterministic enforcement, never prompts

Prompt instructions have "a non-zero failure rate" (Task 1.4, verbatim). If the failure has financial or compliance consequences, the correct answer is *code*, not *words*.

- **Q1** — Agent skips `get_customer` in 12% of cases → misidentified accounts → **incorrect refunds**. Winner: **programmatic prerequisite that blocks `lookup_order`/`process_refund` until `get_customer` returns a verified customer ID**. The explanation kills the prompt options by name: "probabilistic LLM compliance … is insufficient when errors have financial consequences."
- Task 1.5 backs this up with the canonical hook example: intercept tool calls to **block refunds over $500** and redirect to human escalation. Hooks = deterministic guarantees; prompts = probabilistic compliance.

**How P2 and P3 coexist:** P2 (cheap prompt fix) applies to *quality* problems — accuracy, consistency, tool selection, escalation calibration. P3 (hooks/gates) applies to *guarantee* problems — must-happen ordering, policy thresholds, financial operations. The stem tells you which world you're in: look for words like *incorrect refunds, compliance, mandatory, must, policy* vs *inconsistent, suboptimal, below target, unreliable*.

### P4. Match the API to latency and blocking requirements

- **Q11** — Two workflows: blocking pre-merge check + overnight tech-debt report. Winner: **Batches API for the overnight report only; synchronous for pre-merge**. Physics: Batches = 50% cheaper, up to 24-hour window, **no latency SLA**, no multi-turn tool calling. Anyone waiting on the result = synchronous. Nobody waiting = batch. "Often completes faster" is explicitly *not* acceptable for blocking workflows, and a timeout-fallback hybrid is "unnecessary complexity."
- **Q10** — CI pipeline hangs because Claude Code waits for interactive input. Winner: **`claude -p "..."`** (`--print`, the documented non-interactive mode). Pair with `--output-format json --json-schema` when CI needs machine-parseable findings.

### P5. Least privilege and separation of concerns — scope everything to its role

- **Q9** — Synthesis agent needs verification; 85% are simple fact-checks, 15% deep. Winner: **give synthesis a single scoped `verify_fact` tool for the 85%, keep routing the 15% through the coordinator**. Giving it *all* web search tools "over-provisions the synthesis agent, violating separation of concerns." The explanation names the principle: least privilege.
- **Q4** — Team command → **`.claude/commands/` in the repo** (version-controlled, arrives on clone). Personal → `~/.claude/commands/`. Same scoping logic everywhere: `.mcp.json` (project, shared, `${ENV_VAR}` for secrets) vs `~/.claude.json` (personal/experimental); project CLAUDE.md (team) vs `~/.claude/CLAUDE.md` (you only — a classic bug is "new teammate isn't getting the instructions" because they live in someone's user-level file).
- Task 2.3: an agent with 18 tools selects worse than one with 4–5. Restricting tool sets *is* the fix, not a limitation to work around.

### P6. Explicit criteria and concrete examples beat vague instructions — every time

The model can't read your mind; it can read your examples.

- **Q3** — Explicit escalation criteria **with few-shot examples** demonstrating escalate-vs-resolve.
- **Q6** — Explicit glob matching (`.claude/rules/` frontmatter `paths: ["**/*.test.tsx"]`) beats "relying on Claude to infer which section applies" from a monolithic CLAUDE.md. Deterministic loading beats inference.
- Task 4.1: "be conservative" and "only report high-confidence findings" **fail**; "flag comments only when claimed behavior contradicts actual code behavior" works. Specific categorical criteria (report bugs/security; skip style) beat confidence-based filtering. Severity levels need concrete code examples per level.
- Task 3.5: when prose descriptions are interpreted inconsistently, 2–3 concrete input/output examples are "the most effective way to communicate expected transformations."

### P7. Blame the agent whose OUTPUT the logs show is wrong

In multi-agent debugging questions, the stem hands you log evidence. Find the agent whose *output* is defective; everyone downstream of it "executed correctly within their assigned scope."

- **Q7** — Report on "AI in creative industries" covers only visual arts. Coordinator's logs show it decomposed the topic into digital art / graphic design / photography. That decomposition IS the defect. Winner: **coordinator's task decomposition is too narrow**. The three distractors all blame downstream agents (synthesis, search, analysis) that did exactly what they were assigned.
- **Q8** is the flip side — when a subagent *fails* (timeout), the right move is to pass **structured error context up**: failure type, attempted query, partial results, alternative approaches. So the coordinator can decide: retry modified, try alternative, or proceed with partials + annotate coverage gaps.

---

## 2. Distractor taxonomy

The same seven wrong answers keep getting re-skinned. Name the archetype and it dies.

### D1. Over-engineered infrastructure
A heavyweight system where a prompt/description/config fix works. Instant kill on any "first step" question.
- Q2-C: routing layer that parses input and pre-selects tools ("over-engineered and bypasses the LLM's natural language understanding")
- Q3-C: separate classifier model trained on historical tickets ("requiring labeled data and ML infrastructure when prompt optimization hasn't been tried")
- Q1-D: routing classifier per request type ("addresses tool availability rather than tool ordering")
- Q12-C: bigger context window ("larger context windows don't solve attention quality issues")
- Q11-D: batch + timeout-fallback hybrid ("unnecessary complexity")

### D2. Prompt-hope where a guarantee is required
Prompt/few-shot enforcement of something that MUST happen. Only wrong when stakes are money/compliance/ordering — this is the mirror image of D1.
- Q1-B: "enhance the system prompt to state verification is mandatory"
- Q1-C: few-shot examples of calling get_customer first
Both die to: "probabilistic LLM compliance … insufficient when errors have financial consequences."

### D3. Solves a different problem
Real technique, wrong disease. Verify the answer touches the defect named in the stem.
- Q3-D: sentiment-based escalation ("sentiment doesn't correlate with case complexity, which is the actual issue")
- Q1-D: tool availability filter for a tool *ordering* problem
- Q7-A/C/D: fixing synthesis/search/analysis agents when the coordinator's decomposition was the defect
- Q4-C: putting a command in CLAUDE.md (instructions/context, not command definitions)

### D4. Nonexistent features
Made-up flags, env vars, and config mechanisms. If you've never seen it in docs, it doesn't exist.
- Q10-B: `CLAUDE_HEADLESS=true` — doesn't exist
- Q10-D: `claude --batch` — doesn't exist
- Q4-D: `.claude/config.json` with a commands array — "a configuration mechanism that doesn't exist in Claude Code"
- Also in this family: generic Unix workarounds (Q10-C: `< /dev/null`) that dodge the documented mechanism (`-p`).

### D5. Named anti-patterns (the guide lists these explicitly)
The task statements literally enumerate anti-patterns; distractors are built from the list:
- **Self-reported confidence scores** as routing signal — Q3-B ("LLM self-reported confidence is poorly calibrated — the agent is already incorrectly confident on hard cases")
- **Sentiment-based escalation** — Q3-D
- **Consensus voting / majority-of-N runs** — Q12-D ("would actually suppress detection of real bugs" that are only caught intermittently)
- **Silent error suppression** (return empty result marked success) — Q8-C ("prevents any recovery and risks incomplete research outputs")
- **Generic error status** ("search unavailable" after exhausting retries) — Q8-B ("hides valuable context from the coordinator")
- **Kill the whole workflow on one failure** — Q8-D
- **Iteration caps / parsing natural-language signals / checking assistant text** as loop termination (Task 1.1) — the loop runs on `stop_reason`: continue on `"tool_use"`, stop on `"end_turn"`
- **Heuristic selection among multiple customer matches** instead of asking for another identifier (Task 5.2)

### D6. Burden-shifting
Makes humans absorb the system's failure instead of fixing the system.
- Q12-B: "require developers to split large PRs into 3–4 file submissions" ("shifts burden to developers without improving the system")
- Same smell: "have the customer call back," "require reviewers to double-check everything."

### D7. Right answer, wrong scope
Correct mechanism, wrong location/blast radius.
- Q4-B: `~/.claude/commands/` for a command that must reach "every developer who clones" — personal scope can't travel through version control
- Q6-D: per-directory CLAUDE.md for test files spread across the whole tree ("directory-bound")
- Q6-C: skills for always-on conventions ("requires manual invocation … contradicting the need for deterministic 'automatic' application")
- Q9-C: ALL search tools when one scoped tool covers 85% (over-provisioning)
- Q9-B: batching verifications when synthesis steps depend on earlier verified facts (blocking dependency)
- Q9-D: speculative caching ("cannot reliably predict what the synthesis agent will need")
- Q5-B/C/D: direct execution for architecture-scale work — B risks "costly rework," C "assumes you already know the right structure," D "ignores that the complexity is already stated in the requirements."

---

## 3. The 20-second elimination checklist

Run in order on every question. Most questions die by step 4.

1. **Find the defect sentence.** What does the stem/logs say is actually broken? Underline it mentally. (Q7: the coordinator's three subtasks. Q2: "minimal descriptions." Q12: "inconsistent … contradictory.")
2. **Classify stakes: guarantee or quality?** Words like *must, mandatory, financial, refund, compliance, policy, before any* → deterministic answer (hook, prerequisite gate, forced tool_choice, glob rule). Words like *inconsistent, below target, unreliable, suboptimal* → prompt/description/criteria/examples answer.
3. **Check the ask's size.** "First step" / "most effective way" → cheapest root-cause fix. "How should you restructure/design" → architectural answer is allowed.
4. **Kill nonexistent features.** Any flag/env/config you've never seen in the docs is fabricated. (`--batch`, `CLAUDE_HEADLESS`, config.json commands array.)
5. **Kill named anti-patterns on sight.** Self-reported confidence, sentiment escalation, consensus voting, silent suppression, generic errors, workflow termination, iteration caps, burden-shifting, heuristic identity guessing.
6. **Kill answers that fix a component the logs cleared.** If an agent's output matched its assignment, it's innocent.
7. **Check scope fit.** Who needs this? Whole team via git → project scope (`.claude/commands/`, `.mcp.json`, project CLAUDE.md, `.claude/rules/`). Just you / experimental → user scope (`~/.claude/...`). Spread-across-tree files → glob rules, not directory files.
8. **Latency check (API questions).** Someone blocked waiting → synchronous. Overnight/weekly/report → Batches. Never batch a blocking path.
9. **Two survivors?** Pick the one that (a) is closer to the underlined defect and (b) preserves existing structure (adds a scoped tool, keeps coordinator routing for the hard cases) over the one that rebuilds the system.

---

## 4. Trigger-phrase tells

The stem phrase → the answer shape. Grounded in the sample questions (Q#) and task statements (T#).

### Enforcement and workflow

| Stem says | Correct answer shape | Source |
|---|---|---|
| "must / mandatory / guarantee / compliance / financial consequences / incorrect refunds" | Programmatic hook or prerequisite gate that *blocks* the tool call — never prompt instructions | Q1, T1.4, T1.5 |
| "refunds above $X / policy threshold" | Tool-call interception hook that blocks and redirects to human escalation | T1.5 |
| "tools return mixed formats (Unix timestamps, ISO 8601, numeric codes)" | PostToolUse hook normalizing results before the model sees them | T1.5 |
| "when should the loop stop / termination" | `stop_reason`: continue on `"tool_use"`, stop on `"end_turn"` — never NL parsing, iteration caps, or checking for text | T1.1 |
| "verify identity before financial operations" | Prerequisite gate blocking downstream tools until upstream returned verified ID | Q1, T1.4 |

### Diagnosis and improvement

| Stem says | Correct answer shape | Source |
|---|---|---|
| "most effective FIRST step" | Cheapest root-cause fix (descriptions, criteria, examples) — not new infra, not consolidation | Q2 |
| "wrong tool selected + descriptions are minimal/similar" | Expand tool descriptions: input formats, example queries, edge cases, when-to-use-vs-alternatives | Q2, T2.1 |
| "two tools with near-identical names/descriptions (analyze_content vs analyze_document)" | Rename + differentiate descriptions to eliminate overlap | T2.1 |
| "agent prefers built-in Grep over your MCP tool" | Enhance the MCP tool's description (capabilities + outputs) | T2.4 |
| "escalates easy cases, attempts hard ones / calibration off" | Explicit escalation criteria + few-shot escalate-vs-resolve examples in system prompt | Q3 |
| "be conservative / only high-confidence didn't help" | Specific categorical criteria (report bugs+security, skip style); disable high-FP categories temporarily | T4.1 |
| "inconsistent severity labels" | Explicit severity criteria with a concrete code example per level | T4.1 |
| "agent has 18 tools, picks wrong ones" | Restrict each agent to its role's 4–5 tools | T2.3 |
| "logs show what the coordinator assigned" | Blame the agent whose output is defective (usually the coordinator's decomposition); downstream agents "executed correctly" | Q7 |

### Claude Code config and scoping

| Stem says | Correct answer shape | Source |
|---|---|---|
| "available to every developer who clones/pulls" | Project scope in the repo: `.claude/commands/`, `.mcp.json`, project CLAUDE.md | Q4, T2.4, T3.1 |
| "personal / experimental / don't affect teammates" | User scope: `~/.claude/commands/`, `~/.claude.json`, `~/.claude/CLAUDE.md`, personal skill variants with different names | Q4, T2.4, T3.2 |
| "new team member isn't getting the instructions" | They're in user-level config; move to project-level | T3.1 |
| "conventions for files spread throughout the codebase (*.test.tsx next to source)" | `.claude/rules/` file with YAML frontmatter glob `paths:` — beats monolithic CLAUDE.md (inference) and per-dir CLAUDE.md (directory-bound) | Q6, T3.3 |
| "CLAUDE.md is huge/monolithic" | Split into `.claude/rules/` topic files, or `@import` per-package standards | T3.1 |
| "inconsistent behavior across sessions — which files are loaded?" | `/memory` command to verify loaded memory files | T3.1 |
| "always-on universal standard" vs "on-demand task workflow" | CLAUDE.md vs skill — always-loaded vs invoked | T3.2 |
| "skill output is verbose / pollutes main conversation" | `context: fork` frontmatter (isolated sub-agent context) | T3.2 |
| "restrict what a skill can do" | `allowed-tools` frontmatter | T3.2 |
| "developers invoke skill without required parameters" | `argument-hint` frontmatter | T3.2 |
| "architectural decisions / dozens of files / multiple valid approaches / migration touching 45+ files" | Plan mode first (explore + design before changing) | Q5, T3.4 |
| "single-file fix, clear stack trace, well-scoped change" | Direct execution — plan mode is overhead | T3.4 |
| "verbose discovery/exploration filling the context" | Explore subagent (or subagent delegation generally) returning summaries | T3.4, T5.4 |
| "secrets/tokens in shared MCP config" | `${ENV_VAR}` expansion in `.mcp.json` — never commit credentials | T2.4 |
| "standard integration (Jira etc.)" | Existing community MCP server; custom only for team-specific workflows | T2.4 |
| "agent makes many exploratory calls just to see what data exists" | Expose the catalog as MCP **resources** | T2.4 |

### CI/CD

| Stem says | Correct answer shape | Source |
|---|---|---|
| "pipeline hangs / waiting for interactive input" | `claude -p` (`--print`) non-interactive mode | Q10, T3.6 |
| "machine-parseable findings / post as PR comments" | `--output-format json` + `--json-schema` | T3.6 |
| "duplicate comments when review re-runs after new commits" | Include prior findings in context; instruct to report only new/unaddressed issues | T3.6 |
| "test generation suggests duplicates" | Provide existing test files in context | T3.6 |
| "low-value tests / wrong fixtures" | Document testing standards + fixtures in CLAUDE.md | T3.6 |
| "same session that wrote the code reviews it poorly" | Independent second Claude instance without the generator's reasoning context — not self-review instructions, not extended thinking | T3.6, T4.6 |
| "14 files, inconsistent depth, contradictory findings" | Per-file local passes + separate cross-file integration pass (attention dilution fix) | Q12, T1.6, T4.6 |

### API selection and structured output

| Stem says | Correct answer shape | Source |
|---|---|---|
| "overnight / weekly / nightly / latency-tolerant / cut costs" | Message Batches API: 50% off, ≤24h window, no SLA, `custom_id` correlation, no multi-turn tools | Q11, T4.5 |
| "blocking / pre-merge / developers wait for the result" | Synchronous API — never batch, no "usually fast enough," no timeout-fallback hybrid | Q11 |
| "N-hour SLA with 24h batch window" | Do the submission-frequency math (e.g., submit every 4h to guarantee 30h SLA) | T4.5 |
| "some batch requests failed" | Resubmit only failures identified by `custom_id`, with modifications (e.g., chunk oversized docs) | T4.5 |
| "before running a huge batch" | Refine the prompt on a sample set first | T4.5 |
| "guaranteed schema-compliant output / no JSON syntax errors" | Tool use (`tool_use`) with a JSON schema — not "ask nicely for JSON" | T4.3 |
| "model must call a tool, any tool / unknown document type with multiple schemas" | `tool_choice: "any"` | T4.3, T2.3 |
| "specific extraction must run first / this exact tool" | Forced `tool_choice: {"type": "tool", "name": "..."}` | T4.3, T2.3 |
| "some fields missing from source documents / model fabricates values" | Nullable/optional schema fields so the model can return null instead of inventing | T4.3 |
| "categories don't cover everything / ambiguous cases" | Enum with `"unclear"`, and `"other"` + detail string | T4.3 |
| "schema valid but line items don't sum to total" | Semantic validation — tool_use kills syntax errors only; extract `calculated_total` alongside `stated_total`, add `conflict_detected` | T4.3, T4.4 |
| "extraction failed validation — retry how?" | Retry with original document + failed extraction + the specific validation errors appended | T4.4 |
| "will retrying help?" | Yes for format/structure errors; **no if the information is absent from the source** | T4.4 |
| "inconsistent output format despite detailed instructions" | Few-shot examples demonstrating the exact format — most effective technique for format consistency | T4.2 |
| "prose spec keeps being interpreted differently" | 2–3 concrete input/output examples | T3.5 |
| "want design considerations surfaced you didn't anticipate" | Interview pattern — Claude asks questions before implementing | T3.5 |
| "multiple issues to fix — one message or several?" | Interacting fixes → single detailed message; independent fixes → sequential | T3.5 |
| "track why findings get dismissed as false positives" | Add a `detected_pattern` field to structured findings | T4.4 |

### Multi-agent and context

| Stem says | Correct answer shape | Source |
|---|---|---|
| "subagent doesn't know what the coordinator knows" | Context is NOT inherited — pass complete prior findings explicitly in the subagent's prompt | T1.3 |
| "run subagents in parallel" | Multiple Task tool calls in a *single* coordinator response; coordinator's `allowedTools` must include `"Task"` | T1.3 |
| "coordinator prompt style" | Research goals + quality criteria, not step-by-step procedures (subagent adaptability) | T1.3 |
| "timeout in subagent / design error flow" | Structured error context up to coordinator: failure type, attempted query, partial results, alternatives | Q8, T5.3 |
| "no results — error or fine?" | Distinguish access failures (retry decision needed) from valid empty results (successful query, no matches) | T5.3, T2.2 |
| "which errors should subagents handle themselves" | Local recovery for transient failures; propagate only unresolvable ones, with partials and what was attempted | T2.2, T5.3 |
| "generic 'Operation failed' responses" | Structured error metadata: `errorCategory` (transient/validation/permission), `isRetryable`, human-readable description | T2.2 |
| "agent needs one frequent capability outside its role (85/15 split)" | One scoped tool for the common case; coordinator routing stays for complex cases (least privilege) | Q9 |
| "numbers/dates/amounts getting lost in summarization" | Persistent "case facts" block (amounts, dates, order numbers, statuses) outside summarized history, included in every prompt | T5.1 |
| "tool returns 40+ fields, only 5 matter" | Trim tool outputs to relevant fields before they accumulate in context | T5.1 |
| "findings from the middle of long input get dropped" | Lost-in-the-middle: key-findings summary at the top + explicit section headers | T5.1 |
| "downstream agent has a small context budget" | Upstream agents return structured data (key facts, citations, scores), not verbose reasoning chains | T5.1 |
| "long session — agent starts citing 'typical patterns' instead of actual code" | Context degradation: scratchpad files for key findings, subagent delegation, `/compact` | T5.4 |
| "system crash mid-research — recover how?" | Structured state exports (manifest per agent); coordinator loads manifest on resume | T5.4 |
| "resume session after files changed" | Tell the resumed session exactly which files changed; if prior tool results are stale, start fresh with an injected summary instead | T1.7 |
| "compare two approaches from one shared analysis" | `fork_session` — independent branches from a shared baseline | T1.7 |
| "continue a named prior investigation" | `--resume <session-name>` | T1.7 |
| "citations lost after synthesis / who said what" | Structured claim-source mappings (URL, doc name, excerpt) that synthesis must preserve and merge | T5.6 |
| "two credible sources give different numbers" | Include BOTH, annotated with source attribution — never arbitrarily pick one | T5.6 |
| "old vs new data read as contradiction" | Require publication/collection dates in structured outputs | T5.6 |
| "some sources were unavailable" | Coverage annotations: which findings are well-supported vs which areas have gaps | T5.3, T5.6 |
| "customer explicitly demands a human" | Escalate immediately — don't investigate first | T5.2 |
| "customer frustrated but issue is simple" | Acknowledge frustration + offer resolution; escalate only if they reiterate | T5.2 |
| "policy is silent/ambiguous on the request" | Escalate — policy gap is a trigger (complexity alone is not) | T5.2 |
| "lookup returns multiple customer matches" | Ask for an additional identifier — never pick by heuristic | T5.2 |
| "97% overall accuracy — automate?" | Aggregate masks segment failures: analyze by document type and field first; stratified random sampling of high-confidence extractions | T5.5 |
| "limited human reviewer capacity" | Field-level confidence scores calibrated on labeled validation sets; route low-confidence + ambiguous/contradictory sources to review | T5.5 |
| "search file CONTENTS for a pattern" | Grep | T2.5 |
| "find files by NAME/extension pattern" | Glob (`**/*.test.tsx`) | T2.5 |
| "Edit fails — anchor text not unique" | Read + Write fallback | T2.5 |
| "understand an unfamiliar codebase" | Incremental: Grep entry points → Read to follow imports — never read everything upfront | T2.5 |
| "open-ended task (add tests to legacy codebase)" | Dynamic decomposition: map structure → find high-impact areas → prioritized plan that adapts; fixed prompt chaining is for predictable multi-aspect work | T1.6 |

---

## 5. The one-sentence version

**Find the defect the stem names, apply the cheapest fix that touches exactly it — unless the stakes are money/compliance/ordering, in which case enforce it in code — and kill any option that is a named anti-pattern, a fabricated feature, the wrong scope, or a fix for a component the logs already cleared.**
