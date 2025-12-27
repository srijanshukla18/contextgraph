# OpenAI Agents SDK Quickstart

Get ContextGraph capturing your agent decisions in 5 minutes.

## Prerequisites

- Python 3.10+
- OpenAI Agents SDK (`pip install openai-agents`)
- ContextGraph server running (or local mode)

## Installation

```bash
pip install contextgraph
# or from source
pip install -e ./sdk/python
```

## 3-Line Integration

```python
from agents import set_tracing_processor
from contextgraph.integrations.openai_agents import ContextGraphTraceProcessor

processor = ContextGraphTraceProcessor(write_tools=["send_email", "create_ticket"])
set_tracing_processor(processor)

# Done. All agent runs now create DecisionRecords.
```

## Full Example

```python
from agents import Agent, Runner, function_tool, set_tracing_processor
from contextgraph.integrations.openai_agents import ContextGraphTraceProcessor

# 1. Define your tools
@function_tool
def get_account(account_id: str) -> dict:
    """Fetch account from CRM (read operation)."""
    return {"id": account_id, "name": "Acme Corp", "tier": "enterprise"}

@function_tool
def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email (write operation)."""
    return {"status": "sent", "message_id": "msg_123"}

# 2. Configure ContextGraph
processor = ContextGraphTraceProcessor(
    write_tools=["send_email"],      # These become "actions"
    read_tools=["get_account"],      # These become "evidence"
    server_url="http://localhost:8080",
)
set_tracing_processor(processor)

# 3. Create and run your agent
agent = Agent(
    name="outreach-agent",
    instructions="Help customers with their accounts.",
    tools=[get_account, send_email],
)

result = Runner.run_sync(agent, "Send a follow-up email to account ACC-001")

# 4. Cleanup
processor.shutdown()
```

## What Gets Captured

| Tool Type | ContextGraph Record |
|-----------|---------------------|
| Read tools (`get_account`, `search_db`) | **Evidence** - what the agent saw |
| Write tools (`send_email`, `create_ticket`) | **Actions** - what the agent did |
| Guardrails | **Policies** - rules that were checked |
| Handoffs | **Metadata** - agent-to-agent transfers |

## Configuration Options

```python
processor = ContextGraphTraceProcessor(
    # Tool classification
    write_tools=["send_email", "create_ticket", "update_crm"],
    read_tools=["get_account", "search_knowledge"],

    # Server connection
    server_url="http://localhost:8080",  # ContextGraph server

    # Local mode (skip server, write directly to Postgres)
    local_mode=True,
    postgres_url="postgresql://user:pass@localhost/contextgraph",
)
```

### Tool Classification

If you don't specify `read_tools`/`write_tools`, ContextGraph uses heuristics:

- **Write patterns**: `send_`, `create_`, `update_`, `delete_`, `post_`, `put_`
- **Read patterns**: `get_`, `fetch_`, `search_`, `list_`, `read_`

Explicit configuration always takes precedence.

## Running the Server

### Docker (recommended)

```bash
cd contextgraph
make docker-up    # Starts Postgres + API server on :8080
```

### Local

```bash
make setup        # Create DB
make server       # Start API on :8080
```

## Verify It Works

1. Run your agent
2. Check the API:

```bash
# List all decisions
curl http://localhost:8080/v1/decisions

# Get details for a specific decision
curl http://localhost:8080/v1/decisions/{decision_id}/explain
```

Example response:

```json
{
  "decision_id": "dec_abc123",
  "outcome": "committed",
  "evidence": [
    {
      "source": "get_account",
      "snapshot": {"id": "ACC-001", "name": "Acme Corp"}
    }
  ],
  "actions": [
    {
      "tool": "send_email",
      "params": {"to": "john@acme.com", "subject": "Follow-up"},
      "success": true
    }
  ]
}
```

## Run the Example

```bash
# Mock mode (no OpenAI API key needed)
python examples/openai_agents_example.py

# Real SDK mode
python examples/openai_agents_example.py --real
```

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│                   OpenAI Agents SDK                      │
│                                                          │
│   Agent.run() ─────► Trace Started                       │
│       │                   │                              │
│       ▼                   ▼                              │
│   tool_call() ────► Span (function) ──► ContextGraph    │
│       │                                  Processor       │
│       ▼                                      │           │
│   guardrail() ───► Span (guardrail)          │           │
│       │                                      │           │
│       ▼                                      ▼           │
│   Trace End ─────────────────────► DecisionRecord       │
│                                    created + sent        │
└─────────────────────────────────────────────────────────┘
```

The processor hooks into the SDK's native tracing system:

- `on_trace_start` - Initializes accumulator for the run
- `on_span_end` - Captures each tool call, guardrail, handoff
- `on_trace_end` - Builds and sends the DecisionRecord

## Guardrails → Policies

If you use OpenAI's guardrails, they're automatically captured as policy evaluations:

```python
from agents import Agent, InputGuardrail, GuardrailFunctionOutput

async def no_pii_guardrail(ctx, agent, input_data):
    has_pii = "ssn" in input_data.lower()
    return GuardrailFunctionOutput(
        output_info={"checked": "pii"},
        tripwire_triggered=has_pii,
    )

agent = Agent(
    name="safe-agent",
    input_guardrails=[InputGuardrail(guardrail_function=no_pii_guardrail)],
    ...
)
```

This becomes:

```json
{
  "policies": [
    {
      "policy_id": "no_pii_guardrail",
      "result": "pass",
      "message": "[\"pii\"]"
    }
  ]
}
```

## Troubleshooting

### No DecisionRecord created

DecisionRecords are only created when there are **actions** (write operations). If your agent only reads data, no record is created.

Fix: Ensure at least one tool is classified as a write tool.

### Server connection errors

```python
# Use local mode to skip the server
processor = ContextGraphTraceProcessor(
    write_tools=["send_email"],
    local_mode=True,
    postgres_url="postgresql://localhost/contextgraph",
)
```

### Tool not classified correctly

```python
# Explicitly specify tool classification
processor = ContextGraphTraceProcessor(
    write_tools=["my_custom_action"],  # Force as action
    read_tools=["my_custom_query"],    # Force as evidence
)
```

## Next Steps

- [Query API Reference](../README.md#query-api) - Search and explain decisions
- [DecisionRecord Schema](../spec/jsonschema/decision_record.json) - Full schema
- [Explorer UI](../ui/) - Visual decision browser
