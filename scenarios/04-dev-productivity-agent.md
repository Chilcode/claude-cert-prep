# Scenario 4 — Developer Productivity with Claude

> **Guide definition:** You are building developer productivity tools using the Claude Agent SDK. The agent helps engineers explore unfamiliar codebases, understand legacy systems, generate boilerplate code, and automate repetitive tasks. It uses the built-in tools (Read, Write, Bash, Grep, Glob) and integrates with MCP servers.
>
> **Primary domains:** D2 Tool Design & MCP Integration (18%), D3 Claude Code Configuration & Workflows (20%), D1 Agentic Architecture & Orchestration (27%).

This is the scenario closest to your daily life — it's basically "build Claude Code yourself, then configure Claude Code for a team." That's an advantage and a trap: the exam tests the *mechanics underneath* the CLI you already use. You need to know **why** Grep-then-Read works, **where** each config file lives, and **what actually exists** (the distractors are fake flags and fake config files).

---

## 1. The system at a glance

Two halves, one system:

**Half A — the Agent SDK program.** A Python process running an agentic loop against the Claude API. Claude gets built-in tools (Read, Write, Edit, Bash, Grep, Glob) plus MCP tools from connected servers. The loop sends a request, inspects `stop_reason`, executes whatever tool Claude asked for, appends the result to conversation history, and repeats until `stop_reason == "end_turn"`. For big jobs (map a legacy codebase, add tests everywhere) a coordinator agent spawns subagents via the **Task tool**, each with its own isolated context and restricted tool set.

**Half B — the Claude Code team configuration.** The repo carries the shared brain: `CLAUDE.md` (universal standards), `.claude/rules/` (path-scoped conventions), `.claude/commands/` (shared slash commands), `.claude/skills/` (on-demand workflows), `.mcp.json` (shared MCP servers with env-var credentials). Personal stuff lives in the home directory (`~/.claude/CLAUDE.md`, `~/.claude/commands/`, `~/.claude.json`).

```
 ENGINEER
    │ "explain this legacy billing module"
    ▼
┌─────────────────────────────────────────────────┐
│ COORDINATOR AGENT (agentic loop)                │
│   while stop_reason == "tool_use": run tools    │
│   allowedTools: [Task, Read, Grep, Glob, ...]   │
│   PostToolUse hooks: normalize / enforce        │
└──────┬──────────────┬───────────────┬───────────┘
       │ Task         │ Task          │ Task   (parallel = multiple
       ▼              ▼               ▼         Task calls in ONE response)
 ┌──────────┐   ┌──────────┐   ┌──────────────┐
 │ Explore  │   │ Test-map │   │ Boilerplate  │   subagents: ISOLATED
 │ subagent │   │ subagent │   │ subagent     │   context — coordinator
 │ Grep,Read│   │ Grep,Glob│   │ Read,Write   │   must pass findings
 └────┬─────┘   └────┬─────┘   └──────┬───────┘   explicitly in prompt
      ▼              ▼                ▼
 ┌─────────────────────────────────────────────────┐
 │ TOOLS                                           │
 │  built-in: Read Write Edit Bash Grep Glob       │
 │  MCP servers (.mcp.json): jira, github, docs    │
 │  MCP resources: schema/issue catalogs           │
 └─────────────────────────────────────────────────┘
      ▲
 scratchpad files + state manifests (crash recovery,
 counteracting context degradation in long sessions)
```

Data flow to memorize: **user request → coordinator decomposes → subagents explore with scoped tools → structured summaries flow back through the coordinator → coordinator synthesizes**. Subagents never talk to each other directly (hub-and-spoke), and they inherit *nothing* automatically — context passing is explicit, in the prompt.

---

## 2. Build it step by step

### Step 1 — The agentic loop (the engine everything sits on)

First thing you build, because nothing else runs without it. The loop's contract: **continue while `stop_reason == "tool_use"`, terminate when `stop_reason == "end_turn"`.** Nothing else decides termination.

```python
import anthropic

client = anthropic.Anthropic()

tools = [...]           # defined in Step 2
messages = [{"role": "user", "content": "Trace how invoices get created in this repo."}]

while True:
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        system="You are a codebase exploration agent. Build understanding "
               "incrementally: Grep for entry points first, then Read to follow imports.",
        tools=tools,
        messages=messages,
    )

    # Assistant turn (may contain text + tool_use blocks) goes into history
    messages.append({"role": "assistant", "content": response.content})

    if response.stop_reason == "tool_use":
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = execute_tool(block.name, block.input)   # your dispatch
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
        # Tool results go back as a USER message → next iteration reasons over them
        messages.append({"role": "user", "content": tool_results})
        continue

    if response.stop_reason == "end_turn":
        break            # Claude decided it's done. THIS is the stop condition.
```

Burn in the three anti-patterns the guide names explicitly — each is a distractor on the exam:

1. **Parsing natural-language signals** ("if the reply contains 'done', stop") — never.
2. **An arbitrary iteration cap as the *primary* stopping mechanism** — a safety ceiling is fine; it must not be how the loop normally ends.
3. **Checking for assistant text content as a completion indicator** — Claude emits text alongside tool calls all the time.

Also core: tool results are **appended to conversation history** so the model can reason about the next action. That append-and-resend is *the* mechanism; drop it and the agent goes amnesiac between iterations.

### Step 2 — Tool definitions with descriptions that carry their weight

Tool descriptions are **the primary mechanism LLMs use for tool selection**. Minimal descriptions → misrouting between similar tools. A good description covers: purpose, input formats, example queries, edge cases, and **boundaries — when to use it vs. its neighbors**.

```python
tools = [
    {
        "name": "search_code",
        "description": (
            "Search FILE CONTENTS for a regex pattern (function names, error "
            "messages, import statements). Returns matching lines with file:line. "
            "Input: a regex plus optional path filter. Use this to find WHERE "
            "something is referenced in code. Do NOT use this to find files by "
            "name — use find_files for filename/extension patterns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex, e.g. 'def create_invoice'"},
                "path":    {"type": "string", "description": "Optional dir to scope the search"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "find_files",
        "description": (
            "Find FILE PATHS matching a glob pattern (e.g. '**/*.test.tsx', "
            "'src/billing/**/*.py'). Returns paths only, no contents. Use this "
            "to locate files by naming convention. Do NOT use this to search "
            "inside files — use search_code for content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"glob": {"type": "string"}},
            "required": ["glob"],
        },
    },
]
```

If two tools keep getting confused (`analyze_content` vs `analyze_document`), the guide's fixes, in order: **expand/differentiate the descriptions first** (low effort, high leverage), **rename to eliminate overlap** (`analyze_content` → `extract_web_results`), or **split a generic tool into purpose-specific tools** with defined I/O contracts. Also **review the system prompt for keyword-sensitive instructions** that can override well-written descriptions. Few-shot routing examples and pre-parse routing layers are the plausible-but-wrong answers for a *first* step.

Structured errors, from day one — the agent can't recover from `"Operation failed"`:

```python
# What a well-designed MCP tool returns on failure (isError flag pattern)
{
    "isError": True,
    "errorCategory": "transient",        # transient | validation | permission | business
    "isRetryable": True,
    "message": "Repo index service timed out after 10s; safe to retry.",
}
```

And keep this distinction sacred: a query that ran fine and matched nothing is a **valid empty result** (success, no matches), not an error. Returning empties as failures — or failures as empties — poisons the agent's retry decisions.

### Step 3 — Wire MCP servers and expose resources

Standard integration (GitHub, Jira)? **Use an existing community MCP server.** Custom servers are for team-specific workflows only. Two scopes:

`.mcp.json` — project scope, committed, shared with the whole team, **env-var expansion so no secrets hit git**:

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

`~/.claude.json` — user scope, for your personal/experimental servers. Both scopes' tools are **discovered at connection time and available simultaneously**.

Two D2 facts that show up as questions:

- **The agent ignores your fancy MCP code-intel tool and keeps using built-in Grep** → the MCP tool's description is too thin. Enhance it to explain capabilities and outputs in detail; the model picks tools by description.
- **The agent burns turns on exploratory tool calls just to learn what data exists** → expose a content catalog (issue summaries, documentation hierarchy, database schema) as an **MCP resource**. Resources are for *content the agent can consult*; tools are for *actions*.

### Step 4 — Subagents via the Task tool (Agent SDK)

When exploration output would drown the coordinator's context, delegate. *(Sketch code — exact SDK surface varies; the concepts and names below are what the exam tests.)*

```python
# SKETCH — Agent SDK concepts, exam terminology
agents = {
    "code-explorer": AgentDefinition(
        description="Investigates specific codebase questions: find files, "
                    "trace call chains, map module dependencies. Returns a "
                    "structured summary, not raw file dumps.",
        prompt="Explore incrementally: Grep entry points, Read to follow imports. "
               "Output findings as structured facts with file:line references.",
        tools=["Read", "Grep", "Glob"],          # scoped: read-only explorer
    ),
    "boilerplate-writer": AgentDefinition(
        description="Generates boilerplate from an approved spec and existing patterns.",
        prompt="Follow the conventions in the examples provided in your prompt.",
        tools=["Read", "Write", "Glob"],          # no Bash: can't run anything
    ),
}

coordinator = AgentDefinition(
    prompt="Decompose the engineer's request, delegate investigation to "
           "subagents, synthesize their structured findings.",
    allowedTools=["Task", "Read", "Grep", "Glob"],   # ← "Task" REQUIRED to spawn
)
```

The four rules the exam hammers:

1. **`allowedTools` must include `"Task"`** or the coordinator physically cannot spawn subagents.
2. **Subagents do not inherit the coordinator's conversation history** and don't share memory between invocations. Everything they need — prior findings, file lists, constraints — goes **explicitly in the prompt** you spawn them with.
3. **Parallel subagents = multiple Task tool calls in a single coordinator response**, not one per turn.
4. Coordinator prompts should specify **goals and quality criteria, not step-by-step procedures** — that's what lets subagents adapt.

Keep each agent's tool set at **4–5 role-relevant tools**; handing an agent 18 tools measurably degrades selection reliability, and agents misuse tools outside their specialization.

### Step 5 — Hooks for deterministic guarantees

Prompt instructions are probabilistic; when a rule must *always* hold, use a hook. Two patterns:

```python
# SKETCH — PostToolUse hook: normalize before the model sees the result.
# Three MCP servers return dates as Unix epoch, ISO 8601, and "MM/DD/YYYY"?
# Don't prompt around it — normalize deterministically.
def post_tool_use(tool_name, tool_result):
    if tool_name in ("jira_get_issue", "github_get_pr"):
        tool_result = normalize_timestamps_to_iso8601(tool_result)
        tool_result = normalize_status_codes(tool_result)
    return tool_result

# SKETCH — tool-call interception hook: block policy violations pre-execution.
def pre_tool_use(tool_name, tool_input):
    if tool_name == "Bash" and is_destructive(tool_input["command"]):
        return block(reason="Destructive commands require human approval",
                     redirect="escalate_to_human")
    return allow()
```

Decision rule: **hooks for guaranteed compliance, prompts for judgment.** "The system prompt says never do X" still has a non-zero failure rate; the exam's correct answer to any "must never happen" requirement is programmatic enforcement.

### Step 6 — Built-in tool discipline (the exploration playbook)

The selection table you must know cold:

| Need | Tool | Note |
|---|---|---|
| Find text *inside* files (callers, error strings, imports) | **Grep** | content search |
| Find files by *name/extension* pattern (`**/*.test.tsx`) | **Glob** | path matching, no contents |
| Load a whole file | **Read** | — |
| Create/replace a whole file | **Write** | — |
| Targeted in-place change | **Edit** | needs **unique** anchor text |
| Edit keeps failing (anchor text non-unique) | **Read + Write fallback** | the guide's named recovery |
| Run commands, tests, builds | **Bash** | — |

The exploration strategy (this exact phrasing wins exam points): **build understanding incrementally — Grep to find entry points, then Read to follow imports and trace flows. Never read all files upfront.** For tracing usage across wrapper/re-export modules: **first identify all exported names, then Grep for each name across the codebase.**

### Step 7 — Session state: `--resume`, `fork_session`, fresh-with-summary

Long-running codebase work spans days. Three moves:

| Situation | Move |
|---|---|
| Continue yesterday's named investigation; prior context still valid | `--resume <session-name>` |
| Files changed since the session analyzed them | Resume **and tell the agent exactly which files changed** for targeted re-analysis — don't force full re-exploration |
| Prior tool results are substantially stale | **Start a new session with a structured summary injected** — more reliable than resuming on rotten context |
| Compare two approaches (e.g., two testing strategies) from one shared analysis | **`fork_session`** — independent branches from the shared baseline, explore divergently |

For crash recovery in multi-agent runs: each agent **exports state to a known location (manifest)**; on resume the coordinator loads the manifest and injects it into agent prompts. And for marathon sessions, counteract context degradation with **scratchpad files** (persist key findings, reference them later), **subagent delegation** (verbose discovery stays out of the main context), phase summaries before spawning the next phase, and **`/compact`** when discovery output fills the window.

### Step 8 — Team Claude Code configuration (Half B)

The repo layout that answers half of D3:

```
repo/
├── CLAUDE.md                        # project scope: universal standards, all teammates
│                                    #   @import docs/standards/api.md   ← modular imports
├── .claude/
│   ├── rules/
│   │   ├── testing.md               # path-scoped: loads ONLY when editing matching files
│   │   ├── terraform.md
│   │   └── api-conventions.md
│   ├── commands/
│   │   └── onboard.md               # /onboard — shared via version control
│   ├── skills/
│   │   └── explore-codebase/
│   │       └── SKILL.md             # frontmatter: context: fork, allowed-tools, argument-hint
│   └── ...
├── .mcp.json                        # shared MCP servers, ${ENV_VAR} expansion
└── src/legacy/CLAUDE.md             # directory-level: legacy-module-specific context

~/.claude/CLAUDE.md                  # user scope: YOUR prefs only — NOT shared via git
~/.claude/commands/                  # personal slash commands
~/.claude.json                       # personal/experimental MCP servers
```

Path-scoped rule — the answer whenever conventions apply to files *spread across* directories:

```markdown
---
paths: ["**/*.test.tsx", "**/*.test.ts"]
---
# Testing conventions
- Use React Testing Library; never enzyme.
- One behavior per test; name tests "does X when Y".
```

Loads only when editing matching files → less irrelevant context, fewer tokens. Beats per-directory CLAUDE.md files exactly because glob patterns don't care where the file sits.

Skill with the three frontmatter options the exam names:

```markdown
---
context: fork              # runs in an isolated sub-agent context —
                           #   verbose analysis output can't pollute the main session
allowed-tools: Read, Grep, Glob      # restrict what the skill may touch
argument-hint: <module-path>         # prompts the dev if invoked without args
---
# Explore Codebase
Map the module at $ARGUMENTS: entry points, dependencies, test coverage.
Return a structured summary only.
```

**Skills vs CLAUDE.md:** skills = on-demand invocation for task-specific workflows; CLAUDE.md = always-loaded universal standards. Want a personal variant of a team skill? Create it in `~/.claude/skills/` **under a different name** so teammates are unaffected.

Debugging config: **`/memory`** shows which memory files are loaded — first move when behavior differs across machines or sessions.

### Step 9 — Plan mode vs direct execution

| Task | Mode |
|---|---|
| Monolith→microservices restructuring, library migration touching 45+ files, multiple valid approaches, architectural decisions | **Plan mode** — explore and design before committing; prevents costly rework |
| Single-file bug fix with a clear stack trace, adding one validation conditional | **Direct execution** |
| Verbose discovery phase inside a multi-phase task | **Explore subagent** — isolates discovery output, returns summaries, preserves main context |
| Big migration | **Combine:** plan mode to investigate → direct execution to implement the plan |

The distractor pattern: "start direct, switch to plan if it gets complex." Wrong when the complexity is *already stated in the requirements* — you don't wait for it to emerge.

### Step 10 — Iterative refinement for boilerplate quality

When generated output misses the mark:

- Prose descriptions interpreted inconsistently → give **2–3 concrete input/output examples**. Most effective single move.
- Quality drift → **test-driven iteration**: write the test suite first, iterate by sharing test failures.
- Unfamiliar domain, unknown unknowns → **interview pattern**: have Claude ask questions first (surfaces cache invalidation, failure modes, things you didn't anticipate).
- Multiple issues to fix → **interacting issues: one detailed message. Independent issues: sequential.**

---

## 3. The decision points this scenario tests

### D2 — Tool Design & MCP Integration

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Agent confuses two similar tools with minimal descriptions | Expand descriptions: input formats, example queries, edge cases, when-to-use-vs-alternatives | Descriptions are the LLM's primary tool-selection signal; fixes root cause cheaply | Few-shot routing examples, pre-parse routing layer, tool consolidation — all heavier than a "first step" warrants |
| One generic tool used for wildly different jobs | Split into purpose-specific tools with defined I/O contracts | Each tool gets a clean selection signal | Making the generic description longer |
| Agent has 18 tools, selection is flaky | Restrict each agent to 4–5 role-relevant tools | Fewer options = higher selection reliability; out-of-specialty tools get misused | "More capable model" or more prompt instructions |
| Subagent needs one frequent cross-role operation (85% simple case) | Scoped narrow tool (e.g., `verify_fact`) for the common case; complex cases still route through coordinator | Least privilege + preserved coordination | Granting the full foreign tool set (over-provisioning) or batching verifications (blocking dependencies) |
| Must guarantee a tool call happens / a specific tool runs first | `tool_choice: "any"` (must call *some* tool) / forced `{"type": "tool", "name": "..."}` | Deterministic, not prompt-hoped | `"auto"` — model may just answer in text |
| Tool failure handling | `isError` + `errorCategory` (transient/validation/permission/business) + `isRetryable` + readable message | Agent can decide: retry, rephrase, escalate | Generic "Operation failed" — blocks recovery decisions |
| Query succeeded, zero matches | Return as **valid empty result** | Distinct from access failure; prevents wasted retries | Marking empties as errors, or errors as empty successes |
| Team-shared vs personal MCP server | `.mcp.json` (project, committed) vs `~/.claude.json` (user) | Version control distributes team config | Putting shared servers in user config; hardcoding tokens instead of `${VAR}` |
| Agent won't use the capable MCP tool, sticks to built-in Grep | Enrich the MCP tool's description (capabilities + outputs) | Selection follows description quality | Removing built-in tools; forcing via system prompt |
| Agent wastes calls discovering what data exists | Expose a catalog as an **MCP resource** | Resources = consultable content; tools = actions | Building a `list_everything` tool |
| Need a standard Jira/GitHub integration | Existing community MCP server | Custom is for team-specific workflows only | Building custom for standard integrations |

### D3 — Claude Code Configuration & Workflows

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Standard/command must reach every teammate | Project scope: root `CLAUDE.md` / `.claude/commands/` | Version control distributes it | `~/.claude/...` — user-level, never shared via git |
| New teammate doesn't get instructions others get | Check config hierarchy — it's sitting in someone's user-level file; verify with `/memory` | User scope applies to that user only | Blaming the model or re-prompting |
| Conventions for file *types* scattered across directories (tests everywhere) | `.claude/rules/` file with YAML frontmatter `paths: ["**/*.test.tsx"]` | Glob matching is location-independent and deterministic | Per-directory CLAUDE.md (directory-bound); one big CLAUDE.md (relies on inference); skills (need invocation) |
| CLAUDE.md turning monolithic | Split into `.claude/rules/` topic files; `@import` shared standards per package | Modular, loads what's relevant | One giant file with headers |
| Skill produces verbose/exploratory output | `context: fork` in SKILL.md frontmatter | Isolated sub-agent context; no pollution of main session | Running in main context and `/compact`-ing after |
| Skill shouldn't be able to do damage | `allowed-tools` frontmatter restriction | Deterministic tool scoping during skill execution | Prompt-level "please don't" |
| Devs invoke skill without required params | `argument-hint` frontmatter | Prompts for the parameter | Failing silently |
| Architectural, multi-file, multiple-valid-approaches task | Plan mode first | Safe exploration before committing; prevents rework | "Start direct, escalate to plan if needed" when complexity is already known |
| Simple scoped fix | Direct execution | Plan mode is overhead here | Plan mode for everything |
| Discovery output flooding a multi-phase task | Explore subagent | Verbose output isolated, summary returned | Reading everything in the main session |
| Run in CI/automation | `claude -p "..."` (+ `--output-format json --json-schema` for structured findings) | `-p`/`--print` is the real non-interactive flag | `--batch` and `CLAUDE_HEADLESS=true` **do not exist**; `< /dev/null` is a wrong workaround |

### D1 — Agentic Architecture & Orchestration

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| When does the loop stop? | `stop_reason == "end_turn"`; continue on `"tool_use"` | Model-driven termination is the contract | Text parsing, iteration caps as primary stop, "assistant produced text = done" |
| Model needs tool output to plan next step | Append `tool_result` to history, resend full conversation | That's how new info enters reasoning | Fresh request per step (amnesia) |
| Coordinator must spawn subagents | `allowedTools` includes `"Task"` | Task tool is *the* spawning mechanism | Assuming spawning is ambient |
| Subagent needs prior findings | Paste complete findings into its prompt; structured format separating content from metadata (URLs, doc names) for attribution | No automatic context inheritance, no shared memory | Assuming it "sees" the parent conversation |
| Independent subtasks | Multiple Task calls in **one** coordinator response | That's what runs them in parallel | One Task call per turn (serialized) |
| Predictable multi-aspect review vs open-ended investigation | Prompt chaining (fixed sequence: per-file passes + cross-file integration pass) vs dynamic decomposition (map structure → high-impact areas → adaptive prioritized plan) | Match decomposition to workflow shape | One-size-fits-all pipelines |
| "Add comprehensive tests to a legacy codebase" | Dynamic: map structure first, identify high-impact areas, plan adapts as dependencies surface | Open-ended tasks can't be pre-sequenced | Fixed pipeline defined upfront |
| Rule must ALWAYS hold (destructive ops, ordering prerequisites) | Programmatic hook / prerequisite gate | Deterministic; prompts have non-zero failure rate | "Strengthen the system prompt", few-shot compliance |
| Heterogeneous formats from multiple MCP servers | PostToolUse hook normalizes before the model sees results | Deterministic normalization beats prompt gymnastics | Prompting the model to mentally convert every time |
| Resume vs fresh vs fork | Resume when context valid (+ tell it what files changed); fresh + injected summary when stale; `fork_session` for divergent exploration from a shared baseline | Stale tool results mislead resumed sessions | Always resuming; full re-exploration after small changes |

---

## 4. Failure-modes drill

Eight production symptoms, exam-style. Cover the fix column and self-test.

| # | Production symptom | Root cause | Fix |
|---|---|---|---|
| 1 | CI job invoking `claude "review this PR"` hangs forever; logs show it waiting for interactive input | Claude Code launched in interactive mode | `claude -p "review this PR"`. The distractors — `--batch`, `CLAUDE_HEADLESS=true` — are **fake features**; `< /dev/null` doesn't address the command syntax |
| 2 | You shipped a powerful MCP code-intelligence server but the agent keeps using built-in Grep for everything | The MCP tools' descriptions are minimal; the model can't see why they're better | Enhance the MCP tool descriptions to explain capabilities and outputs in detail — description quality drives selection |
| 3 | Agent repeatedly fails to modify a legacy file with Edit; loop churns on the same edit | Edit needs a **unique** text anchor; the target snippet appears multiple times | Fall back to **Read the full file, then Write** the modified version |
| 4 | New hire clones the repo; Claude Code ignores the team's testing standards that work on your machine | Standards live in *your* `~/.claude/CLAUDE.md` (user scope) — never distributed via version control | Move them to project scope (root `CLAUDE.md` / `.claude/rules/`); diagnose with `/memory` to see what's actually loaded |
| 5 | Three hours into a codebase exploration, the agent gives inconsistent answers and cites "typical patterns" instead of the specific classes it found earlier | Context degradation in the extended session | Scratchpad files persisting key findings + delegate verbose exploration to subagents + summarize each phase before the next + `/compact` when discovery output fills the window |
| 6 | Coordinator's plan says "delegating to the test-mapping subagent" but no subagent ever runs | Coordinator's `allowedTools` doesn't include `"Task"` — the spawning mechanism is unavailable | Add `"Task"` to the coordinator's `allowedTools` |
| 7 | You `--resume` yesterday's investigation after a teammate refactored two modules; the agent confidently reasons from function signatures that no longer exist | Resumed session carries stale tool results from before the refactor | Tell the resumed session exactly which files changed for targeted re-analysis — or, if staleness is broad, start a fresh session with a structured summary injected |
| 8 | Synthesis-style subagent with access to the full search tool set starts issuing its own web searches mid-task, off-spec and slow | Tools outside an agent's specialization get misused; over-broad tool grants | Restrict each subagent to its 4–5 role-relevant tools; for the frequent simple case, add one **scoped** cross-role tool (`verify_fact`), routing complex cases back through the coordinator |

Bonus tell for question-writing patterns: when a symptom is "agent skips a required step sometimes," the answer is **never** a stronger prompt — it's a programmatic gate or hook. When a symptom is "wrong tool chosen," the answer is almost always **fix the descriptions first**.

---

## Cram card (last 5 minutes before the exam)

- Loop: continue on `stop_reason=="tool_use"`, stop on `"end_turn"`. Never parse text, never cap iterations as the primary stop.
- Grep = contents. Glob = paths. Edit needs unique anchor; non-unique → Read+Write.
- Explore = Grep entry points → Read to follow imports. Never read everything upfront.
- Descriptions drive tool selection. Fix descriptions before few-shot, routers, or consolidation.
- 4–5 tools per agent. `"Task"` in `allowedTools` to spawn. Subagents inherit nothing — context goes in the prompt. Parallel = multiple Task calls in one response.
- Hooks = deterministic guarantees. Prompts = probabilistic judgment. PostToolUse = normalize results before the model sees them.
- `.mcp.json` = project/shared, `${ENV_VAR}` for secrets. `~/.claude.json` = personal. Resources = catalogs, tools = actions. Community server > custom for standard integrations.
- Project `CLAUDE.md` / `.claude/commands/` = shared via git. `~/.claude/...` = yours alone. `/memory` to debug. `.claude/rules/` + `paths:` globs for scattered file types.
- SKILL.md frontmatter: `context: fork` (isolation), `allowed-tools` (restriction), `argument-hint` (params).
- Plan mode = architectural/multi-file/multiple approaches. Direct = scoped single fix. Explore subagent = verbose discovery.
- `-p` is real. `--batch` and `CLAUDE_HEADLESS` are fake.
- Resume when valid (+ declare changed files); fresh + summary when stale; `fork_session` to compare approaches from a shared baseline.
