# Domain 4 — Prompt Engineering & Structured Output (20% of exam)

**~12 of 60 questions.** Feeds two scenarios directly: **Scenario 5 (Claude Code for CI — code review prompts, false positives)** and **Scenario 6 (Structured Data Extraction — JSON schemas, validation, batching)**. If either scenario is drawn, this domain is where those points live.

Six task statements. Each decoded below: plain-words concept → decision-rules table. Then one Memorize-Cold section and the Anti-Pattern Wall for the whole domain.

---

## 4.1 — Explicit criteria beat vague instructions (precision / false positives)

### Concepts in plain words

When a review prompt says "be conservative" or "only report high-confidence findings," the model has no operational definition of *conservative* — precision doesn't improve. What works is **explicit categorical criteria**: name the categories to report, name the categories to skip. "Flag comments only when claimed behavior contradicts actual code behavior" is testable; "check that comments are accurate" is not.

Why the exam cares: **false positives destroy developer trust**, and the damage spreads — a noisy category makes devs ignore the *accurate* categories too. The exam-approved emergency move is to **temporarily disable a high-FP category** while you fix its prompt, rather than let it poison the whole review system.

For severity classification, the fix is the same shape: define each severity level with **concrete code examples**, not adjectives.

```text
# BAD (confidence-based filtering — exam marks this wrong)
Review this PR. Be conservative and only report issues you are
highly confident about.

# GOOD (categorical criteria)
Report ONLY:
- Bugs: logic errors, null-handling failures, off-by-one errors
- Security: injection, auth bypass, secrets in code
Do NOT report:
- Minor style (naming, formatting)
- Patterns local to this codebase (see examples below)

Severity levels — classify using these anchors:
- critical: e.g. `query = f"SELECT * WHERE id={user_input}"`  (injection)
- major:    e.g. missing null check before `.items[0]`
- minor:    e.g. unused import
```

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Automated review floods PRs with false positives | Write specific criteria: which categories to report (bugs, security) vs skip (minor style, local patterns) | Categorical criteria are operational; the model can apply them | "Add 'be conservative' / 'only high-confidence findings' to the prompt" — vague instructions don't improve precision |
| One review category has a high FP rate, devs are losing trust | **Temporarily disable** that category while improving its prompt | High-FP categories undermine confidence in accurate categories; protect trust first | Keep it running while tuning, or lower a global confidence threshold |
| Severity labels are inconsistent across runs | Define explicit severity criteria with a **concrete code example per level** | Anchored examples produce consistent classification | Prose definitions of "critical/major/minor" without examples |
| Reviewer flags legitimate codebase-local patterns as issues | Enumerate the acceptable patterns explicitly (and see 4.2 — few-shot the distinction) | The model can't know your conventions unless told | Assuming a smarter model or bigger context fixes it |

---

## 4.2 — Few-shot prompting for consistency, ambiguity, and FP reduction

### Concepts in plain words

Few-shot examples are the **most effective single technique** when detailed instructions alone still produce inconsistent output. The exam's magic number: **2–4 targeted examples** (the "iterative refinement" statement in D3 says 2–3 for input/output transformations — same idea). "Targeted" means examples chosen for the **ambiguous cases**, showing the *reasoning* for why one action beat the plausible alternative — not 8 examples of the easy case.

Four exam-tested jobs few-shot does:
1. **Ambiguous-case handling** — e.g., which tool to pick for an ambiguous request, or what counts as a branch-level test coverage gap.
2. **Format consistency** — demonstrate the exact output shape (location, issue, severity, suggested fix).
3. **False-positive reduction** — show pairs: *this pattern is acceptable in our codebase* vs *this is a genuine issue*. The model then **generalizes the judgment to novel patterns** — it doesn't just memorize the listed cases.
4. **Extraction from varied document structures** — inline citations vs bibliographies, methodology sections vs embedded details, informal measurements. This reduces hallucination and fixes empty/null extraction of fields that *are* present but formatted unusually.

```text
Example 1 (ambiguous case — show the reasoning):
Input: "check my order #12345"
Correct action: lookup_order
Why: the request contains an order ID and asks about an order;
get_customer would be wrong even though a customer is implied.

Example 2 (acceptable pattern vs genuine issue):
ACCEPTABLE: `except Exception: log.warn(...)` in our telemetry
wrappers (established local pattern — do not flag)
GENUINE ISSUE: `except Exception: pass` swallowing errors in
payment flow (flag as major)
```

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Detailed instructions still give inconsistently formatted output | 2–4 few-shot examples demonstrating the exact format (location, issue, severity, suggested fix) | Examples beat prose for format transfer | Writing even longer prose instructions |
| Model mishandles ambiguous edge cases | Few-shot examples of the ambiguous cases **with reasoning** why one action beat the alternatives | Model generalizes the judgment to novel cases | Examples of only the obvious/easy cases; or 5–8 examples when 2–4 targeted ones suffice |
| Extraction returns empty/null for required fields that exist in oddly-formatted docs | Few-shot examples showing correct extraction from the varied formats (inline citations vs bibliographies, informal measurements) | Demonstrates structural variety the model must tolerate | Making the fields required in the schema (that causes fabrication — see 4.3) |
| Review flags acceptable local code patterns | Few-shot pairs distinguishing acceptable patterns from genuine issues | Reduces FPs while still generalizing | Blanket "don't flag style" without examples |
| Tool misrouting between two similar tools, descriptions are minimal | **Fix tool descriptions first** (Domain 2), not few-shot | Descriptions are the primary selection mechanism; few-shot adds token overhead without fixing root cause | Sample Q2 distractor: "add 5–8 few-shot routing examples" |

---

## 4.3 — Structured output via tool_use + JSON schemas

### Concepts in plain words

The **most reliable** way to get schema-compliant output: define a tool whose `input_schema` *is* your output schema, make the model call it, and read your data out of the `tool_use` content block. This **eliminates JSON syntax errors** (no markdown fences, no trailing commas). It does **not** eliminate **semantic errors** — line items that don't sum to the total, values placed in the wrong field. That gap is what 4.4's validation loops exist for.

`tool_choice` has exactly three modes:
- `{"type": "auto"}` — model *may* call a tool or may just answer in text. Not a guarantee.
- `{"type": "any"}` — model **must call some tool**, its choice which. Use when you have multiple extraction schemas and don't know the document type.
- `{"type": "tool", "name": "extract_metadata"}` — **forced**: model must call that specific tool. Use to guarantee a particular extraction runs (e.g., metadata before enrichment).

Schema design rules the exam grades:
- Fields that may be **absent from the source → optional/nullable**. A required field forces the model to invent a value to satisfy the schema. Nullable = anti-fabrication.
- **Enums for categories**, plus `"unclear"` for ambiguous cases and `"other"` **+ a detail string field** so novel categories don't get force-fit into wrong buckets.
- Strict schema handles output shape; put **format normalization rules in the prompt** (e.g., "convert all dates to ISO 8601") to handle inconsistent *source* formatting.

```python
import anthropic
client = anthropic.Anthropic()

tools = [{
    "name": "record_invoice",
    "description": "Record structured data extracted from an invoice.",
    "input_schema": {
        "type": "object",
        "properties": {
            "vendor": {"type": "string"},
            "po_number": {"type": ["string", "null"]},   # nullable: may be absent → prevents fabrication
            "category": {"enum": ["hardware", "software", "services", "unclear", "other"]},
            "category_detail": {"type": ["string", "null"]},  # pairs with "other"
            "stated_total": {"type": "number"},
            "calculated_total": {"type": "number"},      # self-check field (see 4.4)
        },
        "required": ["vendor", "category", "stated_total"],
    },
}]

resp = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    tools=tools,
    tool_choice={"type": "tool", "name": "record_invoice"},  # forced
    messages=[{"role": "user", "content": f"Extract from:\n{doc}\nNormalize dates to ISO 8601."}],
)
data = next(b.input for b in resp.content if b.type == "tool_use")
```

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Need guaranteed schema-valid JSON out of Claude | Tool use with a JSON `input_schema`; read from the `tool_use` block | Most reliable path; eliminates syntax errors | "Ask for JSON in the prompt and parse the text" (fragile) |
| Multiple extraction schemas, unknown document type | `tool_choice: {"type": "any"}` | Guarantees a tool call while letting the model pick the right schema | `"auto"` — model may return conversational text instead |
| A specific extraction must run before enrichment steps | Forced: `tool_choice: {"type": "tool", "name": "extract_metadata"}`, then process later steps in follow-up turns | Deterministic first step | Prompt-only "please call extract_metadata first" |
| Source docs sometimes lack a field | Make it optional/**nullable** in the schema | Required fields force the model to fabricate values | Marking everything required "for data quality" |
| Category set won't cover everything / some cases genuinely ambiguous | Enum + `"unclear"` value + `"other"` with a detail string field | Extensible; ambiguity is representable instead of forced | Closed enum that force-fits novel cases |
| Source formatting is inconsistent (dates, units) | Format normalization rules **in the prompt**, strict schema for shape | Schema constrains output shape, not input interpretation | Believing strict schema alone normalizes messy sources |
| Output validates against schema but totals don't sum / values in wrong fields | That's a **semantic** error — needs validation + retry (4.4) or self-check fields | Tool use only kills *syntax* errors | "Tool use guarantees correct output" |

---

## 4.4 — Validation, retry, and feedback loops

### Concepts in plain words

**Retry-with-error-feedback**: when validation (Pydantic / JSON schema / business rules) fails, don't just re-send the same prompt. Send a follow-up containing **(1) the original document, (2) the failed extraction, (3) the specific validation errors**. The model self-corrects against concrete feedback.

**Know when retry cannot help.** Retries fix *format mismatches and structural output errors*. Retries are **useless when the information is simply absent from the source** (e.g., it lives in an external document you never provided). Detecting this saves money and latency — route those to a different path (fetch the missing doc, mark null, or human review) instead of burning retries.

**Self-check fields** catch semantic errors at extraction time: extract `calculated_total` (model sums the line items) alongside `stated_total` (what the doc says); a mismatch flags the record. Add a `conflict_detected` boolean for internally inconsistent source data.

**detected_pattern feedback loop**: have findings include a `detected_pattern` field naming the code construct that triggered the finding. When developers dismiss findings, you can aggregate dismissals by pattern and systematically fix the false-positive-generating patterns — closing the loop from production feedback to prompt improvement.

```python
from pydantic import BaseModel, ValidationError

class Invoice(BaseModel):
    vendor: str
    stated_total: float
    calculated_total: float

for attempt in range(3):
    data = extract(doc, error_feedback)          # tool_use call from 4.3
    try:
        inv = Invoice(**data)
        if abs(inv.calculated_total - inv.stated_total) > 0.01:
            error_feedback = ("Semantic error: calculated_total "
                              f"{inv.calculated_total} != stated_total {inv.stated_total}. "
                              "Re-extract line items and re-sum.")
            continue
        break
    except ValidationError as e:
        # retry = original doc + failed extraction + SPECIFIC errors
        error_feedback = f"Previous extraction:\n{data}\nValidation errors:\n{e}"
else:
    route_to_human(doc)   # retry exhausted, or info likely absent from source
```

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Extraction fails schema/Pydantic validation | Follow-up request with original document + failed extraction + specific validation errors | Concrete feedback steers the correction | Blind re-send of the identical prompt; or feedback without the original document |
| Required info exists only in an external doc not provided | Recognize retry is **ineffective**; fetch the doc, allow null, or route to review | No amount of retrying conjures absent information | Retry loop with escalating temperature/attempts |
| Output is schema-valid but numbers don't reconcile | Extract `calculated_total` alongside `stated_total`; flag discrepancies; add `conflict_detected` boolean for inconsistent sources | Semantic self-check inside the extraction itself | Trusting schema validation as full validation |
| Developers dismiss review findings, you need to improve precision systematically | Add a `detected_pattern` field to every finding; analyze dismissals by pattern | Turns dismissals into a measurable FP feedback loop | Anecdote-driven prompt tweaks; asking devs to write reports |
| Deciding whether a failure class is retryable | Format/structural output errors → retry helps. Information-absent → retry cannot help | The exam explicitly tests this split | Treating all validation failures identically |

---

## 4.5 — Message Batches API: batch processing strategy

### Concepts in plain words

The Message Batches API trades latency for money: **50% cost savings**, processing takes **up to 24 hours**, with **no guaranteed latency SLA**. You submit many requests, **poll for completion**, and correlate each response to its request via the **`custom_id`** field you set on submission.

Two hard constraints decide everything:
1. **Latency tolerance.** Batch fits non-blocking workloads: overnight technical-debt reports, weekly audits, nightly test generation. It does **not** fit blocking workflows — a pre-merge check a developer is waiting on stays on the synchronous API. (This is sample Q11 verbatim: split the workloads, don't move both.)
2. **No multi-turn tool calling within a batch request.** A batch request can't execute a tool mid-request and feed results back. Agentic loops don't batch; single-shot extraction/analysis does.

Operational skills the exam tests:
- **SLA math**: submission cadence + 24h max processing must fit inside the SLA. Guide's example: submit in **4-hour windows** to guarantee a **30-hour SLA** given 24-hour max processing (4 + 24 < 30, with margin).
- **Failure handling**: resubmit **only the failed requests**, identified by `custom_id`, *with modifications that address why they failed* (e.g., chunk documents that blew the context limit).
- **Sample-first refinement**: tune the prompt on a small sample **before** batching the full volume — maximizes first-pass success, minimizes expensive resubmission cycles.

```python
batch = client.messages.batches.create(requests=[
    {
        "custom_id": f"doc-{d.id}",          # correlation key — responses come back unordered
        "params": {
            "model": "claude-sonnet-4-5",
            "max_tokens": 1024,
            "tools": tools,
            "tool_choice": {"type": "tool", "name": "record_invoice"},
            "messages": [{"role": "user", "content": d.text}],
        },
    }
    for d in documents
])
# ...poll batch status until ended; then resubmit ONLY failures by custom_id,
# modified (e.g., chunked) to fix the failure cause.
```

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Cut API cost; workloads = blocking pre-merge check + overnight report | Batch the overnight report **only**; keep sync API for the pre-merge check | No latency SLA → can't sit in a blocking path | "Batch both with polling" or "batch with timeout fallback to real-time" (Q11 distractors) |
| Worried batch responses come back out of order | Correlate with `custom_id` | That's exactly what it's for | "Keep real-time calls to avoid result-ordering issues" (Q11 distractor C) |
| Must deliver results within a 30-hour SLA | Compute submission cadence: e.g. 4-hour submission windows + 24h max processing | up-to-24h window is the planning number, not the average | Assuming batches "usually finish faster" |
| Some batch requests failed (context overflow etc.) | Resubmit only failed `custom_id`s, modified to fix the cause (chunk oversized docs) | Cheapest correct recovery | Resubmitting the entire batch; resubmitting failures unmodified |
| About to batch 100k documents with a new prompt | Refine the prompt on a **sample set first** | First-pass success is the cost lever; resubmission cycles at scale are expensive | Batch first, iterate on the whole corpus |
| Workflow needs tools executed mid-request | Synchronous API — batch does **not** support multi-turn tool calling | Hard API constraint | Trying to run an agentic loop inside a batch request |

---

## 4.6 — Multi-instance and multi-pass review architectures

### Concepts in plain words

**Self-review is structurally weak**: the same session that generated the code retains its own reasoning context, so it's biased toward its own decisions. A **second, independent Claude instance** — no access to the generator's reasoning — catches subtle issues that self-review instructions or even extended thinking miss. (This is why the guide's D3 section calls out "session context isolation" for CI review: don't have the code-writing session review its own diff.)

**Multi-pass review** fixes attention dilution: one pass over 14 files produces uneven depth, missed bugs, and *contradictory* findings (flagging a pattern in one file, approving it in another). Restructure as **per-file local passes** (consistent depth on local issues) **plus one cross-file integration pass** (data flow between files). Sample Q12 tests exactly this — and its distractors are all named traps: bigger context window doesn't fix attention quality; forcing devs to split PRs shifts the burden; consensus voting across 3 runs *suppresses real bugs* that are only caught intermittently.

**Confidence self-reporting for routing**: have the review pass self-report a confidence score **alongside each finding** so downstream review attention can be routed (low-confidence findings get human eyes first). Nuance the exam may probe: self-reported confidence is fine as a *routing/prioritization* signal on findings, but D5 says it's **unreliable as an escalation trigger** for case complexity — don't use "confidence < 7 → escalate to human agent" as primary escalation logic.

```python
# Generator and reviewer are ISOLATED instances — reviewer never sees
# the generator's conversation/reasoning, only the artifact.
gen = client.messages.create(model=..., messages=[{"role": "user", "content": task}])
code = gen.content[0].text

review = client.messages.create(   # fresh message list = independent instance
    model=...,
    tools=[finding_tool],          # schema: file, line, issue, severity,
                                   # detected_pattern, confidence
    tool_choice={"type": "any"},
    messages=[{"role": "user", "content": f"Review this code:\n{code}"}],
)
```

### Decision rules

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Generated code needs quality review | Second **independent** instance with no generator reasoning context | Generator is biased toward its own decisions | "Add self-review instructions" or "use extended thinking" in the same session |
| 14-file PR review: uneven depth, missed bugs, contradictory findings | Per-file local passes + separate cross-file integration pass | Fixes attention dilution at the root | Bigger context window (Q12-C); force devs to split PRs (Q12-B); 2-of-3 consensus voting (Q12-D — suppresses intermittently-caught real bugs) |
| Limited human review capacity for findings | Model self-reports confidence per finding → route low-confidence findings to review | Calibrated routing of scarce attention | Using self-reported confidence as the primary *escalation* trigger (unreliable for case complexity — D5) |
| Cross-file bugs (data flow) getting missed by per-file passes | That's the job of the dedicated integration pass | Local passes can't see cross-file flow by design | Assuming per-file passes alone are complete |

---

## Memorize cold

Flashcard facts. If a D4 question hinges on a single detail, it's one of these.

**tool_choice — exactly three values**
- `{"type": "auto"}` → model MAY return plain text instead of calling a tool
- `{"type": "any"}` → model MUST call a tool, ANY tool (use: multiple schemas, unknown doc type)
- `{"type": "tool", "name": "extract_metadata"}` → model MUST call THAT tool (forced)

**stop_reason values** (agentic-loop boundary, shared with D1): `"tool_use"` → execute tools and continue; `"end_turn"` → done.

**Tool-use structured output**
- Tool definition fields: `name`, `description`, `input_schema` (JSON Schema)
- Data comes back in the `tool_use` content block's `input`
- Eliminates: JSON **syntax** errors. Does NOT eliminate: **semantic** errors (bad sums, wrong-field values)
- API params in play: `tools`, `tool_choice`, `max_tokens`, `system`

**Schema design**
- May-be-absent field → **optional/nullable** (prevents fabrication)
- Enum patterns: `"unclear"` for ambiguous; `"other"` + **detail string field** for extensibility
- Format normalization rules go **in the prompt**, schema handles shape
- Pydantic = validation layer; catches **semantic** validation errors; drives validation-retry loops

**Retry-with-error-feedback — the 3 ingredients**: original document + failed extraction + specific validation errors.
- Retry WORKS: format mismatches, structural output errors
- Retry CANNOT work: information absent from the source document

**Self-check / feedback fields**: `calculated_total` vs `stated_total` (discrepancy flag) · `conflict_detected` boolean (inconsistent source) · `detected_pattern` (FP dismissal analysis).

**Message Batches API — the numbers**
- **50%** cost savings · up to **24-hour** processing window · **no** guaranteed latency SLA
- **`custom_id`** correlates request ↔ response (responses unordered) · **poll** for completion
- **No multi-turn tool calling** within a batch request
- SLA math example: **4-hour** submission windows → guarantees **30-hour** SLA with 24h processing
- Recovery: resubmit **only failures by custom_id, modified** (e.g., chunk oversized docs)
- **Sample-first** prompt refinement before large-volume batch runs
- Fits: overnight reports, weekly audits, nightly test generation. Never: blocking pre-merge checks.

**Few-shot numbers**: **2–4 targeted** examples for ambiguous scenarios (2–3 for I/O transformations, per D3). Show reasoning for why the chosen action beat plausible alternatives. Format demo fields: location, issue, severity, suggested fix.

**Precision prompting**: categorical report/skip criteria > "be conservative" / "only high-confidence." Severity = concrete code example per level. High-FP category → temporarily disable while fixing.

**Multi-pass/multi-instance**: independent instance > self-review instructions > extended thinking (for catching generator's own bugs). Per-file passes + cross-file integration pass. Confidence self-report per finding = routing signal, not escalation trigger.

**Border facts from D3 you'll see in D4-flavored CI questions**: `-p` / `--print` (non-interactive), `--output-format json`, `--json-schema` (structured CI output). Not D4's core, but they co-occur in Scenario 5.

---

## Anti-pattern wall

Recognize these on sight — each is a wrong-answer template.

| # | Anti-pattern | Why it's wrong | Correct alternative |
|---|---|---|---|
| 1 | **"Be conservative" / "only report high-confidence findings"** as a precision fix | Vague instructions don't change behavior; no operational definition | Explicit categorical report/skip criteria |
| 2 | **Confidence-based filtering instead of criteria** | Model confidence is uncalibrated for this | Categories + severity anchored with code examples |
| 3 | **Keeping a high-FP category live while tuning** | Poisons trust in the accurate categories | Temporarily disable, fix, re-enable |
| 4 | **Prompt-parse JSON from text output** | Syntax errors, markdown fences, drift | tool_use with `input_schema` |
| 5 | **All schema fields required "for quality"** | Forces fabrication when source lacks the info | Nullable/optional fields |
| 6 | **Closed enum with no escape hatch** | Novel/ambiguous cases get force-fit into wrong buckets | `"unclear"` + `"other"` + detail field |
| 7 | **Assuming schema-valid = correct** | Tool use kills syntax errors only, not semantics | Self-check fields + validation-retry |
| 8 | **Blind retry (same prompt, no feedback)** | Model has nothing new to correct against | Doc + failed extraction + specific errors |
| 9 | **Retrying when the info is absent from source** | Cannot succeed; wastes cost and latency | Detect absence → null / fetch / human review |
| 10 | **Batching a blocking workflow** (pre-merge check) | No latency SLA; up-to-24h window | Sync API for blocking, batch for overnight/weekly |
| 11 | **"Batch with timeout fallback to real-time"** | Complexity papering over a wrong fit | Match each workload to the right API |
| 12 | **Avoiding batch over result-ordering fears** | `custom_id` exists precisely for correlation | Use `custom_id` |
| 13 | **Resubmitting the whole batch (or failures unmodified)** | Pays twice, fails identically | Failed `custom_id`s only, modified (e.g., chunked) |
| 14 | **Full-volume batch before sample refinement** | Iterating on 100k docs is the expensive loop | Refine on a sample first |
| 15 | **Multi-turn tool use inside a batch request** | Not supported by the Batches API | Sync agentic loop; batch single-shot work |
| 16 | **Self-review in the generating session** | Retained reasoning context biases toward own decisions | Independent second instance |
| 17 | **Bigger context window to fix uneven review depth** | Attention dilution isn't a capacity problem | Per-file passes + integration pass |
| 18 | **N-run consensus voting on findings** | Suppresses real bugs caught intermittently | Focused passes with consistent depth |
| 19 | **Forcing devs to split PRs so the reviewer copes** | Shifts burden without improving the system | Restructure the review, not the workflow |
| 20 | **5–8 few-shot examples for a tool-routing problem with bad descriptions** | Token overhead; root cause is the descriptions (D2) | Fix tool descriptions first; few-shot for genuine ambiguity |
