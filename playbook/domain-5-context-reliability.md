# Domain 5 — Context Management & Reliability (15%)

~9 of 60 questions. D5 is a **primary domain in 4 of the 6 scenarios**: S1 Customer Support Agent, S2 Claude Code codegen, S3 Multi-Agent Research, S6 Structured Extraction. So even at 15% weight, D5 judgment shows up everywhere.

The whole domain is one idea: **context is a lossy, finite resource, and LLM self-assessment is unreliable — so you protect critical facts structurally, escalate on explicit signals, propagate errors with detail, and verify accuracy with real measurement, not vibes.**

---

## 5.1 — Preserve critical information across long interactions

### What it means
Long conversations degrade in two ways. (1) **Summarization loss**: when you progressively summarize history, exact numbers, dates, percentages, and customer-stated expectations get blurred into "customer wants a refund for a recent order." (2) **Lost in the middle**: models reliably attend to the *beginning and end* of long inputs but drop findings from the middle. On top of that, **verbose tool results pile up** — an order lookup returns 40+ fields when only ~5 matter — burning tokens on junk. The fixes are structural, not prompt magic:

- Pull **transactional facts** (amounts, dates, order numbers, statuses) into a persistent **"case facts" block** injected into *every* prompt, *outside* the summarized history. Summaries can lose detail; the case-facts block cannot.
- **Trim tool outputs to relevant fields before they enter context**, not after.
- **Put the key-findings summary at the beginning** of aggregated inputs; organize detail under explicit section headers — mitigates position effects.
- Pass **complete conversation history** in each API request for coherence (the API is stateless — you own the transcript).
- When downstream agents have tight context budgets, make **upstream agents return structured data** (key facts, citations, relevance scores, dates, source locations, methodological context) instead of verbose prose + reasoning chains.

```python
# Case-facts block: extracted once, injected verbatim every turn — never summarized
case_facts = {
    "order_id": "ORD-88214",
    "amount": 149.99,
    "order_date": "2026-06-12",
    "status": "delivered",
    "customer_expectation": "full refund, not store credit",
}

def trim_order(raw: dict) -> dict:
    """40+ fields come back; only return-relevant ones enter context."""
    keep = ("order_id", "status", "amount", "delivery_date", "return_window_ends")
    return {k: raw[k] for k in keep if k in raw}

messages = [
    {"role": "user", "content":
        f"<case_facts>{json.dumps(case_facts)}</case_facts>\n"
        f"<history_summary>{summary}</history_summary>\n"
        f"{new_user_message}"}
]
```

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Long support session; summarization is dropping amounts/dates | Extract transactional facts into a persistent case-facts block in every prompt, outside summarized history | Summaries condense numbers into vagueness; a verbatim block can't drift | "Improve the summarization prompt" — still probabilistic loss |
| Multi-issue session (3 orders, 2 disputes) | Persist structured issue data (order IDs, amounts, statuses) in a separate context layer | Keeps issues from bleeding into each other across turns | One mega-summary mixing all issues |
| Order lookups dump 40+ fields, context fills fast | Trim tool output to the ~5 relevant fields *before* it accumulates in context | Tool results consume tokens disproportionately to relevance | Bigger context window / summarize later — junk already cost you attention |
| Aggregated multi-source input; middle findings get ignored | Key-findings summary at the **beginning**, details under explicit section headers | Lost-in-the-middle: start/end are reliable, middle isn't | Assuming the model reads all positions equally |
| Synthesis agent misinterprets subagent findings | Require subagents to include metadata (dates, source locations, methodological context) in structured outputs | Downstream synthesis needs the context that prose drops | Passing raw prose findings and hoping |
| Downstream agent has limited context budget | Modify **upstream** agents to emit structured data (key facts, citations, relevance scores), not verbose content + reasoning chains | Fix the producer, not the consumer | Truncating downstream input arbitrarily |
| Multi-turn API app loses thread | Send complete conversation history each request | API is stateless; coherence is your job | Sending only the latest message |

---

## 5.2 — Escalation and ambiguity resolution

### What it means
The exam wants you to know the **three legitimate escalation triggers** and the **two famous fakes**. Legit: (1) customer **explicitly asks for a human**, (2) **policy exception or gap** — policy is silent/ambiguous on this exact request, (3) agent **can't make meaningful progress**. Fakes: **sentiment** (frustration ≠ complexity — an angry customer with a simple damage claim should get resolution, not a queue) and **self-reported confidence scores** (LLMs are poorly calibrated — the agent is already wrongly confident on the hard cases, so asking it to rate itself measures nothing). The fix for bad escalation calibration is **explicit escalation criteria in the system prompt with few-shot examples** showing escalate-vs-resolve — this was sample question 3, answer A. And when a lookup returns **multiple matching customers**, the agent must **ask for additional identifiers**, never pick one by heuristic ("most recent account").

```python
SYSTEM = """Escalate to a human ONLY when:
1. The customer explicitly requests a human — comply immediately, no investigation first.
2. Policy does not cover the request (e.g., competitor price match when policy
   only covers own-site adjustments).
3. You cannot make meaningful progress after using available tools.

Do NOT escalate for: customer frustration alone, case difficulty you can still
work, or low confidence feelings.

If a lookup returns multiple matches, ask for another identifier
(email, order #, billing zip). Never guess which record is theirs.

<example>Customer: "This is ridiculous, third damaged item this year!" +
photo of damage → In policy, agent capability: acknowledge frustration,
process the replacement. Do not escalate.</example>
<example>Customer: "I just want to talk to a person." → Escalate immediately.</example>
"""
```

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Agent escalates easy cases, autonomously botches policy-exception cases (55% FCR vs 80% target) | Explicit escalation criteria + few-shot escalate-vs-resolve examples in the system prompt | Root cause is unclear decision boundaries; proportionate first fix | Self-reported confidence threshold (uncalibrated), sentiment routing (wrong signal), separate classifier model (over-engineered before prompt work) |
| Customer explicitly says "give me a human" | Escalate immediately, without attempting investigation first | Explicit request is an absolute trigger | "Let me just try one lookup first" |
| Customer is furious but the issue is a standard in-policy fix | Acknowledge frustration, offer resolution; escalate only if they **reiterate** wanting a human | Sentiment doesn't correlate with complexity | Auto-escalate on negative sentiment |
| Request hits a policy gap (competitor price match; policy covers only own-site) | Escalate — policy exceptions/gaps are for humans | Agent has no authority to invent policy | Agent improvises a "reasonable" exception |
| get_customer returns 3 matches for "John Smith" | Ask for an additional identifier (email, order #, zip) | Wrong-account actions are unrecoverable | Heuristic pick (most recent, best fuzzy match) |
| Want automated escalation signal | Encode explicit *criteria* (categories of case), not confidence scores | Criteria are checkable; confidence is vibes | `if self_confidence < 7: escalate` |

---

## 5.3 — Error propagation across multi-agent systems

### What it means
When a subagent fails, what flows back to the coordinator determines whether recovery is possible. A generic `"search unavailable"` gives the coordinator nothing to act on. **Structured error context** — failure type, the attempted query, any partial results, and potential alternative approaches — lets the coordinator decide: retry modified query? alternative source? proceed with partials? (Sample question 8, answer A.) Order of operations: **subagents recover locally first** (retry transient timeouts themselves) and propagate only what they can't fix, *with* partials and what was attempted. Two hard distinctions the exam loves: an **access failure** (timeout — a retry decision is needed) is not a **valid empty result** (query succeeded, zero matches — that's a real answer, don't retry it). And when synthesis runs on incomplete inputs, the output must carry **coverage annotations**: which findings are well-supported vs. which topic areas have gaps because a source was unavailable.

This is the multi-agent layer above D2's `isError` / `errorCategory` / `isRetryable` tool-level pattern — same philosophy, one level up.

```python
# Subagent → coordinator failure payload (after local retries were exhausted)
{
  "status": "error",
  "failure_type": "timeout",              # not "operation failed"
  "attempted": "web_search('EU AI Act enforcement 2026')",
  "local_recovery": "2 retries w/ backoff, both timed out",
  "partial_results": [ {...3 findings gathered before timeout...} ],
  "alternatives": ["narrow query to official EU sources", "use document corpus instead"]
}

# Synthesis output on incomplete inputs → annotate coverage, don't fake completeness
{
  "well_supported": ["finding A (3 sources)", "finding B (2 sources)"],
  "coverage_gaps": ["enforcement timeline — web search unavailable, not covered"]
}
```

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Web-search subagent times out; design the failure flow | Return structured error context: failure type + attempted query + partial results + alternatives | Coordinator can choose retry / re-route / proceed-with-partials | Generic "search unavailable" after silent internal retries — hides everything actionable |
| Subagent hits a transient failure | Recover **locally** (retry/backoff) first; propagate only unresolvable errors, with partials + what was attempted | Don't make the coordinator manage every blip | Propagating every transient error up, or retrying forever silently |
| Query returns zero rows | Report as **valid empty result** (success, no matches) — distinct from access failure | Retrying a correct empty answer wastes turns; treating timeout as "no data" fabricates a conclusion | One `null`-ish return shape for both cases |
| One subagent fails mid-pipeline | Proceed with partial results; annotate the gap | Single failure shouldn't zero out all completed work | Terminating the whole workflow on one failure |
| Tempted to keep output "clean" | Never return empty results marked as success after a failure | Silent suppression prevents any recovery and yields confidently incomplete reports | `except: return []` |
| Synthesis ran with a missing source | Coverage annotations: well-supported findings vs. gap areas due to unavailable sources | Consumers must know what the report *doesn't* cover | Uniformly confident final report |

---

## 5.4 — Context management in large-codebase exploration

### What it means
Extended exploration sessions degrade in a recognizable way: the model starts giving **inconsistent answers** and citing **"typical patterns"** instead of the *specific classes it discovered earlier* — that phrase is the exam's symptom fingerprint for context degradation. Four mitigations, and questions hinge on picking the right one:

1. **Scratchpad files** — the agent writes key findings to a file and re-reads it for later questions. Findings survive context boundaries because they're on disk, not in the window.
2. **Subagent delegation** — spawn subagents for verbose investigations ("find all test files," "trace refund flow dependencies"); the main agent keeps only summaries and stays a high-level coordinator.
3. **Phase summaries** — summarize each exploration phase's key findings *before* spawning the next phase's subagents, injecting the summary into their initial context.
4. **/compact** — Claude Code command to compress the current session's context when it fills with verbose discovery output.

For long-running multi-agent jobs that might die: **crash recovery via manifests** — each agent exports structured state to a **known location**; on resume the coordinator **loads the manifest** and injects state into agent prompts. No re-exploration from zero.

```text
project/
├── .scratch/
│   ├── findings.md          # agent-maintained scratchpad: key classes, file:line refs
│   └── manifest.json        # crash-recovery state, exported to a KNOWN location
└── src/ ...

# manifest.json — coordinator loads this on resume, injects into agent prompts
{
  "phase": "2-trace-dependencies",
  "completed": ["1-map-structure"],
  "agents": {
    "test-finder":  {"status": "done",    "output": ".scratch/test-files.md"},
    "refund-tracer":{"status": "partial", "last_file": "src/billing/refund.py"}
  }
}
```

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Model starts citing "typical patterns" instead of specific classes it found earlier | Maintain a scratchpad file of key findings; reference it for subsequent questions | Disk persists; context degrades | Re-asking the model to "remember carefully" |
| Need verbose investigation (find all test files, trace a flow) mid-task | Spawn a subagent for the question; main agent keeps high-level coordination | Verbose output stays in the subagent's context, only the summary returns | Main agent Grep/Reads everything itself and drowns |
| Multi-phase exploration, phase 1 done | Summarize phase-1 key findings, inject the summary into phase-2 subagents' initial context | Subagents don't inherit context; fresh agents need the distilled state | Assuming the next phase "knows" what phase 1 found |
| Extended session, context filling with discovery output | `/compact` | Purpose-built to reduce context usage in-session | Starting over from scratch, losing everything |
| Long multi-agent job could crash/be interrupted | Each agent exports structured state to a known location; coordinator loads the manifest on resume and injects it into prompts | Resume from state, not from zero | Relying on session history surviving a crash |

---

## 5.5 — Human review workflows and confidence calibration

### What it means
"97% overall accuracy" is the exam's bait number: **aggregate accuracy masks per-segment failure** — the system can be 99.5% on invoices and 71% on handwritten receipts and still average 97%. Before you reduce human review, you must **segment accuracy by document type AND by field** and verify every segment holds. Two mechanisms make ongoing quality measurable: (1) **stratified random sampling** of *high-confidence* extractions — humans review a random slice of the stuff you'd otherwise auto-pass, which measures the true error rate up there and catches **novel error patterns** confidence scores won't flag; (2) **field-level confidence scores calibrated against a labeled validation set** — raw LLM confidence numbers are meaningless until you've mapped "model says 0.9" to an observed accuracy on labeled data, and only then do you set the auto-accept threshold. Routing: **low confidence OR ambiguous/contradictory source documents → human review**, so limited reviewer capacity goes where errors live.

```python
def route(extraction: dict, thresholds: dict) -> str:
    # thresholds were CALIBRATED per-field on a labeled validation set —
    # not guessed, not the model's raw self-assessment taken at face value
    if extraction["source_flags"].get("ambiguous_or_contradictory"):
        return "human_review"
    if any(conf < thresholds[field]
           for field, conf in extraction["field_confidence"].items()):
        return "human_review"
    if random.random() < 0.05:          # stratified sample of high-confidence
        return "human_review_sample"    # → ongoing error rate + novel patterns
    return "auto_accept"
```

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| "97% accurate — can we drop human review?" | Segment accuracy by document type and by field first; reduce review only if all segments hold | Aggregates mask segment-level failure | Trusting the headline number |
| Auto-accepting high-confidence extractions | Stratified random sampling of high-confidence extractions for ongoing human review | Measures real error rate in the auto-pass lane; detects novel error patterns | Only reviewing low-confidence items — you never learn your high-confidence error rate |
| Want confidence-based routing | Model outputs field-level confidence → calibrate thresholds on a **labeled validation set** → then route | Raw LLM confidence is uncalibrated; labels anchor it to observed accuracy | Using self-reported scores directly as thresholds (same failure as 5.2) |
| Limited reviewer capacity | Route low-confidence + ambiguous/contradictory-source extractions to humans first | Prioritizes review where errors concentrate | Uniform random review of everything, or review by document order |
| One field type keeps failing inside a "good" doc type | Per-field accuracy analysis, not per-document | Field-level granularity finds it; doc-level averages hide it | Whole-document accuracy as the only metric |

---

## 5.6 — Provenance and uncertainty in multi-source synthesis

### What it means
Every summarization step is a chance to sever the claim→source link. The fix is **structured claim-source mappings** that subagents *emit* and downstream agents are *required to preserve and merge*: each finding carries claim, evidence excerpt, source URL/document name, and **publication or data-collection date**. Dates matter because two credible sources reporting different numbers may not conflict at all — one is 2023 data, one is 2025; without dates, **temporal differences masquerade as contradictions**. When sources genuinely conflict, the rule is: **keep both values, annotate the conflict with attribution** — the analysis agent completes its work with conflicting values included and explicitly flagged, and the **coordinator decides how to reconcile** before synthesis. Never let a mid-pipeline agent silently pick a winner. Reports should **separate well-established findings from contested ones**, preserving original source characterizations and methodological context. And rendering is content-type-appropriate: **financial data as tables, news as prose, technical findings as structured lists** — not one uniform format.

```python
# Subagent finding — the unit that must survive synthesis intact
{
  "claim": "EU AI enforcement fines totaled EUR 287M",
  "evidence_excerpt": "…regulators levied 287 million euros in fines…",
  "source": {"url": "https://…", "document": "EC enforcement report", "published": "2025-11-02"},
  "relevance": 0.92
}

# Genuine conflict → annotate, attribute, escalate the reconciliation decision
{
  "field": "market_size_2025",
  "conflict_detected": True,
  "values": [
    {"value": "42B", "source": "Gartner note",   "published": "2025-03-01"},
    {"value": "55B", "source": "McKinsey report", "published": "2025-09-15"}
  ]
  # coordinator reconciles; synthesis never silently picks one
}
```

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Final report has claims but no idea which source said what | Subagents output structured claim-source mappings (URL, document name, excerpt); synthesis must preserve and merge them | Attribution is lost at summarization steps unless structurally carried | "Add citations at the end" — the link is already gone |
| Two credible sources give different statistics | Include **both** values, annotated with source attribution; coordinator decides reconciliation before synthesis | No agent has grounds to arbitrate mid-pipeline | Analysis agent silently picks the "more credible" number |
| Sources "contradict" on a time-varying metric | Require publication/collection dates in structured outputs | 2023-vs-2025 data isn't a contradiction, it's a timeline | Flagging temporal differences as conflicts (or averaging them) |
| Report mixes solid and shaky findings uniformly | Explicit sections: well-established vs. contested; preserve original source characterizations + methodological context | Readers must see the epistemic split | Uniform confident tone over everything |
| Synthesis flattens everything to prose | Render per content type: financial → tables, news → prose, technical → structured lists | Format is part of fidelity | One-format-fits-all output |
| Passing findings between agents | Structured formats separating content from metadata (URLs, doc names, page numbers) | Preserves attribution across handoffs (ties to D1 context passing) | Concatenated prose blobs |

---

## Memorize cold

**Weights & mechanics**
- D5 = **15%** of scored content ≈ 9/60 questions; exam = 60 Qs / 120 min / pass 720 of 1000 scaled.
- D5 is primary in scenarios **1, 2, 3, 6** (support agent, Claude Code codegen, multi-agent research, extraction).

**5.1 context preservation**
- Case-facts block = **amounts, dates, order numbers, statuses + customer-stated expectations** — in **every prompt, outside summarized history**.
- Lost-in-the-middle: reliable at **beginning and end**, drops **middle** → key-findings summary **first**, then explicit section headers.
- Canonical waste number: **40+ fields** returned per order lookup, **~5 relevant** → trim **before** accumulation.
- Multi-turn coherence = pass **complete conversation history** each API request.
- Downstream budget fix = change **upstream** agents to emit structured data (key facts, citations, relevance scores) instead of verbose prose + reasoning chains.

**5.2 escalation**
- Valid triggers (3): **explicit customer request** (immediate, no investigation first) · **policy exception/gap** · **no meaningful progress**.
- Invalid proxies (2): **sentiment**, **self-reported confidence** (LLM confidence is poorly calibrated — already wrong on hard cases).
- Calibration fix = **explicit criteria + few-shot escalate-vs-resolve examples in the system prompt** (sample Q3 answer).
- Frustrated + in-policy → acknowledge, offer resolution; escalate only if customer **reiterates**.
- Multiple customer matches → **request additional identifiers**; never heuristic selection.

**5.3 error propagation**
- Structured error context (4 parts): **failure type · attempted query · partial results · alternative approaches** (sample Q8 answer).
- Order: **local recovery first** (transient → retry in subagent), propagate only unresolvable, **with partials + what was attempted**.
- **Access failure ≠ valid empty result** (timeout needs a retry decision; empty = successful query, no matches).
- Named anti-patterns: generic status ("search unavailable"), **silent suppression** (empty-as-success), **whole-workflow termination** on one failure.
- Incomplete synthesis → **coverage annotations**: well-supported findings vs. gap areas from unavailable sources.
- (D2 tool-level cousins: `isError` flag, `errorCategory` transient/validation/permission, `isRetryable` boolean.)

**5.4 large-codebase context**
- Degradation fingerprint: inconsistent answers + citing **"typical patterns"** instead of specific classes discovered earlier.
- Four tools: **scratchpad files** (findings persist across context boundaries) · **subagent delegation** (verbose output isolated; main agent = high-level coordinator) · **phase summaries** (summarize before spawning next phase, inject into initial context) · **`/compact`** (reduce in-session context bloat).
- Crash recovery: each agent **exports state to a known location**; coordinator **loads the manifest on resume** and injects into agent prompts.
- (Adjacent, other domains: Explore subagent = D3; `--resume <name>` / `fork_session` = D1.)

**5.5 human review & calibration**
- Bait number: **97% aggregate accuracy** can mask per-segment failure → segment by **document type AND field** before reducing review.
- **Stratified random sampling of HIGH-confidence extractions** → measures true auto-pass error rate + detects **novel error patterns**.
- Confidence pipeline: model emits **field-level confidence** → **calibrate thresholds on a labeled validation set** → route.
- Human-review routing: **low confidence OR ambiguous/contradictory source documents** first.

**5.6 provenance**
- Claim-source mapping fields: **claim, evidence excerpt, source URL/document name, publication (or data-collection) date**; synthesis must **preserve and merge**, never drop.
- Conflicting credible stats → **both values + source attribution**; **coordinator** reconciles before synthesis.
- **Publication dates** prevent temporal differences reading as contradictions.
- Report structure: **well-established vs. contested** sections, preserving original characterizations + methodological context.
- Rendering: **financial → tables, news → prose, technical → structured lists**.

---

## Anti-pattern wall — recognize on sight

| Anti-pattern | Where | Why it's wrong |
|---|---|---|
| Progressive summarization of transactional facts | 5.1 | Numbers, dates, expectations blur into vagueness; use a case-facts block |
| Letting raw 40-field tool dumps accumulate in context | 5.1 | Tokens spent disproportionately to relevance; trim before entry |
| Burying key findings mid-input | 5.1 | Lost-in-the-middle drops them; lead with the summary |
| Verbose prose + reasoning chains handed to a context-tight downstream agent | 5.1 | Fix the upstream producer: structured facts, citations, scores |
| **Sentiment-based escalation** | 5.2 | Frustration ≠ complexity; angry-but-simple cases deserve resolution |
| **Self-reported confidence as escalation/routing signal** | 5.2, 5.5 | LLM confidence is uncalibrated — wrongly confident exactly on hard cases |
| Investigating first when the customer explicitly asked for a human | 5.2 | Explicit request = immediate escalation |
| Heuristic selection among multiple customer matches | 5.2 | Wrong-account actions; ask for another identifier |
| Separate ML classifier for escalation before trying prompt criteria | 5.2 | Over-engineering; explicit criteria + few-shot is the proportionate first fix |
| Generic error statuses ("Operation failed", "search unavailable") | 5.3 | Hides failure type/partials/alternatives; coordinator can't recover |
| **Silent error suppression** — returning empty results marked success | 5.3 | Failure becomes invisible; confidently incomplete output |
| **Terminating the entire workflow on a single subagent failure** | 5.3 | Discards all completed work; proceed with partials + coverage gaps |
| Conflating access failures with valid empty results | 5.3 | One triggers retry decisions; the other IS the answer |
| Relying on in-window memory for multi-hour exploration | 5.4 | Context degrades to "typical patterns"; use scratchpads/subagents/manifests |
| Main agent doing verbose discovery itself | 5.4 | Drowns coordination context; delegate to subagents |
| No exported state in long multi-agent jobs | 5.4 | A crash means full re-exploration; export manifests to a known location |
| Trusting aggregate accuracy to cut human review | 5.5 | Masks per-doc-type/per-field failure; segment first |
| Reviewing only low-confidence extractions | 5.5 | High-confidence error rate stays unknown; stratified-sample the auto-pass lane |
| Raw model confidence as a routing threshold without labeled calibration | 5.5 | Uncalibrated numbers; validate against labels first |
| Summarization that strips claim-source links | 5.6 | Attribution unrecoverable later; carry structured mappings through |
| Mid-pipeline agent silently picking one of two conflicting values | 5.6 | Annotate both with attribution; coordinator reconciles |
| Omitting publication dates from findings | 5.6 | Temporal differences get misread as contradictions |
| Flattening all content types to one uniform format | 5.6 | Tables for financial, prose for news, lists for technical |
