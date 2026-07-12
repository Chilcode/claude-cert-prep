# Scenario 1 — Customer Support Resolution Agent

> **Exam frame:** You're building a customer support resolution agent with the **Claude Agent SDK**. It handles high-ambiguity requests (returns, billing disputes, account issues) through four custom MCP tools: `get_customer`, `lookup_order`, `process_refund`, `escalate_to_human`. Target: **80%+ first-contact resolution** while knowing when to escalate.
>
> **Domains tested here:** D1 Agentic Architecture & Orchestration (27%), D2 Tool Design & MCP Integration (18%), D5 Context Management & Reliability (15%). That's 60% of the exam weight concentrated in one scenario. Questions 1–3 in the guide's sample set come from this scenario — all three are dissected below.

---

## 1. The system at a glance

One agent, one loop, four tools, two enforcement layers. No subagents needed — this is a **single-agent loop** with programmatic guardrails wrapped around the tool calls.

Components:

- **The agentic loop** — send request → check `stop_reason` → if `"tool_use"`, execute tools, append results to history, loop; if `"end_turn"`, reply to the customer. The model decides which tool to call next based on context (model-driven), not a hardcoded decision tree.
- **Four MCP tools** — each with a detailed description (input formats, example queries, edge cases, boundaries vs. similar tools) and structured error responses (`errorCategory`, `isRetryable`, human-readable message, MCP `isError` flag).
- **Enforcement layer (code, not prompt)** — a programmatic prerequisite gate that blocks `lookup_order`/`process_refund` until `get_customer` has returned a verified customer ID, plus a tool-call interception hook that blocks refunds over $500 and redirects to human escalation.
- **PostToolUse hook** — normalizes heterogeneous data from different backend systems (Unix timestamps vs. ISO 8601, numeric status codes) and trims 40-field order payloads to the ~5 fields that matter, *before* the model sees them.
- **Context layer** — a persistent "case facts" block (amounts, dates, order IDs, statuses, customer-stated expectations) injected into every request, outside the summarized conversation history.
- **Escalation path** — `escalate_to_human` takes a **structured handoff** (customer ID, root cause, refund amount, recommended action) because the human agent has no access to the transcript.

```
 Customer message
       │
       ▼
┌──────────────────────── AGENTIC LOOP ────────────────────────┐
│  messages + case-facts block ──► Claude (Agent SDK)          │
│                                     │                        │
│              stop_reason == "end_turn"? ──yes──► reply       │
│                                     │ no ("tool_use")        │
│                                     ▼                        │
│   ┌── ENFORCEMENT (deterministic, in code) ──────────────┐   │
│   │ prerequisite gate: get_customer verified first?      │   │
│   │ interception hook: refund > $500 → block → escalate  │   │
│   └───────────────┬──────────────────────────────────────┘   │
│                   ▼                                          │
│     MCP tools:  get_customer  lookup_order                   │
│                 process_refund  escalate_to_human            │
│                   │                                          │
│   ┌── PostToolUse hook ──────────────────────────────────┐   │
│   │ normalize timestamps/status codes, trim to           │   │
│   │ relevant fields, structured errors pass through      │   │
│   └───────────────┬──────────────────────────────────────┘   │
│                   ▼                                          │
│     tool_result appended to messages ──► next iteration      │
└──────────────────────────────────────────────────────────────┘
       │
       └──► escalate_to_human(customer_id, root_cause,
             refund_amount, recommended_action)  [human has no transcript]
```

The exam's core thesis for this scenario: **anything with financial consequences gets deterministic enforcement in code; everything judgment-shaped (tool selection, escalation calibration) gets fixed with descriptions and few-shot examples in the prompt.** Nearly every question maps back to that split.

---

## 2. Build it step by step

Build order matters because each layer depends on the one before it. Loop mechanics shown against the raw Messages API (`anthropic` Python package) — that's the stable surface and what the exam's `stop_reason`/`tool_choice` questions describe. Agent-SDK-specific concepts (hooks, `AgentDefinition`, `allowedTools`) are labeled sketches using the exam guide's exact terminology.

### Step 1 — Tool contracts first (descriptions + JSON schemas)

Tools before loop, because **tool descriptions are the primary mechanism the model uses for tool selection**. `get_customer` and `lookup_order` both take an identifier string — with minimal descriptions ("Retrieves customer information" / "Retrieves order details") the model will misroute. Each description must state: input formats, example queries, edge cases, and boundaries vs. the similar tool.

```python
TOOLS = [
    {
        "name": "get_customer",
        "description": (
            "Look up and verify a customer's identity in the CRM. Call this FIRST, "
            "before any order or refund operation. Input: an email address "
            "(e.g. 'jane@example.com') or a customer ID (format CUST-######). "
            "Does NOT accept order numbers — use lookup_order for those. "
            "Returns a verified customer_id, account status, and contact info. "
            "If multiple customers match, all candidates are returned — ask the "
            "user for an additional identifier instead of guessing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "identifier": {
                    "type": "string",
                    "description": "Email address or CUST-###### customer ID",
                }
            },
            "required": ["identifier"],
        },
    },
    {
        "name": "lookup_order",
        "description": (
            "Retrieve details for a specific order. Input: an order number "
            "(format ORD-#####, e.g. from 'check my order #12345'). Requires a "
            "verified customer first (get_customer). Does NOT accept emails or "
            "customer IDs — use get_customer for identity. Returns order status, "
            "items, amounts, and dates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "ORD-##### order number"},
                "customer_id": {"type": "string", "description": "Verified CUST-###### ID"},
            },
            "required": ["order_id", "customer_id"],
        },
    },
    {
        "name": "process_refund",
        "description": (
            "Issue a refund for an order. Only call after get_customer has verified "
            "identity AND lookup_order has confirmed the order belongs to that "
            "customer. Refunds over $500 are blocked by policy and must go through "
            "escalate_to_human instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "customer_id": {"type": "string"},
                "amount": {"type": "number", "description": "Refund amount in USD"},
                "reason": {"type": "string"},
            },
            "required": ["order_id", "customer_id", "amount", "reason"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Hand the case to a human agent. The human has NO access to this "
            "conversation transcript, so every field must be complete and "
            "self-contained. Use when: the customer explicitly asks for a human, "
            "policy is ambiguous or silent on the request, you cannot make "
            "meaningful progress, or a refund exceeds the $500 policy limit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "root_cause": {"type": "string", "description": "Your analysis of the underlying issue"},
                "refund_amount": {"type": "number", "description": "Requested/blocked amount, if any"},
                "recommended_action": {"type": "string", "description": "What the human should do"},
            },
            "required": ["customer_id", "root_cause", "recommended_action"],
        },
    },
]
```

The escalation schema is not decoration — the guide names those exact four fields (customer ID, root cause, refund amount, recommended action) as the structured handoff for humans who lack transcript access.

### Step 2 — The agentic loop (control flow on `stop_reason`, nothing else)

The lifecycle the exam tests: send request → inspect `stop_reason` (`"tool_use"` vs `"end_turn"`) → execute requested tools → return results for the next iteration. Tool results are appended to conversation history so the model can reason about the next action.

```python
import anthropic

client = anthropic.Anthropic()

def run_agent(user_message: str, case_facts: str) -> str:
    messages = [{"role": "user", "content": f"{case_facts}\n\n{user_message}"}]

    while True:
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=4096,
            system=SYSTEM_PROMPT,          # escalation criteria + few-shot (Step 6)
            tools=TOOLS,
            messages=messages,             # full history every time — API is stateless
        )

        # Whole assistant turn goes into history, tool_use blocks included
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Model is done — final customer-facing text
            return next(b.text for b in response.content if b.type == "text")

        if response.stop_reason == "tool_use":
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    output = execute_tool(block.name, block.input)   # Steps 3-5
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,     # must match the tool_use block
                        "content": output,
                    })
            # All results go back in ONE user message; loop continues
            messages.append({"role": "user", "content": results})
```

**Anti-patterns the exam names as wrong answers:** parsing natural-language signals ("I'm finished") to decide termination, setting an arbitrary iteration cap as the *primary* stopping mechanism, or checking whether the assistant produced text content as a completion indicator. `stop_reason` is the only loop-control signal.

`tool_choice` stays `"auto"` here (the default) — a support agent must be able to answer conversationally. `"any"` forces *some* tool call every turn; forced selection (`{"type": "tool", "name": "..."}`) forces one specific tool. Know all three for D2, but know that forced `tool_choice` is **not** how you enforce tool *ordering* — that's the next step.

### Step 3 — Structured error responses in every tool

Generic `"Operation failed"` blocks intelligent recovery. Each tool returns structured error metadata using the MCP `isError` flag pattern: an `errorCategory` (transient / validation / business / permission), an `isRetryable` boolean, and a human-readable description.

```python
import json, time

def execute_tool(name: str, args: dict) -> str:
    gate_error = check_prerequisites(name, args)      # Step 4
    if gate_error:
        return gate_error
    try:
        return json.dumps(BACKENDS[name](args))
    except BackendTimeout:
        return json.dumps({
            "isError": True,
            "errorCategory": "transient",
            "isRetryable": True,
            "message": "Order service timed out. Safe to retry.",
        })
    except PolicyViolation as e:
        return json.dumps({
            "isError": True,
            "errorCategory": "business",
            "retriable": False,   # guide's wording for business-rule violations
            "message": (
                f"Refund denied: {e.reason}. This is a policy decision, not a "
                "system error — explain it to the customer; do not retry."
            ),
        })
```

Two distinctions the exam drills:
- **Transient vs. business vs. validation vs. permission** — the category tells the agent whether to retry, rephrase input, explain to the customer, or escalate.
- **Access failure vs. valid empty result.** A timeout ("couldn't reach the order system") and "this customer has no orders" must look different. Empty-but-successful is a *result*, not an error — returning it as an error triggers pointless retries; returning a timeout as an empty success silently corrupts the answer.

### Step 4 — Programmatic prerequisite gate (identity before money)

The scenario's signature question. Production shows the agent skipping `get_customer` in 12% of cases and refunding misidentified accounts. Prompt instructions ("verification is MANDATORY") and few-shot examples are **probabilistic** — a non-zero failure rate is unacceptable when errors have financial consequences. The fix is a programmatic prerequisite that **blocks downstream tool calls until `get_customer` has returned a verified customer ID**:

```python
session_state = {"verified_customer_id": None}
GATED_TOOLS = {"lookup_order", "process_refund"}

def check_prerequisites(name: str, args: dict) -> str | None:
    if name in GATED_TOOLS and session_state["verified_customer_id"] is None:
        return json.dumps({
            "isError": True,
            "errorCategory": "validation",
            "isRetryable": False,
            "message": ("Blocked: customer identity not verified. Call get_customer "
                        "with the customer's email or CUST ID first."),
        })
    return None

# set on success inside the get_customer backend wrapper:
#   session_state["verified_customer_id"] = result["customer_id"]
```

The blocked call comes back as a tool result, so the model reads it, calls `get_customer`, and self-corrects — but the *guarantee* lives in code. This is Sample Question 1: answer A (programmatic prerequisite) beats B (system prompt), C (few-shot), and D (routing classifier — which fixes tool *availability*, not tool *ordering*, the wrong problem).

### Step 5 — Agent SDK hooks: interception + PostToolUse normalization

Two hook patterns, both D1 Task 1.5. Sketch code — the concepts and names (`PostToolUse`, tool call interception, hooks-for-deterministic-guarantees) are what the exam tests, not exact SDK signatures.

**Tool call interception — enforce the $500 refund policy:**

```python
# Agent SDK concept sketch — intercepts OUTGOING tool calls before execution
async def block_large_refunds(tool_name: str, tool_input: dict):
    if tool_name == "process_refund" and tool_input["amount"] > 500:
        return {
            "decision": "block",
            "reason": ("Policy: refunds over $500 require human approval. "
                       "Call escalate_to_human with a structured handoff "
                       "(customer_id, root_cause, refund_amount, recommended_action)."),
        }
    # returning nothing lets the call proceed
```

Block **and redirect to the alternative workflow** (escalation) — don't just fail. Same principle as Step 4: business rules that require *guaranteed* compliance go in hooks; prompt instructions are for probabilistic steering.

**PostToolUse — normalize heterogeneous tool results before the model processes them:**

```python
# Agent SDK concept sketch — PostToolUse hook: transform results BEFORE the model sees them
RELEVANT_ORDER_FIELDS = {"order_id", "status", "total", "delivery_date", "refund_eligible"}

async def normalize_results(tool_name: str, result: dict) -> dict:
    if tool_name == "lookup_order":
        # Different backends disagree: Unix timestamps vs ISO 8601, numeric status codes
        result["delivery_date"] = to_iso8601(result["delivery_date"])
        result["status"] = STATUS_CODE_MAP.get(result["status"], result["status"])
        # Trim 40+ fields to the ~5 return-relevant ones before they hit context
        result = {k: v for k, v in result.items() if k in RELEVANT_ORDER_FIELDS}
    return result
```

Why a hook and not a prompt instruction ("convert all timestamps to ISO 8601")? Deterministic transformation, zero model attention spent, and it doubles as context hygiene (D5): raw order lookups carry 40+ fields when only ~5 are relevant — trimming *before* they accumulate is the guide's stated fix for tool results consuming tokens disproportionately to their relevance.

**Agent SDK framing for the rest:** the agent is configured via an **AgentDefinition** (description, system prompt, tool restrictions). This scenario doesn't need subagents, but know the trigger facts anyway: subagents are spawned with the **Task tool**, the coordinator's **allowedTools must include "Task"**, subagents do **not** inherit the parent's conversation history — context is passed explicitly in the prompt — and **fork_session** creates independent branches from a shared baseline. Multi-concern requests here ("wrong item AND double-charged AND locked account") don't need subagents — decompose into distinct items, investigate each (in parallel where possible) with shared context, then synthesize one unified resolution.

### Step 6 — Escalation criteria in the system prompt (with few-shot)

Escalation calibration is a *judgment* problem, so it lives in the prompt — explicit criteria plus 2–4 few-shot examples demonstrating escalate-vs-resolve, showing the *reasoning* for why one action beat the plausible alternative.

```python
SYSTEM_PROMPT = """You are a customer support resolution agent.

ESCALATE (call escalate_to_human) when:
- The customer explicitly asks for a human — escalate immediately, do NOT
  investigate first.
- Policy is ambiguous or silent on the request (e.g. competitor price matching
  when policy only covers own-site adjustments).
- You cannot make meaningful progress after reasonable investigation.
- A refund exceeds the $500 policy limit.

RESOLVE AUTONOMOUSLY when:
- The case fits standard policy (e.g. damage replacement with photo evidence),
  even if the customer sounds frustrated. Acknowledge the frustration, offer the
  resolution; escalate only if they reiterate wanting a human.

NEVER escalate based on: customer sentiment alone, or your own confidence level.
Complexity is judged against policy coverage, not tone.

If get_customer returns multiple matches, ask for an additional identifier
(order number, phone, billing zip). Never pick a match heuristically.

<example>
Customer: "My blender arrived shattered, here's a photo. I want a replacement."
Reasoning: standard damage claim with evidence — squarely inside policy.
Action: resolve autonomously (verify, confirm order, process replacement).
</example>
<example>
Customer: "Competitor sells this for $40 less, match it or I return everything."
Reasoning: policy covers own-site price adjustments only; silent on competitor
matching. Policy gap → not my call.
Action: escalate_to_human with root cause and recommended action.
</example>
<example>
Customer: "This is ridiculous, I've been waiting a week. Where is my package?!"
Reasoning: frustrated, but the issue (shipment tracking) is fully within my
capability. Sentiment is not complexity.
Action: acknowledge frustration, look up the order, resolve.
</example>"""
```

This is Sample Question 3: 55% FCR because the agent escalates easy cases and freelances hard ones → the root cause is **unclear decision boundaries**, fixed with explicit criteria + few-shot (answer A). Not self-reported confidence scores (LLM confidence is poorly calibrated — the agent is already wrongly confident on hard cases), not a trained classifier (over-engineered before prompt optimization is tried), not sentiment analysis (sentiment doesn't correlate with case complexity).

### Step 7 — The case-facts context layer

Long, multi-issue conversations get summarized; progressive summarization **condenses numerical values, percentages, dates, and customer-stated expectations into vague summaries**. Defense: extract transactional facts into a persistent block included in *each* prompt, outside the summarized history.

```python
case_facts = """<case_facts>
customer_id: CUST-004821 (verified)
order_id: ORD-99120 | total: $129.99 | delivered: 2026-06-30
issue_1: damaged item, photo provided | status: refund pending
issue_2: duplicate charge $129.99 on 2026-07-01 | status: investigating
customer_expectation: full refund to card, NOT store credit
</case_facts>"""
```

Update it as tools return facts; for multi-issue sessions persist per-issue structured data (order IDs, amounts, statuses) as its own context layer. Companion rules from D5 Task 5.1: pass complete conversation history in each API request (the loop in Step 2 already does), and when aggregating long inputs, put key-findings summaries at the **beginning** with explicit section headers — models reliably process the beginning and end of long inputs but drop the middle ("lost in the middle").

---

## 3. The decision points this scenario tests

Situation → correct move → why → the trap. These map directly to task statements 1.1, 1.4, 1.5, 2.1–2.3, 5.1–5.3.

### D1 — Loop and enforcement (Tasks 1.1, 1.4, 1.5)

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| When does the loop stop? | Continue while `stop_reason == "tool_use"`, terminate on `"end_turn"` | Deterministic API signal, the only reliable one | Parsing assistant text for "done", iteration caps as the primary stop, treating presence of text as completion |
| Model just called a tool | Execute it, append `tool_result` (matching `tool_use_id`) to history, request again | The model needs the result in context to reason about the next action | Dropping results, starting a fresh conversation, sending results without the assistant's `tool_use` turn |
| Who decides which tool runs next? | The model, from context (model-driven decision-making) | That's what makes it an agent handling high-ambiguity requests | Pre-configured decision trees / fixed tool sequences |
| Identity must be verified before refunds | Programmatic prerequisite gate blocking `lookup_order`/`process_refund` until `get_customer` returns a verified ID | Prompt compliance is probabilistic; financial errors need deterministic guarantees | "Strengthen the system prompt", "add few-shot", routing classifier (fixes availability, not ordering) |
| Refunds over $500 forbidden | Tool call interception hook: block + redirect to `escalate_to_human` | Hooks give guaranteed compliance; also route to the alternative workflow, don't just fail | A `MUST NOT` line in the prompt; blocking without offering escalation |
| Tools return mixed formats (Unix ts / ISO 8601 / numeric codes) | PostToolUse hook normalizes results before the model processes them | Deterministic transformation; no model attention wasted | Prompt instruction "convert timestamps"; per-tool duplicate parsing logic |
| Customer message contains 3 distinct issues | Decompose into distinct items, investigate each in parallel with shared context, synthesize one unified resolution | Coverage of every concern without context fragmentation | Answering the first issue only; forcing the customer to re-ask; one subagent per issue with no shared context |
| Escalating mid-process | Structured handoff: customer ID, root cause, refund amount, recommended action | The human agent has no access to the conversation transcript | "Escalating now" with no payload; dumping the raw transcript |

### D2 — Tool design (Tasks 2.1, 2.2, 2.3)

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Agent calls `get_customer` for "check my order #12345"; both tools have minimal descriptions | **First step:** expand descriptions — input formats, example queries, edge cases, boundaries vs. similar tools | Descriptions are the primary tool-selection mechanism; low-effort, high-leverage, fixes the root cause | Few-shot first (token overhead, doesn't fix root cause), keyword routing layer (over-engineered, bypasses NLU), consolidating into one `lookup_entity` tool (valid architecture, too much for a "first step") |
| Two tools overlap functionally | Rename + rewrite descriptions to eliminate overlap; split generic tools into purpose-specific ones with defined I/O contracts | Ambiguous/overlapping descriptions cause misrouting | Adding more prompt rules about which to prefer |
| Tool selection ignores good descriptions | Review the **system prompt** for keyword-sensitive instructions creating unintended tool associations | System prompt wording can override well-written descriptions | Rewriting descriptions again; adding a router |
| Tool fails | Structured error: `errorCategory` (transient/validation/business/permission) + `isRetryable` + human-readable message, via the MCP `isError` flag | The agent needs metadata to choose retry vs. explain vs. escalate | Uniform `"Operation failed"` — prevents any recovery decision |
| Refund denied by policy | `retriable: false` + customer-friendly explanation | Agent won't waste retries and can communicate the reason appropriately | Returning it as a generic/transient error → retry storm |
| Query succeeds but finds nothing | Return valid empty result, clearly distinct from access failure | Empty ≠ broken; conflating them causes wrong retries or silent data loss | Timeout returned as empty success; empty result returned as error |
| How many tools should the agent see? | Only the 4–5 its role needs (scoped access) | Too many tools (e.g. 18) degrades selection reliability | "Give it everything for flexibility" |
| Must guarantee a tool call (any tool) | `tool_choice: "any"` | `"auto"` may return conversational text instead | Assuming `"auto"` guarantees a call |
| Must guarantee one *specific* tool runs first | Forced selection `tool_choice: {"type": "tool", "name": "..."}`, then follow-up turns for subsequent steps | Only forced selection pins the exact tool | Using `"any"` and hoping; using forced tool_choice as a substitute for a prerequisite gate across turns |

### D5 — Context, escalation, reliability (Tasks 5.1, 5.2, 5.3)

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Long conversation; amounts/dates drift or vanish | Persistent case-facts block (amounts, dates, order numbers, statuses, stated expectations) in every prompt, outside summarized history | Progressive summarization condenses exact values into vague prose | "Summarize more often/better"; bigger context window |
| Order lookups return 40+ fields, 5 relevant | Trim tool outputs to relevant fields before they accumulate in context | Tool results consume tokens disproportionately to relevance | Larger context window (cost + lost-in-the-middle, not a fix) |
| Aggregating long multi-part input | Key-findings summary at the beginning + explicit section headers | Lost-in-the-middle: beginning and end are processed reliably, middle isn't | Dumping sections in arbitrary order |
| Customer explicitly demands a human | Escalate **immediately**, no investigation first | Explicit customer request is a first-class escalation trigger | "Let me just try to resolve it first" |
| Customer is angry but the issue is simple | Acknowledge frustration + offer resolution; escalate only if they reiterate | Sentiment is an unreliable proxy for complexity | Auto-escalation on negative sentiment threshold |
| Policy is silent (competitor price match) | Escalate — policy exception/gap | The agent can't invent policy | Improvising a "reasonable" answer; refusing outright |
| Agent escalates easy cases, attempts hard ones (FCR 55%) | Explicit escalation criteria + few-shot escalate-vs-resolve examples in the system prompt | Root cause is unclear decision boundaries; proportionate fix before infrastructure | Self-reported confidence thresholds (poorly calibrated), trained escalation classifier (over-engineered), sentiment routing (wrong problem) |
| `get_customer` returns multiple matches | Ask the customer for additional identifiers | Heuristic selection risks misidentified accounts and wrong refunds | Picking most-recent/best-match account |
| Backend failure mid-case | Structured error context: failure type, what was attempted, partial results, alternatives; local recovery for transient errors first | Enables intelligent recovery decisions | Generic "service unavailable" after silent retries; suppressing the error as empty success; killing the whole workflow on one failure |

---

## 4. Failure-modes drill

Production symptom → root cause → fix. This is the shape of the actual exam questions — read the symptom, name the root cause *before* looking at options, then find the option that fixes that root cause (not a different problem).

**1. Skipped verification.**
*Symptom:* In 12% of cases the agent calls `lookup_order` with just the customer's stated name, never calling `get_customer`; occasional wrong-account refunds.
*Root cause:* Tool ordering enforced only by prompt language — probabilistic compliance on a rule with financial consequences.
*Fix:* Programmatic prerequisite that blocks `lookup_order` and `process_refund` until `get_customer` has returned a verified customer ID. (Not: stronger prompt, few-shot, or a routing classifier — the last one changes which tools are *available*, not their *order*.)

**2. Misrouted lookups.**
*Symptom:* "Check my order #12345" routes to `get_customer` instead of `lookup_order`. Both descriptions are one-liners and both tools accept similar identifier formats.
*Root cause:* Minimal, near-identical tool descriptions — the model has nothing to differentiate on.
*Fix (first step):* Expand each description with input formats, example queries, edge cases, and when-to-use-this-vs-that boundaries. Few-shot, routing layers, and tool consolidation are all second-line or over-engineered.

**3. Miscalibrated escalation.**
*Symptom:* 55% first-contact resolution vs. 80% target. Logs show escalation of standard damage claims (with photo evidence) while the agent freelances policy-exception cases.
*Root cause:* No explicit escalation decision boundaries in the system prompt.
*Fix:* Explicit escalation criteria + few-shot examples demonstrating escalate vs. resolve. (Not confidence self-scores — the agent is already miscalibrated; not a separate ML classifier; not sentiment analysis.)

**4. Retry storm on a policy denial.**
*Symptom:* A refund outside the return window fails; the agent retries `process_refund` three times, then tells the customer "there's a system issue."
*Root cause:* The tool returns a uniform generic error, so the agent can't distinguish a business-rule violation from a transient fault.
*Fix:* Structured error responses: `errorCategory: "business"`, `retriable: false`, plus a customer-friendly explanation the agent can relay.

**5. Numbers drift late in the conversation.**
*Symptom:* Forty turns into a billing dispute, the agent offers a "$89.99 refund" for a $129.99 order and forgets the customer refused store credit.
*Root cause:* Progressive summarization condensed transactional facts (amounts, dates, stated expectations) into vague summary prose.
*Fix:* Extract transactional facts into a persistent case-facts block included in every prompt, outside the summarized history.

**6. Context exhaustion from tool bloat.**
*Symptom:* Multi-issue sessions blow the context budget after a handful of order lookups; late-conversation answers degrade.
*Root cause:* Each `lookup_order` result carries 40+ fields into history when only ~5 are relevant — tool results accumulate tokens disproportionately to relevance.
*Fix:* Trim tool outputs to relevant fields before they enter context (natural home: the PostToolUse hook). Not "buy a bigger context window."

**7. Empty result treated as outage (and vice versa).**
*Symptom:* Customer with no purchase history asks about orders; the agent retries the "failing" lookup, then reports the order system is down. Separately, a real timeout once returned `[]` and the agent confidently said "you have no orders."
*Root cause:* The tool conflates access failures with valid empty results.
*Fix:* Distinguish them structurally — empty-with-success is a normal result; timeouts are `errorCategory: "transient"`, `isRetryable: true`.

**8. Escalations bounce back.**
*Symptom:* Human agents reject or re-triage most escalated tickets, asking "who is this customer and what do they want?"
*Root cause:* The handoff carried no context — human agents have no access to the conversation transcript.
*Fix:* `escalate_to_human` requires a structured handoff summary: customer ID, root cause, refund amount, recommended action — complete and self-contained.

---

## Memorize-this recap

1. Loop control = `stop_reason` only: `"tool_use"` → run tools and continue; `"end_turn"` → done. Text-parsing and iteration caps are named anti-patterns.
2. Deterministic rule (verify-before-refund, $500 cap) → enforce in code: prerequisite gates and interception hooks. Judgment call (tool choice, escalation) → fix in prompt: descriptions and few-shot.
3. Wrong tool selected? Fix descriptions **first** — they're the primary selection mechanism.
4. Every tool error carries `errorCategory` + `isRetryable` + readable message; business denials get `retriable: false` + customer-friendly wording.
5. Valid empty result ≠ access failure. Ever.
6. Escalate on: explicit customer request (immediately), policy gap, no meaningful progress. Never on sentiment or self-reported confidence.
7. Multiple customer matches → ask for another identifier, never guess.
8. Facts with digits in them (amounts, dates, IDs, statuses) live in a persistent case-facts block, not in summarized history.
9. Trim and normalize tool results (PostToolUse) *before* they accumulate in context.
10. Escalation handoff = customer ID + root cause + refund amount + recommended action; the human never sees your transcript.
