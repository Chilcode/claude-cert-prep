# Exercises 1 & 2 — Multi-Tool Agent + Claude Code Team Workflow

> Claude Certified Architect — Foundations. Two build-it-tonight labs.
> Exercise 1 = raw Anthropic Messages API (Python). Exercise 2 = Claude Code config files + the CLI you already use.
> Model for all API code: `claude-sonnet-5`. Everything here is paste-ready.

The whole point of these labs is the thing you said you're missing: **given a scenario, build the thing.** So each step ends with a checkpoint (what to run, what you should see), and each exercise ends with **Break it on purpose** — deliberately sabotage the working thing and watch the failure mode. The exam tests whether you recognize those failure modes. Seeing them once beats reading about them ten times.

---

# Exercise 1 — Build a Multi-Tool Agent with Escalation Logic

## 1.1 Objective + exam mapping

Build a customer-support resolution agent on the raw Messages API: an agentic loop, 4 tools with careful descriptions, structured error responses, a deterministic tool-call interception hook enforcing a `$500` business rule, and multi-concern request handling.

| What you build | Task statements drilled |
|---|---|
| Agentic loop driven by `stop_reason` (`tool_use` → continue, `end_turn` → stop) | **1.1** |
| 4 tools, incl. 2 easily-confused ones (`get_customer` vs `lookup_order`) with careful descriptions | **2.1** |
| Structured tool errors: `errorCategory` (transient/validation/business/permission) + `isRetryable` | **2.2** |
| Interception hook: block refunds > `$500` and refunds before identity is verified → redirect to escalation | **1.4, 1.5** |
| Multi-concern message → decompose → investigate each → one unified resolution + structured handoff | **1.4, 1.6, 5.2** |

This *is* exam Scenario 1 (Customer Support Resolution Agent). Sample questions 1, 2, and 3 are literally about the tradeoffs you'll build here.

## 1.2 Setup (Windows / PowerShell)

You need an **Anthropic API key** from console.anthropic.com. This is billed separately from your Claude Max / Claude Code subscription — the raw API is not the same account surface as the CLI.

```powershell
cd C:\Users\david.rios\Dev\claude-cert-prep\exercises
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
pip install anthropic
$env:ANTHROPIC_API_KEY = "sk-ant-..."  # your key; session-scoped
$env:PYTHONIOENCODING  = "utf-8"       # cp1252 defense, per your usual setup
```

Starter tree:

```
claude-cert-prep\exercises\
  .venv\
  agent.py          # you build this
```

## 1.3 Step-by-step build

### Step 1 — Fake backend + 4 tools with careful descriptions

The tool **descriptions** are the only thing the model uses to pick a tool. Two of these tools overlap on purpose (`get_customer` and `lookup_order` both "look something up" and both take an id-like string) — the exam's sample Q2 is exactly this confusion. Careful descriptions are what keep them apart. Notice each description states: what it does, its input format, an example query, and *when to use it vs. the other tool*.

Create `agent.py`:

```python
import json
import anthropic

client = anthropic.Anthropic()
MODEL = "claude-sonnet-5"

# ---------------------------------------------------------------- fake backend
CUSTOMERS = {
    "jane doe":  {"customer_id": "cust_001", "name": "Jane Doe",  "email": "jane@example.com"},
    "john smith":{"customer_id": "cust_002", "name": "John Smith","email": "john@example.com"},
}
ORDERS = {
    "1001": {"order_id": "1001", "customer_id": "cust_001", "amount": 49.99, "status": "delivered", "item": "Wireless mouse"},
    "1002": {"order_id": "1002", "customer_id": "cust_001", "amount": 620.00, "status": "delivered", "item": "Standing desk"},
    "1003": {"order_id": "1003", "customer_id": "cust_001", "amount": 89.50, "status": "delivered", "item": "Desk lamp"},
}

def err(category, is_retryable, message):
    # This dict is what the MODEL reads to decide retry vs explain vs escalate.
    return {"error": {"errorCategory": category, "isRetryable": is_retryable, "message": message}}

# ---------------------------------------------------------------- tool schemas
TOOLS = [
    {
        "name": "get_customer",
        "description": (
            "Look up a CUSTOMER ACCOUNT and return a verified customer_id. "
            "Input: the customer's full name or email address (e.g. \"Jane Doe\" or \"jane@example.com\"). "
            "Use this FIRST for any request, before any order or refund operation — it is how you "
            "establish which account you are acting on. Do NOT use this to look up an order number; "
            "for anything tied to an order (status, amount, refunds) use lookup_order instead. "
            "Returns customer_id, name, email. Returns a validation error if no account matches."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"identifier": {"type": "string", "description": "Customer full name or email"}},
            "required": ["identifier"],
        },
    },
    {
        "name": "lookup_order",
        "description": (
            "Look up a single ORDER by its numeric order number and return its details "
            "(amount, status, item, owning customer_id). Input: the order number as a string "
            "(e.g. \"1002\"). Use this when the customer references a specific order — a charge, a "
            "delivery, a damaged item, a refund target. Do NOT use this to find a person; if you only "
            "have a name or email, call get_customer first. Returns a validation error if the order "
            "number does not exist, and a transient error if the order service times out."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "description": "Order number, e.g. 1002"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "process_refund",
        "description": (
            "Issue a refund against an order. Input: order_id (string) and amount (number, USD). "
            "Only call this after the customer's identity is verified via get_customer and the order "
            "is confirmed via lookup_order. Refunds at or under the auto-approval limit are issued "
            "immediately; larger refunds are blocked by policy and must be escalated to a human."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "amount":   {"type": "number", "description": "Refund amount in USD"},
            },
            "required": ["order_id", "amount"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Hand the case to a human agent. Use this when the customer explicitly asks for a human, "
            "when policy blocks an action (e.g. a refund over the limit), or when you cannot make "
            "progress. Input: a structured handoff summary — customer_id, a one-line root_cause, the "
            "refund_amount or action at issue, and your recommended_action — because the human cannot "
            "see this conversation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id":       {"type": "string"},
                "root_cause":        {"type": "string"},
                "amount_or_action":  {"type": "string"},
                "recommended_action":{"type": "string"},
            },
            "required": ["root_cause", "recommended_action"],
        },
    },
]

# ---------------------------------------------------------------- tool execution
def execute_tool(name, tool_input, state):
    if name == "get_customer":
        rec = CUSTOMERS.get(tool_input["identifier"].strip().lower())
        if not rec:
            return err("validation", False, f"No account matches '{tool_input['identifier']}'. Ask for a valid name or email.")
        state["verified_customer_id"] = rec["customer_id"]   # <- prerequisite is now satisfied
        return rec
    if name == "lookup_order":
        oid = tool_input["order_id"]
        if oid == "9999":  # simulated flaky backend
            return err("transient", True, "Order service timed out. Safe to retry.")
        rec = ORDERS.get(oid)
        if not rec:
            return err("validation", False, f"Order '{oid}' does not exist. Ask the customer to confirm the number.")
        return rec
    if name == "process_refund":
        return {"refund_id": "rf_" + tool_input["order_id"], "refunded": tool_input["amount"], "status": "issued"}
    if name == "escalate_to_human":
        return {"ticket_id": "esc_204", "status": "escalated", "handoff": tool_input}
    return err("validation", False, f"Unknown tool {name}")
```

**Checkpoint 1.** Run `python -c "import agent; print(len(agent.TOOLS))"` — you should see `4`. Nothing calls the API yet; you've just defined the surface.

### Step 2 — The agentic loop (stop_reason drives everything)

This is the beating heart of Domain 1. The loop continues **only** because `stop_reason == "tool_use"` and stops **only** on `end_turn`. The `max_steps` cap is a *safety net*, not the stop condition — the exam explicitly flags "iteration caps as the primary stopping mechanism" as an anti-pattern, and so is "parsing assistant text to decide you're done." We do neither.

Thinking is disabled here so `response.content` is just text + `tool_use` blocks — cleaner to watch while you learn. Append the **full `response.content`** back as the assistant turn every iteration (that's how the model sees its own tool calls), and return every `tool_result` in a single user message.

Add to `agent.py`:

```python
SYSTEM = (
    "You are a customer support resolution agent. Resolve returns, billing disputes, and account "
    "issues using your tools. Verify who you are helping before acting on their orders. Escalate to "
    "a human when a case needs human approval or you cannot make progress."
)

def run(user_message, intercept=None):
    state = {"verified_customer_id": None}
    messages = [{"role": "user", "content": user_message}]

    for step in range(20):  # safety net ONLY. Real stop condition is end_turn below.
        resp = client.messages.create(
            model=MODEL, max_tokens=2048, system=SYSTEM, tools=TOOLS,
            thinking={"type": "disabled"}, messages=messages,
        )
        print(f"\n[step {step}] stop_reason = {resp.stop_reason}")

        if resp.stop_reason == "end_turn":
            final = "".join(b.text for b in resp.content if b.type == "text")
            print("\n=== FINAL ===\n" + final)
            return final

        # stop_reason == "tool_use": echo the assistant turn, run each tool, feed results back.
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            # (interception hook wires in here in Step 4)
            gate = intercept(block.name, block.input, state) if intercept else None
            result = gate if gate is not None else execute_tool(block.name, block.input, state)
            is_error = "error" in result or "blocked" in result
            print(f"  -> {block.name}({json.dumps(block.input)}) => {json.dumps(result)}")
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
                "is_error": is_error,
            })
        messages.append({"role": "user", "content": results})

    print("hit safety cap without end_turn")  # you should almost never see this

if __name__ == "__main__":
    run("Hi, I'm Jane Doe. Can you check the status of order 1001?")
```

**Checkpoint 2.** Run `python agent.py`. You should see step 0 print `stop_reason = tool_use` and a `get_customer` call, step 1 another `tool_use` for `lookup_order`, then a step with `stop_reason = end_turn` and a final answer stating order 1001 (wireless mouse) is delivered. If you see the model call `lookup_order` on the name "Jane Doe" instead of `get_customer` on the number — that's the tool-confusion failure you'll force on purpose later.

### Step 3 — Exercise the structured error paths

Structured errors (`errorCategory` + `isRetryable`) are what let the agent recover *correctly*: retry a transient timeout, but explain a validation/business error to the customer instead of hammering it. Your backend already returns these. Now watch the model consume them.

Run two inputs (edit the `__main__` line or add calls):

```python
run("I'm Jane Doe. What's the status of order 8888?")   # validation: order doesn't exist
run("I'm Jane Doe. Check order 9999 for me.")           # transient: times out, then retryable
```

**Checkpoint 3.**
- For `8888` (validation, `isRetryable: false`): the model reads the error, does **not** retry, and asks Jane to confirm the number. One `lookup_order` call, then it explains.
- For `9999` (transient, `isRetryable: true`): the model sees `isRetryable: true` and **retries** `lookup_order("9999")` at least once before giving up gracefully. Watch for two `lookup_order` calls in the trace.

That difference — retry vs. don't — is entirely driven by the metadata you returned. That's Task 2.2.

### Step 4 — The interception hook (deterministic business rule)

Here's the exam's single most-tested idea (sample Q1): when a rule has money or identity consequences, **enforce it in code, not in a prompt.** A prompt says "please don't refund over $500" — the model complies *most* of the time. A hook is a gate the tool call physically cannot pass. In the Claude Agent SDK this is a tool-call interception hook; on the raw API you build the same gate by hand, which is better for learning because you can see it's just code sitting between the model's decision and the side effect.

The hook enforces two things:
1. **Prerequisite gate** — block `lookup_order` and `process_refund` until `get_customer` has set a verified `customer_id`. (Directly sample Q1.)
2. **Threshold + redirect** — block `process_refund` over `$500` and steer the model to `escalate_to_human`.

Add to `agent.py`:

```python
AUTO_REFUND_LIMIT = 500.0

def intercept(name, tool_input, state):
    # Return a dict to BLOCK (becomes the tool result); return None to ALLOW execution.
    if name in ("lookup_order", "process_refund") and not state["verified_customer_id"]:
        return {"blocked": {"errorCategory": "permission", "isRetryable": False,
                "message": "Identity not verified. Call get_customer and confirm the account before this operation."}}
    if name == "process_refund" and float(tool_input.get("amount", 0)) > AUTO_REFUND_LIMIT:
        return {"blocked": {"errorCategory": "business", "isRetryable": False,
                "message": (f"Refund ${tool_input['amount']:.2f} exceeds the ${AUTO_REFUND_LIMIT:.0f} auto-approval "
                            "limit. Do not retry. Escalate to a human with escalate_to_human.")}}
    return None
```

Wire it in — change the `__main__` block:

```python
if __name__ == "__main__":
    run("I'm Jane Doe. Order 1002 (the standing desk) arrived broken. Please refund me the full $620.",
        intercept=intercept)
```

**Checkpoint 4.** Run it. You should see: `get_customer` → `lookup_order("1002")` → the model attempts `process_refund("1002", 620)` → the trace shows a `blocked` result with `errorCategory: business` → the model then calls `escalate_to_human` with a filled-in handoff, and the final message tells Jane it's been escalated. The refund **never executed.** That's a deterministic guarantee — no phrasing of the request can get $620 past the gate.

### Step 5 — Multi-concern decomposition + handoff

Real tickets bundle problems. The agent must split one message into distinct items, investigate each (sharing the verified customer context), and synthesize one resolution — escalating only the part that needs it, with a structured handoff the human can act on without the transcript.

```python
if __name__ == "__main__":
    run(
        "Hi, I'm Jane Doe. Two things: I want a $89.50 refund on order 1003, the desk lamp, "
        "because it's defective — AND order 1002, the standing desk, also arrived damaged and "
        "I want the full $620 back for that one too.",
        intercept=intercept,
    )
```

**Checkpoint 5.** Watch the trace: `get_customer` once (shared context), `lookup_order("1003")` and `lookup_order("1002")` (both concerns investigated), `process_refund("1003", 89.50)` **succeeds** (under the limit), `process_refund("1002", 620)` is **blocked** and routed to `escalate_to_human`. The final message resolves concern 1 (refund issued) and reports concern 2 as escalated — two problems, two different outcomes, one coherent answer. That's Task 1.4 / 1.6 / 5.2 in one run.

## 1.4 Break it on purpose

Each of these turns a working agent into a broken one so you can feel the failure the exam is testing.

### Break-it #1 — Strip the descriptions, watch tool selection collapse (Task 2.1)

Replace both descriptions with the exam's "minimal" versions and remove the disambiguation:

```python
# get_customer:  "description": "Retrieves customer information."
# lookup_order:  "description": "Retrieves order details."
```

Run `run("Hi, can you check my order 1002?")`. With rich descriptions the model reliably starts with `get_customer` (it has no account yet) or correctly reaches for `lookup_order`. With the stripped ones you'll see it misroute — often calling `get_customer` with "1002" as if 1002 were a name, or picking the wrong tool outright. **Lesson:** tool descriptions are the routing mechanism; "first step to fix misrouting" on the exam is *expand the descriptions*, not add a classifier (sample Q2, answer B). Restore the good descriptions after.

### Break-it #2 — Delete the hook, trust the prompt instead (Tasks 1.4, 1.5)

Comment out `intercept=intercept` in the `process_refund` run, and instead add a line to `SYSTEM`: `"Never issue a refund over $500."` Now run the $620 refund a handful of times. Sometimes it escalates — and sometimes it just calls `process_refund("1002", 620)` and the money goes out. **Lesson:** prompt-based compliance is probabilistic; for money/identity rules you need the deterministic hook (sample Q1, answer A — a programmatic prerequisite, not a stronger prompt). Re-enable the hook.

### Break-it #3 — Downgrade structured errors to a generic string (Task 2.2)

In `execute_tool`, make the validation and transient branches return a bare string instead of the structured dict:

```python
return err("validation", False, "...")   # replace with:  return {"error": "Operation failed"}
```

Re-run the `9999` (transient) and `8888` (validation) inputs. Now the model can't tell retryable from not: it may retry the permanent validation error uselessly, or give up on the transient one that a retry would have fixed. **Lesson:** uniform "Operation failed" errors destroy the agent's ability to recover appropriately; `errorCategory` + `isRetryable` are what make recovery correct. Restore the structured version.

---

# Exercise 2 — Configure Claude Code for a Team Development Workflow

## 2.1 Objective + exam mapping

Configure a repo the way a team would: a project `CLAUDE.md`, path-scoped rules that load only for matching files, a skill that runs in an isolated fork with restricted tools, a shared MCP server plus a personal one, and hands-on feel for plan mode vs. direct execution. All of this happens in config files and the Claude Code CLI you already drive daily.

| What you configure | Task statements drilled |
|---|---|
| Project `CLAUDE.md` (project vs user scope, `@import`) | **3.1** |
| `.claude/rules/*.md` with `paths:` glob frontmatter (load only when a matching file is edited) | **3.3** |
| A project skill with `context: fork` + `allowed-tools` | **3.2** |
| `.mcp.json` with `${VAR}` env-var expansion + a personal `~/.claude.json` server, both live at once | **2.4** |
| Plan mode vs. direct execution across three tasks of increasing complexity | **3.4** |

## 2.2 Setup (throwaway practice repo)

Do this in a scratch repo so you don't touch a real project.

```powershell
cd C:\Users\david.rios\Dev\claude-cert-prep\exercises
mkdir cc-team-practice
cd cc-team-practice
git init
mkdir src\api, src\components, docs
"export function handler(req) { return req; }"           | Out-File -Encoding utf8 src\api\handler.ts
"export function Button() { return null; }"              | Out-File -Encoding utf8 src\components\Button.tsx
"import { Button } from './Button'; test('renders', () => {});" | Out-File -Encoding utf8 src\components\Button.test.tsx
"Team docs live here." | Out-File -Encoding utf8 docs\README.md
$env:TEAM_DOCS_ROOT = "C:\Users\david.rios\Dev\claude-cert-prep\exercises\cc-team-practice\docs"
```

Target tree once you finish the steps:

```
cc-team-practice\
  CLAUDE.md
  .mcp.json
  .claude\
    rules\
      api-conventions.md
      testing.md
    skills\
      map-area\
        SKILL.md
  src\api\handler.ts
  src\components\Button.tsx
  src\components\Button.test.tsx
  docs\README.md
```

## 2.3 Step-by-step build

### Step 1 — Project `CLAUDE.md` (shared, version-controlled)

Project-level config is committed and reaches every teammate on clone/pull. User-level (`~/.claude/CLAUDE.md`) is yours alone and is **never shared via git** — that distinction is the whole of sample-question territory for Task 3.1. Put universal standards here.

`cc-team-practice\CLAUDE.md`:

```markdown
# Project Standards — cc-team-practice

## Universal
- Language: TypeScript. Prefer explicit types over `any`.
- Every new function gets a colocated `*.test.ts(x)` next to the file it tests.
- Never commit secrets. Config that needs a token reads it from an env var.

## Testing
- Test files sit beside their source (e.g. Button.test.tsx next to Button.tsx).
- One behavior per `test()`; name tests by the behavior, not the function.

@docs/README.md
```

The `@docs/README.md` line is the `@import` syntax — it pulls that file's contents into context so you can keep `CLAUDE.md` modular instead of monolithic.

**Checkpoint 1.** Launch `claude` in `cc-team-practice`, then run `/memory`. You should see `CLAUDE.md` listed as a loaded project memory file. Ask *"what are this project's testing conventions?"* — it should answer from the file without you pasting anything.

### Step 2 — Path-scoped rules with glob frontmatter

Conventions that apply to files **spread across directories** (like test files, which live next to every component) don't fit a single-directory `CLAUDE.md`. `.claude/rules/*.md` with a `paths:` glob in the YAML frontmatter solves this: the rule loads **only** when you're editing a file that matches the glob — less irrelevant context, fewer tokens, and it follows the file type regardless of folder. This is sample Q6, answer A.

`.claude\rules\api-conventions.md`:

```markdown
---
paths: ["src/api/**/*"]
---
# API conventions
- Handlers are async and use try/catch with a typed error response.
- Validate the request shape at the top of every handler before any logic.
```

`.claude\rules\testing.md`:

```markdown
---
paths: ["**/*.test.*"]
---
# Testing conventions
- Arrange-Act-Assert, with a blank line between each section.
- Mock network calls; never hit a live endpoint in a unit test.
```

**Checkpoint 2.** In `claude`, ask it to *"add a test case to `src/components/Button.test.tsx`."* The `**/*.test.*` glob matches, so the testing rule loads and the generated test follows Arrange-Act-Assert. Then ask it to *"tweak `src/components/Button.tsx`"* (not a test, not under `src/api`) — neither rule's glob matches, so neither loads. You've made conventions travel with the file *type*, not the folder.

### Step 3 — A project skill with `context: fork` + `allowed-tools`

A skill is on-demand (invoked when relevant), unlike `CLAUDE.md` which is always loaded. Two frontmatter options matter here:
- **`context: fork`** runs the skill in an isolated sub-agent, so its verbose output (a codebase map, an exploration dump) returns a summary and **doesn't pollute your main conversation**.
- **`allowed-tools`** restricts what the skill can do while it runs — here, read-only, so a "map the code" skill can't accidentally write or run shell commands.

`.claude\skills\map-area\SKILL.md`:

```markdown
---
name: map-area
description: Summarize the structure of a subdirectory — files, exports, and how they connect. Read-only.
context: fork
allowed-tools: Read, Grep, Glob
argument-hint: <directory path, e.g. src/api>
---
# Map Area

Explore the directory given as the argument. Use Grep and Glob to find files and their
exported names, follow imports to see how they connect, and return a SHORT summary:
- files and what each exports
- the dependency edges between them
- anything that looks like an entry point

Do not modify any files. Return only the summary.
```

**Checkpoint 3.** In `claude`, invoke the skill (e.g. `/map-area src`, or ask "use the map-area skill on src"). Because of `context: fork`, the noisy file-by-file exploration happens in a sub-agent and you get back a tidy summary — your main transcript stays clean. Try to make it write a file mid-skill; `allowed-tools: Read, Grep, Glob` means it can't. If you invoke it with no argument, `argument-hint` prompts you for the directory.

### Step 4 — MCP servers: shared (`.mcp.json`) + personal (`~/.claude.json`)

Two scopes, both discovered at connection time and available **simultaneously**:
- **`.mcp.json`** (project root, committed) = shared team tooling. Secrets are never hardcoded — you expand an environment variable with `${VAR}`, so the file is safe to commit.
- **`~/.claude.json`** (your home dir) = personal / experimental servers your teammates don't get.

`cc-team-practice\.mcp.json` — a shared docs server whose root path is env-var-expanded (no token needed to run tonight; the pattern is identical for a real `${GITHUB_PERSONAL_ACCESS_TOKEN}`):

```json
{
  "mcpServers": {
    "team-docs": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "${TEAM_DOCS_ROOT}"]
    }
  }
}
```

> The exam's canonical credential example is a token: `"env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}" }`. Same `${VAR}` mechanism — the point is that the secret lives in your environment, not in the committed file.

Add a **personal, experimental** server to `~/.claude.json` (Windows: `C:\Users\david.rios\.claude.json`). Merge this into the existing JSON's top level — don't overwrite the file:

```json
{
  "mcpServers": {
    "scratch-memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
```

> On native Windows PowerShell, `npx` sometimes needs wrapping: set `"command": "cmd"` and prepend `"/c", "npx"` to args. In your WSL bash session, plain `npx` works.

**Checkpoint 4.** Restart `claude` in the repo and run `/mcp`. You should see **both** `team-docs` (project) and `scratch-memory` (personal) connected at the same time — proving project- and user-scoped servers coexist. Tools from both are now available to the agent.

### Step 5 — Plan mode vs. direct execution

Plan mode explores and designs *before* changing anything — right for large, multi-file, or multiple-valid-approach work where blind edits cause costly rework. Direct execution is right for a small, well-scoped, unambiguous change. Enter plan mode by pressing **Shift+Tab** to cycle permission modes until it shows plan mode (or launch `claude --permission-mode plan`). Run these three and notice where the plan step earns its keep:

1. **Direct execution — single-file, clear scope.** *"In `src/api/handler.ts`, add a guard that returns a 400 error object when `req` is null."* One file, obvious change. Plan mode here is pure overhead; just let it edit.
2. **Plan mode — multi-file change.** *"Rename `Button` to `PrimaryButton` everywhere it's defined, exported, imported, and tested."* This spans `Button.tsx` and `Button.test.tsx` (and any importer). Plan mode maps the usages and shows you the change set before touching anything — you catch a missed reference *before* it breaks.
3. **Plan mode — multiple valid approaches.** *"Add response caching to the API handler."* In-memory? Keyed how? TTL? There are several defensible designs. Plan mode surfaces the options and their tradeoffs so you decide the architecture up front, then execute the chosen one.

**Checkpoint 5.** You should feel the difference: task 1 is faster and cleaner in direct execution; tasks 2 and 3 give you a reviewable plan that prevents rework. That judgment — *is this architectural / multi-file / multi-approach, or is it a single well-scoped edit?* — is exactly what sample Q5 tests (answer A: enter plan mode for the monolith-to-microservices restructure).

## 2.4 Break it on purpose

### Break-it #1 — Wrong glob, silent no-op (Tasks 3.3, 3.1)

Change `testing.md`'s frontmatter to `paths: ["src/api/**/*"]`, then ask Claude to add a test to `Button.test.tsx`. The glob no longer matches the test file, so the testing rule **silently doesn't load** — the generated test ignores your Arrange-Act-Assert convention, with no error to tell you why. **Lesson:** path-scoped rules only fire on a matching glob; a convention that "isn't being applied" is usually a glob that doesn't match the file you're editing. (Related diagnosis for Task 3.1: put a rule in `~/.claude/CLAUDE.md` instead of the project and a teammate who clones the repo never receives it — same "silently missing" failure, different cause.) Restore `["**/*.test.*"]`.

### Break-it #2 — Remove `context: fork`, watch the transcript flood (Task 3.2)

Delete the `context: fork` line from `SKILL.md` and re-run `map-area` on `src`. Now the skill runs **in your main conversation**: every file it reads, every grep, every intermediate note dumps straight into your context instead of coming back as a summary. On a real codebase this exhausts your context window fast. **Lesson:** `context: fork` is what isolates verbose or exploratory skills so their output doesn't pollute the session. Restore it.

### Break-it #3 — Unset the env var, watch the MCP server fail (Task 2.4)

In a fresh shell (so `TEAM_DOCS_ROOT` is unset), launch `claude` and run `/mcp`. The `team-docs` server can't resolve `${TEAM_DOCS_ROOT}` and fails to start — it shows as errored, not silently skipped. **Lesson:** `${VAR}` expansion keeps secrets out of committed config, but the variable has to actually be present in the environment where Claude Code launches; a missing var is a visible startup failure, not a no-op. Re-export `TEAM_DOCS_ROOT` and confirm it connects again.

---

## Where this maps on the exam

- **Exercise 1** is Domain 1 (Agentic Architecture & Orchestration, 27%) + Domain 2 (Tool Design & MCP, 18%) + a slice of Domain 5 (Reliability): the loop, the hook, structured errors, decomposition, escalation.
- **Exercise 2** is Domain 3 (Claude Code Config & Workflows, 20%) + Domain 2 (MCP integration): hierarchy, glob rules, forked skills, MCP scoping, plan vs. direct.

If you can rebuild both from a blank folder without looking, you own roughly 45% of the scored content by weight — and, more to the point, you'll be reading each scenario question and already knowing which lever it's testing.
