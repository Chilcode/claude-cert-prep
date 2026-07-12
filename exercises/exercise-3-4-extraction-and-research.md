# Exercises 3 & 4 — Structured Extraction Pipeline + Multi-Agent Research

> Claude Certified Architect — Foundations. Two build-it-tonight labs, same rules as Exercises 1 & 2.
> Both run on the raw Anthropic Messages API (Python). Model for all API code: `claude-sonnet-5`. Everything here is paste-ready.
> Exercise 3 = exam Scenario 6 (Structured Data Extraction). Exercise 4 = exam Scenario 3 (Multi-Agent Research System).

Same drill as last time: every step ends with a checkpoint (run this, see that), and every exercise ends with **Break it on purpose**. The exam questions for these scenarios are almost all "here's a broken pipeline, what's the root cause?" — so the break-it sections are the actual studying.

One heads-up before you start: the exam's Exercise 4 talks about the Agent SDK's `Task` tool and `allowedTools`. You're going to build the exact same machinery by hand on the raw API — a `Task` tool the coordinator calls, a runner that spawns a fresh, isolated conversation per subagent. That's better for learning: you'll *see* why subagents don't inherit context, because you wrote the code that doesn't pass it.

---

# Exercise 3 — Build a Structured Data Extraction Pipeline

## 3.1 Objective + exam mapping

Build an invoice-extraction pipeline: a schema that refuses to let the model lie, a validation-retry loop that feeds errors back, few-shot examples for messy real-world formats, a Message Batches pass with `custom_id` failure handling, and confidence-based routing to human review.

| What you build | Task statements drilled |
|---|---|
| Extraction tool: required + optional + **nullable** fields, enum + `"other"` + detail, forced `tool_choice` | **4.3** |
| Pydantic validation-retry loop feeding the *specific* error back; retry-fixable vs. retry-hopeless errors | **4.4** |
| Few-shot examples demonstrating extraction from varied document formats | **4.2** |
| Message Batches API run: 50% cost, `custom_id` correlation, resubmit-only-failures | **4.5** |
| Field-level confidence scores → human-review routing, accuracy-by-segment thinking | **5.5** |

This is exam Scenario 6 end to end. Sample Q11 (batch vs. real-time) is Step 4 verbatim.

## 3.2 Setup (Windows / PowerShell)

Same venv and API key as Exercise 1. One new dependency: Pydantic (the exam names it by name for validation-retry loops).

```powershell
cd C:\Users\david.rios\Dev\claude-cert-prep\exercises
.\.venv\Scripts\Activate.ps1
pip install pydantic
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # if not still set from Exercise 1
$env:PYTHONIOENCODING  = "utf-8"
```

Tree after both exercises tonight:

```
claude-cert-prep\exercises\
  .venv\
  agent.py           # from Exercise 1
  extract.py         # Exercise 3 — you build this
  research.py        # Exercise 4 — you build this
```

## 3.3 Step-by-step build

### Step 1 — The extraction tool: a schema that blocks fabrication

The whole game of Task 4.3 is in three schema decisions:

1. **Nullable fields** (`"type": ["string", "null"]`) for anything a real document might not contain. If you make a maybe-absent field required and non-nullable, the model *will* invent a value to satisfy the schema — you'll prove that in Break-it #1.
2. **Enum + `"other"` + detail string** for categories. Real payments include Venmo, gift cards, barter. Without `"other"`, those get shoehorned into `check` or `wire`. `"unclear"` covers genuinely ambiguous docs.
3. **Forced `tool_choice`** so the response is *always* a schema-valid tool call, never prose. Tool use with a JSON schema eliminates JSON *syntax* errors entirely — you'll never `json.loads()`-crash again. (It does NOT eliminate *semantic* errors. That's Step 2.)

Create `extract.py`:

```python
import json
import time
from datetime import date
from typing import Literal, Optional

import anthropic
from pydantic import BaseModel, ValidationError, model_validator

client = anthropic.Anthropic()
MODEL = "claude-sonnet-5"

# ---------------------------------------------------------------- the tool
EXTRACT_TOOL = {
    "name": "record_invoice",
    "description": (
        "Record structured data extracted from an invoice, receipt, or payment-related document. "
        "Only record what the document actually states. If a field's information is absent from "
        "the document, use null — NEVER guess or fabricate a value."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "vendor_name":    {"type": "string", "description": "Who is being paid"},
            "invoice_number": {"type": ["string", "null"],
                               "description": "The document's invoice/reference number. null if none appears."},
            "invoice_date":   {"type": ["string", "null"],
                               "description": "ISO format YYYY-MM-DD. null if no date appears."},
            "total_amount":   {"type": "number", "description": "Total amount due, in the document's currency"},
            "payment_method": {"type": "string",
                               "enum": ["credit_card", "ach", "wire", "check", "other", "unclear"],
                               "description": "How payment is/was made. 'other' for anything not listed "
                                              "(then fill payment_method_detail). 'unclear' if ambiguous."},
            "payment_method_detail": {"type": ["string", "null"],
                               "description": "Free-text detail. REQUIRED when payment_method is 'other'."},
            "line_items": {
                "type": "array",
                "items": {"type": "object",
                          "properties": {"description": {"type": "string"}, "amount": {"type": "number"}},
                          "required": ["description", "amount"]},
                "description": "Every individual charge on the document, INCLUDING tax, fees, and shipping. "
                               "Must sum to total_amount.",
            },
        },
        "required": ["vendor_name", "invoice_number", "invoice_date",
                     "total_amount", "payment_method", "line_items"],
    },
}
# Note: invoice_number and invoice_date are REQUIRED **and** NULLABLE. That combination is the
# exam pattern — the model must always address the field, but null is a legal, honest answer.

# ---------------------------------------------------------------- sample documents
DOC_CLEAN = """INVOICE #INV-4471
Blue Ridge Hosting LLC
Date: 2026-06-14
Managed VPS (June)........$120.00
Backup storage............$18.00
TOTAL DUE: $138.00
Payment: ACH transfer to account on file"""

DOC_EMAIL = """From: dave@chilcode.com
Subject: banner payment
Hey — heads up, we still owe Maria's Print Shop for the trade-show banner job.
It came to $150 even. She doesn't do invoices for small jobs, said just Venmo her
whenever. Can you take care of it this week?"""

DOC_TAX = """RECEIPT — Lakeside Office Supply
Standing desk mat.........$40.00
Monitor arm...............$35.00
Sales tax (10%)...........$7.50
Amount charged: $82.50"""
```

**Checkpoint 1.** `python -c "import extract; print(extract.EXTRACT_TOOL['name'])"` prints `record_invoice`. Nothing calls the API yet. Read the three docs and predict: which fields come back null for `DOC_EMAIL`? (Should be `invoice_number` and `invoice_date`; `payment_method` should be `other` + `"Venmo"`.)

### Step 2 — Pydantic validation + the retry loop

Tool use guarantees the output *parses* and *matches the schema shape*. It does not guarantee the output makes *sense* — line items that don't sum to the total, a date in the wrong format, `"other"` with no detail. That's semantic validation, and it's your job. When it fails, the exam-correct move (Task 4.4) is: **re-send the document + the failed extraction + the specific validation error**, and let the model self-correct. Not "try again" — the *specific error*. That's the entire difference between a retry that converges and one that flails.

Add to `extract.py`:

```python
# ---------------------------------------------------------------- semantic validation
class LineItem(BaseModel):
    description: str
    amount: float

class Invoice(BaseModel):
    vendor_name: str
    invoice_number: Optional[str]
    invoice_date: Optional[str]
    total_amount: float
    payment_method: Literal["credit_card", "ach", "wire", "check", "other", "unclear"]
    payment_method_detail: Optional[str] = None
    line_items: list[LineItem]

    @model_validator(mode="after")
    def semantic_checks(self):
        if self.line_items:
            s = round(sum(li.amount for li in self.line_items), 2)
            if abs(s - self.total_amount) > 0.01:
                raise ValueError(
                    f"line_items sum to {s} but total_amount is {self.total_amount}. Every charge on "
                    "the document — including tax, fees, shipping — must appear as a line item.")
        if self.payment_method == "other" and not self.payment_method_detail:
            raise ValueError("payment_method is 'other' but payment_method_detail is empty.")
        if self.invoice_date is not None:
            try:
                date.fromisoformat(self.invoice_date)
            except ValueError:
                raise ValueError(f"invoice_date '{self.invoice_date}' is not ISO YYYY-MM-DD.")
        return self

# ---------------------------------------------------------------- extraction + retry loop
SYSTEM = ("You extract structured data from payment documents by calling record_invoice. "
          "Record only what the document states; use null for absent information.")

def extract(document, system=SYSTEM, max_retries=2):
    messages = [{"role": "user", "content":
                 f"Extract the invoice data from this document:\n\n<document>\n{document}\n</document>"}]
    for attempt in range(max_retries + 1):
        resp = client.messages.create(
            model=MODEL, max_tokens=2048, system=system,
            tools=[EXTRACT_TOOL],
            tool_choice={"type": "tool", "name": "record_invoice"},  # ALWAYS a tool call, never prose
            thinking={"type": "disabled"},  # forced tool_choice requires thinking off
            messages=messages,
        )
        tool_use = next(b for b in resp.content if b.type == "tool_use")
        try:
            inv = Invoice.model_validate(tool_use.input)
            print(f"  [attempt {attempt}] VALID")
            return inv, attempt
        except ValidationError as e:
            print(f"  [attempt {attempt}] validation failed: {e.errors()[0]['msg'][:90]}")
            # Retry-with-error-feedback: document is still in context, add the failed
            # extraction (assistant turn) + the SPECIFIC error (tool_result).
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": [{
                "type": "tool_result", "tool_use_id": tool_use.id, "is_error": True,
                "content": (f"Validation failed:\n{e}\n\nRe-read the document and call record_invoice "
                            "again with corrected values. If information is genuinely absent from the "
                            "document, use null — do not invent it."),
            }]})
    print("  gave up: error not resolvable by retry")
    return None, max_retries

if __name__ == "__main__":
    print("--- DOC_CLEAN ---"); extract(DOC_CLEAN)
    print("--- DOC_TAX ---");   extract(DOC_TAX)
```

**Checkpoint 2.** Run `python extract.py`.
- `DOC_CLEAN`: `VALID` on attempt 0.
- `DOC_TAX`: this doc is a trap — the "obvious" extraction is two line items ($40 + $35) against a total of $82.50, which fails the sum check. Watch attempt 0 fail with the exact sum error, then attempt 1 come back with tax added as a third line item and pass. That's a **format/structural error — retry-fixable**. (If the model gets it right on attempt 0, run it again or remove the word "tax" from the line to make the trap stronger.)
- Add `extract(DOC_EMAIL)` and confirm `invoice_number=None`, `invoice_date=None`, `payment_method='other'`, `payment_method_detail` mentioning Venmo. Null instead of fabrication — the nullable schema doing its job.

### Step 3 — Few-shot examples for varied formats

Detailed instructions plateau; few-shot examples generalize. The exam's specific claim (Task 4.2): 2–4 targeted examples demonstrating *varied document structures* fix inconsistent extraction better than more prose rules. Show one formal-table doc and one informal-narrative doc, each with its correct output — including correct null handling — so the model learns the *judgment*, not just the format.

Add to `extract.py`:

```python
FEW_SHOT = """
Here are examples of correct extractions from differently-formatted documents:

<example>
<document>STATEMENT 2209 | Vexler Legal | 03/02/2026 | Retainer $500.00 | Filing fees $85.00 | Balance: $585.00 | Remit by check</document>
<correct_extraction>{"vendor_name": "Vexler Legal", "invoice_number": "2209", "invoice_date": "2026-03-02",
"total_amount": 585.00, "payment_method": "check", "payment_method_detail": null,
"line_items": [{"description": "Retainer", "amount": 500.00}, {"description": "Filing fees", "amount": 85.00}]}
</correct_extraction>
Note: "03/02/2026" was normalized to ISO. The statement number counts as the invoice_number.
</example>

<example>
<document>text from Jim: "yo the lawn guys came by, $75, I paid cash from the drawer"</document>
<correct_extraction>{"vendor_name": "lawn service (unnamed)", "invoice_number": null, "invoice_date": null,
"total_amount": 75.00, "payment_method": "other", "payment_method_detail": "cash",
"line_items": [{"description": "lawn service", "amount": 75.00}]}
</correct_extraction>
Note: no document number or date exists, so both are null — they were not invented.
</example>
"""

SYSTEM_FS = SYSTEM + "\n" + FEW_SHOT
```

Change the `__main__` calls to `extract(DOC_EMAIL, system=SYSTEM_FS)` etc.

**Checkpoint 3.** Re-run all three docs with `SYSTEM_FS`. Everything should now pass on attempt 0 more consistently (run `DOC_TAX` a few times — the few-shot examples' "sums must match" demonstrations raise the first-pass rate). This is your baseline for Break-it comparisons: **few-shot is the tool for format variety, prompts-with-more-rules is not.**

### Step 4 — Message Batches: cheap, slow, and correlated by custom_id

The Batches API facts the exam tests cold (Task 4.5, sample Q11):

- **50% cost savings**, up to **24-hour** processing window, **no latency SLA**. Right for overnight/weekly jobs; *wrong* for anything blocking (pre-merge checks, live extraction).
- **No multi-turn tool calling inside a batch request.** Your Step-2 retry loop cannot run inside the batch — so the architecture is: batch does single-shot extraction → you validate locally → failures get the synchronous retry loop (or go into the *next* batch).
- Results come back **in any order** — correlate by `custom_id`, never by position.
- On failures: resubmit **only the failed custom_ids**, with the fix applied (real-world: chunking a doc that blew the context limit; tonight: a poisoned model name).

Add to `extract.py`:

```python
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

def build_request(custom_id, document, model=MODEL):
    return Request(custom_id=custom_id, params=MessageCreateParamsNonStreaming(
        model=model, max_tokens=2048, system=SYSTEM_FS,
        tools=[EXTRACT_TOOL], tool_choice={"type": "tool", "name": "record_invoice"},
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content":
                   f"Extract the invoice data from this document:\n\n<document>\n{document}\n</document>"}],
    ))

def run_batch(requests):
    batch = client.messages.batches.create(requests=requests)
    print(f"batch {batch.id}: {batch.processing_status}")
    t0 = time.time()
    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        print(f"  ...{batch.processing_status} ({batch.request_counts})")
        time.sleep(15)
    print(f"batch ended in {time.time() - t0:.0f}s")
    ok, failed = {}, {}
    for result in client.messages.batches.results(batch.id):   # arrives in ANY order
        if result.result.type == "succeeded":
            msg = result.result.message
            ok[result.custom_id] = next(b for b in msg.content if b.type == "tool_use").input
        else:
            failed[result.custom_id] = result.result           # errored / canceled / expired
    return ok, failed

def batch_pipeline():
    docs = {"doc-clean": DOC_CLEAN, "doc-email": DOC_EMAIL, "doc-tax": DOC_TAX}
    requests = [build_request(cid, d) for cid, d in docs.items()]
    requests.append(build_request("doc-poisoned", DOC_CLEAN, model="claude-sonnet-5-typo"))  # forced failure

    ok, failed = run_batch(requests)
    print(f"\nsucceeded: {list(ok)}\nfailed: {list(failed)}")

    # Local validation — batches can't run the retry loop, so failures fall back to sync
    for cid, data in ok.items():
        try:
            Invoice.model_validate(data)
            print(f"  {cid}: valid")
        except ValidationError:
            print(f"  {cid}: semantic failure -> synchronous retry loop")
            extract(docs[cid])

    # Resubmit ONLY the failed custom_ids, with the fix applied
    if failed:
        print("\nresubmitting failed docs with corrected params...")
        retry = [build_request(cid, DOC_CLEAN) for cid in failed]   # fix = real model name
        ok2, failed2 = run_batch(retry)
        print(f"resubmit: succeeded={list(ok2)} failed={list(failed2)}")

if __name__ == "__main__":
    batch_pipeline()
```

**Checkpoint 4.** Run it. Small batches usually end within a minute or two (remember: *up to* 24h, no guarantee). You should see 3 succeeded + `doc-poisoned` errored (`invalid_request` — the bogus model name), then a resubmit of just that one custom_id succeeding. Do the SLA math out loud while you wait: *if a customer SLA is 30 hours and the batch window is 24 hours, you must submit at most every 30 − 24 = 6 hours.* And note the exam's other move: **refine your prompt on a small sample synchronously (Steps 1–3) before batching thousands** — first-pass success rate is your cost lever, because every resubmission is a new batch.

### Step 5 — Field-level confidence → human-review routing

An aggregate "97% accurate" can hide a document type or field that's failing badly (Task 5.5). Two mechanics tonight: make the model emit **field-level confidence scores**, and route low-confidence extractions to a human queue. In production you'd calibrate the threshold against a labeled validation set and stratified-sample the *high*-confidence bucket to catch novel error patterns — self-reported confidence is a routing signal, not truth.

Add a `confidence` property to `EXTRACT_TOOL["input_schema"]["properties"]` and to `required`:

```python
EXTRACT_TOOL["input_schema"]["properties"]["confidence"] = {
    "type": "object",
    "description": "Your confidence (0.0-1.0) that each extracted field is correct, per field. "
                   "Be honest: informal or ambiguous sources warrant lower scores.",
    "properties": {k: {"type": "number"} for k in
                   ["vendor_name", "invoice_number", "invoice_date", "total_amount", "payment_method"]},
    "required": ["vendor_name", "invoice_number", "invoice_date", "total_amount", "payment_method"],
}
EXTRACT_TOOL["input_schema"]["required"].append("confidence")
```

Add the field to the Pydantic model (`confidence: dict[str, float]`) and a router:

```python
REVIEW_THRESHOLD = 0.8

def route(doc_id, doc_type, inv: Invoice):
    low = {k: v for k, v in inv.confidence.items() if v < REVIEW_THRESHOLD}
    dest = "HUMAN REVIEW" if low else "AUTO-ACCEPT"
    print(f"  {doc_id} [{doc_type}] -> {dest}" + (f"  low-confidence: {low}" if low else ""))
    return dest

if __name__ == "__main__":
    for doc_id, doc_type, doc in [("doc-clean", "formal_invoice", DOC_CLEAN),
                                  ("doc-email", "informal_email", DOC_EMAIL),
                                  ("doc-tax",   "retail_receipt", DOC_TAX)]:
        inv, _ = extract(doc, system=SYSTEM_FS)
        if inv:
            route(doc_id, doc_type, inv)
```

**Checkpoint 5.** `doc-clean` and `doc-tax` should auto-accept; `doc-email` should route to human review (the vendor name and amount come from an informal secondhand message — confidence should reflect that). Notice you tagged each doc with a `doc_type`: that's the hook for the exam's real point — **track accuracy by document type and field**, because "informal_email" failing at 40% is invisible inside a 97% aggregate. If `doc-email` sails through at 0.95 confidence everywhere, that's LLM overconfidence — exactly why production calibrates thresholds against labeled data instead of trusting the raw scores.

## 3.4 Break it on purpose

### Break-it #1 — Non-nullable required field → watch it fabricate (Task 4.3)

Change `invoice_number` to `{"type": "string"}` (drop the `"null"`), keep it required, drop the "use null, never guess" line from the tool description, and make the Pydantic field `invoice_number: str`. Run `extract(DOC_EMAIL)` several times. The document contains no invoice number — but the schema *demands a string*, so the model produces one: `"N/A"`, `""`, or on a bad day something plausible-looking like `"MPS-150"`. That last one is the killer — downstream nothing flags it, and it looks real. **Lesson:** required non-nullable fields don't make missing data appear; they make the model fabricate it to satisfy the schema. Nullable-but-required is the honest design. Restore the nullable type.

### Break-it #2 — `tool_choice: "auto"` → prose instead of data (Task 4.3)

Change `tool_choice={"type": "tool", "name": "record_invoice"}` to `{"type": "auto"}` and remove `thinking={"type": "disabled"}` if you like. Run all three docs a handful of times. Usually it still calls the tool — but sometimes (especially on `DOC_EMAIL`, which reads like a message someone might *reply* to) it answers in prose, and your `next(b for b in resp.content if b.type == "tool_use")` throws `StopIteration`. A pipeline that crashes on 1-in-20 documents is not a pipeline. **Lesson:** `"auto"` means *the model may return text instead*; `"any"` guarantees *some* tool; forced `{"type": "tool", "name": ...}` guarantees *that* tool. For extraction, force it. Restore.

### Break-it #3 — Retry a doc where the information doesn't exist (Task 4.4)

Add this doc and run it through `extract()`:

```python
DOC_NO_TOTAL = """QUOTE — Ferrier Consulting
Scope: services as described in SOW-114.
Pricing: per the attached rate card and hours actually incurred.
Payment terms: Net 30 upon invoice."""
```

`total_amount` is required and non-nullable — and genuinely absent (it lives in an attachment you don't have). Watch every retry attempt fail or fabricate: the error feedback can't conjure information that isn't in the source. Compare with `DOC_TAX`, where retry #1 fixed it. **Lesson:** the exam's exact distinction — retries resolve *format and structural* errors; they are useless when the information is *absent from the source*. Classify your failures: format-mismatch → retry; info-absent → null the field (schema fix) or route to human, and cap retries so you don't burn tokens flailing.

---

# Exercise 4 — Design and Debug a Multi-Agent Research Pipeline

## 4.1 Objective + exam mapping

Build a coordinator that delegates to isolated subagents via a hand-rolled `Task` tool: explicit context passing, parallel Task calls in one response, structured claim/evidence/source/date findings, a simulated timeout with structured error propagation and coverage-gap annotation, and conflicting-source handling with attribution.

| What you build | Task statements drilled |
|---|---|
| Coordinator with `Task` in its tool list; hub-and-spoke, coordinator decomposes + aggregates | **1.2** |
| Subagents as fresh isolated conversations; ALL context passed explicitly in the prompt | **1.3** |
| Parallel subagents = multiple Task calls in ONE response (ThreadPoolExecutor + timing) | **1.3** |
| Per-role tool restriction (search agent can't read docs, synthesis agent has no data tools) | **2.3** |
| Structured findings: claim / evidence / source / date, preserved through synthesis | **5.6, 5.1** |
| Simulated timeout → structured error (failure type, attempted query, partial results, alternatives) → coordinator proceeds + annotates coverage gaps | **5.3** |
| Conflicting stats from credible sources → both preserved with attribution, well-established vs. contested | **5.6** |

This is exam Scenario 3. Sample Q7 (too-narrow decomposition), Q8 (structured error propagation), and Q9 (scoped cross-role tools) all live in this build.

## 4.2 Setup

Same venv, no new packages. Create `research.py` next to `extract.py`. There's no live web search here — a canned corpus stands in for the web, so runs are deterministic-ish and free of flaky networking. The two "credible sources that disagree" are baked in on purpose.

## 4.3 Step-by-step build

### Step 1 — Corpus + isolated subagent runner

A subagent is nothing magical: **a brand-new `messages` list with its own system prompt and its own (restricted) tool set.** It knows exactly what its prompt string tells it — nothing else. In the Agent SDK this is what the `Task` tool + `AgentDefinition` gives you; here you build it so the isolation is visible.

Each research subagent must return findings through a `report_findings` tool whose schema forces **claim / evidence / source / date** on every finding. That structure is what survives the trip back to the coordinator — separate content from metadata, or attribution dies in transit (Task 5.6).

Create `research.py`:

```python
import concurrent.futures
import json
import time

import anthropic

client = anthropic.Anthropic()
MODEL = "claude-sonnet-5"
SIMULATE_TIMEOUT = False   # flipped on in Step 4

# ---------------------------------------------------------------- fake web + local docs
WEB = [
    {"url": "https://econlab.example/remote-meta-2025", "date": "2025-11-02",
     "text": "Meta-analysis across 42 firms (n=310,000): fully remote teams showed a 4% DECLINE in "
             "measured output vs in-office baselines, concentrated in collaboration-heavy roles."},
    {"url": "https://futureofwork.example/pulse-2026", "date": "2026-03-18",
     "text": "Pulse survey of 1,200 knowledge workers: respondents self-report a 13% INCREASE in "
             "productivity when remote. Self-selected sample; productivity self-reported, not measured."},
    {"url": "https://hbs.example/hybrid-rct", "date": "2026-01-20",
     "text": "RCT at a 1,600-person firm: hybrid (2 days remote) output statistically indistinguishable "
             "from full-office, with 35% lower attrition."},
]
DOCS = {
    "internal_productivity_review.pdf": {"date": "2026-05-10",
        "text": "ACME internal review: ticket throughput per engineer flat YoY after the remote policy "
                "change; code-review latency up 22%; employee satisfaction up 18 points."},
}

# ---------------------------------------------------------------- subagent tools
SEARCH_TOOL = {
    "name": "search_web",
    "description": ("Search the web. Input: a short keyword query. Returns a list of {url, date, text}. "
                    "An empty list is a VALID result (no matches) — it is not an error."),
    "input_schema": {"type": "object", "properties": {"query": {"type": "string"}},
                     "required": ["query"]},
}
READ_TOOL = {
    "name": "read_document",
    "description": "Read a document from the local research library. Available: internal_productivity_review.pdf",
    "input_schema": {"type": "object", "properties": {"name": {"type": "string"}},
                     "required": ["name"]},
}
FINDINGS_TOOL = {
    "name": "report_findings",
    "description": ("Submit your final findings. Call exactly once, when done. Every finding MUST carry "
                    "verbatim evidence, the source URL/document name, and the source's publication date — "
                    "downstream agents cannot see the raw sources."),
    "input_schema": {"type": "object", "properties": {
        "findings": {"type": "array", "items": {"type": "object", "properties": {
            "claim":    {"type": "string"},
            "evidence": {"type": "string", "description": "verbatim excerpt"},
            "source":   {"type": "string", "description": "URL or document name"},
            "date":     {"type": "string", "description": "source publication date"}},
            "required": ["claim", "evidence", "source", "date"]}},
        "notes": {"type": "string"}},
        "required": ["findings"]},
}
REPORT_TOOL = {
    "name": "submit_report",
    "description": "Submit the final synthesized research report. Call exactly once.",
    "input_schema": {"type": "object", "properties": {
        "well_established": {"type": "array", "items": {"type": "object", "properties": {
            "claim": {"type": "string"},
            "sources": {"type": "array", "items": {"type": "object", "properties": {
                "source": {"type": "string"}, "date": {"type": "string"}},
                "required": ["source", "date"]}}},
            "required": ["claim", "sources"]}},
        "contested": {"type": "array", "items": {"type": "object", "properties": {
            "question": {"type": "string"},
            "positions": {"type": "array", "items": {"type": "object", "properties": {
                "position": {"type": "string"}, "source": {"type": "string"}, "date": {"type": "string"}},
                "required": ["position", "source", "date"]}}},
            "required": ["question", "positions"]}},
        "coverage_gaps": {"type": "array", "items": {"type": "string"}}},
        "required": ["well_established", "contested", "coverage_gaps"]},
}

# Each subagent gets ONLY the tools its role needs (Task 2.3: scoped tool access).
AGENTS = {
    "web_search": {
        "system": ("You are a web-search subagent. Search for sources relevant to your task, then call "
                   "report_findings exactly once. Report only what sources actually say."),
        "tools": [SEARCH_TOOL, FINDINGS_TOOL],
    },
    "doc_analysis": {
        "system": ("You are a document-analysis subagent. Read the document(s) named in your task, then "
                   "call report_findings exactly once."),
        "tools": [READ_TOOL, FINDINGS_TOOL],
    },
    "synthesis": {
        "system": ("You are a synthesis subagent. Your prompt contains research findings — you have NO "
                   "search tools and NO other source of information. Call submit_report exactly once. "
                   "Preserve source attribution on every claim. When credible sources conflict, put BOTH "
                   "positions under 'contested' with their sources and dates — never pick a winner "
                   "(differing dates may mean change over time, not contradiction). List any subtopics "
                   "that failed or are missing under coverage_gaps."),
        "tools": [REPORT_TOOL],
    },
}

# ---------------------------------------------------------------- subagent runner
def execute_subagent_tool(name, tool_input):
    if name == "search_web":
        q = tool_input["query"].lower()
        hits = [d for d in WEB if any(w in d["text"].lower() for w in q.split() if len(w) > 3)]
        return {"results": hits}
    if name == "read_document":
        doc = DOCS.get(tool_input["name"])
        return doc or {"error": {"errorCategory": "validation", "isRetryable": False,
                                 "message": f"No document named '{tool_input['name']}'"}}
    return {"error": f"unknown tool {name}"}

def run_subagent(agent_type, prompt):
    spec = AGENTS[agent_type]
    messages = [{"role": "user", "content": prompt}]   # <- this prompt is ALL the context it gets
    for _ in range(8):
        resp = client.messages.create(model=MODEL, max_tokens=4096, system=spec["system"],
                                      tools=spec["tools"], thinking={"type": "disabled"},
                                      messages=messages)
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            if block.name in ("report_findings", "submit_report"):     # terminal tool
                return {"status": "ok", "agent": agent_type, "output": block.input}
            out = execute_subagent_tool(block.name, block.input)
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": json.dumps(out)})
        if not results:   # ended without reporting — that's a structured error, not silence
            return {"status": "error", "failure_type": "no_structured_output", "agent": agent_type,
                    "message": "subagent ended its turn without calling its report tool"}
        messages.append({"role": "user", "content": results})
    return {"status": "error", "failure_type": "max_steps_exceeded", "agent": agent_type}
```

**Checkpoint 1.** Run a subagent directly:

```python
if __name__ == "__main__":
    out = run_subagent("web_search", "Find evidence on how remote work affects measured productivity.")
    print(json.dumps(out, indent=2))
```

You should get `status: ok` with 2–3 findings, each carrying `claim`, verbatim `evidence`, `source` URL, and `date`. Also try `run_subagent("synthesis", "Write a report about remote work.")` — with no findings in the prompt and no tools to fetch any, it produces a near-empty or hedged report. It literally cannot know anything you didn't pass. That's context isolation, experienced firsthand.

### Step 2 — The coordinator: Task tool + hub-and-spoke loop

The coordinator's tool list contains exactly one tool: `Task`. That's the raw-API equivalent of `allowedTools: ["Task"]` — no Task in the tool list, no subagents, full stop. The Task tool's *description* carries the two rules the exam hammers: subagents see **only the prompt you pass** (so pass findings verbatim), and independent subtasks go out as **multiple Task calls in a single response**.

Add to `research.py`:

```python
# ---------------------------------------------------------------- coordinator
TASK_TOOL = {
    "name": "Task",
    "description": (
        "Spawn a subagent. subagent_type: 'web_search' (searches the web, returns structured findings), "
        "'doc_analysis' (reads local research documents; available: internal_productivity_review.pdf), "
        "'synthesis' (combines findings into a final report — it has NO tools and NO memory of this "
        "conversation, so its prompt must contain, VERBATIM, every finding it should use, including each "
        "claim's evidence, source, and date). Subagents are isolated: they see ONLY the prompt string "
        "passed here. For independent subtasks, emit multiple Task calls in a SINGLE response so they "
        "run in parallel."),
    "input_schema": {"type": "object", "properties": {
        "subagent_type": {"type": "string", "enum": ["web_search", "doc_analysis", "synthesis"]},
        "prompt": {"type": "string"}},
        "required": ["subagent_type", "prompt"]},
}

COORDINATOR_SYSTEM = (
    "You are a research coordinator. Decompose the research question into subtopics covering its FULL "
    "scope, delegate research via Task, then delegate synthesis. Rules: "
    "(1) run independent research subtasks in parallel — multiple Task calls in one response; "
    "(2) pass complete findings verbatim into the synthesis prompt; "
    "(3) if a subagent fails, decide based on its error: retry, use an alternative approach, or proceed "
    "with partial results — any subtopic you drop MUST end up in the report's coverage_gaps; "
    "(4) never resolve conflicting statistics yourself — pass all positions, with sources and dates, to "
    "synthesis. After synthesis returns, present the report to the user, preserving attribution."
)

def run_task(subagent_type, prompt):
    if SIMULATE_TIMEOUT and subagent_type == "web_search" and "gig" in prompt.lower():
        return {"status": "error", "failure_type": "timeout",
                "attempted_task": prompt[:150], "partial_results": [],
                "alternatives": ["retry once with a narrower query",
                                 "proceed without this subtopic and flag it as a coverage gap"]}
    if subagent_type == "synthesis":
        print(f"\n  [prompt passed to synthesis — first 400 chars]\n  {prompt[:400]}\n")
    return run_subagent(subagent_type, prompt)

def run_research(question):
    messages = [{"role": "user", "content": question}]
    for step in range(12):
        resp = client.messages.create(model=MODEL, max_tokens=4096, system=COORDINATOR_SYSTEM,
                                      tools=[TASK_TOOL],           # <- "allowedTools includes Task"
                                      thinking={"type": "disabled"}, messages=messages)
        print(f"\n[coordinator step {step}] stop_reason={resp.stop_reason}")
        if resp.stop_reason == "end_turn":
            final = "".join(b.text for b in resp.content if b.type == "text")
            print("\n=== FINAL ===\n" + final)
            return final
        messages.append({"role": "assistant", "content": resp.content})
        calls = [b for b in resp.content if b.type == "tool_use"]
        for c in calls:
            print(f"  Task -> {c.input['subagent_type']}: {c.input['prompt'][:90]}...")
        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            outputs = list(ex.map(lambda c: run_task(c.input["subagent_type"], c.input["prompt"]), calls))
        print(f"  {len(calls)} task(s) completed in {time.perf_counter() - t0:.1f}s")
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": c.id, "content": json.dumps(o),
             "is_error": o.get("status") == "error"}
            for c, o in zip(calls, outputs)]})
    print("hit safety cap")

if __name__ == "__main__":
    run_research("Research: how does remote work affect productivity? Cover measured-output studies, "
                 "worker self-reports, hybrid arrangements, and our internal company data.")
```

**Checkpoint 2.** Run it. Watch the shape: coordinator decomposes → Task calls to `web_search` and `doc_analysis` → findings come back → coordinator spawns `synthesis`. Read the printed **synthesis prompt**: it should contain the actual findings — claims, evidence excerpts, URLs, dates — copied in verbatim, because the coordinator was told (twice: system prompt + tool description) that synthesis can't see anything else. That's Task 1.3's core skill: **explicit context passing, in the prompt, every time.** Also note sample Q7's failure lives right here: if the coordinator decomposed "productivity" into only measured-output subtopics and skipped self-reports, the miss happened at *decomposition* — the subagents downstream would all be executing their narrow briefs perfectly.

### Step 3 — Prove the parallelism

You already execute concurrently (`ThreadPoolExecutor`), but parallelism only happens if the model **emits multiple Task calls in one response**. Task calls spread across separate turns serialize no matter what your executor does — that's the exam's exact phrasing.

Run Step 2's script twice and compare the timing lines:

1. As-is. Expect step 0 to show `Task -> web_search` *and* `Task -> doc_analysis` together, and `2 task(s) completed in ~Ns` where N ≈ the *slower* subagent, not the sum.
2. Now edit `COORDINATOR_SYSTEM` rule (1) to say: *"run subtasks one at a time — emit at most one Task call per response, wait for each result before the next."* Re-run. Same subagents, now sequential turns: total wall-clock roughly the *sum* of subagent times, plus an extra coordinator round-trip per task.

**Checkpoint 3.** Write down both wall-clock numbers. The parallel run should be meaningfully faster (typically 1.5–2x here; more with more subagents). Restore rule (1). **Lesson:** parallelism is a *model-output pattern* (N tool_use blocks in one assistant message) that your executor then exploits — not something the executor can create on its own.

### Step 4 — Simulated timeout: structured error → partial results → coverage gap

Sample Q8, live. Flip the switch and add a subtopic that will fail:

```python
SIMULATE_TIMEOUT = True

if __name__ == "__main__":
    run_research("Research: how does remote work affect productivity? Cover measured-output studies, "
                 "worker self-reports, hybrid arrangements, our internal company data, AND gig-economy "
                 "platform work.")
```

Any `web_search` task mentioning gig work now returns a **structured error**: `failure_type: "timeout"`, the attempted task, (empty) partial results, and two concrete alternatives. It does *not* return a generic `"search unavailable"` (hides context — Q8 option B), does *not* return an empty result marked success (silent suppression — option C), and does *not* crash the whole run (workflow termination — option D).

**Checkpoint 4.** Watch the coordinator's next step after the error lands: with the alternatives spelled out, it should either retry once or proceed — and either way, the final report's `coverage_gaps` array should name gig-economy work as unresearched. The other four subtopics still get covered. That's the full Task 5.3 chain: **structured error → informed coordinator decision → partial results used → gap annotated instead of hidden.** Leave `SIMULATE_TIMEOUT = True` for Break-it #2; set it back to `False` for Step 5.

### Step 5 — Conflicting sources: preserve both, attribute, don't arbitrate

Your corpus already contains the landmine: econlab.example (2025-11-02) says measured output *fell 4%*; futureofwork.example (2026-03-18) says self-reported productivity *rose 13%*. Both "credible," different dates, different methodologies. The wrong behaviors: pick one, average them, or fuzz it into "studies show mixed results" with no attribution.

Re-run Step 2's original question and read the synthesis output's `contested` section closely.

**Checkpoint 5.** The report should show, under one contested question, **both** positions — each with its own source URL and date — and ideally note the methodological difference (measured output vs. self-report) that the evidence excerpts carry. The hybrid-RCT and internal-doc findings should sit in `well_established` with their sources. If the model editorializes a winner, tighten the synthesis system prompt ("never pick a winner") — but you'll usually find the *schema* did the heavy lifting: because `positions[].source` and `positions[].date` are required fields, the model can't structurally drop attribution. **Schema design is behavior design.** The `date` field also matters on its own: two different numbers from 2025 vs 2026 might be change-over-time, not contradiction — without dates, synthesis can't tell (Task 5.6).

## 4.4 Break it on purpose

### Break-it #1 — Assume context inheritance, watch synthesis hallucinate (Task 1.3)

In `TASK_TOOL`'s description, delete the isolation warning and replace it with a lie: *"Subagents can see this conversation, so keep Task prompts short — e.g. 'synthesize the findings above'."* Delete rule (2) from `COORDINATOR_SYSTEM` too. Re-run. The coordinator now sends synthesis a stub prompt; the printed synthesis prompt shows no findings in it. Synthesis — which genuinely cannot see the conversation — either returns a hollow report or, worse, **fabricates plausible findings with invented sources**. On the exam, "subagent output ignores the actual research" is diagnosed as missing explicit context passing, every time. Restore both texts.

### Break-it #2 — Degrade the structured error to a generic string (Task 5.3)

With `SIMULATE_TIMEOUT = True`, replace the timeout return in `run_task` with the exam's anti-pattern:

```python
return {"status": "error", "message": "search unavailable"}
```

Re-run the Step 4 question a few times. The coordinator now has nothing to reason with: no failure type (transient? permanent?), no attempted query (retry what?), no alternatives. Watch it retry blindly, or silently drop the gig-economy subtopic — and check the final report: `coverage_gaps` frequently comes back empty, because nothing downstream knew there *was* a gap. Compare against the Step 4 run. **Lesson:** generic errors don't just lose debugging info — they destroy the coordinator's ability to make recovery decisions and the report's honesty about its own coverage. Restore the structured error.

### Break-it #3 — Strip source/date from findings, watch attribution die (Task 5.6)

In `FINDINGS_TOOL`, remove `source` and `date` from the item properties and from `required` (leave `claim` and `evidence`). Re-run Step 5's question. The search agent still finds both conflicting studies — but the findings arrive at synthesis as bare claims. Now synthesis faces "-4%" vs "+13%" with no way to attribute either, no dates to consider change-over-time, and required `source`/`date` fields in *its* output schema that it can't honestly fill. Watch it invent attribution, collapse the conflict into mush ("estimates vary"), or arbitrarily crown one number. **Lesson:** provenance is lost at the *first* hop that drops it — no downstream prompt can reconstruct a claim-source mapping that was never carried. Structure the metadata into every intermediate output, not just the final one. Restore the schema.

---

## Where this maps on the exam

- **Exercise 3** is Domain 4 (Prompt Engineering & Structured Output, 20%) + Domain 5 (Context Management & Reliability, 15%): schemas, tool_choice, nullable-vs-fabrication, validation-retry, few-shot, batches, confidence routing. Exam Scenario 6, sample Q11.
- **Exercise 4** is Domain 1 (Agentic Architecture & Orchestration, 27%) + slices of Domain 2 (scoped tool distribution) and Domain 5 (error propagation, provenance): coordinator/Task, isolation, parallel spawning, structured errors, conflict handling. Exam Scenario 3, sample Q7–Q9.

Stacked with Exercises 1 & 2, you've now built against every scenario except CI/CD — and the failure modes you deliberately caused tonight (fabrication from a non-nullable field, hallucinated synthesis from missing context, a coverage gap nobody reported) are precisely the wrong-answer options you'll be eliminating on test day.
