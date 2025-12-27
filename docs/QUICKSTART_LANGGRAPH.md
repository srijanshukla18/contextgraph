# LangGraph Quickstart

Get ContextGraph capturing your LangGraph workflow decisions in 5 minutes.

## Prerequisites

- Python 3.10+
- LangGraph (`pip install langgraph`)
- ContextGraph server running (or local mode)

## Installation

```bash
pip install langgraph contextgraph
# or from source
pip install -e ./sdk/python
```

## "Doesn't LangGraph already have tracing via LangSmith?"

Yes. LangGraph workflows can be [traced via LangSmith](https://docs.langchain.com/langsmith/trace-with-langgraph) by setting env vars + API key. LangGraph also has great [interrupt/persistence primitives](https://docs.langchain.com/oss/python/langgraph/interrupts) for HITL workflows.

**ContextGraph is not a replacement for that.** It's the layer you add when:

| Need | LangSmith | ContextGraph |
|------|-----------|--------------|
| Trace execution | ✓ | ✓ |
| Data lives in your infra | ✗ LangChain-hosted | ✓ Self-hosted Postgres |
| Structured decision schema | Spans/events | DecisionRecord (evidence → policy → approval → action) |
| HITL → Approval records | ✗ (interrupts are workflow state) | ✓ Approvals with approver ID |
| Cross-vendor (OpenAI, Claude) | ✗ LangChain ecosystem | ✓ Same schema |

LangSmith gives you **execution traces**. ContextGraph gives you a **decision ledger**.

## Basic Integration

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from contextgraph.integrations.langgraph import ContextGraphCheckpointer

# Wrap your existing checkpointer
cg_checkpointer = ContextGraphCheckpointer(
    underlying=MemorySaver(),
    write_tools=["send_email", "update_crm"],
)

# Use it when compiling
graph = builder.compile(checkpointer=cg_checkpointer)

# Run your graph
result = graph.invoke({"messages": []}, {"configurable": {"thread_id": "123"}})

# Finalize to create DecisionRecord
cg_checkpointer.finalize_thread({"configurable": {"thread_id": "123"}})
```

## Full Example

```python
from typing import TypedDict, Annotated
from operator import add
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from contextgraph import ContextGraphClient, Config
from contextgraph.integrations.langgraph import ContextGraphCheckpointer

# 1. Define state
class State(TypedDict):
    messages: Annotated[list, add]
    account_data: dict
    credit_amount: float

# 2. Configure ContextGraph
config = Config(
    server_url="http://localhost:8080",
    write_tools=["issue_credit", "send_notification"],
)

# 3. Wrap checkpointer
cg_checkpointer = ContextGraphCheckpointer(
    underlying=MemorySaver(),
    config=config,
    state_keys_as_evidence=["account_data"],  # Snapshot these as evidence
    action_node_names=["issue_credit_node"],   # These nodes are actions
)

# 4. Define nodes
def gather_account(state: State) -> dict:
    """Fetch account data (becomes evidence)."""
    return {
        "account_data": {
            "id": "ACC-100",
            "name": "Acme Corp",
            "arr": 500000,
            "tier": "enterprise",
        }
    }

def calculate_credit(state: State) -> dict:
    """Calculate credit amount."""
    arr = state["account_data"]["arr"]
    return {"credit_amount": arr * 0.10}  # 10% credit

def issue_credit_node(state: State) -> dict:
    """Issue the credit (becomes action)."""
    return {"messages": [f"Issued ${state['credit_amount']} credit"]}

# 5. Build graph
builder = StateGraph(State)
builder.add_node("gather", gather_account)
builder.add_node("calculate", calculate_credit)
builder.add_node("issue_credit_node", issue_credit_node)

builder.add_edge(START, "gather")
builder.add_edge("gather", "calculate")
builder.add_edge("calculate", "issue_credit_node")
builder.add_edge("issue_credit_node", END)

graph = builder.compile(checkpointer=cg_checkpointer)

# 6. Run
thread_config = {"configurable": {"thread_id": "credit-request-001"}}
result = graph.invoke({"messages": [], "account_data": {}, "credit_amount": 0}, thread_config)

# 7. Finalize
record = cg_checkpointer.finalize_thread(thread_config)
print(f"DecisionRecord: {record.decision_id}")
```

## What Gets Captured

| Source | DecisionRecord Field |
|--------|---------------------|
| `state_keys_as_evidence` values | **Evidence** snapshots |
| `action_node_names` outputs | **Actions** |
| Tool calls in messages | **Evidence** or **Actions** (by tool name) |
| `on_interrupt()` calls | **Evidence** (interrupt context) |
| `on_resume()` calls | **Approvals** |

## Human-in-the-Loop

LangGraph's interrupt feature maps to ContextGraph approvals:

```python
# Build with interrupt
graph = builder.compile(
    checkpointer=cg_checkpointer,
    interrupt_before=["issue_credit_node"],  # Pause here for approval
)

thread_config = {"configurable": {"thread_id": "request-456"}}

# Run until interrupt
result = graph.invoke(initial_state, thread_config)

# Record the interrupt
cg_checkpointer.on_interrupt(thread_config, interrupt_value={"pending": "credit_approval"})

# ... human reviews and approves ...

# Record the approval
cg_checkpointer.on_resume(
    thread_config,
    approver_id="manager@company.com",
    resume_value="Approved: customer impact justified",
)

# Continue execution
result = graph.invoke(None, thread_config)

# Finalize
record = cg_checkpointer.finalize_thread(thread_config)
```

The resulting DecisionRecord includes:

```json
{
  "approvals": [
    {
      "approver": {"type": "human", "id": "manager@company.com"},
      "granted": true,
      "reason": "Approved: customer impact justified"
    }
  ]
}
```

## Configuration Options

```python
cg_checkpointer = ContextGraphCheckpointer(
    # Required: the actual checkpointer to wrap
    underlying=MemorySaver(),  # or PostgresSaver, SqliteSaver, etc.

    # Tool classification
    write_tools=["send_email", "update_db", "create_ticket"],
    read_tools=["fetch_account", "search_docs"],

    # State capture
    state_keys_as_evidence=["account_data", "context"],  # Snapshot these keys

    # Node classification
    action_node_names=["send_node", "commit_node"],  # These nodes are actions

    # Server
    server_url="http://localhost:8080",

    # Or pass pre-configured client
    client=ContextGraphClient(config),
)
```

## Async Support

For async graphs, use the async wrapper:

```python
from contextgraph.integrations.langgraph import AsyncContextGraphCheckpointer

cg_checkpointer = AsyncContextGraphCheckpointer(
    underlying=AsyncPostgresSaver(...),
    write_tools=["send_email"],
)

# Async methods available
await cg_checkpointer.aget_tuple(config)
await cg_checkpointer.aput(config, checkpoint, metadata, new_versions)
```

## Key Difference: Manual Finalization

Unlike OpenAI/Claude integrations, LangGraph requires you to call `finalize_thread()`:

```python
# OpenAI: automatic on trace end
# Claude: automatic on stop hook
# LangGraph: YOU must call this
record = cg_checkpointer.finalize_thread(thread_config)
```

Why? LangGraph graphs can be long-running, paused, resumed across sessions. Only you know when a "decision" is complete.

## Running the Server

```bash
# Docker
make docker-up

# Local
make setup && make server
```

## Verify It Works

```bash
# List decisions
curl http://localhost:8080/v1/decisions

# Explain a decision
curl http://localhost:8080/v1/decisions/{decision_id}/explain
```

Example response:

```json
{
  "decision_id": "dec_abc",
  "outcome": "committed",
  "evidence": [
    {
      "source": "state:account_data",
      "snapshot": {"id": "ACC-100", "arr": 500000}
    }
  ],
  "actions": [
    {
      "tool": "issue_credit_node",
      "params": {"credit_amount": 50000},
      "success": true
    }
  ],
  "approvals": [
    {
      "approver": {"type": "human", "id": "manager@company.com"},
      "granted": true
    }
  ],
  "metadata": {"steps": 3}
}
```

## Comparison with Other Integrations

| Aspect | OpenAI | Claude | LangGraph |
|--------|--------|--------|-----------|
| Integration | Trace processor | Hooks | Checkpointer wrapper |
| Automatic finalization | Yes | Yes | **No** (manual) |
| HITL support | No | No | **Yes** (on_interrupt/on_resume) |
| State snapshots | No | No | **Yes** (state_keys_as_evidence) |
| Complexity | Low | Medium | Higher |

LangGraph integration is most powerful for complex workflows with human approval steps.

## Troubleshooting

### No DecisionRecord created

1. Did you call `finalize_thread()`?
2. Were there any actions? (write tools or action nodes)

### State not captured as evidence

Ensure the key is in `state_keys_as_evidence`:

```python
state_keys_as_evidence=["account_data", "customer_info"]
```

### Approvals not showing

You must explicitly call both:

```python
cg_checkpointer.on_interrupt(config, value)   # When pausing
cg_checkpointer.on_resume(config, approver_id, value)  # When resuming
```

### Thread not found

Each thread_id has its own accumulator. Ensure consistent config:

```python
thread_config = {"configurable": {"thread_id": "my-thread"}}
# Use same config for invoke() and finalize_thread()
```

## Next Steps

- [Query API](../README.md#query-api) - Search and explain
- [DecisionRecord Schema](../spec/jsonschema/decision_record.json)
- [Example](../examples/langgraph_example.py)
