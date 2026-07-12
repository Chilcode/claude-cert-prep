# Scenario 6 — Structured Data Extraction

> **Exam framing:** "You are building a structured data extraction system using Claude. The system extracts information from unstructured documents, validates the output using JSON schemas, and maintains high accuracy. It must handle edge cases gracefully and integrate with downstream systems."
>
> **Primary domains:** D4 Prompt Engineering & Structured Output (20%) + D5 Context Management & Reliability (15%). If this scenario is drawn, you're answering ~10 questions worth of pipeline-architecture judgment. This is a raw **Claude API** scenario — no Agent SDK, no Claude Code config. Vision/OCR is explicitly out of scope; documents arrive as text.

---

## 1. The system at a glance

Five components. The core insight the whole scenario hangs on: **you don't ask Claude to "respond in JSON" — you define a tool whose `input_schema` IS your output schema, force Claude to call it, and read the arguments.** The tool is never executed; it's a schema container. Everything else is plumbing around that call.

```
                 ┌─────────────────────────────────────────────────────┐
                 │                EXTRACTION PIPELINE                   │
                 └─────────────────────────────────────────────────────┘

  docs (text) ──► [1] PRE-PROCESS ──► [2] EXTRACTION CALL ──► [3] VALIDATE
                   chunk oversized      tool_use + JSON          Pydantic:
                   docs; key info       schema, forced           schema +
                   up front             tool_choice              semantic checks
                                             ▲                        │
                                             │  retry w/ specific     │ fail
                                             └── validation error ◄───┤ (max N)
                                                 appended             │
                                                                      ▼ pass
                                              [4] CONFIDENCE ROUTER
                                              field-level confidence,
                                              calibrated thresholds
                                               │                │
                                     low conf /│                │ high conf
                                     conflicts ▼                ▼
                                        HUMAN REVIEW      [5] DOWNSTREAM
                                        queue             systems (DB, API)
                                             ▲                  │
                                             └── stratified ────┘
                                                 random sample
                                                 (ongoing QA)

  Volume path: same call params → Message Batches API (50% cheaper, ≤24h,
  no SLA) → correlate & resubmit failures by custom_id
```

Data flow in one sentence: document text goes in, a forced tool call returns schema-shaped data, Pydantic validates it (syntax is already guaranteed — you're checking *semantics*), failures retry with the specific error appended, survivors route by confidence to either humans or downstream systems, and a stratified sample of the "good" output gets audited forever.

---

## 2. Build it step by step

The exam guide's Exercise 3 is literally this build order (steps 11–15 of the guide). Build in this sequence because each layer catches what the previous one can't.

### Step 1 — The schema-as-tool (get this right and half the scenario is solved)

Design decisions baked into the schema, each one an exam question:

- **Nullable/optional fields** for anything the source may not contain — a `required` field the document lacks forces the model to *fabricate* a value to satisfy the schema.
- **Enum + `"other"` + detail string** for extensible categories; **`"unclear"`** enum value for ambiguous cases.
- **Self-correction fields**: extract `calculated_total` *alongside* `stated_total` so discrepancies get flagged, and a `conflict_detected` boolean for inconsistent source data.
- **Field-level confidence** so Step 5 has something to route on.

```python
import anthropic

client = anthropic.Anthropic()
MODEL = "claude-sonnet-4-5"  # any current model; exam doesn't test model IDs

INVOICE_TOOL = {
    "name": "record_invoice",
    "description": (
        "Record structured data extracted from an invoice document. "
        "Call this exactly once with every field you can ground in the "
        "document text. Use null for any field not present in the document — "
        "never guess or infer missing values."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "vendor_name": {"type": "string"},
            "invoice_date": {
                "type": ["string", "null"],
                "description": "ISO 8601 (YYYY-MM-DD). Null if no date appears in the document.",
            },
            "po_number": {
                "type": ["string", "null"],
                "description": "Null if the document has no purchase order number.",
            },
            "category": {
                "type": "string",
                "enum": ["utilities", "software", "hardware", "services", "other", "unclear"],
            },
            "category_detail": {
                "type": ["string", "null"],
                "description": "Required free-text detail when category is 'other'.",
            },
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "amount": {"type": "number"},
                    },
                    "required": ["description", "amount"],
                },
            },
            "stated_total": {"type": "number", "description": "Total as printed on the document."},
            "calculated_total": {"type": "number", "description": "Sum of line item amounts, computed by you."},
            "conflict_detected": {
                "type": "boolean",
                "description": "True if the document contains internally inconsistent values.",
            },
            "field_confidence": {
                "type": "object",
                "description": "Confidence 0.0-1.0 per extracted field.",
                "properties": {
                    "vendor_name": {"type": "number"},
                    "invoice_date": {"type": "number"},
                    "stated_total": {"type": "number"},
                },
            },
        },
        # required = fields every invoice genuinely has. Everything else stays optional.
        "required": ["vendor_name", "line_items", "stated_total",
                     "calculated_total", "conflict_detected", "category"],
    },
}
```

### Step 2 — The extraction call: forced tool_choice, few-shot in the system prompt

Know the three `tool_choice` modes cold:

| Mode | Behavior | Use here when |
|---|---|---|
| `{"type": "auto"}` | Model *may* return plain text instead of calling a tool | Never for extraction — text responses break your parser |
| `{"type": "any"}` | Model *must* call some tool, its choice which | Multiple extraction schemas (invoice/contract/receipt tools) and **document type is unknown** |
| `{"type": "tool", "name": "record_invoice"}` | Model must call *that* tool | Document type is known; also to force a specific step (guide's example: force `extract_metadata` before enrichment tools run in follow-up turns) |

The system prompt carries the two things the schema can't enforce: **format normalization rules** ("dates → ISO 8601, currency → number without symbols") and **2–4 few-shot examples** showing correct extraction from *varied document formats* — that's the guide's stated fix for hallucination and for empty/null extraction of required fields. Target examples at the ambiguous cases: informal measurements, inline data vs. tabular data, a document that's missing a field (show null being returned).

```python
SYSTEM = """You extract invoice data. Rules:
- Dates: convert any format to ISO 8601 (YYYY-MM-DD).
- Amounts: numbers only, no currency symbols or thousands separators.
- If a field is not in the document, return null. Never infer or fabricate.

<example>
Document: "Bill from Acme Corp, March 3rd 2026... services rendered $1,200"
Correct: vendor_name="Acme Corp", invoice_date="2026-03-03",
         stated_total=1200, po_number=null (no PO in document)
</example>
<example>
Document: "INVOICE #A-99 ... [tabular line items, no date anywhere]"
Correct: invoice_date=null — the document contains no date; do not use today's date.
</example>"""

def extract(doc_text: str):
    msg = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=SYSTEM,
        messages=[{"role": "user", "content": doc_text}],
        tools=[INVOICE_TOOL],
        tool_choice={"type": "tool", "name": "record_invoice"},
    )
    block = next(b for b in msg.content if b.type == "tool_use")
    return msg, block  # block.input is your schema-shaped dict
```

**Architectural note the exam probes:** this is *not* an agentic loop. With forced `tool_choice`, `stop_reason` is `"tool_use"` every time — there is no `"end_turn"` to wait for, and the tool never executes. The loop that matters in this scenario is the **validation-retry loop your code drives** (Step 4). A distractor will offer you a D1-style agentic loop here; it's solving a different problem.

### Step 3 — Semantic validation with Pydantic

The single most-tested fact in this scenario: **tool use with a strict JSON schema eliminates *syntax* errors (malformed JSON, wrong types) but does NOT prevent *semantic* errors** — line items that don't sum to the total, values landed in the wrong field. That's what this layer exists for.

```python
from pydantic import BaseModel, ValidationError, model_validator

class LineItem(BaseModel):
    description: str
    amount: float

class Invoice(BaseModel):
    vendor_name: str
    invoice_date: str | None = None
    po_number: str | None = None
    category: str
    category_detail: str | None = None
    line_items: list[LineItem]
    stated_total: float
    calculated_total: float
    conflict_detected: bool
    field_confidence: dict[str, float] = {}

    @model_validator(mode="after")
    def totals_consistent(self):
        if abs(sum(li.amount for li in self.line_items) - self.stated_total) > 0.01 \
                and not self.conflict_detected:
            raise ValueError(
                "line_items sum "
                f"({sum(li.amount for li in self.line_items):.2f}) != stated_total "
                f"({self.stated_total:.2f}) but conflict_detected is false"
            )
        return self
```

### Step 4 — Retry with error feedback (and knowing when NOT to retry)

The guide's pattern: the follow-up request must contain **the original document, the failed extraction, and the specific validation errors**. Continuing the conversation gives you the first two for free; the `tool_result` carries the third.

```python
def extract_validated(doc_text: str, max_retries: int = 2):
    messages = [{"role": "user", "content": doc_text}]
    for attempt in range(max_retries + 1):
        msg = client.messages.create(
            model=MODEL, max_tokens=2048, system=SYSTEM,
            messages=messages,
            tools=[INVOICE_TOOL],
            tool_choice={"type": "tool", "name": "record_invoice"},
        )
        block = next(b for b in msg.content if b.type == "tool_use")
        try:
            return Invoice.model_validate(block.input)          # success
        except ValidationError as e:
            messages.append({"role": "assistant", "content": msg.content})
            messages.append({"role": "user", "content": [{
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": (
                    f"Extraction failed validation:\n{e}\n"
                    "Re-extract the document and correct ONLY these errors. "
                    "If the information is absent from the document, return null "
                    "— do not invent a value."
                ),
            }]})
    return route_to_human(doc_text, block.input, str(e))        # retries exhausted
```

The judgment call the exam tests harder than the code: **retries fix format and structural errors; retries can never fix information that is absent from the source document.** "Extract the PO number" from a document with no PO number will fail forever — burn zero retries on it, return null, and route by confidence instead. Classify your validation failures before retrying.

### Step 5 — Confidence routing + human review (D5.5)

Three rules from the guide, in build order:

1. **Model outputs field-level confidence scores** (already in the schema), then you **calibrate review thresholds against a labeled validation set** — never trust raw self-reported confidence uncalibrated.
2. **Route to human review**: low-confidence fields, and documents with ambiguous/contradictory source data (`conflict_detected: true`). Prioritize limited reviewer capacity there.
3. **Never stop auditing the auto-approved lane**: stratified random sampling of *high-confidence* extractions measures ongoing error rate and catches novel error patterns.

And the trap that guards this whole step: **aggregate accuracy (e.g., "97% overall") can mask terrible performance on one document type or one field.** Analyze accuracy **by document type AND by field** before you reduce human review anywhere.

```python
THRESHOLDS = {"vendor_name": 0.90, "stated_total": 0.95, "invoice_date": 0.85}
# values come from a labeled validation set, not from vibes

def route(inv: Invoice, doc_text: str):
    low = [f for f, t in THRESHOLDS.items()
           if inv.field_confidence.get(f, 0.0) < t]
    if low or inv.conflict_detected:
        return human_review_queue(inv, doc_text, reasons=low)
    if random.random() < STRATIFIED_SAMPLE_RATE[inv.category]:   # per-segment QA
        audit_queue(inv, doc_text)
    return push_downstream(inv)      # trimmed to fields downstream actually needs
```

### Step 6 — Scale it: Message Batches API (D4.5)

Facts to memorize verbatim — they show up as distractors: **50% cost savings, processing window up to 24 hours, NO guaranteed latency SLA, `custom_id` correlates request/response pairs, and no multi-turn tool calling within a single batch request.** That last one is fine here — forced-tool extraction is single-shot (the tool never executes, so no tool results ever need returning). What you *can't* do in a batch is the Step 4 retry conversation — retries go into the *next* batch (or sync calls) as resubmissions.

```python
batch = client.messages.batches.create(requests=[
    {
        "custom_id": f"doc-{d.id}",
        "params": {
            "model": MODEL, "max_tokens": 2048, "system": SYSTEM,
            "messages": [{"role": "user", "content": d.text}],
            "tools": [INVOICE_TOOL],
            "tool_choice": {"type": "tool", "name": "record_invoice"},
        },
    } for d in docs
])

# poll until processing_status == "ended", then:
failed = []
for r in client.messages.batches.results(batch.id):
    if r.result.type == "succeeded":
        handle(r.custom_id, r.result.message)
    else:
        failed.append(r.custom_id)   # resubmit ONLY these, with modifications
```

Operational rules the exam tests:

- **Match API to latency tolerance.** Blocking workflows (anything a human waits on) → synchronous API. Overnight reports, weekly audits, nightly runs → batch.
- **SLA math.** 24h max processing means submission cadence is your lever: e.g., submitting every 4 hours guarantees a 30-hour end-to-end SLA (4h max queue wait + 24h processing + buffer).
- **Failure handling = resubmit only the failed `custom_id`s, with modifications** — e.g., chunk the documents that blew the context limit. Never resubmit the whole batch.
- **Refine the prompt on a sample set first**, then batch the large volume — maximizes first-pass success and avoids paying for iterative resubmission at scale.

### Step 7 — Long documents: context management (D5.1)

For 80-page contracts, three moves:

- **Lost-in-the-middle is real**: models reliably process the beginning and end of long inputs and drop middle content. Put a key-information summary **at the beginning** of aggregated input and organize the rest with **explicit section headers**.
- **Chunk oversized documents** (this is also the standard fix when a batch item fails on context limits).
- **Trim before it accumulates**: pass downstream systems only the relevant fields, not the full extraction blob — verbose payloads consume tokens disproportionately to their relevance in any later Claude-in-the-loop step.

---

## 3. The decision points this scenario tests

Each row is a task statement converted to the exam's actual shape: a situation, one correct move, three plausible wrong ones.

### D4.3 — Enforcing structured output

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Need guaranteed schema-compliant JSON from extraction | Define a tool with the JSON schema as `input_schema`; read the `tool_use` block's input | Tool use eliminates JSON syntax errors entirely | "Respond only in valid JSON" prompting + a regex/parser cleanup layer |
| Multiple extraction schemas, document type unknown | `tool_choice: {"type": "any"}` | Guarantees a tool call while letting the model pick the right schema | Forcing one specific tool (wrong schema for half the docs), or `"auto"` (model may answer in prose) |
| A specific extraction must run before enrichment steps | `tool_choice: {"type": "tool", "name": "extract_metadata"}`, then process later steps in follow-up turns | Forced selection is deterministic; prompt ordering is probabilistic | System-prompt instruction "always call extract_metadata first" |
| Source docs sometimes lack a field | Make it optional/nullable in the schema | A required field the doc lacks pressures the model to fabricate a value | Making everything required "for data quality" |
| Categories won't stay fixed forever; some cases are genuinely ambiguous | Enum + `"other"` with a detail string; add `"unclear"` for ambiguity | Extensible without schema churn; ambiguity becomes visible data | Free-text category field, or forcing every doc into the closed enum |
| Source formatting is inconsistent (dates, currencies) | Format normalization rules in the prompt **alongside** the strict schema | Schema constrains shape; prompt constrains content conventions | Assuming the schema alone normalizes formats |

### D4.4 — Validation, retry, feedback loops

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Schema-valid output but line items don't sum to total | Pydantic semantic validation + retry with the specific error appended | Strict schemas kill syntax errors, **not** semantic errors | "Tighten the JSON schema" — no schema expresses cross-field arithmetic |
| Validation fails, deciding whether to retry | Retry format/structural errors; **don't** retry when the info is absent from the source | Retries can't create information that isn't there | Uniform retry-3-times policy for every failure class |
| Building the retry request | Include the original document + the failed extraction + the specific validation errors | The model needs all three to self-correct | Bare re-ask ("try again, output valid JSON") with no error context |
| Totals on source docs are sometimes internally wrong | Extract `calculated_total` alongside `stated_total`; add `conflict_detected` boolean | Self-correction flow flags discrepancies instead of hiding them | Extracting only `stated_total` and trusting the document |
| Want to learn from reviewer dismissals / false positives | Add a `detected_pattern` field to structured findings | Enables systematic analysis of what triggers bad output | Reading dismissal comments ad hoc |

### D4.2 — Few-shot prompting for extraction

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Required fields come back empty/null on unusual layouts | Add few-shot examples showing correct extraction from **varied document formats** | Examples demonstrate structural variety; the model generalizes | Longer prose instructions ("be thorough, check tables too") |
| Hallucinated values on informal/odd inputs | 2–4 targeted few-shot examples covering exactly those ambiguous cases, showing the reasoning | Few-shot is the guide's stated hallucination-reducer for extraction | 15+ examples covering everything (token bloat, no targeting) |
| Output format drifts run to run | Few-shot examples demonstrating the exact desired output | Format demonstration beats format description | Re-describing the format in more detail |

### D4.5 — Batch processing

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Nightly 10K-document extraction + an on-demand single-doc lane | Batch API for the nightly run; synchronous API for on-demand | Batch = 50% cheaper but ≤24h, no SLA — latency-tolerant only | Batch for both ("it usually finishes fast") |
| 12 of 5,000 batch items failed | Resubmit only those `custom_id`s, modified (e.g., chunk oversized docs) | `custom_id` exists precisely for correlation and selective retry | Rerunning the full batch |
| Must guarantee 30h turnaround with 24h batch processing | Submit batches every 4 hours | 4h max queue wait + 24h processing < 30h | One giant daily batch and hoping |
| New prompt, 100K docs to process | Refine on a sample set first, then batch the volume | First-pass success is the cost lever; resubmission at scale is expensive | Batch everything immediately, iterate on failures |
| Extraction needs a mid-request tool round-trip | Restructure to single-shot, or use the sync API | Batch requests do not support multi-turn tool calling | Assuming batch behaves like the sync API with tools |

### D5.5 — Human review & confidence calibration

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| "97% overall accuracy — can we drop human review?" | Analyze accuracy **by document type and by field** first | Aggregate metrics mask segment-level failure | Trusting the aggregate number |
| Limited reviewer capacity | Route low-confidence fields + ambiguous/contradictory source docs to review | Puts scarce attention where errors concentrate | Reviewing a flat random N% of everything |
| Using model confidence to route | Calibrate thresholds against a **labeled validation set** | Raw self-reported confidence is poorly calibrated | Trusting confidence scores as-is (same failure as sentiment-based escalation) |
| High-confidence lane fully automated | Stratified random sampling of it, forever | Measures ongoing error rate; detects **novel** error patterns | "It passed validation, we're done" |

### D5.1 — Long-document context

| Situation | Correct move | Why | The trap |
|---|---|---|---|
| Fields from the middle of long docs come back null/wrong | Key-info summary at the beginning + explicit section headers; chunk if oversized | Lost-in-the-middle: start/end are processed reliably, middles get dropped | "Use the bigger context window" — capacity ≠ attention quality |
| Downstream step chokes on huge extraction payloads | Trim to only the relevant fields before passing on | Verbose outputs eat tokens disproportionately to relevance | Forwarding the full 40-field blob because "more context is better" |

---

## 4. Failure-modes drill

Styled like the guide's sample questions: production symptom → root cause → fix. Cover these and you can reverse-engineer most distractors.

**1. Invoices with no date come back with plausible-looking dates that aren't in the document.**
Root cause: `invoice_date` is a **required** schema field, so the model fabricates a value to satisfy it.
Fix: make fields the source may lack optional/nullable, and state "return null, never infer" in the tool description and prompt. (Not: "add instructions to be more careful.")

**2. ~5% of responses fail `json.loads` — markdown fences, trailing commas, prose preambles.**
Root cause: output is prompted JSON in a text response, not tool use.
Fix: define an extraction tool with the JSON schema as `input_schema` and read the `tool_use` block. Tool use eliminates syntax errors by construction. (Not: a regex cleanup layer, or "respond ONLY with JSON" in caps.)

**3. Every extraction passes the JSON schema, but finance reports line items that don't sum to the stated total.**
Root cause: strict schemas eliminate syntax errors only — semantic errors sail through.
Fix: Pydantic semantic validation (cross-field checks) + retry-with-error-feedback; add `calculated_total` next to `stated_total` and a `conflict_detected` boolean so discrepancies surface as data. (Not: making the schema stricter.)

**4. The retry loop burns 3 attempts per document on a batch of receipts, then fails anyway — the failing field is `po_number` and receipts don't have PO numbers.**
Root cause: retrying an information-absence failure. Retries fix format/structural errors; they cannot fix information missing from the source.
Fix: classify validation failures; absent-info failures return null immediately and route by confidence — zero retries. (Not: raising max_retries or "improving" the retraction prompt.)

**5. With three extraction tools registered (invoice/contract/receipt), the model occasionally replies "This appears to be an invoice for..." — plain text, no tool call.**
Root cause: `tool_choice: "auto"` permits text responses.
Fix: `tool_choice: {"type": "any"}` — a tool call is guaranteed, the model picks the schema (doc type is unknown, so don't force one). (Not: prompt instructions to "always use a tool.")

**6. Team moved the customer-facing, on-demand extraction endpoint to the Batches API for the 50% savings; users now sometimes wait hours.**
Root cause: Batch API has up to a 24-hour window and **no latency SLA** — it's for latency-tolerant workloads only.
Fix: synchronous API for anything blocking a human; keep batch for the overnight/weekly volume. (Not: "batch with a timeout fallback to real-time" — that's the complexity distractor.)

**7. Dashboard shows 97% accuracy, so human review was cut — a month later, lease-agreement date fields turn out to be ~70% accurate.**
Root cause: aggregate accuracy masked a failing segment (one document type × one field).
Fix: segment accuracy by document type and field *before* reducing review; keep stratified random sampling of high-confidence output to catch novel error patterns. (Not: raising the overall confidence threshold — the model was confidently wrong.)

**8. Long contracts (60+ pages) extract fine except clauses from the middle sections, which come back null even though they're present.**
Root cause: lost-in-the-middle — reliable processing at the beginning and end of long input, middles dropped.
Fix: chunk the document, place key-info summaries first, use explicit section headers; add few-shot examples of varied document structures. (Not: switching to a larger context window — capacity doesn't fix attention position effects.)

---

## Cheat-row: the eight facts to walk in with

1. Schema-valid output = **tool use with JSON schema**, never JSON-by-prompting.
2. `auto` may return text · `any` forces *a* tool · `{"type":"tool","name":...}` forces *the* tool.
3. Might-be-missing → **nullable**, or the model fabricates.
4. Strict schema kills **syntax** errors only; semantics need Pydantic + retry-with-error-feedback.
5. Retry fixes format errors; retry **never** fixes absent information.
6. Enum + `"other"`+detail + `"unclear"` for real-world categories.
7. Batch: 50% off, ≤24h, no SLA, no multi-turn tools, `custom_id` for selective resubmission.
8. Calibrate confidence on labeled sets, segment accuracy by doc-type×field, stratified-sample the automated lane forever.
