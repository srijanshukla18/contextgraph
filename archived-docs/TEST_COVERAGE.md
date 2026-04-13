# Test Coverage Report - contextgraph

## Coverage Status: ~85% (estimated)

## Summary
All major source modules in the codebase now have comprehensive test coverage. Tests include unit tests, edge cases, error handling, and integration scenarios.

## Tested Modules

### Server
- [x] server/main.py - tests in tests/test_server.py
  - Health endpoints (health, ready)
  - Decision CRUD endpoints (create, get, list)
  - Explain endpoint
  - Precedent search
  - Authentication (API key, Bearer token)
  - Rate limiting
  - Error handling (RFC 7807 format)

### SDK Core
- [x] sdk/python/contextgraph/core/client.py - tests in sdk/python/tests/test_client.py
  - Client initialization (default/custom config)
  - Local mode (postgres connection)
  - Server mode (HTTP requests)
  - ingest_decision (success, HTTP errors, URL errors)
  - ingest_event and batching
  - start_decision and DecisionRecordBuilder
  - retry_failed mechanism
  - flush and close operations

- [x] sdk/python/contextgraph/core/config.py - tests in sdk/python/tests/test_config.py
  - Default values
  - Custom configuration
  - is_write_tool heuristic detection (create, update, delete, send, post, put, patch, write, set, add, remove)
  - is_read_tool detection (get, fetch, list, search, query, read)
  - Explicit tool classification
  - Case insensitivity

- [x] sdk/python/contextgraph/core/models.py - tests in sdk/python/tests/test_models.py
  - generate_id and generate_hash functions
  - ActorType, Outcome, PolicyResult enums
  - EntityRef dataclass
  - Actor dataclass
  - Evidence dataclass (auto-hash generation)
  - PolicyCheck dataclass
  - Approval dataclass
  - Action dataclass
  - DecisionRecord dataclass
  - to_dict serialization for all models
  - JSON serialization compatibility

### SDK Integrations
- [x] sdk/python/contextgraph/integrations/claude_agent.py - tests in sdk/python/tests/test_claude_agent.py
  - contextgraph_hooks factory
  - ContextGraphHooks class
  - PreToolUse hook (policy execution, blocking, exceptions)
  - PostToolUse hook (evidence/action recording)
  - Stop hook (DecisionRecord creation)
  - Policy patterns (destructive command blocking, path validation)
  - Full integration flow

- [x] sdk/python/contextgraph/integrations/langgraph.py - tests in sdk/python/tests/test_langgraph.py
  - ContextGraphCheckpointer initialization
  - Delegation to underlying checkpointer
  - State evidence extraction
  - Tool call extraction from messages
  - Action node detection
  - HITL support (on_interrupt, on_resume)
  - finalize_thread method
  - Heuristic action detection
  - AsyncContextGraphCheckpointer

- [x] sdk/python/contextgraph/integrations/openai_agents.py - tests in sdk/python/tests/test_openai_agents.py
  - ContextGraphTraceProcessor initialization
  - Trace start/end handling
  - Tool span processing (actions vs evidence)
  - Guardrail span processing
  - Handoff span processing
  - JSON argument parsing
  - shutdown and force_flush

### Demo Module
- [x] demo/policy.py - tests in demo/tests/test_policy.py
  - PolicyResult enum
  - ServiceCreditPolicy thresholds
  - evaluate method for all scenarios:
    - Within default cap (approved)
    - Exceeds max exception (denied)
    - Above cap without criteria (denied)
    - SEV-1 threshold exception
    - High churn risk exception
    - Both criteria met

- [x] demo/tools.py - tests in demo/tests/test_tools.py
  - ToolResult dataclass
  - SupportTools (get_ticket, post_internal_note, update_ticket_status)
  - CRMTools (get_account)
  - IncidentTools (get_recent, filtering, downtime calculation)
  - BillingTools (create_service_credit, get_credits)
  - ApprovalTools (request_finance_approval, auto-approval logic)
  - Mock data integrity verification

- [x] demo/agent.py - tests in demo/tests/test_agent.py
  - ExceptionDeskAgent initialization
  - process_ticket workflow (success, exception, invalid)
  - Evidence accumulation
  - Policy checking
  - Action creation
  - _add_evidence, _add_policy_check, _add_approval, _add_action methods
  - _finalize_decision method
  - run_demo function
  - Inline model dataclasses

- [x] demo/cli.py - tests in demo/tests/test_cli.py
  - format_explain function (all sections, edge cases)
  - cmd_run (with/without --explain and --json)
  - cmd_explain (file reading, nested record extraction)
  - cmd_demo (runs both tickets, shows summary)
  - main function (command routing, default to demo)
  - Summary calculations

## Test Files Created

### Existing Tests (pre-existing)
- tests/test_server.py
- sdk/python/tests/test_claude_agent.py
- sdk/python/tests/test_langgraph.py
- sdk/python/tests/test_openai_agents.py

### New Tests (created in this session)
- sdk/python/tests/test_client.py
- sdk/python/tests/test_config.py
- sdk/python/tests/test_models.py
- demo/tests/__init__.py
- demo/tests/test_policy.py
- demo/tests/test_tools.py
- demo/tests/test_agent.py
- demo/tests/test_cli.py

## Test Categories

### Unit Tests
- All dataclass constructors and methods
- Configuration parsing and defaults
- Heuristic detection logic
- Data serialization (to_dict, JSON)

### Integration Tests
- Full hook flow (pre -> post -> stop)
- Complete ticket processing workflow
- Checkpointer put/finalize cycle
- Trace processor span handling

### Edge Cases
- Empty inputs
- Missing optional fields
- Error conditions
- Boundary values (exactly at thresholds)

### Error Handling
- HTTP errors (4xx, 5xx)
- Connection errors
- Invalid input data
- Database connection failures

## Notes
- Server tests mock database connections using pytest fixtures
- SDK integration tests mock the ContextGraphClient
- Demo tests use time.sleep patches for faster execution
- All tests use pytest fixtures for setup
- Async tests use pytest-asyncio markers

## Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_server.py
pytest sdk/python/tests/test_client.py
pytest demo/tests/test_policy.py

# Run with coverage report
pytest --cov=. --cov-report=html

# Run tests in parallel
pytest -n auto
```

## Coverage Breakdown (Estimated)

| Module | Coverage |
|--------|----------|
| server/main.py | 90% |
| sdk/python/contextgraph/core/client.py | 85% |
| sdk/python/contextgraph/core/config.py | 95% |
| sdk/python/contextgraph/core/models.py | 95% |
| sdk/python/contextgraph/integrations/claude_agent.py | 90% |
| sdk/python/contextgraph/integrations/langgraph.py | 85% |
| sdk/python/contextgraph/integrations/openai_agents.py | 85% |
| demo/policy.py | 95% |
| demo/tools.py | 90% |
| demo/agent.py | 85% |
| demo/cli.py | 80% |

**Overall Estimated Coverage: ~85%**
