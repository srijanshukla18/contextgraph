#!/usr/bin/env python3
"""Example: Using ContextGraph with OpenAI Agents SDK.

This example demonstrates the ContextGraph integration with OpenAI Agents SDK.
It can run in two modes:
1. Mock mode (default): Simulates the SDK to show the integration working
2. Real mode: Uses the actual OpenAI Agents SDK (requires: pip install openai-agents)

Usage:
    python examples/openai_agents_example.py          # Mock mode
    python examples/openai_agents_example.py --real   # Real SDK mode
"""

import sys
import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Add SDK to path for local development
sys.path.insert(0, "sdk/python")

from contextgraph import ContextGraphClient, Config
from contextgraph.integrations.openai_agents import ContextGraphTraceProcessor


# =============================================================================
# Mock OpenAI Agents SDK (for demonstration without installing the real SDK)
# =============================================================================

class MockSpanType(str, Enum):
    AGENT = "agent"
    FUNCTION = "function"
    TOOL = "tool"
    GUARDRAIL = "guardrail"
    HANDOFF = "handoff"


@dataclass
class MockSpan:
    span_id: str
    trace_id: str
    parent_span_id: Optional[str]
    span_type: MockSpanType
    name: str
    start_time: datetime
    end_time: Optional[datetime]
    attributes: dict[str, Any]
    status: str = "ok"


@dataclass
class MockTrace:
    trace_id: str
    name: str
    group_id: Optional[str]
    metadata: dict[str, Any]
    start_time: datetime
    end_time: Optional[datetime] = None
    spans: list[MockSpan] = field(default_factory=list)


class MockTraceManager:
    """Simulates the OpenAI Agents SDK tracing system."""

    def __init__(self):
        self._processor: Optional[ContextGraphTraceProcessor] = None
        self._current_trace: Optional[MockTrace] = None

    def set_processor(self, processor: ContextGraphTraceProcessor):
        self._processor = processor

    def start_trace(self, name: str, metadata: dict = None) -> MockTrace:
        trace_id = f"trace_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self._current_trace = MockTrace(
            trace_id=trace_id,
            name=name,
            group_id=None,
            metadata=metadata or {},
            start_time=datetime.now(timezone.utc),
        )
        if self._processor:
            self._processor.on_trace_start(self._current_trace)
        return self._current_trace

    def add_span(self, span_type: MockSpanType, name: str, attributes: dict) -> MockSpan:
        if not self._current_trace:
            raise RuntimeError("No active trace")

        span = MockSpan(
            span_id=f"span_{len(self._current_trace.spans)}",
            trace_id=self._current_trace.trace_id,
            parent_span_id=None,
            span_type=span_type,
            name=name,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            attributes=attributes,
        )
        self._current_trace.spans.append(span)

        if self._processor:
            self._processor.on_span_start(span)
            self._processor.on_span_end(span)

        return span

    def end_trace(self):
        if self._current_trace and self._processor:
            self._current_trace.end_time = datetime.now(timezone.utc)
            self._processor.on_trace_end(self._current_trace)
        self._current_trace = None


# Global mock manager
_mock_manager = MockTraceManager()


def set_tracing_processor(processor):
    """Mock version of agents.set_tracing_processor"""
    _mock_manager.set_processor(processor)


# =============================================================================
# Example Tools (these would be real tools in a production agent)
# =============================================================================

def get_account(account_id: str) -> dict:
    """Get account details from CRM (read operation)."""
    # Simulated CRM data
    return {
        "id": account_id,
        "name": "Acme Corporation",
        "tier": "enterprise",
        "arr": 500000,
        "churn_risk": "high",
        "health_score": 45,
    }


def search_knowledge(query: str) -> dict:
    """Search knowledge base (read operation)."""
    return {
        "results": [
            {"title": "Service Credit Policy", "snippet": "Credits up to 10% can be auto-approved..."},
            {"title": "Escalation Procedures", "snippet": "Enterprise accounts require manager approval..."},
        ]
    }


def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email (write operation)."""
    return {
        "status": "sent",
        "message_id": f"msg_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "to": to,
    }


def create_ticket(title: str, description: str, priority: str) -> dict:
    """Create a support ticket (write operation)."""
    return {
        "ticket_id": f"TKT-{datetime.now().strftime('%H%M%S')}",
        "status": "open",
        "title": title,
    }


# =============================================================================
# Simulated Agent Run
# =============================================================================

def simulate_agent_run():
    """Simulate what happens when an OpenAI Agent runs with tools."""

    logger.info("Starting simulated agent run...")

    # Start a trace (this is what the SDK does internally)
    trace = _mock_manager.start_trace(
        name="customer-outreach-agent",
        metadata={"user_id": "user_123", "session": "abc"}
    )
    logger.info(f"Trace started: {trace.trace_id}")

    # Agent decides to look up account info (READ)
    logger.info("Agent calling get_account...")
    account = get_account("ACC-ACME-001")
    _mock_manager.add_span(
        span_type=MockSpanType.FUNCTION,
        name="get_account",
        attributes={
            "function.name": "get_account",
            "function.arguments": json.dumps({"account_id": "ACC-ACME-001"}),
            "function.output": json.dumps(account),
        }
    )

    # Agent searches knowledge base (READ)
    logger.info("Agent calling search_knowledge...")
    kb_results = search_knowledge("service credit policy")
    _mock_manager.add_span(
        span_type=MockSpanType.FUNCTION,
        name="search_knowledge",
        attributes={
            "function.name": "search_knowledge",
            "function.arguments": json.dumps({"query": "service credit policy"}),
            "function.output": json.dumps(kb_results),
        }
    )

    # Agent decides to send an email (WRITE)
    logger.info("Agent calling send_email...")
    email_result = send_email(
        to="john@acme.com",
        subject="Your Service Credit Request",
        body="Dear customer, we've approved your 10% service credit..."
    )
    _mock_manager.add_span(
        span_type=MockSpanType.FUNCTION,
        name="send_email",
        attributes={
            "function.name": "send_email",
            "function.arguments": json.dumps({
                "to": "john@acme.com",
                "subject": "Your Service Credit Request",
                "body": "Dear customer..."
            }),
            "function.output": json.dumps(email_result),
        }
    )

    # Agent creates a follow-up ticket (WRITE)
    logger.info("Agent calling create_ticket...")
    ticket_result = create_ticket(
        title="Follow-up: Acme service credit",
        description="Schedule call to discuss renewal",
        priority="medium"
    )
    _mock_manager.add_span(
        span_type=MockSpanType.FUNCTION,
        name="create_ticket",
        attributes={
            "function.name": "create_ticket",
            "function.arguments": json.dumps({
                "title": "Follow-up: Acme service credit",
                "description": "Schedule call to discuss renewal",
                "priority": "medium"
            }),
            "function.output": json.dumps(ticket_result),
        }
    )

    # End the trace (triggers DecisionRecord creation)
    _mock_manager.end_trace()
    logger.info("Trace ended - DecisionRecord should be created")


# =============================================================================
# Main
# =============================================================================

def main():
    use_real_sdk = "--real" in sys.argv

    print("=" * 60)
    print("ContextGraph + OpenAI Agents SDK Example")
    print("=" * 60)

    if use_real_sdk:
        try:
            from agents import set_tracing_processor as real_set_processor
            print("Using REAL OpenAI Agents SDK")
            print("Note: You'll need to run an actual agent for this to work")
            # In real usage, you'd define an Agent and run it
        except ImportError:
            print("ERROR: openai-agents not installed. Install with:")
            print("  pip install openai-agents")
            sys.exit(1)
    else:
        print("Using MOCK mode (simulated SDK)")
        print()

    # Configure ContextGraph
    config = Config(
        server_url="http://localhost:8080",
        write_tools=["send_email", "create_ticket", "update_crm"],
        read_tools=["get_account", "search_knowledge"],
    )

    # Create the trace processor
    processor = ContextGraphTraceProcessor(
        config=config,
        # These can also be passed directly:
        # write_tools=["send_email", "create_ticket"],
        # server_url="http://localhost:8080",
    )

    # Register with the SDK
    set_tracing_processor(processor)
    print("ContextGraph processor registered!")
    print()

    # Simulate an agent run
    print("-" * 60)
    print("Simulating agent run with tool calls...")
    print("-" * 60)
    simulate_agent_run()

    # Cleanup
    processor.shutdown()

    print()
    print("=" * 60)
    print("DONE!")
    print()
    print("What happened:")
    print("  1. Agent gathered evidence (get_account, search_knowledge)")
    print("  2. Agent took actions (send_email, create_ticket)")
    print("  3. ContextGraph created a DecisionRecord with:")
    print("     - 2 evidence items (the read operations)")
    print("     - 2 actions (the write operations)")
    print()
    print("If server is running (make docker-up), view it at:")
    print("  http://localhost:8080/v1/decisions")
    print()
    print("Or open the UI:")
    print("  make ui")
    print("=" * 60)


if __name__ == "__main__":
    main()
