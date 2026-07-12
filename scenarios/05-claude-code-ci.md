# Scenario 5 — Claude Code for Continuous Integration

> **Exam framing (verbatim intent):** You are integrating Claude Code into your CI/CD pipeline. The system runs automated code reviews, generates test cases, and provides feedback on pull requests. You must design prompts that provide actionable feedback and minimize false positives.
>
> **Primary domains:** D3 Claude Code Configuration & Workflows (20%), D4 Prompt Engineering & Structured Output (20%). Three of the guide's 12 sample questions (Q10–Q12) come from this exact scenario — this is high-yield territory.

---

## 1. The system at a glance

Two lanes, and the exam loves testing whether you know which workload goes in which lane:

- **Sync lane (blocking):** PR opens → CI runner checks out the repo → runs `claude -p` headless → Claude Code reads the repo's committed config (CLAUDE.md, `.claude/rules/`, `.claude/commands/`, `.mcp.json`) → emits schema-enforced JSON findings → a small script posts them as inline PR comments. Developers are waiting, so this must be a synchronous real-time call.
- **Batch lane (latency-tolerant):** Nightly test generation and weekly tech-debt reports go through the **Message Batches API** — 50% cheaper, up to 24-hour processing window, no latency SLA. Never put anything blocking in this lane.

```
                    PR opened / updated
                           │
                           ▼
┌───────────────────── CI runner (sync lane) ─────────────────────┐
│ git checkout ── repo carries the config Claude Code reads:      │
│    CLAUDE.md            review criteria, test standards,        │
│    .claude/rules/        fixtures (path-scoped via globs)       │
│    .claude/commands/    /review-pr prompt (team-shared)         │
│    .mcp.json            MCP servers, ${GITHUB_TOKEN} expansion  │
│                                                                 │
│ claude -p "/review-pr" --output-format json \                   │
│        --json-schema .claude/schemas/findings.json              │
│              │                                                  │
│              ▼                                                  │
│ findings.json ──► post_comments.py ──► inline PR comments       │
│      ▲                                                          │
│      └── prior-run findings fed back in on re-review (dedup)    │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────── overnight (batch lane) ─────────────────────┐
│ Message Batches API: nightly test generation, weekly audits     │
│ 50% cost · ≤24 h window · no SLA · custom_id correlation        │
│ NO multi-turn tool calling inside a batch request               │
└─────────────────────────────────────────────────────────────────┘
```

Key architectural principle baked in from the start: the **review instance is independent from any instance that generated the code**. A session that wrote the code retains its generation reasoning and won't question its own decisions. CI reviews always run fresh.

---

## 2. Build it step by step

### Step 1 — Prove the headless invocation

Everything else is useless if the CI job hangs. Claude Code is interactive by default; in a pipeline you run it with **`-p` (or `--print`)** — non-interactive mode: process the prompt, print to stdout, exit.

```bash
claude -p "Review the diff between main and HEAD for security issues"
```

Burn this in: `-p`/`--print` is the **only** documented mechanism. `CLAUDE_HEADLESS=true` and `--batch` **do not exist** — they are distractors on the real exam (sample Q10). Redirecting stdin from `/dev/null` is a Unix hack that doesn't address Claude Code's syntax either.

### Step 2 — Put project context where CI can see it

CI runners clone the repo. Anything in your personal `~/.claude/CLAUDE.md` (user-level) never reaches the runner — or your teammates. So all review criteria, testing standards, and fixture documentation go in **project-level, version-controlled** config:

```
repo/
├── CLAUDE.md                      # universal: review criteria, test standards
├── .claude/
│   ├── rules/
│   │   ├── testing.md             # path-scoped: loads only for test files
│   │   └── api-conventions.md     # path-scoped: loads only under src/api/
│   ├── commands/
│   │   └── review-pr.md           # team-shared slash command
│   └── schemas/
│       └── findings.json          # JSON schema for --json-schema
├── .mcp.json                      # project-scoped MCP servers
└── scripts/
    └── post_comments.py
```

**CLAUDE.md** (root, project-level — loaded on every invocation):

```markdown
# Code Review Standards
- Report: logic bugs, security vulnerabilities, data-loss risks.
- Skip: style preferences, patterns consistent with the local codebase.

# Testing Standards
- A valuable test covers a distinct behavior or branch, not a restated implementation.
- Fixtures live in tests/fixtures/ — factory_user(), factory_order(). Use them;
  do not construct raw model objects in tests.
- Existing suites: tests/unit/, tests/integration/. Check before proposing new cases.
```

This is D3.6 verbatim: *CLAUDE.md is the mechanism for providing project context (testing standards, fixture conventions, review criteria) to CI-invoked Claude Code.* Documenting valuable-test criteria and available fixtures here is what "improves test generation quality and reduces low-value test output."

**Path-scoped rules** — `.claude/rules/testing.md` with YAML frontmatter glob patterns. Rules load only when Claude edits matching files, saving tokens and keeping context relevant. Globs beat per-directory CLAUDE.md files when the convention applies to files *spread across* the codebase (e.g., `Button.test.tsx` next to `Button.tsx` everywhere):

```markdown
---
paths: ["**/*.test.*", "tests/**/*"]
---
- Use pytest parametrize for input matrices; no copy-pasted test bodies.
- Every test asserts on behavior, never on log output.
```

Sanity-check what actually loads with the **`/memory`** command — that's the diagnostic tool the guide names for "instructions applied on my machine but not in CI / for the new teammate."

### Step 3 — Write the review prompt as a shared slash command

Project-scoped commands live in **`.claude/commands/`** (version-controlled, every developer and every CI run gets them on clone/pull). `~/.claude/commands/` is personal-only — wrong answer for anything "the whole team should have."

`.claude/commands/review-pr.md` — and this file is where D4.1 and D4.2 live or die:

```markdown
Review the diff between origin/main and HEAD.

REPORT only these categories:
- Bugs: code that produces incorrect results, unhandled failure paths, race conditions.
- Security: injection, authn/authz gaps, secrets in code, unsafe deserialization.
- Comment contradictions: flag a comment ONLY when its claimed behavior
  contradicts what the code actually does.

SKIP entirely:
- Style and formatting preferences.
- Patterns consistent with surrounding code in this repo.
- Speculative performance concerns without a concrete hot path.

Severity — classify using these anchors:
- critical: exploitable security flaw or guaranteed data corruption.
  e.g. `query = f"SELECT * FROM users WHERE id = {user_input}"`
- major: wrong behavior on realistic inputs.
  e.g. `if discount > 100:` where percent discounts are stored as 0–1 floats
- minor: correct today, fragile tomorrow (dead branch, misleading name).

Examples of correct judgment:

<example>
Code: `except Exception: pass` inside a metrics-emit helper
Verdict: SKIP — swallowing errors in fire-and-forget telemetry matches this
repo's established pattern (see CLAUDE.md); not a genuine issue.
</example>

<example>
Code: `except Exception: pass` wrapping a payment capture call
Verdict: REPORT, severity=critical — silently dropped payment failures cause
revenue loss with no operator signal.
Suggested fix: catch the specific gateway error, log, and re-raise.
</example>
```

Why it's built this way — three guide rules:

1. **Explicit categorical criteria beat vague instructions.** "Flag comments only when claimed behavior contradicts actual code behavior" works; "check that comments are accurate" doesn't. And blanket instructions like *"be conservative"* or *"only report high-confidence findings"* **fail to improve precision** — that's stated flat-out in D4.1 and it's a favorite wrong answer.
2. **Severity needs concrete code examples per level** to classify consistently — prose definitions alone drift.
3. **2–4 targeted few-shot examples for the ambiguous cases**, showing the *reasoning* for why one verdict beat the plausible alternative — including an acceptable-pattern example that is explicitly NOT flagged. That's how you cut false positives while still letting the model generalize to novel patterns (few-shot generalizes; hard-coded pattern lists don't).

One more D4.1 lever for production: if one category (say, comment-accuracy) is generating most of the false positives, **temporarily disable that category** while you improve its prompt. High-FP categories poison developer trust in the *accurate* categories too.

### Step 4 — Enforce structured output

Prose findings can't be posted as inline PR comments by a script. The CI flags are **`--output-format json`** plus **`--json-schema`** to get machine-parseable, schema-enforced findings.

`.claude/schemas/findings.json`:

```json
{
  "type": "object",
  "properties": {
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "file":             { "type": "string" },
          "line":             { "type": "integer" },
          "category":         { "type": "string",
                                "enum": ["bug", "security", "comment_contradiction", "other"] },
          "category_detail":  { "type": ["string", "null"] },
          "severity":         { "type": "string", "enum": ["critical", "major", "minor"] },
          "issue":            { "type": "string" },
          "suggested_fix":    { "type": ["string", "null"] },
          "detected_pattern": { "type": "string" },
          "confidence":       { "type": "number" }
        },
        "required": ["file", "line", "category", "severity", "issue", "detected_pattern"]
      }
    }
  },
  "required": ["findings"]
}
```

Schema design decisions the exam tests (D4.3/D4.4):

| Field | Why it's shaped this way |
|---|---|
| `suggested_fix` nullable | Optional/nullable fields prevent the model **fabricating values** just to satisfy `required` |
| `category` enum + `"other"` + `category_detail` | The "other + detail string" pattern keeps categories extensible without schema churn |
| `detected_pattern` | When developers dismiss findings, you can analyze **which code constructs trigger false positives** systematically — the guide's named feedback-loop mechanism |
| `confidence` | Self-reported confidence per finding enables **calibrated review routing** (D4.6) — but it is NOT a precision fix on its own |

And the limit you must know cold: **strict schemas eliminate JSON syntax errors, not semantic errors.** The output will always parse; the `line` number can still be wrong, the severity can still be misassigned. Validation-retry loops (append the specific validation error and retry) fix format/structure errors — they cannot conjure information that isn't in the diff.

### Step 5 — Wire the pipeline

```yaml
# .github/workflows/claude-review.yml (sketch)
jobs:
  claude-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - name: Run review
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          claude -p "/review-pr" \
            --output-format json \
            --json-schema .claude/schemas/findings.json \
            > findings.json
      - name: Post inline comments
        run: python scripts/post_comments.py findings.json "$PR_NUMBER"
```

`scripts/post_comments.py` — plain Python, nothing clever:

```python
import json, sys

findings = json.load(open(sys.argv[1]))["findings"]
for f in findings:
    post_review_comment(          # gh api / REST call
        pr=sys.argv[2],
        path=f["file"], line=f["line"],
        body=f"**{f['severity']} {f['category']}**: {f['issue']}\n\n"
             + (f"Suggested fix: {f['suggested_fix']}" if f["suggested_fix"] else ""),
    )
```

If an MCP server is involved (e.g., a GitHub server so Claude can read PR metadata itself), it goes in **project-scoped `.mcp.json` with environment-variable expansion** so no secret is ever committed:

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}" }
    }
  }
}
```

Project scope (`.mcp.json`, committed) = shared team tooling. User scope (`~/.claude.json`) = personal/experimental servers. Both are available simultaneously when configured.

### Step 6 — Handle scale: multi-pass review and re-run dedup

**Large PRs (the 14-file problem, sample Q12).** A single pass over many files produces attention dilution: detailed feedback on some files, superficial on others, and contradictory verdicts on identical code. The fix is structural, not a bigger model:

1. **Per-file passes** — analyze each file individually for local issues (consistent depth per file).
2. **One separate cross-file integration pass** — data flow, interface mismatches between files.

This is prompt chaining (D1.6) applied to review. Wrong answers to recognize: bigger context window (context size ≠ attention quality), forcing developers to split PRs (shifts burden, fixes nothing), consensus voting across 3 runs (suppresses real bugs that are caught intermittently).

**Re-runs after new commits.** A stateless re-review reposts every old comment and craters trust. The guide's pattern: **include the prior run's findings in context and instruct Claude to report only new or still-unaddressed issues.**

```bash
claude -p "/review-pr Prior findings from the last run are in prior-findings.json. \
Report ONLY issues that are new in this diff or previously reported and still \
unfixed. Do not re-report resolved or unchanged findings." \
  --output-format json --json-schema .claude/schemas/findings.json
```

**Reviewing Claude-generated code.** If Claude Code generated the change, the review must run in a **fresh, independent instance**. Same-session self-review retains the generation reasoning and won't question its own decisions; self-review instructions and extended thinking do not fix this (D3.6 + D4.6). In CI this is free — every job is a new session. Don't break it by resuming the generator's session for the review.

### Step 7 — Test generation, and the batch lane

Test generation quality hinges on two context inputs, both already staged in Step 2:

1. **Existing test files in context** → avoids proposing duplicate scenarios the suite already covers.
2. **CLAUDE.md testing standards + fixture docs** → avoids low-value tests and raw-object construction.

Now the economics. Two workflows want Claude: a **blocking pre-merge check** and **nightly/weekly analysis**. The Message Batches API gives 50% cost savings — but processing takes **up to 24 hours with no latency SLA**. So (sample Q11): batch the overnight work only; keep synchronous calls for anything a developer waits on. "Batch both with a timeout fallback" is added complexity for a mismatched tool — a distractor.

```python
# nightly_testgen.py — Message Batches API sketch
import anthropic
client = anthropic.Anthropic()

batch = client.messages.batches.create(
    requests=[
        {
            "custom_id": f"testgen::{path}",       # correlates request -> result
            "params": {
                "model": MODEL,
                "max_tokens": 4096,
                "messages": [{
                    "role": "user",
                    # Batch requests CANNOT tool-call mid-request (no multi-turn
                    # tool use) -> inline the source AND existing tests up front.
                    "content": build_prompt(source=read(path),
                                            existing_tests=read_tests_for(path)),
                }],
            },
        }
        for path in modules_missing_coverage()
    ],
)

# Poll for completion (24h worst case). On failures: resubmit ONLY the failed
# custom_ids, with modifications (e.g., chunk files that blew the context limit).
```

Three batch facts that show up as exam decision points:

- **No multi-turn tool calling inside a batch request** — the agentic Read/Grep loop is unavailable; everything the model needs must be in the prompt.
- **Failure handling is per-`custom_id`**: resubmit only the failed items, modified — never rerun the whole batch.
- **SLA math**: with a 24 h worst-case processing window, submitting batches every 4 hours means an item waits ≤ 4 h + 24 h = 28 h — that's how you guarantee a 30 h SLA. Submission frequency = SLA − processing window.
- Before batch-processing a large volume, **refine the prompt on a small sample set** first — maximizes first-pass success and avoids paying for iterative resubmissions.

---

## 3. The decision points this scenario tests

Each row maps to a task statement (TS) from the guide. These are the exact judgment calls the distractors are built around.

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| CI job hangs; logs show Claude Code waiting for input (TS 3.6) | `claude -p "..."` (`--print`) | Documented non-interactive mode: prompt → stdout → exit | `CLAUDE_HEADLESS=true`, `--batch` (both **fake**), `< /dev/null` |
| Findings must post as inline PR comments (TS 3.6) | `--output-format json` + `--json-schema` | Machine-parseable, schema-enforced output | Regex-parse prose; "return JSON" in the prompt with no enforcement |
| CI reviews ignore team standards that work on your laptop (TS 3.1/3.6) | Move criteria to project CLAUDE.md / `.claude/rules/`, verify with `/memory` | User-level `~/.claude/CLAUDE.md` isn't in the repo — CI and teammates never load it | "Increase model temperature", re-prompting, or copying config to each runner by hand |
| Team-wide review command (TS 3.2) | `.claude/commands/` in the repo | Version control ships it on clone/pull | `~/.claude/commands/` (personal only); putting command defs in CLAUDE.md; a nonexistent `config.json` commands array |
| Test-file conventions, files scattered repo-wide (TS 3.3) | `.claude/rules/` file, frontmatter `paths: ["**/*.test.*"]` | Globs match by file type regardless of directory; load only when relevant | Per-directory CLAUDE.md (directory-bound); one monolithic CLAUDE.md relying on inference |
| Verbose skill (codebase analysis) pollutes main context (TS 3.2) | `context: fork` in SKILL.md frontmatter; restrict via `allowed-tools` | Runs in isolated sub-agent context; outputs don't flood the session | Running it inline and `/compact`-ing afterward |
| Too many false positives, devs losing trust (TS 4.1) | Explicit report/skip categories + few-shot examples separating acceptable patterns from genuine issues | Precision comes from criteria, not caution | "Be conservative" / "only report high-confidence findings" — the guide says these **fail** |
| One category generates most FPs (TS 4.1) | Temporarily disable that category while fixing its prompt | High-FP categories undermine trust in accurate ones | Global confidence thresholds; ignoring it |
| Severity labels inconsistent across runs (TS 4.1) | Explicit severity criteria with a concrete code example per level | Anchored definitions classify consistently | Confidence-based filtering; longer prose definitions |
| Output format inconsistent despite detailed instructions (TS 4.2) | 2–4 few-shot examples demonstrating the exact format (location, issue, severity, fix) | Few-shot is the most effective consistency technique; generalizes to novel cases | Piling on more prose instructions |
| Re-review after fixes duplicates old comments (TS 3.6) | Feed prior findings into context; instruct "only new or still-unaddressed" | The model can't dedup against runs it never saw | Post-hoc string-match dedup only; wiping comments and reposting |
| Generated tests duplicate existing coverage (TS 3.6) | Provide existing test files in context + valuable-test criteria and fixtures in CLAUDE.md | Model can't avoid duplicating what it can't see | "Don't duplicate tests" instruction with no test files provided |
| 14-file PR: inconsistent, contradictory review (TS 4.6/1.6) | Per-file local passes + separate cross-file integration pass | Fixes attention dilution structurally | Bigger context model; force smaller PRs; 2-of-3 consensus voting |
| Reviewing code Claude just generated (TS 3.6/4.6) | Fresh independent instance, no generator context | Generator session won't question its own reasoning | Self-review instructions; extended thinking in the same session |
| Cut costs: blocking pre-merge check + overnight report (TS 4.5) | Batch API for overnight only; sync for pre-merge | Batch = 50% cheaper, ≤24 h, **no SLA** — never on a blocking path | Batch both; batch with timeout-fallback-to-sync |
| Some batch requests fail (oversized files) (TS 4.5) | Resubmit only failed `custom_id`s, modified (chunked) | `custom_id` exists precisely for request/response correlation | Rerun the entire batch; abandon failed items |
| Devs dismiss findings, you want to learn why (TS 4.4) | `detected_pattern` field in the findings schema | Enables systematic analysis of which constructs trigger FPs | Reading dismissals ad hoc; asking the model to "do better" |

---

## 4. Failure-modes drill

Styled like the guide's sample questions: symptom → root cause → fix. Cover the distractor in your head before reading the fix.

**1. Pipeline job hangs indefinitely; logs show Claude Code awaiting interactive input.**
Root cause: invoked without non-interactive mode.
Fix: `claude -p "..."`. Not `CLAUDE_HEADLESS`, not `--batch` — neither exists. That's sample Q10 verbatim.

**2. The comment-posting script crashes intermittently on malformed JSON.**
Root cause: JSON requested via prompt text only — nothing enforces it.
Fix: `--output-format json --json-schema findings.json`. Remember the boundary: this eliminates *syntax* errors; *semantic* errors (wrong line number, misfiled severity) survive and need validation + retry-with-error-feedback.

**3. Reviews follow your standards locally but CI output is generic; a new teammate sees the same gap.**
Root cause: criteria live in user-level `~/.claude/CLAUDE.md`, which is never cloned.
Fix: move them to project-level CLAUDE.md / `.claude/rules/`, commit, and use `/memory` to verify which memory files actually load.

**4. Developers have started auto-dismissing the bot — including its correct security findings.**
Root cause: one high-false-positive category (e.g., comment accuracy prompted as "check that comments are accurate") destroyed trust across all categories.
Fix: rewrite as explicit contrast criteria ("flag only when claimed behavior contradicts actual code behavior"), add few-shot examples of acceptable-pattern vs genuine-issue, and temporarily disable the worst category until its precision recovers. Adding "be conservative" is the trap — the guide says it doesn't work.

**5. On a 14-file PR: deep feedback on 3 files, superficial on the rest, and the same pattern flagged in one file but approved in another.**
Root cause: attention dilution in a single all-files pass.
Fix: restructure into per-file local passes plus a separate cross-file integration pass. Not a larger context window (attention, not capacity), not consensus-of-three (suppresses intermittently-caught real bugs). Sample Q12.

**6. After a developer pushes fix commits, the bot reposts all 11 original comments.**
Root cause: each run is stateless; the model has no knowledge of prior findings.
Fix: include the previous run's findings in the new run's context and instruct: report only new or still-unaddressed issues.

**7. Nightly test generation proposes tests the suite already has, plus trivial getter tests nobody wants.**
Root cause: missing context — no existing test files provided, no definition of a valuable test.
Fix: inline the relevant existing test files in the prompt, and document testing standards + valuable-test criteria + available fixtures in CLAUDE.md so every CI invocation inherits them.

**8. You moved the pre-merge check to the Batches API for the 50% savings; developers are now blocked for hours.**
Root cause: batch has an up-to-24-hour window and no latency SLA — it's for latency-tolerant work only.
Fix: sync API for anything blocking; batch for overnight/weekly jobs. And within batch: single-shot prompts only (no mid-request tool calling), failures resubmitted per `custom_id` after modification. Sample Q11.

---

## Quick-recall card

- `-p` / `--print` = headless CI mode. `--batch` and `CLAUDE_HEADLESS` are fictional.
- `--output-format json` + `--json-schema` = structured CI findings.
- Project CLAUDE.md = CI's context channel (review criteria, test standards, fixtures).
- `.claude/commands/` shared · `~/.claude/commands/` personal. Same split: `.mcp.json` vs `~/.claude.json` (with `${VAR}` expansion for secrets).
- `.claude/rules/` + `paths:` globs > directory CLAUDE.md for scattered file types.
- Precision = explicit categories + severity anchors + 2–4 few-shot; never "be conservative."
- Big PR = per-file passes + one integration pass. Generated code = independent reviewer instance.
- Batch API: 50% off, ≤24 h, no SLA, `custom_id`, no multi-turn tools — never blocking.
