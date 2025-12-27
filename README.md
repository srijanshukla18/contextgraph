# ContextGraph

**Decision traces as data. Context as a graph. Precedent you can query.**

ContextGraph captures *why* your AI agents and workflows made decisions—not just what they did. Every tool call, policy check, approval, and commit becomes a queryable record.

```
┌─────────────────────────────────────────────────────────────────┐
│                      DecisionRecord                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Evidence          Policy           Approval        Action     │
│   ┌──────┐         ┌──────┐         ┌──────┐       ┌──────┐     │
│   │ CRM  │────────▶│ Cap  │────────▶│ HITL │──────▶│Commit│     │
│   │ Data │         │ 10%  │         │      │       │      │     │
│   └──────┘         └──────┘         └──────┘       └──────┘     │
│   ┌──────┐              │                              │        │
│   │Ticket│              ▼                              ▼        │
│   └──────┘         Exception              Service Credit        │
│   ┌──────┐         Required                  Issued             │
│   │ SEV1 │                                                      │
│   │ x 3  │                                                      │
│   └──────┘                                                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Why ContextGraph?

Each framework already provides observability primitives. ContextGraph adds a **unified decision ledger** on top.

### OpenAI Agents SDK

OpenAI has [built-in tracing](https://openai.github.io/openai-agents-python/tracing/) with a Traces dashboard.

| Need | OpenAI Tracing | + ContextGraph |
|------|----------------|----------------|
| See what happened | ✓ Dashboard | ✓ API |
| Data in your infra | ✗ OpenAI-hosted | ✓ Self-hosted Postgres |
| Zero Data Retention orgs | ✗ Unavailable | ✓ Works |
| Structured audit schema | Raw spans | DecisionRecord |

### Claude Agent SDK

Claude has [hooks](https://platform.claude.com/docs/en/agent-sdk/hooks) (`PreToolUse`, `PostToolUse`, `Stop`) for intercepting tool calls.

| Need | Claude Hooks | + ContextGraph |
|------|--------------|----------------|
| Intercept tools | ✓ You implement | ✓ Pre-built |
| Block dangerous ops | ✓ You implement | ✓ Policy functions |
| Structured audit store | ✗ You build it | ✓ DecisionRecord |
| Query API | ✗ You build it | ✓ `/v1/decisions` |

### LangGraph

LangGraph has [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) for HITL and [LangSmith](https://docs.langchain.com/langsmith/trace-with-langgraph) for tracing.

| Need | LangSmith | + ContextGraph |
|------|-----------|----------------|
| Trace execution | ✓ | ✓ |
| Data in your infra | ✗ LangChain-hosted | ✓ Self-hosted |
| HITL → Approval records | ✗ Workflow state only | ✓ Approvals with approver ID |
| Cross-vendor schema | ✗ LangChain ecosystem | ✓ Same as OpenAI/Claude |

### The bottom line

They give you **primitives** (traces, hooks, interrupts). ContextGraph gives you:

- **Normalized schema** → DecisionRecord (evidence → policy → approval → action)
- **Self-hosted storage** → Your Postgres, your data
- **Query API** → `/v1/decisions/{id}/explain`, `/v1/precedents/search`
- **Vendor-neutral** → Same record format across OpenAI, Claude, LangGraph

## Quick Start

```bash
# Clone and run the demo
git clone https://github.com/contextgraph/contextgraph
cd contextgraph

# Run the Exception Desk demo (no setup required)
make demo
```

Output:
```
EXCEPTION DESK AGENT - Processing SUP-4312

[1] Gathering evidence...
    Ticket: Request for service credit due to outages
    Requested: 20% credit
    Account: Acme Corporation (enterprise, ARR $500,000)
    Churn Risk: high, Health: 45
    Incidents (30d): 3 SEV-1, 2 SEV-2

[2] Evaluating policy...
    Policy: service_credit v1.0
    Result: exception_required
    Exception Route: service_impact_exception

[3] Requesting Finance approval...
    Approver: finance-lead@ourcompany.com
    Decision: APPROVED

[4] Issuing service credit...
    Credit ID: CREDIT-71564
    Amount: $8,333.40 (20%)

[5] Decision COMMITTED
    DecisionRecord: 3f35d5ee-adc5-4759-8376-290692970bf4
```

Then query it:
```bash
curl http://localhost:8080/v1/decisions/{id}/explain
```

## Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Agent / LLM    │     │   ContextGraph   │     │     Query API    │
│                  │     │                  │     │                  │
│  ┌────────────┐  │     │  ┌────────────┐  │     │  GET /explain    │
│  │Tool Calls  │──┼────▶│  │  Events    │  │     │  GET /precedents │
│  │Approvals   │  │     │  │  (append)  │  │     │  GET /state?as_of│
│  │Commits     │  │     │  └─────┬──────┘  │     │                  │
│  └────────────┘  │     │        │         │     └────────┬─────────┘
│                  │     │        ▼         │              │
│  OpenAI Agents   │     │  ┌────────────┐  │              │
│  Claude SDK      │     │  │  Decision  │◀─┼──────────────┘
│  LangGraph       │     │  │  Records   │  │
│                  │     │  └────────────┘  │
└──────────────────┘     └──────────────────┘
```

## Framework Integrations

### OpenAI Agents SDK
```python
from agents import set_tracing_processor
from contextgraph.integrations.openai_agents import ContextGraphTraceProcessor

processor = ContextGraphTraceProcessor(
    write_tools=["send_email", "update_crm"],
)
set_tracing_processor(processor)

# That's it. All decisions are now captured.
```

### Claude Agent SDK
```python
from claude_agent_sdk import Agent, AgentConfig
from contextgraph.integrations.claude_agent import contextgraph_hooks

agent = Agent(config=AgentConfig(
    model="claude-sonnet-4-5-20250929",
    hooks=contextgraph_hooks(
        write_tools=["Bash", "Write", "Edit"],
    ),
))
```

### LangGraph
```python
from contextgraph.integrations.langgraph import ContextGraphCheckpointer

cg_checkpointer = ContextGraphCheckpointer(
    underlying=MemorySaver(),
    write_tools=["send_email"],
    state_keys_as_evidence=["account_data"],
)

graph = builder.compile(checkpointer=cg_checkpointer)
```

## The DecisionRecord

Every decision captured follows this schema:

```json
{
  "decision_id": "dec_01abc...",
  "run_id": "run_ticket_4312",
  "timestamp": "2025-01-15T10:30:00Z",
  "outcome": "committed",

  "evidence": [
    {"source": "crm.get_account", "snapshot": {"arr": 500000, "churn_risk": "high"}},
    {"source": "incidents.get_recent", "snapshot": {"sev1_count": 3}}
  ],

  "policies": [
    {"policy_id": "service_credit", "version": "1.0", "result": "exception_required"}
  ],

  "approvals": [
    {"approver": "finance-lead@company.com", "granted": true, "reason": "Service impact"}
  ],

  "actions": [
    {"tool": "billing.create_credit", "params": {"amount": 8333}, "success": true}
  ]
}
```

## Query API

### Explain a Decision
```bash
GET /v1/decisions/{id}/explain

# Returns the full chain: evidence → policy → approval → action
```

### Search Precedents
```bash
POST /v1/precedents/search
{
  "policy_id": "service_credit",
  "outcome": "committed"
}

# Find similar past decisions
```

### Time Travel
```bash
GET /v1/entities/{ref}/state?as_of=2025-01-15T10:00:00Z

# What did the agent see at decision time?
```

## Running the Server

### Docker (recommended)
```bash
make docker-up    # Starts server + Postgres
make docker-logs  # Tail logs
```

### Local
```bash
make setup        # Create DB + install deps
make server       # Start on :8080
```

## Production Ready

ContextGraph is built for production workloads:

| Feature | Implementation |
|---------|----------------|
| **Authentication** | API key via `X-API-Key` header or `Bearer` token |
| **Rate Limiting** | Sliding window (configurable via `RATE_LIMIT_REQUESTS`) |
| **Connection Pooling** | `psycopg2.pool.ThreadedConnectionPool` (2-20 connections) |
| **Structured Logging** | JSON logs with request IDs for distributed tracing |
| **Health Checks** | `/health` (with DB status) and `/ready` (k8s probe) |
| **Security** | Non-root container, configurable CORS, no hardcoded secrets |
| **Test Coverage** | 86 tests across server + all SDK integrations |

### Configuration

```bash
# Copy the template
cp .env.example .env

# Required
POSTGRES_PASSWORD=your-secure-password
API_KEYS=key1,key2                    # Comma-separated API keys

# Optional (with defaults)
ALLOWED_ORIGINS=http://localhost:3000 # CORS origins
RATE_LIMIT_REQUESTS=100               # Requests per window
RATE_LIMIT_WINDOW=60                  # Window in seconds
REQUIRE_AUTH=true                     # Set to 'false' for dev
LOG_LEVEL=INFO                        # DEBUG, INFO, WARNING, ERROR
```

### Generate API Keys

```bash
# Generate a secure API key
openssl rand -hex 32
```

## Project Structure

```
contextgraph/
├── demo/                    # Exception Desk demo
│   ├── agent.py            # Service credit approval agent
│   ├── tools.py            # Mock Zendesk/Salesforce/PagerDuty
│   ├── policy.py           # Policy engine (10% cap, exceptions)
│   └── cli.py              # Demo CLI with explain output
├── sdk/python/
│   └── contextgraph/
│       ├── core/           # Models, client, config
│       └── integrations/   # OpenAI, Claude, LangGraph
├── server/                 # FastAPI ingest + query API
├── storage/postgres/       # Schema
├── spec/jsonschema/        # DecisionRecord schema
└── ui/                     # Explorer (coming soon)
```

## Use Cases

| Domain | Decision | Evidence | Policy | Action |
|--------|----------|----------|--------|--------|
| **Support** | Service credit | Ticket, incidents, account | Credit cap | Issue credit |
| **Sales** | Discount approval | Deal size, customer tier | Discount policy | Apply discount |
| **Finance** | Refund | Transaction, dispute | Refund rules | Process refund |
| **Security** | Access grant | Role, justification | RBAC policy | Grant access |
| **Ops** | Escalation | Alert, runbook | SLA policy | Page on-call |

## Roadmap

- [x] Core DecisionRecord schema
- [x] OpenAI Agents SDK integration
- [x] Claude Agent SDK integration
- [x] LangGraph integration
- [x] Explain API
- [x] Production hardening (auth, rate limits, pooling, logging)
- [x] Comprehensive test suite (86 tests)
- [ ] Explorer UI
- [ ] Precedent search (embeddings)
- [ ] Time-travel queries
- [ ] Neo4j plugin

## License

Apache-2.0

---

<p align="center">
  <i>Make "why" first-class data.</i>
</p>
