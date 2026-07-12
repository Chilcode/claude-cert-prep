# Domain 1 — Agentic Architecture & Orchestration (27%)

Biggest domain on the exam: **~16 of 60 questions**. Shows up hardest in Scenario 1 (Customer Support Agent), Scenario 3 (Multi-Agent Research), and Scenario 4 (Developer Productivity). Every question here is a judgment call: *given this failure or this requirement, which architecture move is correct?* The wrong answers are always plausible — usually "put it in the prompt," "add a cap," or "give the agent more tools." Learn the correct move AND why each trap is wrong.

---

## 1.1 — The Agentic Loop (stop_reason drives everything)

### Concepts in plain words

An agent is just a `while` loop around the Messages API. You send a request with tools defined; Claude either answers (`stop_reason: "end_turn"`) or asks you to run a tool (`stop_reason: "tool_use"`). If it's `tool_use`, YOU execute the tool, append the result to the conversation history, and call the API again. The model sees the tool result on the next iteration and reasons about what to do next — this is **model-driven decision-making**, not a pre-configured decision tree. The loop terminates when — and only when — `stop_reason == "end_turn"`.

```python
import anthropic
client = anthropic.Anthropic()
messages = [{"role": "user", "content": "Refund order #12345"}]

while True:
    resp = client.messages.create(
        model="claude-sonnet-4-5", max_tokens=4096,
        tools=TOOLS, messages=messages,
    )
    if resp.stop_reason == "end_turn":      # done — model has answered
        break
    if resp.stop_reason == "tool_use":       # model wants a tool run
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                out = run_tool(block.name, block.input)   # YOU execute it
                results.append({"type": "tool_result",
                                "tool_use_id": block.id,   # ties result to the call
                                "content": out})
        messages.append({"role": "user", "content": results})  # results go back as a user turn
```

Two mechanics the exam checks: (1) tool results are **appended to conversation history** (as `tool_result` blocks in a `user`-role message, keyed by `tool_use_id`) so the model can incorporate them into its next reasoning step; (2) control flow keys off `stop_reason` — nothing else.

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Deciding when the loop ends | `if stop_reason == "end_turn": break` | The API gives you an explicit, machine-readable termination signal | Parsing assistant text for "DONE"/"finished" — natural-language signals are unreliable |
| Response comes back with `stop_reason == "tool_use"` | Execute the tool(s), append `tool_result` blocks, call the API again | The model needs the result in context to pick the next action | Treating any assistant text alongside the tool call as the final answer |
| Worried about runaway loops | Iteration cap only as a **safety net**, never the primary stop | Primary termination is `end_turn`; a cap cutting off mid-task is a bug, not a design | Making `for i in range(10)` the stopping mechanism |
| Choosing agent vs. workflow | Let the model pick the next tool based on context (agentic) for high-ambiguity tasks | Agent value = reasoning about which tool fits the situation | Hard-coding a fixed tool sequence and calling it an "agent" |
| Tool ran but model "forgot" the result | Check the result was appended to `messages` before the next API call | The model only knows what's in the conversation history | Assuming the API remembers tool executions between calls — it's stateless |

---

## 1.2 — Hub-and-Spoke Multi-Agent Orchestration

### Concepts in plain words

The pattern the exam wants: a **coordinator** (hub) that decomposes the task, delegates to specialized **subagents** (spokes), aggregates results, and handles all errors. Subagents never talk to each other — **all communication routes through the coordinator**, which buys you observability, consistent error handling, and controlled information flow. Subagents run with **isolated context**: they do NOT inherit the coordinator's conversation history. The coordinator should **dynamically select** which subagents to invoke based on query complexity — not push everything through the full pipeline every time.

The two failure modes the exam tests: (1) **overly narrow task decomposition** — coordinator splits "impact of AI on creative industries" into three visual-arts subtasks, so music/writing/film never get covered; every subagent succeeds at its assigned task, but the assignment itself was wrong (sample Q7 — root cause is the coordinator, not the downstream agents). (2) No **iterative refinement**: a good coordinator evaluates synthesis output for gaps, re-delegates targeted queries to search/analysis subagents, and re-invokes synthesis until coverage is sufficient — one pass through the pipeline is rarely enough for broad topics.

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Final report misses whole subtopics; each subagent completed its task fine | Fix the **coordinator's decomposition** — it was too narrow | Subagents can only cover what they're assigned | Blaming the search agent's queries or synthesis agent's gap-detection (downstream agents worked correctly within scope) |
| Two subagents keep researching the same sources | Partition scope: assign distinct subtopics or source types per agent | Coordinator owns deduplication at assignment time | Letting agents self-coordinate or dedupe after the fact |
| Synthesis output has coverage gaps | Iterative refinement loop: coordinator detects gaps → re-delegates targeted queries → re-runs synthesis | Coordinator owns quality control | Shipping the first synthesis pass; asking synthesis to "try harder" |
| Simple query hits a 4-agent pipeline | Coordinator analyzes the query and invokes only the needed subagents | Dynamic selection cuts latency/cost | Always routing through the full pipeline regardless of complexity |
| Where should subagent-to-subagent messages flow? | Through the coordinator, always | Observability, consistent error handling, controlled info flow | Direct spoke-to-spoke channels ("mesh") — loses central control |
| Subagent needs the coordinator's earlier findings | Coordinator includes them explicitly in the subagent's prompt | Isolated context — no automatic inheritance | Assuming the subagent "can see" the parent conversation |

---

## 1.3 — Subagent Invocation, Context Passing, Parallel Spawning

### Concepts in plain words

In the Agent SDK, subagents are spawned via the **Task tool** — and the coordinator's **`allowedTools` must include `"Task"`** or it can't delegate at all (classic exam gotcha for "coordinator never invokes subagents"). Each subagent type is configured with an **`AgentDefinition`**: a description (so the coordinator knows when to use it), a system prompt, and tool restrictions. Subagents don't inherit parent context and don't share memory between invocations — **everything they need goes explicitly into their prompt**, including complete findings from prior agents (e.g., pass the web-search results AND document-analysis output into the synthesis agent's prompt).

```python
from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions

options = ClaudeAgentOptions(
    allowed_tools=["Task"],          # REQUIRED or the coordinator cannot spawn subagents
    agents={
        "web-searcher": AgentDefinition(
            description="Searches the web for sources on a subtopic",
            prompt="You are a research searcher. Return findings as structured "
                   "claim/source/date records.",
            tools=["WebSearch"],     # tool restriction: only what the role needs
        ),
        "synthesizer": AgentDefinition(
            description="Combines findings into a cited report",
            prompt="Synthesize the findings provided in your prompt. Preserve source attribution.",
            tools=[],                # no search tools — synthesis only
        ),
    },
)
```

Two more skills the exam grades: (1) **Parallel spawning** — the coordinator emits **multiple Task tool calls in a single response**; separate turns = sequential = slow. (2) **Structured context passing** — separate content from metadata (source URLs, document names, page numbers) so attribution survives handoffs; don't paste one undifferentiated text blob. And write coordinator prompts that state **research goals and quality criteria, not step-by-step procedures** — procedural scripts kill subagent adaptability.

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Coordinator never delegates / can't spawn subagents | Add `"Task"` to the coordinator's `allowedTools` | Task tool IS the spawning mechanism | Rewriting the coordinator prompt to "delegate more" when the tool isn't even available |
| Synthesis agent produces output ignoring earlier research | Include complete prior findings directly in the synthesis agent's prompt | Subagents have isolated context — no inheritance, no shared memory | Expecting the subagent to access the parent's history or a previous invocation's state |
| Citations lost between agents | Pass structured data: content separated from metadata (URL, doc name, page) | Attribution must be carried explicitly through each handoff | Passing a flattened summary blob and hoping sources survive |
| Independent subtopics, latency matters | Emit multiple Task tool calls **in one coordinator response** | Single-response calls run in parallel | Spawning one per turn (sequential) — works, but slow; exam marks it wrong for "parallel" |
| Subagents are rigid, fail on unexpected findings | Coordinator prompt gives goals + quality criteria | Adaptability requires room to reason | Step-by-step procedural instructions in the delegation prompt |
| Want to compare two approaches from one shared analysis | `fork_session` from the analysis baseline (see 1.7) | Independent branches, shared starting context | Re-running the whole analysis twice, or doing both in one session (cross-contamination) |

---

## 1.4 — Programmatic Enforcement vs. Prompt Guidance + Structured Handoffs

### Concepts in plain words

The single highest-yield judgment in this domain: **prompt instructions are probabilistic; hooks and prerequisite gates are deterministic.** A system-prompt rule ("always verify the customer first") has a **non-zero failure rate** — fine for style, unacceptable for money. When compliance MUST be guaranteed (identity verification before financial operations, refund caps), enforce it in code: a **programmatic prerequisite gate** that blocks `process_refund` / `lookup_order` until `get_customer` has returned a verified customer ID (this is sample Q1 — answer A, the gate; B/C are prompt/few-shot = probabilistic; D fixes tool *availability* when the problem is tool *ordering*).

```python
verified_customer_id = None

def gate(tool_name, tool_input):
    if tool_name in ("lookup_order", "process_refund") and verified_customer_id is None:
        return {"blocked": True,
                "reason": "Run get_customer and verify identity first."}
    return {"blocked": False}
```

Two more testable skills: (1) **Multi-concern decomposition** — a customer message with three issues gets split into distinct items, each investigated **in parallel using shared context**, then synthesized into one unified resolution (not answered issue-by-issue across turns, not mashed together). (2) **Structured handoff on escalation** — the human agent receiving the case has NO transcript access, so the handoff must be a compiled summary: **customer ID, root cause analysis, refund amount, recommended action**. "Escalate" without the packet just moves the problem.

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Agent skips identity verification before refunds (12% of cases) | Programmatic prerequisite: block downstream tools until `get_customer` returns a verified ID | Financial ops need deterministic compliance | "Strengthen the system prompt" / "add few-shot examples" — still probabilistic; routing classifier — fixes availability, not ordering |
| Business rule must NEVER be violated | Enforce in code (hook / gate) | Zero failure rate required | Prompt instruction — non-zero failure rate by definition |
| Rule is a soft preference (tone, formatting) | Prompt guidance is fine | Cheap, flexible, failures are low-cost | Building enforcement infrastructure for style rules (over-engineering) |
| Customer raises 3 issues in one message | Decompose into distinct items → investigate each in parallel with shared context → synthesize one unified resolution | Complete coverage + coherent response | Handling only the first issue, or serial one-per-turn handling |
| Escalating mid-process to a human with no transcript access | Compile structured handoff: customer ID, root cause, refund amount, recommended action | The human must act without the conversation history | Escalating with just "customer needs help" or assuming transcript visibility |

---

## 1.5 — Agent SDK Hooks (PostToolUse Normalization + Tool-Call Interception)

### Concepts in plain words

Hooks are code that runs at fixed points in the agent lifecycle — **deterministic guarantees**, versus prompt instructions' **probabilistic compliance**. Two patterns the exam names:

1. **PostToolUse** — intercepts **tool results** before the model sees them. Canonical use: normalizing heterogeneous data from different MCP tools (one returns Unix timestamps, another ISO 8601; one returns numeric status codes, another strings) into a single consistent format so the agent reasons over clean data.
2. **Tool-call interception** (PreToolUse-style) — intercepts **outgoing tool calls** before they execute, to enforce compliance rules: block `process_refund` when `amount > 500` and redirect to a human-escalation workflow.

```python
async def normalize_dates(input_data, tool_use_id, context):
    # PostToolUse: rewrite the tool result BEFORE the model processes it
    result = input_data["tool_response"]
    return {"tool_response": to_iso8601(result)}   # unix ts / mixed formats → ISO 8601

async def refund_cap(input_data, tool_use_id, context):
    # Tool-call interception: block policy-violating calls, redirect
    if input_data["tool_name"] == "process_refund" and input_data["tool_input"]["amount"] > 500:
        return {"decision": "block",
                "reason": "Refunds over $500 require human approval — escalate_to_human."}
```

Direction is the memory hook: **Post = results coming back (transform data). Interception = calls going out (block/allow policy).**

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| MCP tools return dates/statuses in incompatible formats; agent misreads them | **PostToolUse hook** normalizing results before the model processes them | Deterministic, fixes it once for every tool call | Prompt instruction "convert all timestamps" — probabilistic, burns tokens, fails intermittently |
| Refunds over $500 must always go to a human | **Tool-call interception hook**: block the call, redirect to escalation workflow | Guaranteed compliance on a hard business rule | System prompt "never refund more than $500" — will eventually be violated |
| Choosing hooks vs. prompt for a rule | Hooks when the rule requires **guaranteed** compliance; prompt when best-effort is acceptable | Deterministic vs. probabilistic — that's the whole test | Treating them as interchangeable "it usually works" |
| Need to transform what the model sees vs. control what executes | Transform results → PostToolUse. Control execution → interception | Different lifecycle points, different jobs | Picking the hook on the wrong side of the tool call |

---

## 1.6 — Task Decomposition: Prompt Chaining vs. Dynamic Adaptive

### Concepts in plain words

Two decomposition strategies, matched to task shape. **Prompt chaining** = fixed sequential pipeline, right when the steps are known upfront and predictable — e.g., a code review split into per-file local analysis passes plus a separate cross-file integration pass. The split exists to avoid **attention dilution**: one pass over 14 files produces inconsistent depth, missed bugs, and contradictory findings (flagging a pattern in one file, approving it in another — sample Q12; bigger context window does NOT fix attention quality). **Dynamic adaptive decomposition** = generate subtasks based on what each step discovers, right for open-ended work — e.g., "add comprehensive tests to a legacy codebase": first map the structure, identify high-impact areas, then build a prioritized plan that **adapts as dependencies are discovered**.

```text
Prompt chaining (predictable, multi-aspect review):
  pass 1..n: analyze each file individually (local issues)
  pass n+1:  cross-file integration pass (data flow between files)

Dynamic decomposition (open-ended investigation):
  step 1: map codebase structure
  step 2: identify high-impact areas          ← informed by step 1
  step 3: prioritized plan, adapts as         ← informed by step 2,
          dependencies are discovered            revised during execution
```

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Multi-aspect review with known, predictable steps | Prompt chaining — fixed sequential passes | Steps are enumerable upfront; each pass gets full attention | Dynamic planning overhead for a task that never changes shape |
| Open-ended task ("add comprehensive tests to legacy code") | Dynamic adaptive: map → identify high-impact → prioritized plan that adapts | You can't enumerate subtasks before discovery | Locking a fixed pipeline before you know the codebase |
| 14-file PR review: inconsistent depth, missed bugs, contradictions | Per-file local passes + separate cross-file integration pass | Attention dilution is the root cause; focused passes fix it | Bigger context window (doesn't fix attention); forcing devs to split PRs (shifts burden); consensus-of-3-runs (suppresses intermittently-caught real bugs) |
| Cross-file bugs slip through per-file review | Add the dedicated integration pass — don't fatten the per-file passes | Local and cross-file analysis are different concerns | One giant pass "looking at everything" again |

---

## 1.7 — Session State: --resume, fork_session, Stale-Context Judgment

### Concepts in plain words

Claude Code / Agent SDK sessions persist and can be continued: **`--resume <session-name>`** picks up a specific named prior conversation (e.g., a multi-day investigation session). **`fork_session`** creates **independent branches from a shared analysis baseline** — analyze the codebase once, fork twice, explore two testing strategies or refactoring approaches in parallel without cross-contamination and without paying for the analysis again.

The judgment the exam grades is **staleness**. If code changed since the session's tool results were captured, those Read/Grep outputs in history are now lies the model will trust. Rules: prior context **mostly valid** → resume, and **explicitly tell the agent which files changed** so it re-analyzes just those (targeted re-analysis beats full re-exploration). Prior tool results **substantially stale** → **start a NEW session and inject a structured summary** of validated findings — more reliable than resuming on top of stale data.

```bash
claude --resume payment-refactor-investigation   # continue a named session
# resuming after edits? first message:
# "Since last session, src/billing/refunds.py and tests/test_refunds.py changed — re-read those."
```

```python
options = ClaudeAgentOptions(resume=analysis_session_id, fork_session=True)
# → new independent branch; the original session stays untouched
```

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Continue yesterday's named investigation, code untouched | `--resume <session-name>` | Prior context is still valid; resumption is cheapest | Starting fresh and re-exploring everything (wasted work) |
| Resuming after a few files changed | Resume + explicitly name the changed files for targeted re-analysis | Agent otherwise trusts stale tool results in history | Resuming silently (agent reasons from stale reads); full re-exploration (overkill) |
| Most prior tool results are now stale | New session + inject a structured summary of validated findings | Fresh context with curated facts beats history full of stale data | `--resume` "to keep context" — keeping wrong context is worse than none |
| Compare two strategies from one shared codebase analysis | `fork_session` twice from the analysis baseline | Independent branches, no cross-contamination, analysis paid for once | Both experiments in one session (they bleed into each other); redoing analysis per branch |

---

## Memorize Cold — Domain 1 Flashcards

| Prompt | Answer |
|---|---|
| `stop_reason` value meaning "run the tool, loop again" | `"tool_use"` |
| `stop_reason` value meaning "task complete, exit loop" | `"end_turn"` |
| How tool results return to the model | Appended to conversation history as `tool_result` blocks (in a `user`-role message), keyed by `tool_use_id` |
| The ONLY valid loop-termination signal | `stop_reason == "end_turn"` — never text parsing, never an iteration cap as primary |
| Mechanism for spawning subagents | The **Task tool** |
| Requirement for a coordinator to invoke subagents | `allowedTools` must include `"Task"` |
| `AgentDefinition` configures… | description, system prompt, tool restrictions (per subagent type) |
| Do subagents inherit parent context? | **No** — isolated context; no automatic inheritance, no shared memory between invocations; pass everything explicitly in the prompt |
| How to run subagents in parallel | Multiple Task tool calls **in a single coordinator response** (not across turns) |
| Multi-agent topology the exam wants | Hub-and-spoke: ALL inter-subagent communication routes through the coordinator |
| Why route through the coordinator (3 reasons) | Observability, consistent error handling, controlled information flow |
| Coordinator's four jobs | Task decomposition, delegation, result aggregation, dynamic subagent selection |
| Named decomposition risk | Overly narrow decomposition → incomplete coverage of broad topics (root cause lives in the coordinator) |
| Iterative refinement loop | Coordinator evaluates synthesis for gaps → re-delegates targeted queries → re-invokes synthesis until coverage is sufficient |
| Coordinator prompt style | Research goals + quality criteria — NOT step-by-step procedures |
| Context-passing format between agents | Structured data separating content from metadata (source URLs, document names, page numbers) to preserve attribution |
| Prompt guidance vs. programmatic enforcement | Prompt = probabilistic (non-zero failure rate); hooks/gates = deterministic. Financial/compliance rules ⇒ programmatic |
| Canonical prerequisite gate | Block `lookup_order` / `process_refund` until `get_customer` returns a verified customer ID |
| Structured handoff fields (escalation to a human without transcript access) | Customer ID, root cause, refund amount, recommended action |
| Multi-concern request pattern | Decompose into distinct items → investigate in parallel with shared context → synthesize one unified resolution |
| Hook that transforms tool **results** before the model sees them | **PostToolUse** (e.g., normalize Unix timestamps / ISO 8601 / numeric status codes across MCP tools) |
| Hook that blocks outgoing tool **calls** | Tool-call interception (e.g., block refunds > **$500**, redirect to human escalation) |
| When hooks over prompts | Whenever business rules require **guaranteed** compliance |
| Prompt chaining is for… | Fixed sequential pipelines with predictable steps (e.g., per-file passes + cross-file integration pass) |
| Dynamic adaptive decomposition is for… | Open-ended tasks — subtasks generated from what each step discovers (map → high-impact areas → adaptive prioritized plan) |
| Why split per-file + integration passes | Attention dilution in single large passes (inconsistent depth, missed bugs, contradictory findings) — larger context does NOT fix it |
| Flag to continue a specific named session | `--resume <session-name>` |
| Feature for divergent branches from a shared analysis baseline | `fork_session` |
| Resuming after code changed | Explicitly inform the agent which files changed → targeted re-analysis |
| When prior tool results are stale | Start a NEW session with an injected structured summary — more reliable than resuming |
| Model-driven vs. pre-configured | Agent = Claude reasons about the next tool from context; decision tree / fixed sequence = not agentic |

---

## Anti-Pattern Wall — Recognize on Sight

These are named in the exam guide as wrong answers. If an option matches one, kill it.

| # | Anti-pattern | Why it's wrong | Correct alternative |
|---|---|---|---|
| 1 | **Parsing natural-language signals for loop termination** ("check if the reply says 'done'") | Fragile text matching when a machine-readable signal exists | Key off `stop_reason == "end_turn"` |
| 2 | **Arbitrary iteration cap as the primary stopping mechanism** | Cuts off legitimate work mid-task; cap is a safety net only | `stop_reason`-driven termination |
| 3 | **Checking assistant text content as a completion indicator** | Text alongside a `tool_use` block isn't a final answer | Inspect `stop_reason` |
| 4 | **Prompt instructions for deterministic compliance** (identity checks, refund caps) | Non-zero failure rate; unacceptable for financial operations | Programmatic gates / tool-call interception hooks |
| 5 | **Assuming subagents inherit parent context** | Isolated context; no automatic inheritance or shared memory | Pass complete findings explicitly in the subagent prompt |
| 6 | **Spawning "parallel" subagents across separate turns** | Sequential execution — latency stacks | Multiple Task calls in one response |
| 7 | **Step-by-step procedural delegation prompts** | Kills subagent adaptability | Goals + quality criteria |
| 8 | **Always running the full subagent pipeline** | Ignores query complexity; wastes latency/cost | Coordinator dynamically selects subagents |
| 9 | **Spoke-to-spoke (mesh) subagent communication** | No observability, inconsistent error handling, uncontrolled info flow | Route everything through the coordinator |
| 10 | **Blaming downstream agents for coverage gaps** when the coordinator's decomposition was too narrow | Subagents executed their assigned scope correctly | Fix the coordinator's task decomposition |
| 11 | **One giant review pass over many files** (or "just use a bigger context window") | Attention dilution — context size doesn't fix attention quality | Per-file passes + separate cross-file integration pass |
| 12 | **Resuming a session on top of stale tool results** | Model reasons from outdated reads as if true | New session + structured summary; or resume + explicitly name changed files |
| 13 | **Escalating to a human without a structured handoff packet** | Receiving agent has no transcript access | Customer ID + root cause + refund amount + recommended action |
| 14 | **Hard-coded tool sequences sold as "agentic"** | That's a decision tree, not model-driven reasoning | Let Claude choose the next tool from context |

---

## How Domain 1 Questions Are Built (test-taking read)

Every D1 question is a scenario + a failure symptom (or requirement) + four moves. The scoring pattern across the sample questions:

1. **Root cause beats symptom patch.** Minimal tool descriptions? Fix the descriptions, not few-shot examples. Coverage gaps? Fix the coordinator's decomposition.
2. **Deterministic beats probabilistic when money/compliance is involved.** Gate/hook > prompt, every time the stakes are financial.
3. **Proportionate beats over-engineered.** Prompt-level fix that addresses the root cause > routing classifiers, separate ML models, new infrastructure. If prompt optimization hasn't been tried and the cause is unclear boundaries, try it first.
4. **The distractor that "solves a different problem"** is always there — e.g., tool *availability* offered when the problem is tool *ordering* (sample Q1 option D). Name the actual problem before reading the options.
