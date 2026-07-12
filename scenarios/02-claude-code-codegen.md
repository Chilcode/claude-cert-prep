# Scenario 2 — Code Generation with Claude Code

**Scenario text (verbatim intent):** Your team uses Claude Code for code generation, refactoring, debugging, and documentation. You need to integrate it into the development workflow with custom slash commands, CLAUDE.md configurations, and judgment about plan mode vs direct execution.

**Primary domains:** D3 Claude Code Configuration & Workflows (20%) + D5 Context Management & Reliability (15%). Sample questions 4, 5, and 6 in the guide belong to this scenario — command location, plan mode, and path-scoped rules. That's the exam telling you exactly what it cares about.

You live in Claude Code all day, so your edge here is real. The risk is answering from *your* habits instead of the guide's canonical answers. This chapter is the canonical version.

---

## 1. The system at a glance

There is no API code in this scenario. The "system" is a **repository configured so that any developer who clones it gets the same Claude behavior**, plus per-developer personal layers that never leak into version control.

Three layers of configuration, from broadest to narrowest:

1. **Always-loaded context** — CLAUDE.md hierarchy (user → project → directory). Universal standards.
2. **Conditionally-loaded context** — `.claude/rules/` files with YAML frontmatter glob patterns. Loaded only when editing matching files. Saves tokens, guarantees the right conventions activate.
3. **On-demand behavior** — slash commands (`.claude/commands/`) and skills (`.claude/skills/`). Invoked explicitly, not always in context.

Plus two runtime dimensions: **execution mode** (plan mode vs direct execution, Explore subagent) and **session lifecycle** (`--resume`, `fork_session`, `/compact`, scratchpad files).

```
            SHARED (in the repo, version-controlled)          PERSONAL (per developer)
 ┌────────────────────────────────────────────────┐   ┌─────────────────────────────────┐
 │ CLAUDE.md            ← project-level, always   │   │ ~/.claude/CLAUDE.md  (user-lvl) │
 │  └─ @import docs/standards/*.md (modular)      │   │ ~/.claude/commands/  (personal) │
 │ src/api/CLAUDE.md    ← directory-level         │   │ ~/.claude/skills/    (variants, │
 │ .claude/rules/*.md   ← glob-scoped, loads on   │   │    different names)             │
 │                        matching file edits     │   │ ~/.claude.json       (personal/ │
 │ .claude/commands/    ← team slash commands     │   │    experimental MCP servers)    │
 │ .claude/skills/      ← team skills (SKILL.md)  │   └─────────────────────────────────┘
 │ .mcp.json            ← team MCP servers,       │
 │                        ${ENV_VAR} for secrets  │
 └───────────────────────┬────────────────────────┘
                         ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                        Claude Code session                             │
 │  Plan mode ──(investigate/design)──► Direct execution ──(implement)    │
 │  Explore subagent: verbose discovery isolated, summary returned        │
 │  Built-in tools: Grep(content) Glob(paths) Read/Write Edit Bash        │
 │  Context hygiene: /compact, /memory, scratchpad files                  │
 │  Sessions: --resume <name> · fork_session · fresh-start-with-summary   │
 │  CI entry point: claude -p "..." --output-format json --json-schema   │
 └────────────────────────────────────────────────────────────────────────┘
```

**The core scoping rule that decides half the questions in this scenario:** anything the *team* must share goes in the repo (`CLAUDE.md`, `.claude/commands/`, `.claude/rules/`, `.claude/skills/`, `.mcp.json`); anything *personal* goes under `~` (`~/.claude/CLAUDE.md`, `~/.claude/commands/`, `~/.claude/skills/`, `~/.claude.json`). User-level config is never distributed via version control — that's the root cause behind every "new teammate doesn't get the instructions" question.

---

## 2. Build it step by step

### Step 1 — Project-level CLAUDE.md (the always-loaded baseline)

First because everything else layers on top of it. Root `CLAUDE.md` (or `.claude/CLAUDE.md`) — committed, so every clone gets it.

```markdown
# ProjectX — Claude Context

## Universal standards (apply everywhere)
- TypeScript strict mode; no `any` without a justification comment
- All new endpoints require an integration test
- Conventional commits

## Testing (context for test generation)
- Framework: vitest. Fixtures live in tests/fixtures/ — reuse, don't recreate.
- A valuable test asserts behavior, not implementation details.

## Package-specific standards
@import docs/standards/api.md
@import docs/standards/frontend.md
```

Rules the exam pulls from this step:

- **Hierarchy:** user-level (`~/.claude/CLAUDE.md`) → project-level (`.claude/CLAUDE.md` or root `CLAUDE.md`) → directory-level (subdirectory `CLAUDE.md` files).
- **User-level is personal only** — never shared with teammates via version control.
- **`@import`** keeps CLAUDE.md modular: each package's CLAUDE.md imports only the standards files relevant to it (maintainers pick, based on domain knowledge).
- **`/memory`** shows which memory files are loaded. It's the diagnostic for "Claude behaves differently across sessions/machines."
- CLAUDE.md is for **instructions and context** — it is *not* where slash commands are defined (sample Q4 distractor).

### Step 2 — `.claude/rules/` with glob-scoped YAML frontmatter

Second, because a monolithic CLAUDE.md degrades: irrelevant conventions burn tokens and Claude has to *infer* which section applies. Split conventions into topic files that load **only when editing matching files**:

```
.claude/rules/
├── testing.md
├── api-conventions.md
└── deployment.md
```

```markdown
---
paths: ["**/*.test.tsx", "**/*.test.ts"]
---
# Testing conventions
- One describe block per unit under test
- Mock at module boundaries only; never mock internal functions
```

```markdown
---
paths: ["src/api/**/*"]
---
# API handler conventions
- async/await only; wrap handlers in withErrorBoundary()
```

The decisive comparison (sample Q6):

| Mechanism | Loads when | Handles files spread across dirs? | Deterministic? |
|---|---|---|---|
| `.claude/rules/` + `paths:` globs | Editing a matching file | **Yes** (`**/*.test.tsx` matches anywhere) | Yes |
| Directory-level CLAUDE.md | Working in that directory | No — directory-bound | Yes, but per-dir only |
| Root CLAUDE.md with headers | Always | Relies on Claude inferring the right section | No |
| Skills | On invocation | N/A — manual/model-chosen, not automatic | No |

**Rule of thumb:** conventions keyed to *file type scattered across the tree* → glob rules. Conventions keyed to *one directory* → directory CLAUDE.md is acceptable, but glob rules still win on maintainability.

### Step 3 — Team slash commands in `.claude/commands/`

A slash command is a markdown prompt file. Filename = command name. Committed → every developer has `/review` after clone or pull.

```
.claude/commands/
└── review.md        →  invoked as /review
```

```markdown
Run the team code review checklist on the current changes:
1. Correctness: logic errors, unhandled edge cases, off-by-one
2. Security: injection, secrets in code, unvalidated input
3. Report only bugs and security issues — skip style nits.
   Format each finding: file:line — issue — severity — suggested fix
```

Sample Q4 canon: team command → `.claude/commands/` in the repo. Distractors: `~/.claude/commands/` (personal, not shared), CLAUDE.md (context, not commands), `.claude/config.json` with a commands array (**does not exist**).

### Step 4 — Skills in `.claude/skills/` with frontmatter controls

Skills are for **on-demand, task-specific workflows** (vs CLAUDE.md's always-loaded universal standards). Each is a directory with a `SKILL.md`:

```
.claude/skills/
└── analyze-codebase/
    └── SKILL.md
```

```markdown
---
name: analyze-codebase
description: Deep structural analysis of a module — dependencies, entry points, test coverage map
context: fork
allowed-tools: Read, Grep, Glob
argument-hint: <module-or-directory>
---
Map the structure of $ARGUMENTS: entry points, imports/exports,
dependency direction, existing test coverage. Return a concise summary.
```

The three frontmatter options the exam names, and what each buys you:

| Frontmatter | What it does | When the exam wants it |
|---|---|---|
| `context: fork` | Runs the skill in an isolated sub-agent context | Skill produces verbose output (codebase analysis) or exploratory context (brainstorming) that would pollute the main conversation |
| `allowed-tools` | Restricts tool access during skill execution | Prevent destructive actions — e.g., limit a doc-generation skill to file write operations only |
| `argument-hint` | Prompts the developer for required parameters when invoked without arguments | Skill needs input (a module name, a ticket ID) and devs keep invoking it bare |

**Personal customization:** don't edit the team skill. Create a variant in `~/.claude/skills/` **with a different name** so teammates are unaffected.

### Step 5 — MCP servers: `.mcp.json` (team) vs `~/.claude.json` (personal)

Team-shared backend integrations go in project-scoped `.mcp.json`, committed. Secrets stay out of the repo via **environment variable expansion**:

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "${GITHUB_TOKEN}" }
    }
  }
}
```

Personal/experimental servers go in user-scoped `~/.claude.json`. Both are live simultaneously — **tools from all configured MCP servers are discovered at connection time and available at once**.

Two more MCP judgments that leak into this scenario:

- If Claude keeps using built-in Grep instead of a more capable MCP search tool, the fix is **enhancing the MCP tool's description** (capabilities + outputs in detail), not disabling built-ins.
- Standard integration (e.g., Jira)? Use an **existing community MCP server**. Custom servers are for team-specific workflows only.

### Step 6 — Workflow judgment: modes, sessions, context hygiene

No files to create — this is the runtime discipline the exam tests hardest.

**Plan mode vs direct execution.** Plan mode = complex tasks: large-scale changes, multiple valid approaches, architectural decisions, multi-file modifications (monolith→microservices, a library migration touching 45+ files, choosing between integration approaches). Direct execution = simple, well-scoped changes (single validation check, single-file bug fix with a clear stack trace). The blessed combo: **plan mode for investigation and design, then direct execution for implementation**. "Start direct, switch to plan if it gets complex" is a named distractor — if the complexity is stated up front, plan first.

**Explore subagent.** During multi-phase tasks, verbose discovery output exhausts the main context. The Explore subagent isolates that discovery and returns a summary, preserving the main conversation.

**Sessions.**
- `--resume <session-name>` — continue a named investigation across work sessions.
- `fork_session` — branch independent explorations from a **shared analysis baseline** (e.g., compare two refactoring strategies without re-analyzing the codebase twice).
- Resuming after code changed? **Tell the agent which files changed** for targeted re-analysis — don't force full re-exploration.
- Prior tool results mostly stale? **Start a new session with a structured summary injected.** Resuming over stale results is less reliable than a fresh start with facts.

**Context hygiene for long codebase work (D5.4).**
- Symptom of degradation: inconsistent answers, citing "typical patterns" instead of the specific classes it discovered earlier.
- Countermeasures: **scratchpad files** recording key findings (re-read for later questions); **subagent delegation** for scoped questions ("find all test files", "trace the refund flow") while the main agent keeps high-level coordination; **`/compact`** when context fills with verbose discovery output; **summarize each phase before spawning the next phase's subagents** and inject the summary.
- Crash recovery: each agent **exports structured state to a known location (manifest)**; on resume the coordinator loads the manifest and injects it into prompts.
- Trim verbose tool outputs to relevant fields before they accumulate; put key-findings summaries at the **beginning** of aggregated input with explicit section headers (lost-in-the-middle mitigation).

**Iterative refinement (D3.5) — how you steer generation quality.**

| Problem | Technique |
|---|---|
| Prose spec interpreted inconsistently | 2–3 concrete input/output examples showing the transformation |
| Edge case failures (e.g., nulls in a migration script) | Specific test cases: example input + expected output |
| Unfamiliar domain, unknown design considerations | Interview pattern — have Claude ask questions first (cache invalidation, failure modes) |
| Want progressive, verifiable improvement | Write the test suite first (behavior + edge cases + performance), iterate by sharing failures |
| Multiple issues to fix | Interacting fixes → one detailed message. Independent fixes → sequential iteration |

**CI entry point (bleeds in from D3.6).** Automated invocation is `claude -p "..."` (`--print` = non-interactive; processes prompt, prints, exits). Structured findings: `--output-format json` with `--json-schema`. CLAUDE.md is how CI-invoked Claude gets project context (testing standards, fixtures, review criteria). And: the session that *generated* code is worse at reviewing it than an **independent instance** — session context isolation.

---

## 3. The decision points this scenario tests

Each row = one exam-question shape. Situation → correct move → why → the trap.

### Configuration scoping (TS 3.1, 3.2, 2.4)

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Team checklist command must exist for everyone on clone/pull | `.claude/commands/` in the repo | Version-controlled, auto-available | `~/.claude/commands/` (personal); CLAUDE.md (context, not commands); `.claude/config.json` commands array (**fake**) |
| New teammate's Claude ignores team standards | Move instructions from `~/.claude/CLAUDE.md` to project CLAUDE.md | User-level config isn't shared via version control | "Have them copy your user config" — patches one person, not the mechanism |
| CLAUDE.md grown huge, conventions bleed across areas | Split into `.claude/rules/` topic files (testing.md, api-conventions.md, deployment.md) or `@import` per package | Modularity + scoped loading beats one monolith | One giant file "with clear headers" — relies on inference |
| Inconsistent behavior across sessions/machines | `/memory` to verify which memory files load | Diagnose before rewriting anything | Rewriting prompts/CLAUDE.md without checking what's actually loaded |
| Team MCP server needing a token | Project `.mcp.json` with `${GITHUB_TOKEN}` expansion | Shared config, no committed secrets | Hardcoding token in `.mcp.json`; per-user `~/.claude.json` for a *team* tool |
| Your own experimental MCP server | `~/.claude.json` | Personal scope, doesn't touch teammates | Adding experiments to the shared `.mcp.json` |
| Want personal tweak of a shared skill | `~/.claude/skills/` variant **with a different name** | Doesn't affect teammates | Editing the committed skill in place |

### Conditional conventions (TS 3.3)

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Test files scattered next to sources everywhere; same conventions for all | `.claude/rules/` file, `paths: ["**/*.test.tsx"]` | Glob matches by file type regardless of directory; loads deterministically on edit | Per-directory CLAUDE.md (directory-bound, can't cover scattered files); root headers (inference); skills (manual invocation ≠ automatic) |
| Conventions differ by code area (API vs components vs models) | One rules file per area with area-scoped globs (`src/api/**/*`) | Only relevant conventions enter context — less noise, fewer tokens | Loading all conventions always "so nothing is missed" |

### Plan mode vs direct execution (TS 3.4)

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Monolith → microservices; dozens of files; service-boundary decisions | Plan mode first: explore, understand dependencies, design | Architectural decisions + multiple valid approaches = plan-mode signature; prevents costly rework | Direct + "comprehensive upfront instructions" (assumes you already know the structure); incremental direct ("implementation will reveal boundaries") |
| Single-file bug fix with a clear stack trace; add one date-validation conditional | Direct execution | Simple, well-scoped, one obvious approach — planning is overhead | Plan mode reflexively for everything |
| Complexity stated in the task itself | Plan mode from the start | Complexity is known, not emergent | "Start direct, switch to plan if I hit complexity" |
| Multi-phase task; discovery output flooding context | Explore subagent for discovery; summaries return to main | Isolates verbose output, preserves main context | Doing all exploration in the main conversation |
| Library migration | Plan mode to investigate → direct execution to implement the plan | The blessed two-phase pattern | Treating the modes as mutually exclusive |

### Sessions and long-running context (TS 1.7, 5.1, 5.4)

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Continue yesterday's named investigation | `--resume <session-name>` | Prior context is mostly valid — reuse it | Fresh session and re-explaining everything |
| Compare two refactoring/testing strategies from one codebase analysis | `fork_session` per branch | Independent branches from a shared baseline; no duplicate analysis | Sequential trials in one session (approach A's context contaminates B) |
| Resuming after files changed | Tell the agent *which* files changed → targeted re-analysis | Cheaper than full re-exploration, avoids stale conclusions | Resuming silently and trusting stale tool results |
| Most prior tool results now stale | New session + inject a structured summary | More reliable than resuming over stale results | `--resume` because "the context is already there" |
| Hours-long exploration; answers drift to "typical patterns" | Scratchpad files for key findings + subagents for scoped questions + `/compact` | Persists facts across context pressure; isolates verbosity | Larger context window / new model (attention quality, not capacity, is the issue) |
| Long multi-phase workflow might crash | Each agent exports state to a known location; coordinator loads the manifest on resume | Structured state persistence = recoverability | Relying on conversation history surviving the crash |

### Steering generation quality (TS 3.5)

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Claude interprets your prose transformation spec inconsistently | 2–3 concrete input/output examples | Examples pin down what prose can't | Longer, more detailed prose |
| Migration script breaks on nulls | Give specific failing test cases: input + expected output | Concrete cases fix edge-case handling | "Handle edge cases better" |
| Implementing in a domain where you don't know what you don't know | Interview pattern — Claude asks questions before implementing | Surfaces considerations (cache invalidation, failure modes) you didn't anticipate | Just implementing from your incomplete spec |
| Several bugs whose fixes interact | One detailed message with all issues | Sequential fixing of interacting issues thrashes | One-at-a-time when fixes conflict (fine only for independent issues) |
| Want steady, verifiable improvement | Tests first, then iterate on failures | Failures are unambiguous feedback | Vibes-based "looks better now" |

### Built-in tool selection (TS 2.5)

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Find every caller of a function / an error string | **Grep** — content search | Grep searches file *contents* for patterns | Glob (paths only), reading files one by one |
| Find all files matching `**/*.test.tsx` | **Glob** — path pattern match | Glob matches file *names/paths* | Grep for filenames |
| Edit fails: anchor text not unique | **Read + Write** the full file | Documented fallback when unique matching fails | Retrying Edit with the same anchor; regex heroics in Bash |
| Understand an unfamiliar codebase | Incremental: Grep for entry points → Read to follow imports and trace flows | Builds understanding without flooding context | Reading every file upfront |
| Trace usage through wrapper modules | Enumerate exported names first, then Grep each name across the codebase | Wrappers hide direct call sites | Grepping only the original function name |

---

## 4. Failure-modes drill

Guide-style: production symptom → root cause → the fix (and the fake answers to eliminate).

**1. CI job hangs forever on `claude "Analyze this PR"`.**
Root cause: Claude Code launched interactively; it's waiting for input.
Fix: `claude -p "Analyze this PR"` — `-p`/`--print` is the documented non-interactive mode: process, print to stdout, exit. Eliminate on sight: `CLAUDE_HEADLESS=true` and `--batch` **do not exist**; `< /dev/null` is a Unix workaround that doesn't address Claude Code's syntax.

**2. You onboard a new developer; Claude ignores every team convention for them, works fine for you.**
Root cause: the conventions live in *your* `~/.claude/CLAUDE.md` — user-level config is never shared via version control.
Fix: move them to project-level CLAUDE.md (root or `.claude/CLAUDE.md`), commit, then have both of you run `/memory` to confirm what's loaded.

**3. Claude applies testing conventions in `src/components/` but not in `src/utils/`, despite tests in both.**
Root cause: conventions live in a directory-level CLAUDE.md that only covers one subtree — directory files are directory-bound, and your test files are spread everywhere.
Fix: `.claude/rules/testing.md` with `paths: ["**/*.test.tsx", "**/*.test.ts"]` — glob scoping applies by file type regardless of location, and loads only when editing matching files.

**4. `/review` works on your machine; teammates get "unknown command."**
Root cause: the command file is in `~/.claude/commands/` (personal scope).
Fix: move `review.md` into the repo's `.claude/commands/` and commit. Not CLAUDE.md (context, not commands), not a config.json commands array (fake).

**5. Three hours into a legacy-codebase session, Claude describes "typical repository patterns" instead of the actual classes it read earlier, and contradicts its own earlier answers.**
Root cause: context degradation in an extended session — earlier findings have been squeezed out.
Fix: have the agent maintain scratchpad files of key findings and reference them; delegate scoped questions ("find all test files," "trace the refund flow") to subagents so the main context stays high-level; run `/compact` when discovery output piles up. Wrong answer: "use a bigger context window" — attention quality, not capacity, is the failure.

**6. You `--resume` last week's refactoring session; Claude proposes edits to functions that were deleted in Friday's merge.**
Root cause: resumed session is reasoning over stale tool results.
Fix: if changes are contained, tell the agent exactly which files changed and have it re-analyze those; if the analysis is broadly stale, start a **new** session and inject a structured summary of current state. Fresh + summary beats resuming stale context.

**7. Edit keeps failing while updating one entry in a config file full of near-identical blocks.**
Root cause: Edit needs unique anchor text; the file has repeated content, so no match is unique.
Fix: Read the full file, then Write the corrected version — the documented fallback for non-unique matches.

**8. Your codebase-analysis skill works, but after each run the main conversation is stuffed with raw dependency dumps and answers get worse.**
Root cause: the skill runs in the main conversation context; its verbose output pollutes the session.
Fix: add `context: fork` to the SKILL.md frontmatter so it runs in an isolated sub-agent context and returns only the result. While you're in the frontmatter: `allowed-tools` to fence off destructive tools, `argument-hint` so devs invoking it bare get prompted for the module name.

---

## Cram card

- Shared → repo (`CLAUDE.md`, `.claude/commands|rules|skills/`, `.mcp.json`). Personal → home (`~/.claude/*`, `~/.claude.json`). User-level is invisible to teammates.
- Conventions for scattered file types → `.claude/rules/` + `paths:` globs, never per-directory CLAUDE.md.
- Plan mode = architectural / multi-file / multiple valid approaches. Direct = single-file, well-scoped. Plan-then-execute is the pattern; "escalate to plan mode later" is the distractor.
- Skills = on-demand workflows; CLAUDE.md = always-loaded standards. `context: fork` isolates verbose skills.
- CI = `-p` + `--output-format json` + `--json-schema`. `--batch` and `CLAUDE_HEADLESS` are fake.
- Stale session → fresh session + structured summary. Valid session → `--resume`; divergent experiments → `fork_session`.
- Long exploration → scratchpads, subagents, `/compact` — not a bigger context window.
