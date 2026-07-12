# Domain 2 — Tool Design & MCP Integration (18% of exam ≈ 11 questions)

Source: Claude Certified Architect – Foundations exam guide v0.2 (2026-06-30), pages 9–12 + sample Q2/Q9 + appendix.
Scenarios most likely to carry these questions: **S1 Customer Support Agent, S3 Multi-Agent Research, S4 Developer Productivity**.

The whole domain is one idea repeated five ways: **the model picks and uses tools based on words — names, descriptions, and error text. Fix the words before you build infrastructure.** When the exam offers "add a routing layer / classifier / more few-shot examples" vs "fix the description," the description fix wins as the *first step* almost every time.

---

## Task 2.1 — Tool interfaces: descriptions and boundaries

### Plain words

Claude has no schema-introspection magic. When it decides which tool to call, it reads the tool **name + description** the same way you'd read a man page. A minimal description ("Retrieves customer information") gives the model nothing to differentiate on, so selection between similar tools becomes a coin flip. A good description states: purpose, **input formats it accepts, example queries, edge cases, and boundaries — when to use it vs. the similar-sounding alternative.** Also watch the **system prompt**: keyword-sensitive instructions there ("always analyze documents thoroughly") can create unintended associations that override well-written tool descriptions.

```python
# BAD — this is what causes the misrouting in sample Q2
{"name": "lookup_order", "description": "Retrieves order details"}

# GOOD — formats + examples + boundary vs. the sibling tool
{
    "name": "lookup_order",
    "description": (
        "Retrieves order details by order ID. "
        "Input: order ID in format ORD-XXXXX or bare numeric ID (e.g. '12345'). "
        "Use for questions about a specific order: status, items, shipping "
        "(e.g. 'check my order #12345'). "
        "Do NOT use for customer account/profile questions — use get_customer for those."
    ),
    "input_schema": {"type": "object",
                     "properties": {"order_id": {"type": "string"}},
                     "required": ["order_id"]},
}
```

Two repair moves the exam names explicitly:

1. **Rename to kill overlap** — `analyze_content` vs `analyze_document` with near-identical descriptions misroute; rename `analyze_content` → `extract_web_results` with a web-specific description.
2. **Split generic into purpose-specific** — one vague `analyze_document` becomes `extract_data_points`, `summarize_content`, `verify_claim_against_source`, each with a defined input/output contract.

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Agent picks wrong tool; both tools have one-line descriptions (sample Q2) | Expand descriptions: input formats, example queries, edge cases, boundaries vs. similar tools | Descriptions are the **primary selection mechanism**; this fixes the root cause cheaply | Few-shot examples (token overhead, doesn't fix root cause), keyword routing layer (over-engineered), merging tools (too heavy for a "first step") |
| Two tools functionally overlap (`analyze_content` / `analyze_document`) | Rename one to its actual purpose (`extract_web_results`) + rewrite description domain-specific | Distinct names + distinct descriptions = distinct selection signal | Adding "prefer X for web" to the system prompt instead of fixing the tools |
| One generic tool does 3 jobs badly | Split into purpose-specific tools with defined input/output contracts | Narrow contracts → reliable selection and predictable outputs | Making the generic description longer instead of splitting |
| Descriptions are good but selection still wrong | Review the **system prompt** for keyword-sensitive instructions creating tool associations | System prompt wording can override good descriptions | Assuming the tool definitions are the only place selection is influenced |

---

## Task 2.2 — Structured MCP error responses

### Plain words

An MCP tool signals failure with the **`isError` flag** — the result comes back to the model marked as an error instead of throwing out-of-band. The exam cares about what you put *inside* that error. A generic `"Operation failed"` is an anti-pattern: the agent can't decide whether to retry, rephrase, apologize, or escalate. Return **structured metadata**: `errorCategory` (**transient / validation / business / permission**), an `isRetryable` boolean, and a human-readable description. For business-rule violations, include `retriable: false` plus a **customer-friendly explanation** so the agent can relay it verbatim. Two more distinctions the exam grades: **empty result ≠ failure** (a successful query with zero matches must not be reported as an error, and an access failure must not be disguised as an empty success), and **recover locally first** — subagents handle transient failures themselves (retry/backoff) and propagate upward only what they can't resolve, together with partial results and what was attempted.

```python
# MCP tool returning a structured error (Python MCP server, conceptual)
return {
    "isError": True,
    "content": [{"type": "text", "text": json.dumps({
        "errorCategory": "business",       # transient | validation | business | permission
        "isRetryable": False,              # don't waste retries on policy violations
        "message": "Refunds over $500 require supervisor approval.",
        "customerExplanation": "This refund needs a manager's sign-off; I'm escalating it now.",
    })}],
}

# vs. a VALID EMPTY RESULT — success, not an error:
return {"isError": False,
        "content": [{"type": "text",
                     "text": '{"matches": [], "note": "Query succeeded; no orders found for this customer."}'}]}
```

The four categories, mapped to what the agent should do:

| errorCategory | Example | isRetryable | Agent's correct reaction |
|---|---|---|---|
| **transient** | timeout, service unavailable | true | retry (locally, with backoff) |
| **validation** | malformed order ID | false as-is | fix the input and re-call |
| **business** | refund > policy limit | false | explain to user / escalate — never retry |
| **permission** | agent lacks access | false | escalate or use an alternate path |

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Tool failures leave agent guessing what to do next | Return `errorCategory` + `isRetryable` + human-readable message via `isError` | Structured metadata drives correct recovery decisions | Uniform generic "Operation failed" for every failure type |
| Business rule blocks the action (refund > $500) | `retriable: false` + customer-friendly explanation | Agent must communicate the policy, not hammer retries | Marking it transient/retryable → wasted retry loop |
| Query runs fine, finds nothing | Return success with empty results and say so explicitly | Empty ≠ broken; agent should proceed, not retry/escalate | Returning `isError: true` for zero matches — or the mirror image: catching a timeout and returning empty-marked-success |
| Subagent hits a transient failure | Retry locally; propagate to coordinator only unresolvable errors **with partial results + what was attempted** | Coordinator gets decision-grade context without noise from recoverable blips | Propagating every timeout upward, or exhausting retries then returning generic "search unavailable" |

---

## Task 2.3 — Tool distribution across agents + tool_choice

### Plain words

More tools = worse selection. The exam's canonical number: an agent with **18 tools instead of 4–5** degrades tool-selection reliability because decision complexity goes up. And agents holding tools outside their specialization *use them wrong* — a synthesis agent with web-search tools will attempt searches instead of synthesizing. The fix is **scoped access**: each agent gets only its role's tools. Exception (sample Q9): when a cross-role need is **high-frequency and simple** (85% of the synthesis agent's verifications are quick fact-checks), give it one **scoped, constrained** cross-role tool (`verify_fact`) and keep routing the complex 15% through the coordinator. Same spirit: replace a generic `fetch_url` with a constrained `load_document` that validates document URLs — narrow the blast radius.

`tool_choice` is how you control *whether/which* tool gets called on an API request:

```python
# "auto" (default): model may call a tool OR just answer in text
tool_choice={"type": "auto"}

# "any": model MUST call some tool — no conversational text response
tool_choice={"type": "any"}

# forced: model MUST call this specific tool
tool_choice={"type": "tool", "name": "extract_metadata"}
```

Forced selection is for guaranteeing a specific tool runs **first** (e.g., force `extract_metadata` before enrichment tools) — you force it on the first request, then process subsequent steps in follow-up turns with a looser setting. `"any"` is for guaranteeing structured output when several extraction schemas exist and you don't know which fits — the model must pick *a* tool but chooses which.

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Agent has 18 tools, selection is flaky | Cut to the 4–5 its role needs | Fewer options = higher selection reliability | "Better descriptions will fix it" — description quality can't rescue an oversized toolset |
| Synthesis agent misusing web-search tools | Remove out-of-role tools; restrict each subagent to role-relevant set | Agents misuse tools outside their specialization | Giving every agent everything "for flexibility" (sample Q9 option C — violates least privilege) |
| Frequent simple cross-role need, occasional complex one (85/15) | One scoped tool (`verify_fact`) for the common case; coordinator routes the complex case | Least privilege + kills the 2–3 round trips per task | Full tool access (over-provision), batching verifications at end (blocking dependencies), speculative caching |
| Generic tool invites misuse (`fetch_url`) | Replace with constrained variant (`load_document` that validates document URLs) | Constrained contract prevents off-purpose calls | Prompt-begging the agent to only fetch documents |
| Must guarantee a tool call, any tool, no prose | `tool_choice: {"type": "any"}` | Model cannot return conversational text | Leaving `"auto"` and instructing "always use a tool" — probabilistic |
| A specific tool must run first | `tool_choice: {"type": "tool", "name": "..."}` on that turn, then follow-up turns | Deterministic first step | Prompt ordering instructions ("call extract_metadata first") — non-zero failure rate |

---

## Task 2.4 — MCP server integration (Claude Code + agents)

### Plain words

Two config scopes, one rule: **shared team tooling → project-scoped `.mcp.json`** (repo root, version-controlled, every dev gets it on clone/pull); **personal or experimental servers → user-scoped `~/.claude.json`** (your machine only, teammates never see it). Secrets never go in the committed file — `.mcp.json` supports **environment variable expansion** like `${GITHUB_TOKEN}`, resolved from each dev's environment at runtime. Tools from **all configured servers are discovered at connection time and are available simultaneously** — project + user servers coexist in one session.

```json
// .mcp.json — project scope, committed to the repo
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

```
repo/
├── .mcp.json            ← team-shared servers (env-expanded creds, no secrets committed)
└── ...
~/.claude.json           ← your personal/experimental servers
```

Three more testable ideas here:

- **MCP resources = content catalogs.** Tools are for *actions*; resources expose *browsable content* — issue summaries, documentation hierarchies, database schemas — so the agent can see what data exists **without burning exploratory tool calls**.
- **Description quality drives adoption.** If your MCP tool's description is thin, the agent will keep reaching for built-ins (e.g., using Grep instead of your more capable code-search MCP tool). Enhance MCP descriptions to spell out capabilities and outputs.
- **Community vs custom:** standard integration (Jira, GitHub) → use the existing **community server**. Build **custom** only for team-specific workflows nothing off-the-shelf covers.

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Whole team needs the same MCP server | Project `.mcp.json`, committed | Version control distributes it on clone/pull | Each dev hand-editing `~/.claude.json`; or expecting user-scope config to reach teammates |
| Trying out a server just for yourself | User `~/.claude.json` | Doesn't pollute the team's config | Committing your experiment into `.mcp.json` |
| Server needs an API token | `"${GITHUB_TOKEN}"`-style expansion in `.mcp.json` | Credentials come from each dev's env; no secrets in git | Hardcoding the token in the committed file |
| Agent wastes turns probing "what data is there?" | Expose the catalog as **MCP resources** | Visibility into available data without exploratory tool calls | Adding more query *tools*, or dumping the catalog into the system prompt |
| Agent ignores your capable MCP tool, uses Grep instead | Enrich the MCP tool's description (capabilities + outputs) | Built-ins win by default when the MCP description is vague | Disabling built-ins as the first move |
| Need Jira/GitHub/etc. integration | Existing community MCP server | Standard problem, solved artifact | Building custom for a standard integration (reserve custom for team-specific workflows) |

---

## Task 2.5 — Built-in tools: Read, Write, Edit, Bash, Grep, Glob

### Plain words

You know these from daily Claude Code use — the exam tests whether you can name the *right* one for a described job, and one specific failure path. The map:

| Tool | Job | Exam-phrase trigger |
|---|---|---|
| **Grep** | Search file **contents** for patterns | "find all callers of a function," "locate this error message," "find import statements" |
| **Glob** | Match file **paths/names** by pattern | "find all `**/*.test.tsx`," "files matching a naming pattern" |
| **Read** | Load full file contents | reading a file before modifying, following imports |
| **Write** | Write a full file | new file, or full-file replacement |
| **Edit** | **Targeted** modification via **unique text matching** | small precise change with a unique anchor |
| **Bash** | Run commands | builds, tests, git |

The tested failure path: **Edit fails when its anchor text is non-unique** (matches multiple places). The fallback is **Read the full file, then Write the corrected whole file** — deterministic, no anchor needed.

Exploration strategy (S4 territory): build codebase understanding **incrementally** — **Grep to find entry points → Read to follow imports and trace flows**. Never "read all files upfront." For tracing usage through wrapper modules: **first identify all exported names, then Grep for each name** across the codebase — searching only the original function name misses re-exports.

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| "Find every place `processRefund` is called" | Grep | Content search | Glob (paths only), or Read-everything |
| "Find all test files regardless of location" | Glob `**/*.test.tsx` | Filename/path pattern | Grep (that's for contents) |
| Small change, unique surrounding text | Edit | Targeted, minimal diff | Rewriting the whole file for a one-liner |
| Edit fails — anchor text matches multiple spots | Read full file → Write corrected file | Reliable when uniqueness can't be had | Retrying Edit with slightly bigger anchors forever, or Bash/sed hacks |
| "Understand this unfamiliar codebase" | Incremental: Grep entry points → Read to follow imports/flows | Preserves context, scales | Reading all files upfront (context exhaustion) |
| Function re-exported through wrapper modules | List all exported names first, then Grep each name | Aliases hide usages from a single-name search | Grepping only the original definition's name |

---

## Memorize cold

Flashcard facts — any one of these can be the hinge of a question.

**tool_choice (API field):**
- `{"type": "auto"}` — default; model **may** return plain text instead of calling a tool
- `{"type": "any"}` — model **must** call a tool, **chooses which**
- `{"type": "tool", "name": "extract_metadata"}` — model **must call that specific tool** ("forced")
- Guarantee structured output, unknown doc type, multiple schemas → `"any"`
- Guarantee a specific tool runs first → forced, then follow-up turns for later steps

**MCP error fields:**
- Failure flag: **`isError`** (on the tool result)
- **`errorCategory`** values: **transient / validation / business / permission** (guide lists the metadata triple as transient/validation/permission; *business* appears in the knowledge statement and the exercise — know all four)
- **`isRetryable`** boolean; business violations get **`retriable: false`** + customer-friendly explanation
- transient = timeouts/service unavailability → retryable; validation = bad input; business = policy violation; permission = access denied
- **Valid empty result = success with no matches ≠ error.** Access failure ≠ empty result.
- Subagents: **local recovery for transient failures**; propagate only unresolvable errors, with **partial results + what was attempted**

**Tool distribution numbers & names:**
- Degraded selection: **18 tools**; healthy: **4–5**
- Scoped cross-role tool example: **`verify_fact`** for the synthesis agent (85% simple / 15% via coordinator)
- Constrained replacement example: `fetch_url` → **`load_document`** (validates document URLs)
- Rename example: `analyze_content` → **`extract_web_results`**
- Split example: `analyze_document` → **`extract_data_points`**, **`summarize_content`**, **`verify_claim_against_source`**

**MCP config paths:**
- Project/team scope: **`.mcp.json`** (repo root, version-controlled)
- User/personal scope: **`~/.claude.json`**
- Env expansion syntax: **`${GITHUB_TOKEN}`** inside `.mcp.json`
- Tools from **all** configured servers: discovered **at connection time**, available **simultaneously**
- **MCP resources** = content catalogs (issue summaries, doc hierarchies, DB schemas) → fewer exploratory tool calls; **tools = actions, resources = content**
- Community server for standard integrations (**Jira** is the guide's example); custom only for team-specific workflows

**Built-ins:**
- **Grep = contents**, **Glob = paths/names**, **Read/Write = full file**, **Edit = targeted via unique text match**, **Bash = commands**
- **Edit non-unique-match failure → Read + Write fallback**
- Exploration order: **Grep entry points → Read follow imports** (never read-all-upfront)
- Wrapper tracing: **enumerate exported names first, then search each**

**Adjacent facts that leak into D2 questions:**
- Descriptions are the **primary tool-selection mechanism** (the literal phrase from sample Q2's answer)
- A good description contains: **input formats, example queries, edge cases, boundaries vs. similar tools**
- System-prompt keywords can **override** tool descriptions — audit both
- Weak MCP descriptions → agent prefers built-ins (Grep) over your better MCP tool

---

## Anti-pattern wall

Recognize these on sight — they're the distractor answers.

| # | Anti-pattern | Why it's wrong / what the exam wants instead |
|---|---|---|
| 1 | **Minimal one-line tool descriptions** ("Retrieves order details") | Root cause of misrouting; expand with formats/examples/boundaries first |
| 2 | **Few-shot examples or a keyword-routing layer as the *first* fix for tool misselection** | Token overhead / over-engineering; fix descriptions first (sample Q2 distractors A & C) |
| 3 | **Consolidating similar tools into one `lookup_entity` as a quick fix** | Valid architecture, wrong "first step" — too much effort vs. rewriting descriptions |
| 4 | **Overlapping tool names/descriptions** (`analyze_content` vs `analyze_document`) | Causes misrouting; rename/split to eliminate functional overlap |
| 5 | **Uniform generic errors** ("Operation failed") | Agent can't choose recovery; return errorCategory + isRetryable + message |
| 6 | **Returning empty results marked as success when the call actually failed** (or an error for a legit zero-match query) | Conflates access failure with valid emptiness in both directions |
| 7 | **Retrying business/permission errors** | Non-retryable by definition — wasted attempts; needs `retriable: false` + explanation |
| 8 | **Propagating every transient error to the coordinator** (or generic "search unavailable" after silent retries) | Subagent should recover locally, propagate only unresolvables with partial results + attempts |
| 9 | **The 18-tool agent** | Selection reliability degrades with decision complexity; scope to 4–5 per role |
| 10 | **Cross-specialization tool access** ("give synthesis all the search tools") | Agents misuse out-of-role tools; least privilege + scoped cross-role tool for the common case |
| 11 | **Prompt instructions to force tool order/usage** ("always call X first") | Probabilistic; use `tool_choice` forced/`any` (or hooks — D1) for guarantees |
| 12 | **Secrets hardcoded in committed `.mcp.json`** | Use `${VAR}` env expansion |
| 13 | **Team tooling configured in `~/.claude.json`** | User scope never reaches teammates; shared servers belong in project `.mcp.json` |
| 14 | **Building a custom MCP server for a standard integration** (Jira) | Community server exists; custom is for team-specific workflows only |
| 15 | **More query tools instead of MCP resources** for "what data exists?" | Resources expose content catalogs without exploratory calls |
| 16 | **Reading all files upfront to "understand the codebase"** | Context exhaustion; go incremental — Grep entry points, Read to trace |
| 17 | **Fighting Edit after non-unique match failures** | Fall back to Read + Write |

---

## How this shows up in the scenarios

- **S1 Customer Support** (`get_customer`, `lookup_order`, `process_refund`, `escalate_to_human`): description-quality questions (Q2 style), business-error handling with `retriable: false`, empty-vs-failure on customer/order lookups.
- **S3 Multi-Agent Research**: tool distribution per subagent, scoped `verify_fact` (Q9 style), local recovery vs. propagation with partial results.
- **S4 Developer Productivity**: built-in tool selection, Edit→Read+Write fallback, incremental exploration, MCP servers + resources, MCP-description-vs-built-in preference.

**Build-it drill (from the guide's Exercise 1 & 2, D2 parts):** define 3–4 MCP tools where two are deliberately similar and only descriptions disambiguate; add structured errors (`errorCategory`, `isRetryable`) and verify the agent retries transient but explains business; configure one server in `.mcp.json` with `${VAR}` expansion and one in `~/.claude.json`, confirm both sets of tools are live simultaneously.
