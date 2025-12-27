# Claude Agent SDK Quickstart

Get ContextGraph capturing your Claude agent decisions in 5 minutes.

## Prerequisites

- Python 3.10+
- Claude Agent SDK (`pip install claude-agent-sdk`)
- ContextGraph server running (or local mode)

## Installation

```bash
pip install claude-agent-sdk contextgraph
# or from source
pip install -e ./sdk/python
```

## "Doesn't Claude already have hooks for logging?"

Yes. The Claude Agent SDK provides [hooks](https://platform.claude.com/docs/en/agent-sdk/hooks) (`PreToolUse`, `PostToolUse`, `Stop`) that let you log, audit, and block tool calls.

**ContextGraph is not a replacement for that.** It's the layer you add when:

| Need | Claude SDK Hooks | ContextGraph |
|------|------------------|--------------|
| Intercept tool calls | ✓ You implement | ✓ Built-in |
| Block dangerous ops | ✓ You implement | ✓ Policy functions |
| Structured audit schema | ✗ You build it | ✓ DecisionRecord |
| Queryable decision store | ✗ You build it | ✓ API + Postgres |
| Cross-vendor (OpenAI, LangGraph) | ✗ | ✓ Same schema |

Claude gives you the **interception points**. ContextGraph gives you the **decision ledger**.

## Basic Integration

```python
from claude_agent_sdk import Agent, AgentConfig
from contextgraph.integrations.claude_agent import contextgraph_hooks

hooks = contextgraph_hooks(write_tools=["Bash", "Write", "Edit"])

agent = Agent(config=AgentConfig(
    model="claude-sonnet-4-5-20250929",
    hooks=hooks,
))

# Run normally - decisions are captured automatically
result = agent.run("Create a config file for the project")
```

## Full Example with Policies

```python
from claude_agent_sdk import Agent, AgentConfig
from contextgraph import ContextGraphClient, Config
from contextgraph.integrations.claude_agent import contextgraph_hooks

# 1. Configure ContextGraph
config = Config(
    server_url="http://localhost:8080",
    write_tools=["Bash", "Write", "Edit"],
    read_tools=["Read", "Glob", "Grep"],
)

# 2. Define policy checks (optional)
def no_destructive_commands(tool_name: str, tool_input: dict, context) -> dict:
    """Block dangerous bash commands."""
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        dangerous = ["rm -rf", "DROP TABLE", "DELETE FROM", "> /dev/"]
        if any(d in cmd for d in dangerous):
            return {"passed": False, "message": f"Blocked: {cmd[:50]}"}
    return {"passed": True}

def require_file_path(tool_name: str, tool_input: dict, context) -> dict:
    """Ensure Write operations have valid paths."""
    if tool_name == "Write":
        path = tool_input.get("file_path", "")
        if not path or path.startswith("/etc/"):
            return {"passed": False, "message": "Invalid or dangerous path"}
    return {"passed": True}

# 3. Create hooks with policies
hooks = contextgraph_hooks(
    config=config,
    policies={
        "no_destructive": no_destructive_commands,
        "valid_path": require_file_path,
    },
    agent_name="my-claude-agent",
)

# 4. Configure agent
agent = Agent(config=AgentConfig(
    model="claude-sonnet-4-5-20250929",
    hooks=hooks,
))

# 5. Run
result = agent.run("Read the config and update the version number")
```

## What Gets Captured

| Hook | When | What's Recorded |
|------|------|-----------------|
| `PreToolUse` | Before tool runs | Policy checks, blocks |
| `PostToolUse` | After tool runs | Evidence (reads) or Actions (writes) |
| `Stop` | Agent completes | Final DecisionRecord sent |

### Tool Classification

| Tool | Type | DecisionRecord Field |
|------|------|---------------------|
| `Read`, `Glob`, `Grep` | Read | **Evidence** |
| `Bash`, `Write`, `Edit` | Write | **Actions** |
| Custom tools | Heuristic or explicit | Configurable |

## The Three Hooks

### PreToolUse - Policy Enforcement

Runs **before** each tool. Can block execution.

```python
def my_policy(tool_name: str, tool_input: dict, context) -> dict:
    # Return {"passed": False, "message": "..."} to block
    # Return {"passed": True} to allow
    return {"passed": True}
```

Blocked tools are recorded as failed `PolicyEval` in the DecisionRecord.

### PostToolUse - Capture Results

Runs **after** each tool. Captures output as evidence or action.

- Read tools → `Evidence` with snapshot of data
- Write tools → `Action` with params and result

### Stop - Finalize

Runs when agent stops. Creates and sends the `DecisionRecord`.

Only creates a record if there were **actions** (write operations).

## Configuration Options

```python
hooks = contextgraph_hooks(
    # Tool classification
    write_tools=["Bash", "Write", "Edit", "NotebookEdit"],
    read_tools=["Read", "Glob", "Grep", "WebFetch"],

    # Policy checks (tool_name, tool_input, context) -> {passed, message}
    policies={
        "policy_id": policy_function,
    },

    # Server connection
    server_url="http://localhost:8080",

    # Agent identification
    agent_name="my-agent",

    # Or pass a pre-configured client
    client=ContextGraphClient(config),
)
```

## Class-Based Alternative

If you prefer classes over the function:

```python
from contextgraph.integrations.claude_agent import ContextGraphHooks

hooks = ContextGraphHooks(
    write_tools=["Bash", "Write"],
    policies={"no_rm": my_policy},
)

agent = Agent(config=AgentConfig(
    model="claude-sonnet-4-5-20250929",
    hooks=hooks.as_dict(),
))
```

## Running the Server

```bash
# Docker (recommended)
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
  "decision_id": "dec_xyz",
  "outcome": "committed",
  "evidence": [
    {"source": "Read", "snapshot": {"content": "version = 1.0.0"}}
  ],
  "policies": [
    {"policy_id": "no_destructive", "result": "pass"}
  ],
  "actions": [
    {"tool": "Write", "params": {"file_path": "/app/config.py"}, "success": true}
  ]
}
```

## Policy Blocked? Shows in Record

When a policy blocks a tool:

```json
{
  "outcome": "denied",
  "outcome_reason": "Blocked by policy: Destructive command blocked",
  "policies": [
    {"policy_id": "no_destructive", "result": "fail", "message": "Destructive command blocked"}
  ]
}
```

## Comparison with OpenAI Integration

| Aspect | OpenAI Agents | Claude Agent |
|--------|---------------|--------------|
| Integration point | Trace processor | Hooks dict |
| Can block tools | No (observe only) | **Yes** (PreToolUse) |
| Setup | 2 lines | 3 lines |
| Policy enforcement | Via guardrails | Via policies param |

Claude integration is more powerful - you can **prevent** bad actions, not just record them.

## Troubleshooting

### No DecisionRecord created

Records are only created when there are **actions**. If the agent only reads, no record.

### Policy not blocking

Ensure your policy returns `{"passed": False, "message": "..."}` - both fields required.

### Hook errors

Hooks fail open by default (return `{"allow": True}`). Check logs for errors:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Next Steps

- [Query API](../README.md#query-api) - Search and explain
- [DecisionRecord Schema](../spec/jsonschema/decision_record.json)
- [Example](../examples/claude_agent_example.py)
