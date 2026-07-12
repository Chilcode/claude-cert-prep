# Domain 3 — Claude Code Configuration & Workflows (20% of exam, ~12 of 60 questions)

Source of truth: official exam guide, Task Statements 3.1–3.6. This is the domain where you have the
most hands-on hours — the risk is not concepts, it's **exact file paths, exact flag names, and the
distractor patterns** the exam uses. Primary scenarios that pull from this domain: Scenario 2 (Code
Generation with Claude Code), Scenario 4 (Developer Productivity), Scenario 5 (Claude Code for CI).

---

## 3.1 CLAUDE.md hierarchy, @import, .claude/rules/, /memory

### Concepts in plain words

**Three levels of CLAUDE.md.** User-level (`~/.claude/CLAUDE.md`) is yours alone — it lives in your
home dir, it is never in the repo, teammates never see it. Project-level (`.claude/CLAUDE.md` or a
`CLAUDE.md` at repo root) is committed to version control and applies to everyone who clones the repo.
Directory-level (a `CLAUDE.md` inside a subdirectory) applies to work in that subtree. The classic exam
diagnosis: "a new team member isn't getting the team's instructions" → those instructions are sitting
in someone's user-level file instead of the project-level file.

```
~/.claude/CLAUDE.md              # user-level — personal, NOT shared via git
repo/
├── CLAUDE.md                    # project-level (root form) — shared via git
├── .claude/
│   ├── CLAUDE.md                # project-level (alternate form)
│   └── rules/
│       ├── testing.md           # topic-specific rule files
│       ├── api-conventions.md
│       └── deployment.md
└── packages/billing/
    └── CLAUDE.md                # directory-level — applies to this subtree
```

**@import.** Instead of one giant CLAUDE.md, reference external files with `@import` so each
package's CLAUDE.md pulls in only the standards files relevant to it (maintainers pick what applies to
their domain):

```markdown
# packages/billing/CLAUDE.md
@import ../../standards/typescript.md
@import ../../standards/payments-compliance.md
```

**.claude/rules/ as the anti-monolith.** Splitting a bloated CLAUDE.md into focused topic files
(`testing.md`, `api-conventions.md`, `deployment.md`) under `.claude/rules/` is the sanctioned modular
organization pattern.

**/memory.** When Claude behaves inconsistently across sessions ("it follows the rule on my machine
but not Jake's"), `/memory` shows **which memory files are actually loaded**. It's the diagnostic
command for hierarchy problems — run it before rewriting anything.

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Team standard must apply to every dev who clones the repo | Project-level CLAUDE.md (root or `.claude/CLAUDE.md`) | Version-controlled → distributed with the repo | Putting it in `~/.claude/CLAUDE.md` — works on your machine, invisible to teammates |
| New teammate not receiving instructions everyone else has | Diagnose: instructions are user-level, move them to project-level | User-level config never leaves the author's home dir | Assuming it's a bug/model issue and rewording the instruction |
| Personal preferences (your editor quirks, your tone) | User-level `~/.claude/CLAUDE.md` | Shouldn't pollute team config | Committing personal prefs to project CLAUDE.md |
| Conventions specific to one subdirectory | Directory-level CLAUDE.md in that subdirectory | Loads for work in that subtree only | Bloating the root file with area-specific rules |
| CLAUDE.md has grown huge and unfocused | Split into topic files in `.claude/rules/` (testing.md, api-conventions.md, …) | Modular, focused, maintainable | One monolith with headers, "Claude will infer which section applies" — inference is unreliable |
| Each package needs only its relevant standards | `@import` the specific standards files in each package's CLAUDE.md | Selective inclusion, maintainer-owned | Copy-pasting standards into every package (drift) |
| Inconsistent behavior across sessions/machines | Run `/memory` to verify which memory files loaded | Direct observation beats guessing | Rewriting prompts before checking what's actually loaded |

---

## 3.2 Custom slash commands and skills

### Concepts in plain words

**Commands have two scopes.** `.claude/commands/` in the repo = project-scoped, version-controlled,
every dev gets it on clone/pull. `~/.claude/commands/` = user-scoped, personal, not shared. That's the
whole model — there is **no** `.claude/config.json` with a `commands` array (a real exam distractor,
sample Q4).

**Skills live in `.claude/skills/` with a SKILL.md** whose YAML frontmatter carries three tested keys:

```
.claude/skills/analyze-deps/SKILL.md
```
```yaml
---
context: fork                 # run in isolated sub-agent context
allowed-tools: Read, Grep     # restrict tools during skill execution
argument-hint: <package-name> # shown when invoked without arguments
---
Analyze the dependency graph of $ARGUMENTS and report unused packages.
```

- `context: fork` → the skill runs in an isolated sub-agent context so verbose output (codebase
  analysis dumps) or exploratory content (brainstorming alternatives) doesn't pollute the main
  conversation.
- `allowed-tools` → restricts what tools the skill may use while executing (e.g., limit to file-write
  operations so a skill can't run destructive Bash).
- `argument-hint` → prompts the developer for the required parameter when they invoke the skill with
  no arguments.

**Personal skill variants.** Want your own version of a team skill without breaking teammates? Create
it in `~/.claude/skills/` **with a different name**.

**Skills vs CLAUDE.md.** Skills = on-demand invocation for task-specific workflows. CLAUDE.md =
always-loaded universal standards. If it must apply on every interaction, it's not a skill.

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Team `/review` checklist command for every dev on clone/pull | File in `.claude/commands/` in the repo | Version-controlled, auto-available | `~/.claude/commands/` (personal only); CLAUDE.md (context, not commands); `.claude/config.json` commands array (**doesn't exist**) |
| Personal experimental command | `~/.claude/commands/` | Doesn't touch teammates | Committing experiments to the shared repo |
| Skill produces huge verbose output (codebase analysis, brainstorming) | `context: fork` in SKILL.md frontmatter | Isolated sub-agent context, main conversation stays clean | Running it inline and burning the main context window |
| Skill must never take destructive actions | `allowed-tools` in frontmatter listing only what's needed | Deterministic tool restriction at execution time | Prompt text saying "don't run rm" — probabilistic, not enforced |
| Devs keep invoking a skill without required params | `argument-hint` in frontmatter | Prompts for the parameter on bare invocation | Documenting params only in a README nobody reads |
| You want a customized version of a team skill | Personal variant in `~/.claude/skills/` under a **different name** | Team skill untouched | Editing the shared skill in-place (affects everyone) |
| Rule must apply always, everywhere | CLAUDE.md, not a skill | Skills require invocation; CLAUDE.md is always loaded | Encoding universal standards as a skill and hoping it gets invoked |

---

## 3.3 Path-scoped rules (conditional convention loading)

### Concepts in plain words

Files in `.claude/rules/` can carry YAML frontmatter with a `paths` field of glob patterns. The rule
loads **only when Claude edits a file matching the glob** — matching by *file path pattern*, not by
directory. That buys you two things: conventions follow the file type wherever it lives, and irrelevant
rules stay out of context (token savings).

```yaml
# .claude/rules/testing.md
---
paths: ["**/*.test.tsx"]
---
All tests use React Testing Library. No snapshot tests. Arrange-Act-Assert structure.
```

```yaml
# .claude/rules/terraform.md
---
paths: ["terraform/**/*"]
---
Pin provider versions. Never inline secrets; use variables.
```

The killer comparison (sample Q6): test files sit **next to** the code they test, scattered across the
whole tree (`Button.test.tsx` beside `Button.tsx`). A directory-level CLAUDE.md can't cover that —
CLAUDE.md files are directory-bound. A glob rule `**/*.test.tsx` covers every test file no matter
where it lives, automatically and deterministically.

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Conventions for a file *type* scattered across the tree (test files everywhere) | `.claude/rules/` file with `paths: ["**/*.test.tsx"]` | Glob matches by path pattern regardless of directory | Per-directory CLAUDE.md (directory-bound, can't span); monolithic CLAUDE.md with headers (relies on inference) |
| Conventions confined to one contiguous area | Either a glob rule (`paths: ["src/api/**/*"]`) or a directory CLAUDE.md works; glob rule scales better | Both scope correctly here | Overthinking it — exam favors rules when the word "automatic"/"regardless of location" appears |
| Context window bloated by rules irrelevant to current file | Path-scoped rules | Load only on matching edits → fewer wasted tokens | Cramming all conventions into always-loaded CLAUDE.md |
| Conventions must apply "automatically" with no manual step | Path-scoped rules (deterministic match) | Loading is triggered by file path, not model judgment | Skills — require invocation or Claude *choosing* to load them; not deterministic |

---

## 3.4 Plan mode vs direct execution; the Explore subagent

### Concepts in plain words

**Plan mode** = explore and design before touching anything. It's for tasks with large-scale changes,
multiple valid approaches, architectural decisions, or multi-file modifications — the guide's own
examples: monolith→microservices restructuring, a library migration touching 45+ files, choosing
between integration approaches with different infrastructure requirements. Value: safe exploration
prevents costly rework.

**Direct execution** = just do it. For simple, well-scoped changes: adding a single validation check to
one function, a single-file bug fix with a clear stack trace, a date-validation conditional.

**The sequencing trick the exam loves (sample Q5):** if complexity is *stated in the requirements*
("dozens of files", "decisions about service boundaries"), plan mode is the answer **now** — "start
direct and switch to plan mode if it gets complicated" is a named-wrong option. The legitimate combo
is: plan mode for investigation → direct execution for implementing the planned approach.

**Explore subagent.** During multi-phase tasks, discovery output (file dumps, search results) is
verbose and mostly disposable. The Explore subagent does the noisy discovery in its own context and
returns a **summary**, preserving the main conversation's context window.

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Monolith → microservices, dozens of files, boundary decisions | Plan mode first | Large-scale + architectural + multiple valid approaches = plan mode's exact design target | "Direct execution, let implementation reveal boundaries" → costly rework; "detailed upfront instructions" → assumes you already know the answer |
| Single-file bug fix with a clear stack trace | Direct execution | Well-understood, clearly scoped | Plan-mode ceremony on a trivial fix (wasted time; exam counts over-engineering as wrong) |
| Add one validation conditional to one function | Direct execution | Simple, well-scoped | Same as above |
| Library migration affecting 45+ files | Plan mode to design, then direct execution to implement | Investigation and implementation are different phases | Staying in plan mode forever, or executing without a plan |
| Complexity already stated in the requirements | Plan mode immediately | The complexity isn't speculative — it's given | "Start direct, escalate to plan mode if I hit complexity" (sample Q5 distractor D) |
| Discovery phase generating verbose output during a long multi-phase task | Explore subagent → returns summary to main session | Isolates noise, prevents context-window exhaustion | Doing all exploration in the main conversation and running out of context mid-task |

---

## 3.5 Iterative refinement techniques

### Concepts in plain words

**Concrete I/O examples beat prose.** When a natural-language description of a transformation keeps
getting interpreted inconsistently, give **2–3 concrete input/output example pairs**. That is stated as
the *most effective* way to communicate expected transformations.

```text
Convert these log lines. Examples:
IN:  2026-07-11T14:02:11Z ERROR db timeout uid=482
OUT: {"ts": "2026-07-11T14:02:11Z", "level": "error", "msg": "db timeout", "uid": 482}

IN:  Jul 11 14:03:40 WARN cache miss uid=99
OUT: {"ts": "2026-07-11T14:03:40Z", "level": "warn", "msg": "cache miss", "uid": 99}
```

**Test-driven iteration.** Write the test suite first — expected behavior, edge cases, performance
requirements — then iterate by **sharing test failures** with Claude to guide progressive improvement.
To fix a specific edge case (null values in a migration script), hand over a specific test case with
example input and expected output.

**Interview pattern.** In unfamiliar domains, have Claude **ask you questions first** to surface
considerations you didn't anticipate (cache invalidation strategy, failure modes) *before* it
implements anything.

**Single message vs sequential.** If multiple issues **interact** (fixing one changes another), report
them all in a single detailed message so Claude can solve them jointly. If issues are **independent**,
fix them sequentially, one at a time.

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Prose description of a transformation keeps producing inconsistent output | Provide 2–3 concrete input/output examples | Examples pin down what words can't | Rewriting the prose longer and more emphatic |
| Building something with known edge cases and performance requirements | Write the test suite first; iterate by sharing failures | Failures are unambiguous, machine-checkable feedback | Vibes-based "looks right" review each round |
| One specific edge case is broken (nulls in a migration script) | Give a specific test case: example input + expected output | Targets the exact gap | Generic "handle edge cases better" instruction |
| Implementing in a domain you don't fully understand | Interview pattern — Claude asks questions before coding | Surfaces cache invalidation, failure modes, etc., you didn't think of | Letting Claude assume defaults and finding the gaps in prod |
| Several bugs whose fixes interact | All issues in one detailed message | Joint solution avoids fix-A-breaks-B whack-a-mole | Sequential fixes that keep colliding |
| Several independent bugs | Sequential iteration, one at a time | Isolated verification per fix | Dumping unrelated issues in one message (muddled attention, harder to verify) |

---

## 3.6 Claude Code in CI/CD

### Concepts in plain words

**`-p` / `--print` = non-interactive mode.** Without it, `claude "prompt"` in a pipeline waits for
interactive input and the job hangs forever (sample Q10). With `-p`, Claude processes the prompt,
writes the result to stdout, and exits. Distractors that **do not exist**: `CLAUDE_HEADLESS=true`,
`--batch`, stdin redirect from `/dev/null`.

**Structured output flags.** `--output-format json` plus `--json-schema` force machine-parseable
findings, so CI can post them as inline PR comments instead of regex-scraping prose:

```bash
claude -p "Review this diff for security issues" \
  --output-format json \
  --json-schema review-findings.schema.json
```

**CLAUDE.md is the CI context channel.** CI-invoked Claude Code reads the project's CLAUDE.md like
any session. Document testing standards, what makes a test valuable, fixture conventions, and review
criteria there — it directly raises test-generation quality and cuts low-value output.

**Independent instance beats self-review.** The session that generated code retains its generation
reasoning and is less likely to question its own decisions. Reviews should run in a **separate,
independent Claude instance** with no prior reasoning context. (Adjacent D4.6 fact: for big PRs —
e.g., 14 files — split into per-file passes + a cross-file integration pass to avoid attention
dilution.)

**Deduplication on re-review.** When a review re-runs after new commits, feed the **prior review
findings into context** and instruct Claude to report **only new or still-unaddressed issues** — that's
how you avoid duplicate PR comments. Same principle for test generation: provide the **existing test
files** in context so it doesn't suggest scenarios already covered.

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| CI job hangs; logs show Claude Code waiting for input | Add `-p` (`--print`): `claude -p "…"` | Documented non-interactive mode: process, print, exit | `CLAUDE_HEADLESS=true` and `--batch` are fake; `< /dev/null` is a Unix hack, not the fix |
| CI must post findings as inline PR comments | `--output-format json` + `--json-schema` | Machine-parseable, schema-enforced structure | Parsing free-text prose output with regex |
| CI-generated tests are low-value / off-convention | Document testing standards, valuable-test criteria, and available fixtures in CLAUDE.md | CLAUDE.md is the project-context mechanism for CI runs | Stuffing all standards into the per-run prompt string |
| Reviewing code Claude just generated | Independent Claude instance with no generation context | Generator retains reasoning context → won't question its own decisions | "Self-review" instructions or extended thinking in the same session |
| Re-running review after new commits duplicates old comments | Include prior findings in context; instruct: report only new or still-unaddressed issues | Explicit dedup instruction against known state | Re-reviewing from scratch every push (duplicate comment spam) |
| Test generation suggests scenarios already covered | Provide existing test files in context | Model can only avoid what it can see | Instruction "don't duplicate tests" without showing the test suite |
| Cheap overnight analysis vs blocking pre-merge check (crosses into D4.5) | Batch API for overnight jobs only; synchronous calls for anything blocking | Batches: 50% cheaper, up to 24 h, no latency SLA | Batching a blocking pre-merge gate |

---

## Memorize cold

Flashcard facts. If a D3 question hinges on an exact name, it's on this list.

**Paths & hierarchy**
- User-level memory: `~/.claude/CLAUDE.md` — personal, never shared via version control
- Project-level memory: `.claude/CLAUDE.md` **or** root `CLAUDE.md` — shared via version control
- Directory-level memory: `CLAUDE.md` inside a subdirectory — applies to that subtree
- Modular import: `@import path/to/file.md` inside CLAUDE.md
- Topic rule files: `.claude/rules/*.md` (e.g., testing.md, api-conventions.md, deployment.md)
- Diagnostic command: `/memory` — shows which memory files are loaded

**Rules frontmatter**
- Key: `paths:` — YAML frontmatter, list of glob patterns, e.g. `paths: ["terraform/**/*"]`, `paths: ["**/*.test.tsx"]`
- Behavior: rule loads **only when editing a matching file**; matches by path pattern, not directory

**Commands & skills**
- Project commands: `.claude/commands/` (in repo, version-controlled)
- User commands: `~/.claude/commands/` (personal)
- Skills: `.claude/skills/<name>/SKILL.md`; personal variants in `~/.claude/skills/` under a **different name**
- SKILL.md frontmatter keys: `context: fork` (isolated sub-agent context), `allowed-tools` (tool restriction), `argument-hint` (parameter prompt on bare invocation)
- Skills = on-demand / task-specific; CLAUDE.md = always-loaded / universal

**Plan mode & exploration**
- Plan mode triggers: large-scale changes, multiple valid approaches, architectural decisions, multi-file mods (canonical examples: microservices restructuring, 45+-file library migration)
- Direct execution triggers: simple well-scoped change (single validation check, single-file fix with clear stack trace)
- Explore subagent: isolates verbose discovery, returns summaries, preserves main context

**Iterative refinement numbers & names**
- **2–3** concrete input/output examples (D3.5; note D4.2 few-shot is **2–4** — don't cross-wire)
- Test-driven iteration: tests first (behavior + edge cases + performance), then share failures
- Interview pattern: Claude asks questions before implementing (unfamiliar domains)
- Interacting issues → single detailed message; independent issues → sequential

**CI flags & mechanics**
- Non-interactive: `-p` / `--print`
- Structured output: `--output-format json` and `--json-schema <file>`
- CI context mechanism: project CLAUDE.md (testing standards, fixtures, review criteria)
- Review isolation: independent instance > self-review (generator keeps its reasoning context)
- Dedup: prior findings in context + "report only new or still-unaddressed"
- **Fake features used as distractors:** `CLAUDE_HEADLESS` env var, `--batch` flag, `.claude/config.json` with a `commands` array

**Boundary items (owned by D1/D5, but appear in Scenario 2 alongside D3 material)**
- `--resume <session-name>` — resume a named session (D1.7)
- `fork_session` — branch independent explorations from a shared baseline (D1.7)
- `/compact` — reduce context usage in long exploration sessions (D5.4)

---

## Anti-pattern wall

Recognize on sight; each is a wrong answer somewhere.

| Anti-pattern | Why it's wrong | Correct pattern |
|---|---|---|
| Team instructions in `~/.claude/CLAUDE.md` | User-level is never version-controlled — teammates get nothing | Project-level CLAUDE.md |
| Monolithic CLAUDE.md with area headers, "Claude infers the section" | Inference-based, unreliable | `.claude/rules/` topic files; `paths:` globs for conditional load |
| Per-directory CLAUDE.md for conventions spanning scattered files | CLAUDE.md is directory-bound; can't follow file types across the tree | Glob-scoped rule (`**/*.test.tsx`) |
| Skills for always-on standards or "automatic" convention loading | Skills need invocation or Claude choosing them — not deterministic | CLAUDE.md (always-on) or path rules (automatic) |
| Editing a shared skill in-place for a personal tweak | Changes hit every teammate | Personal variant in `~/.claude/skills/` with a different name |
| Direct execution on stated-complex architectural work; "switch to plan mode if it gets hard" | Complexity is already given; late discovery = costly rework | Plan mode first, then execute the plan |
| Plan mode for a one-line, well-scoped fix | Over-engineering; exam penalizes disproportionate responses | Direct execution |
| Verbose discovery in the main conversation during multi-phase work | Context-window exhaustion mid-task | Explore subagent returning summaries |
| Longer prose instead of examples when output stays inconsistent | Words stay ambiguous; examples don't | 2–3 concrete I/O examples |
| Fixing interacting bugs one-by-one (or independent bugs all-at-once) | Whack-a-mole / muddled attention respectively | Match strategy to issue coupling |
| Interactive `claude "…"` in a pipeline | Hangs waiting for input | `claude -p "…"` |
| Regex-parsing prose CI output | Fragile; unstructured | `--output-format json` + `--json-schema` |
| Same session generates and reviews the code | Retained reasoning context → blind to own mistakes | Independent review instance |
| Re-running CI review with no memory of prior findings | Duplicate PR comments every push | Prior findings in context + report-only-new instruction |
| Test generation without existing tests in context | Duplicates covered scenarios | Provide existing test files |
| Believing in `CLAUDE_HEADLESS`, `--batch`, or a `.claude/config.json` commands array | None exist — pure distractor bait | `-p`, Batch **API** (not a CLI flag), `.claude/commands/` |
