# Scenario 3: Multi-Agent Research System

> **Exam framing:** "You are building a multi-agent research system using the Claude Agent SDK. A coordinator agent delegates to specialized subagents: one searches the web, one analyzes documents, one synthesizes findings, and one generates reports. The system researches topics and produces comprehensive, cited reports."
>
> **Primary domains:** D1 Agentic Architecture & Orchestration (27%), D2 Tool Design & MCP Integration (18%), D5 Context Management & Reliability (15%). If this scenario is drawn, it frames roughly a quarter of your exam — and it hits the two heaviest-weighted domains plus D5. This is the highest-yield scenario in the bank.

---

## 1. The system at a glance

Five agents. One coordinator, four specialists. **Hub-and-spoke**: every message between subagents flows *through the coordinator* — subagents never talk to each other directly. That's not a style preference; the guide says it's for **observability, consistent error handling, and controlled information flow**.

**The pieces:**

| Component | Job | Tools it gets |
|---|---|---|
| Coordinator | Decompose the topic, pick which subagents to invoke, route results, evaluate coverage, re-delegate on gaps | `Task` (must be in `allowedTools` or it can't spawn anything) |
| Web search subagent | Find sources for its assigned subtopic | `web_search`, `extract_web_results` |
| Document analysis subagent | Pull facts out of documents | `extract_data_points`, `summarize_content`, `verify_claim_against_source` |
| Synthesis subagent | Merge findings, preserve citations, flag gaps | `verify_fact` (scoped, for simple lookups only) |
| Report generation subagent | Render the final cited report | file-write tools |

**Data flow:** coordinator decomposes topic → spawns search + analysis subagents **in parallel** (multiple Task calls in *one* response) → subagents return **structured findings with claim-source mappings** → coordinator aggregates and passes complete findings *in the synthesis agent's prompt* (no automatic context inheritance) → synthesis returns merged findings with coverage annotations → coordinator checks for gaps → either re-delegates targeted queries or hands off to report generation.

```
                        ┌─────────────────┐
       topic ──────────▶│   COORDINATOR    │◀──── all results, all errors
                        │ (allowedTools    │      flow back through here
                        │  includes "Task")│
                        └───┬───┬───┬───┬──┘
              Task calls    │   │   │   │     (parallel = multiple Task
          in ONE response ─▶│   │   │   │      calls in a single turn)
                ┌───────────┘   │   │   └───────────────┐
                ▼               ▼   ▼                   ▼
        ┌──────────────┐ ┌─────────────┐ ┌───────────┐ ┌────────────┐
        │  WEB SEARCH  │ │  DOC        │ │ SYNTHESIS │ │  REPORT    │
        │  subagent    │ │  ANALYSIS   │ │ subagent  │ │  GEN       │
        │              │ │  subagent   │ │ +verify_  │ │  subagent  │
        └──────────────┘ └─────────────┘ │  fact     │ └────────────┘
                                         └───────────┘
        Each subagent: isolated context, role-scoped tools (4-5 max),
        returns structured findings: {claim, excerpt, source URL,
        doc name, publication date} — never prose blobs.
```

**The three rules that generate most correct answers here:**

1. **Subagents have isolated context.** They do NOT inherit the coordinator's conversation history or share memory between invocations. Anything a subagent needs must be placed explicitly in its prompt.
2. **The coordinator owns decomposition quality.** If the final report has coverage holes, look at what the coordinator *assigned* before blaming downstream agents.
3. **Provenance is structural, not stylistic.** Citations survive only if every hop passes structured claim-source mappings. Summarize findings into prose anywhere in the pipeline and attribution is gone.

---

## 2. Build it step by step

Build order matters: loop first (nothing works without it), then tools, then subagents, then orchestration, then reliability layers.

### Step 1 — The agentic loop (raw Messages API)

Everything in the Agent SDK sits on top of this loop. The exam tests it directly (Task 1.1): continue on `stop_reason == "tool_use"`, terminate on `stop_reason == "end_turn"`, append tool results to history so the model can reason about the next action.

```python
import anthropic

client = anthropic.Anthropic()

messages = [{"role": "user",
             "content": "Research: impact of AI on creative industries. Cited report."}]

while True:
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        system=COORDINATOR_SYSTEM_PROMPT,
        tools=TOOLS,
        messages=messages,
    )

    if response.stop_reason == "end_turn":
        break                      # the ONLY correct termination signal

    if response.stop_reason == "tool_use":
        # Append the assistant turn. It may contain MULTIPLE tool_use
        # blocks — that is how parallel delegation happens.
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = run_tool(block.name, block.input)   # your code runs the tool
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
        # Tool results go back as a USER turn — this is how new
        # information enters the model's reasoning for the next iteration.
        messages.append({"role": "user", "content": tool_results})
```

**Anti-patterns the exam names explicitly** (any of these as an answer option = wrong):

- Parsing natural-language signals ("DONE", "task complete") to decide termination
- An arbitrary iteration cap as the *primary* stopping mechanism
- Checking whether the assistant produced text content as a completion indicator

The model drives the decisions ("model-driven decision-making"); your code just executes tools and checks `stop_reason`. A pre-configured decision tree of tool sequences is the opposite of agentic — distractors love it.

### Step 2 — Tool definitions with rich descriptions

Tool descriptions are **the primary mechanism LLMs use for tool selection**. Minimal descriptions ("Retrieves order details") are the root cause in tool-misrouting questions. Write each description with: purpose, input formats, example queries, edge cases, and *when to use it versus similar tools*.

```python
TOOLS = [
    {
        "name": "extract_web_results",   # renamed from vague "analyze_content"
        "description": (
            "Extracts structured findings from WEB SEARCH results only. "
            "Input: a list of result URLs plus the research subtopic. "
            "Returns per-source findings: claim, evidence excerpt, source URL, "
            "publication date. Use this for web pages and news articles. "
            "Do NOT use for PDFs or uploaded documents — use "
            "extract_data_points for those."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "urls": {"type": "array", "items": {"type": "string"}},
                "subtopic": {"type": "string"},
            },
            "required": ["urls", "subtopic"],
        },
    },
    # ...
]
```

Two moves the guide calls out by name:

- **Rename to eliminate overlap:** `analyze_content` vs `analyze_document` with near-identical descriptions causes misrouting → rename to `extract_web_results` with a web-specific description.
- **Split generic tools:** one `analyze_document` → `extract_data_points`, `summarize_content`, `verify_claim_against_source`, each with a defined input/output contract.
- **Constrain generic tools:** replace `fetch_url` with `load_document` that validates document URLs.

Also check the **system prompt** for keyword-sensitive instructions — a stray "always analyze content thoroughly" can override well-written tool descriptions and create unintended tool associations.

### Step 3 — Structured subagent output (provenance from day one)

Every finding a subagent returns must **separate content from metadata**. This is what keeps citations alive through synthesis and lets temporal data be interpreted correctly.

```json
{
  "findings": [
    {
      "claim": "Generative AI adoption in music production grew 3x in 2025",
      "evidence_excerpt": "…survey of 2,400 producers found…",
      "source_url": "https://example.com/report",
      "document_name": "MIDiA 2025 Producer Survey",
      "publication_date": "2025-11-04",
      "relevance_score": 0.9
    }
  ],
  "coverage_notes": "No sources found for film-scoring subtopic; only 2 sources newer than 2024."
}
```

Publication dates are not optional garnish: without them, a 2019 statistic and a 2025 statistic look like a **contradiction** instead of a trend. The guide tests this exact confusion.

### Step 4 — AgentDefinitions and role-scoped tools (Agent SDK)

```python
# SKETCH — Agent SDK concepts using exam terminology.
# The exam tests the concepts (AgentDefinition, allowedTools, Task tool),
# not exact SDK call signatures.

web_search_agent = AgentDefinition(
    description=(
        "Web research specialist. Finds and extracts sources for one "
        "assigned subtopic. Use for current articles, statistics, primary "
        "sources on the web. Not for analyzing provided documents."
    ),
    prompt=WEB_SEARCH_SYSTEM_PROMPT,          # includes the structured-output contract
    tools=["web_search", "extract_web_results"],   # role-scoped: 4-5 tools max
)

synthesis_agent = AgentDefinition(
    description="Merges structured findings into a coherent, cited synthesis. "
                "Flags coverage gaps. Verifies simple facts itself; routes "
                "complex verification back to the coordinator.",
    prompt=SYNTHESIS_SYSTEM_PROMPT,
    tools=["verify_fact"],    # scoped cross-role tool for the 85% simple case
)

coordinator = AgentDefinition(
    description="Research coordinator: decomposes topics, delegates, aggregates.",
    prompt=COORDINATOR_SYSTEM_PROMPT,
    tools=["Task"],           # allowedTools MUST include "Task" to spawn subagents
)
```

Tool distribution rules the exam tests (Task 2.3):

- **Too many tools degrades selection.** 18 tools instead of 4-5 increases decision complexity and makes selection unreliable. Give each agent only its role's tools.
- **Agents misuse tools outside their specialization** — a synthesis agent with full web-search access will attempt (bad) web searches. Don't give it that access.
- **Scoped cross-role tool for high-frequency needs:** if 85% of synthesis verifications are simple fact-checks, give synthesis a scoped `verify_fact` tool; the 15% complex cases keep routing through the coordinator to the web search agent. Least privilege, existing coordination preserved.

### Step 5 — The coordinator: decomposition, delegation, parallelism

The coordinator's prompt should specify **research goals and quality criteria, not step-by-step procedures** — that's what lets subagents adapt. And it must decompose **broadly enough to cover the whole topic**: the guide's own sample question (Q7) is a report on "AI in creative industries" that covers only visual arts because the coordinator decomposed into three visual-arts subtasks. Correct diagnosis: **coordinator decomposition too narrow**, not any downstream agent.

```python
COORDINATOR_SYSTEM_PROMPT = """
You coordinate a research pipeline. For each topic:

1. Decompose into subtopics that TOGETHER cover the full scope of the
   topic. Enumerate the major domains first, then assign one subagent
   task per domain. Partition scope so subagents do not duplicate work
   (distinct subtopics or distinct source types per agent).
2. Dynamically select which subagents a query actually needs — do not
   always run the full pipeline.
3. Spawn independent research tasks IN PARALLEL by emitting multiple
   Task tool calls in a single response.
4. When invoking synthesis, include the COMPLETE structured findings
   from search and analysis directly in its prompt. Subagents do not
   see your conversation history.
5. Evaluate synthesis output for coverage gaps. If gaps exist,
   re-delegate targeted queries to search/analysis and re-invoke
   synthesis until coverage is sufficient.

Quality bar: every claim in the final report carries a source; coverage
gaps and conflicting sources are explicitly annotated, never hidden.
"""
```

Two mechanics the exam checks precisely:

- **Parallel subagents = multiple Task tool calls in a single coordinator response**, not one call per turn across separate turns.
- **Context passing is explicit.** The synthesis subagent gets web search results + document analysis output *pasted into its prompt*. There is no automatic inheritance and no shared memory between invocations.

Step 4 of the coordinator prompt is the **iterative refinement loop** (Task 1.2): evaluate → re-delegate targeted → re-synthesize. One-shot pipelines that never loop back are the distractor.

### Step 6 — Structured errors and propagation

MCP tools signal failure with the **`isError` flag** plus structured metadata. A uniform "Operation failed" prevents the agent from making recovery decisions.

```json
{
  "isError": true,
  "errorCategory": "transient",        // transient | validation | permission | business
  "isRetryable": true,
  "description": "Search API timeout after 30s",
  "attempted_query": "AI adoption film scoring 2025",
  "partial_results": [ { "claim": "...", "source_url": "..." } ],
  "alternatives": ["narrow the query", "try the news-specific index"]
}
```

Propagation policy across the multi-agent system (Tasks 2.2 + 5.3):

- **Subagents recover locally from transient failures** (retry the timeout themselves). They propagate to the coordinator only errors they cannot resolve — *with* failure type, what was attempted, partial results, and alternatives.
- **Never** return an empty result set marked successful (silent suppression), and **never** let one subagent failure terminate the whole workflow. Both are named anti-patterns.
- **Distinguish access failures from valid empty results.** A timeout needs a retry decision; a successful query with zero matches is an answer. Conflating them corrupts coordinator decisions in both directions.
- When sources stay unavailable, the coordinator proceeds with partial results and the synthesis output carries **coverage annotations**: which findings are well-supported vs which topic areas have gaps.

### Step 7 — Hooks for deterministic normalization

Your search MCP tool returns Unix timestamps; your document tool returns ISO 8601; a third returns numeric status codes. Prompting "please normalize dates" is probabilistic. A **PostToolUse hook** intercepts every tool result and transforms it *before the model processes it* — deterministic.

```python
# SKETCH — Agent SDK hook concept, exam terminology.
def normalize_dates(tool_name, tool_result):
    """PostToolUse hook: normalize heterogeneous formats from different
    MCP tools (Unix timestamps, ISO 8601, numeric status codes) before
    the agent sees them."""
    return canonicalize(tool_result)   # every date -> ISO 8601, every status -> enum

hooks = {"PostToolUse": [normalize_dates]}
```

The rule (Task 1.5): **hooks for deterministic guarantees, prompts for probabilistic guidance.** Hooks can also intercept *outgoing* tool calls to block policy-violating actions. If a question says "must always" or "guaranteed," the answer is a hook or programmatic gate, never a system-prompt sentence.

### Step 8 — Sessions, forking, crash recovery

- `--resume <session-name>` continues a **named** prior session. If files changed since, tell the resumed session *which* files changed for targeted re-analysis — don't force a full re-exploration. If prior tool results are **stale**, starting a *new* session with a structured summary injected is more reliable than resuming.
- **`fork_session`** creates independent branches from a shared analysis baseline — e.g., run the expensive corpus analysis once, then fork twice to compare two synthesis strategies without paying for or contaminating re-analysis.
- **Crash recovery:** each agent exports structured state (findings so far, sources covered) to a known location; the coordinator loads a **manifest** on resume and injects state into agent prompts. Long research runs die; design for it.
- Long exploration filling context: delegate verbose discovery to subagents that return summaries, keep **scratchpad files** of key findings, and use `/compact` in Claude Code sessions.

### Step 9 — Wiring MCP servers (if the search/doc tools live in MCP servers)

```json
// .mcp.json — project scope, committed, shared with the team
{
  "mcpServers": {
    "research-search": {
      "command": "npx",
      "args": ["-y", "@yourorg/search-mcp"],
      "env": { "SEARCH_API_KEY": "${SEARCH_API_KEY}" }   // env var expansion — no secrets committed
    }
  }
}
```

- Project-scoped `.mcp.json` = shared team tooling. User-scoped `~/.claude.json` = personal/experimental servers. Both are discovered at connection time and available **simultaneously**.
- **MCP resources** (vs tools): expose content catalogs — the document corpus index, source lists — so agents see what's available *without exploratory tool calls*. Resources for content, tools for actions.
- Prefer existing community MCP servers for standard integrations; write custom servers only for team-specific workflows.

---

## 3. The decision points this scenario tests

Each row is a task statement converted to exam form. The "trap" column is what the wrong-but-plausible option looks like.

### D1 — Orchestration

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Deciding when the agent loop ends | Check `stop_reason`: continue on `"tool_use"`, stop on `"end_turn"` | It's the model's explicit signal | Parse text for "done"; iteration cap as primary stop; check for assistant text |
| Report misses whole subdomains; all subagents ran clean | Fix coordinator decomposition breadth | Subagents only cover what they're assigned | Blame synthesis gap-detection, search query breadth, or analysis filtering |
| Every query runs the full 4-agent pipeline, simple ones included | Coordinator dynamically selects which subagents each query needs | Coordinator's job includes invocation decisions by query complexity | Hardcode the pipeline "for consistency" |
| Two subagents keep researching the same sources | Partition scope: distinct subtopics or source types per agent | Minimizes duplication by construction | "Tell them to avoid duplication" (prompt hope, no partition) |
| Synthesis output has gaps | Iterative refinement: coordinator evaluates, re-delegates targeted queries, re-invokes synthesis | Coverage is a loop, not a pass | One-shot pipeline; or asking synthesis to "try harder" |
| Need search + analysis running at once | Multiple Task tool calls in a **single** coordinator response | That's the parallel-spawn mechanism | One Task call per turn, sequentially |
| Coordinator can't spawn subagents at all | Add `"Task"` to its `allowedTools` | Task tool is *the* spawn mechanism and must be allowed | Fiddle with subagent configs or prompts |
| Subagent needs prior findings | Paste complete findings directly into its prompt | Isolated context; no inheritance, no shared memory | Assume it sees the coordinator's history |
| Writing the coordinator prompt | Research goals + quality criteria | Enables subagent adaptability | Step-by-step procedural instructions |
| Compare two report structures from one expensive analysis | `fork_session` from the shared baseline | Independent branches, analysis paid once | Re-run analysis per approach; or mutate one session back and forth |
| Dates arrive in 3 formats from 3 MCP tools | PostToolUse hook normalizes before the model sees them | Deterministic guarantee | System-prompt instruction to normalize (probabilistic) |
| Resuming a long research session after source docs changed | Tell the resumed session which files changed; if results are stale, start fresh with an injected summary | Stale tool results poison resumed reasoning | Blind `--resume` and trust old context; or full re-exploration |

### D2 — Tool design & MCP

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Agent picks the wrong tool between two similar tools with thin descriptions | **First step:** expand descriptions — inputs, example queries, edge cases, boundaries vs similar tools | Descriptions are the primary selection mechanism; lowest-effort fix at the root cause | Few-shot examples (token overhead, wrong layer); keyword routing layer (over-engineered); merging tools (bigger change than "first step" warrants) |
| `analyze_content` vs `analyze_document` misrouting persists | Rename to eliminate overlap (`extract_web_results`) + web-specific description | Names + descriptions carry the differentiation | Keep names, add more prompt warnings |
| One mega `analyze_document` tool used inconsistently | Split into `extract_data_points`, `summarize_content`, `verify_claim_against_source` | Purpose-specific tools with defined contracts | One bigger description on the mega-tool |
| An agent has 18 tools and picks badly | Cut to the 4-5 tools its role needs | Tool count drives selection complexity | More selection guidance in the prompt |
| Synthesis needs frequent simple fact-checks (85%), rare deep dives (15%) | Scoped `verify_fact` on synthesis; complex cases still route through coordinator | Least privilege for the common case, coordination for the rest | Full web-search access for synthesis; batch all verifications to the end (blocks dependent steps); speculative pre-caching |
| Must guarantee the model calls *some* tool, never plain text | `tool_choice: "any"` | "auto" permits a text-only reply | Prompt "you must use a tool" |
| A specific tool must run first (e.g., `extract_metadata` before enrichment) | `tool_choice: {"type": "tool", "name": "extract_metadata"}`, then follow-up turns | Forced selection is deterministic | Ordering instructions in the prompt |
| Tool fails — what goes back to the agent? | `isError` + `errorCategory` + `isRetryable` + human-readable description | Enables correct recovery; avoids wasted retries on non-retryable errors | Generic "Operation failed" |
| Agents burn turns discovering what documents exist | Expose the catalog as an **MCP resource** | Resources = content visibility without exploratory tool calls | Add a `list_documents` tool loop |
| Agent prefers built-in Grep over your capable MCP search tool | Enhance the MCP tool's description to explain capabilities and outputs in detail | Selection follows descriptions | Disable built-ins |
| Team needs shared search server; you're testing a new one | Shared → project `.mcp.json` (env-var expansion for creds); experimental → `~/.claude.json` | Scoping rule + no committed secrets | Hardcode keys in `.mcp.json`; put team server in user scope |

### D5 — Context & reliability

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Final report has claims but citations vanished | Structured claim-source mappings emitted by subagents and **preserved through synthesis** | Attribution dies in prose summarization | "Instruct synthesis to cite better" after provenance is already lost |
| Two credible sources give different statistics | Include **both**, annotated with source attribution; coordinator decides reconciliation before synthesis | Arbitrary selection hides real disagreement | Pick the more credible-looking one; average them |
| 2019 vs 2025 figures flagged as a contradiction | Require publication/collection dates in every structured finding | Temporal difference ≠ contradiction | Conflict-resolution logic without dates |
| Synthesis ignores findings from the middle of a big aggregated input | Key-findings summary at the **beginning**, explicit section headers throughout | Lost-in-the-middle: start and end get processed reliably | Bigger context window (doesn't fix attention position effects) |
| Verbose search results blow the synthesis agent's context budget | Upstream agents return structured data (key facts, citations, relevance scores), not raw content + reasoning chains; trim tool outputs to relevant fields | Tool results consume tokens disproportionately to relevance | Progressive summarization that blurs numbers, dates, stated specifics |
| Web search times out mid-research | Structured error context to coordinator: failure type, attempted query, partial results, alternatives | Coordinator can retry-modified, reroute, or proceed with partials | Generic "search unavailable" after silent retries; empty-set-as-success; kill the whole workflow |
| Some sources permanently unavailable | Proceed; synthesis annotates well-supported findings vs coverage gaps | Honest partial output beats fake completeness | Block the report until everything resolves |
| Long run crashes at hour 3 | Structured state exports per agent + coordinator loads a manifest on resume | Designed recovery, not luck | Restart from zero; rely on session history surviving |
| Extended exploration: agent starts citing "typical patterns" instead of the actual sources it read | Scratchpad files of key findings; subagents for verbose phases; summarize before each next phase; `/compact` | Context degradation is predictable; externalize the facts | Push on in the same overloaded session |
| Financial data, news, and technical findings all rendered as uniform prose | Render per content type: tables for financial data, prose for news, structured lists for technical findings | Format should match content, not flatten it | One uniform output template for everything |

---

## 4. Failure-modes drill

Guide-style: production symptom → root cause → fix. These mirror the actual sample questions (Q7-Q9 are from this scenario) plus the task statements most likely to become questions.

**1. Every subagent runs clean, but the "AI in creative industries" report covers only visual arts — no music, writing, or film.** Coordinator logs show subtasks: "AI in digital art," "AI in graphic design," "AI in photography."
→ Root cause: **coordinator task decomposition too narrow.** The subagents did exactly what they were assigned.
→ Fix: coordinator decomposes by enumerating the topic's full domain coverage first, then assigns; add a coverage-evaluation + re-delegation refinement loop.
*(This is sample Q7. Distractors blame synthesis, search queries, or analysis filtering — all downstream agents working correctly within assigned scope.)*

**2. Web search subagent times out; coordinator either retries the identical failing query forever or gives up on the topic.**
→ Root cause: error came back as a generic status (or was swallowed as an empty "success"), so the coordinator has nothing to reason with.
→ Fix: structured error context — failure type, attempted query, partial results, alternative approaches. Subagent handles transient retries locally; only unresolvable errors propagate. *(Sample Q8.)*

**3. Latency up 40%; logs show 2-3 coordinator round-trips per task because synthesis keeps requesting fact verification. 85% of the verifications are simple date/name/statistic checks.**
→ Root cause: synthesis has zero verification capability, so even trivial checks route synthesis → coordinator → web search → coordinator → synthesis.
→ Fix: give synthesis a **scoped `verify_fact` tool** for simple lookups; the 15% complex verifications keep the coordinator path. Not full web-search access (over-provisioning, specialization break), not end-of-pass batching (later synthesis steps depend on earlier verified facts). *(Sample Q9.)*

**4. Final reports read well but citations are missing or attached to the wrong claims.**
→ Root cause: a middle hop compressed findings into prose summaries; claim-source mappings were never a structural requirement, so attribution was lost before synthesis ever saw it.
→ Fix: every subagent outputs `{claim, evidence excerpt, source URL, document name, publication date}`; synthesis is required to preserve and **merge** the mappings, not regenerate citations from memory.

**5. Two credible sources report different market-size numbers; the report confidently states one of them.**
→ Root cause: an agent silently resolved the conflict by picking a value.
→ Fix: document analysis completes **with both conflicting values included and explicitly annotated**; the coordinator decides reconciliation before synthesis; the report separates well-established findings from contested ones, preserving original source characterizations and methodological context.

**6. Report flags a "data inconsistency" between two statistics that are actually a 2019 baseline and a 2025 update.**
→ Root cause: structured findings carry no publication/collection dates, so temporal differences read as contradictions.
→ Fix: make `publication_date` a required field in every subagent's structured output; synthesis interprets time-separated values as trend data.

**7. Synthesis output consistently reflects the first and last search agents' findings; the middle agents' material is thin or missing. All findings verifiably reached the synthesis prompt.**
→ Root cause: **lost-in-the-middle** — long aggregated inputs get reliable attention at the beginning and end, not the middle.
→ Fix: put a key-findings summary at the top of the aggregated input and organize detail under explicit section headers. A bigger context window is the trap answer — capacity doesn't fix position effects.

**8. Six-hour research run dies at hour four (crash/network); restart begins from zero and re-pays every search and analysis call.**
→ Root cause: no state persistence outside the live conversation context.
→ Fix: each agent exports structured state (findings, sources covered, subtopics remaining) to a known location; the coordinator loads a **manifest** on resume and injects prior state into agent prompts. For comparing alternative approaches from the recovered baseline, `fork_session` instead of mutating one session.

---

## Cram card — 10 rules

1. Loop control = `stop_reason` only: `"tool_use"` continue, `"end_turn"` stop. Text-parsing and iteration caps are named anti-patterns.
2. Coverage holes in the report = coordinator decomposition too narrow. Diagnose the assignment, not the subagents.
3. Subagents inherit nothing. Pass complete prior findings explicitly in the subagent's prompt.
4. Parallelism = multiple Task calls in ONE coordinator response; coordinator's `allowedTools` must include `"Task"`.
5. Tool misrouting? First fix is always richer tool descriptions (inputs, examples, boundaries) — not few-shot, not a routing layer, not merging tools.
6. 4-5 role-scoped tools per agent; high-frequency cross-role need gets one scoped tool (`verify_fact`), complex cases stay with the coordinator.
7. Errors: `isError` + `errorCategory` + `isRetryable` + partials + alternatives. Local retry for transient; never empty-as-success; never kill the workflow.
8. "Must always happen" = hook or programmatic gate (deterministic). Prompt instructions = probabilistic; wrong when compliance is required.
9. Provenance is structured claim-source mappings with publication dates, preserved through every hop. Conflicts get annotated with attribution, never silently resolved.
10. Long inputs: summary first + section headers (lost-in-the-middle); long runs: state manifests + scratchpads; alternative approaches: `fork_session` from a shared baseline.
