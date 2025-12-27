"""Tests for OpenAI Agents SDK integration."""

import json
import pytest
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum
from unittest.mock import Mock, patch, MagicMock

from contextgraph.integrations.openai_agents import ContextGraphTraceProcessor
from contextgraph.core.config import Config
from contextgraph.core.client import ContextGraphClient


# =============================================================================
# Mock SDK Types (simulate what OpenAI Agents SDK provides)
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


# =============================================================================
# Tests
# =============================================================================

class TestContextGraphTraceProcessor:
    """Test the ContextGraphTraceProcessor."""

    def test_init_with_defaults(self):
        """Test processor initializes with default config."""
        processor = ContextGraphTraceProcessor()
        assert processor.config is not None
        assert processor.client is not None

    def test_init_with_write_tools(self):
        """Test processor respects write_tools config."""
        processor = ContextGraphTraceProcessor(
            write_tools=["send_email", "create_ticket"]
        )
        assert processor.config.write_tools == ["send_email", "create_ticket"]
        assert processor.config.is_write_tool("send_email")
        assert not processor.config.is_write_tool("get_account")

    def test_on_trace_start(self):
        """Test trace start creates accumulator."""
        processor = ContextGraphTraceProcessor()

        trace = MockTrace(
            trace_id="trace_123",
            name="test-agent",
            group_id=None,
            metadata={"key": "value"},
            start_time=datetime.now(timezone.utc),
        )

        processor.on_trace_start(trace)
        assert "trace_123" in processor._active_traces

    def test_on_trace_end_no_actions_skips_record(self):
        """Test trace end without actions doesn't create record."""
        processor = ContextGraphTraceProcessor()
        processor.client = Mock()

        trace = MockTrace(
            trace_id="trace_123",
            name="test-agent",
            group_id=None,
            metadata={},
            start_time=datetime.now(timezone.utc),
        )

        processor.on_trace_start(trace)
        processor.on_trace_end(trace)

        # Should not call ingest_decision since no actions
        processor.client.ingest_decision.assert_not_called()

    def test_tool_span_creates_action(self):
        """Test function span for write tool creates action."""
        processor = ContextGraphTraceProcessor(
            write_tools=["send_email"]
        )
        processor.client = Mock()

        # Start trace
        trace = MockTrace(
            trace_id="trace_123",
            name="test-agent",
            group_id=None,
            metadata={},
            start_time=datetime.now(timezone.utc),
        )
        processor.on_trace_start(trace)

        # Add tool span
        span = MockSpan(
            span_id="span_1",
            trace_id="trace_123",
            parent_span_id=None,
            span_type=MockSpanType.FUNCTION,
            name="send_email",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            attributes={
                "function.name": "send_email",
                "function.arguments": json.dumps({"to": "test@example.com"}),
                "function.output": json.dumps({"status": "sent"}),
            },
        )
        processor.on_span_end(span)

        # End trace
        trace.end_time = datetime.now(timezone.utc)
        processor.on_trace_end(trace)

        # Should create decision record with action
        processor.client.ingest_decision.assert_called_once()
        record = processor.client.ingest_decision.call_args[0][0]
        assert len(record.actions) == 1
        assert record.actions[0].tool == "send_email"

    def test_tool_span_creates_evidence(self):
        """Test function span for read tool creates evidence."""
        processor = ContextGraphTraceProcessor(
            write_tools=["send_email"],  # get_account is NOT a write tool
        )
        processor.client = Mock()

        # Start trace
        trace = MockTrace(
            trace_id="trace_123",
            name="test-agent",
            group_id=None,
            metadata={},
            start_time=datetime.now(timezone.utc),
        )
        processor.on_trace_start(trace)

        # Add read tool span
        span = MockSpan(
            span_id="span_1",
            trace_id="trace_123",
            parent_span_id=None,
            span_type=MockSpanType.FUNCTION,
            name="get_account",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            attributes={
                "function.name": "get_account",
                "function.arguments": json.dumps({"id": "123"}),
                "function.output": json.dumps({"name": "Acme"}),
            },
        )
        processor.on_span_end(span)

        # Also add write tool to trigger record creation
        write_span = MockSpan(
            span_id="span_2",
            trace_id="trace_123",
            parent_span_id=None,
            span_type=MockSpanType.FUNCTION,
            name="send_email",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            attributes={
                "function.name": "send_email",
                "function.arguments": json.dumps({"to": "test@example.com"}),
            },
        )
        processor.on_span_end(write_span)

        # End trace
        trace.end_time = datetime.now(timezone.utc)
        processor.on_trace_end(trace)

        # Should have evidence
        record = processor.client.ingest_decision.call_args[0][0]
        assert len(record.evidence) == 1
        assert record.evidence[0].source == "get_account"

    def test_guardrail_span_creates_policy(self):
        """Test guardrail span creates policy evaluation."""
        processor = ContextGraphTraceProcessor(write_tools=["action"])
        processor.client = Mock()

        trace = MockTrace(
            trace_id="trace_123",
            name="test-agent",
            group_id=None,
            metadata={},
            start_time=datetime.now(timezone.utc),
        )
        processor.on_trace_start(trace)

        # Add guardrail span
        guardrail_span = MockSpan(
            span_id="span_1",
            trace_id="trace_123",
            parent_span_id=None,
            span_type=MockSpanType.GUARDRAIL,
            name="content_filter",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            attributes={
                "guardrail.name": "content_filter",
                "guardrail.passed": True,
                "guardrail.triggered_rules": [],
            },
        )
        processor.on_span_end(guardrail_span)

        # Add action to trigger record
        action_span = MockSpan(
            span_id="span_2",
            trace_id="trace_123",
            parent_span_id=None,
            span_type=MockSpanType.FUNCTION,
            name="action",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            attributes={"function.name": "action"},
        )
        processor.on_span_end(action_span)

        trace.end_time = datetime.now(timezone.utc)
        processor.on_trace_end(trace)

        record = processor.client.ingest_decision.call_args[0][0]
        assert len(record.policies) == 1
        assert record.policies[0].policy_id == "content_filter"
        assert record.policies[0].result.value == "pass"

    def test_guardrail_failure_sets_denied_outcome(self):
        """Test failed guardrail results in denied outcome."""
        processor = ContextGraphTraceProcessor(write_tools=["action"])
        processor.client = Mock()

        trace = MockTrace(
            trace_id="trace_123",
            name="test-agent",
            group_id=None,
            metadata={},
            start_time=datetime.now(timezone.utc),
        )
        processor.on_trace_start(trace)

        # Add failed guardrail
        guardrail_span = MockSpan(
            span_id="span_1",
            trace_id="trace_123",
            parent_span_id=None,
            span_type=MockSpanType.GUARDRAIL,
            name="content_filter",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            attributes={
                "guardrail.name": "content_filter",
                "guardrail.passed": False,
                "guardrail.triggered_rules": ["rule_1"],
            },
        )
        processor.on_span_end(guardrail_span)

        # Add action
        action_span = MockSpan(
            span_id="span_2",
            trace_id="trace_123",
            parent_span_id=None,
            span_type=MockSpanType.FUNCTION,
            name="action",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            attributes={"function.name": "action"},
        )
        processor.on_span_end(action_span)

        trace.end_time = datetime.now(timezone.utc)
        processor.on_trace_end(trace)

        record = processor.client.ingest_decision.call_args[0][0]
        assert record.outcome.value == "denied"

    def test_handoff_span_adds_metadata(self):
        """Test handoff span adds handoff info to metadata."""
        processor = ContextGraphTraceProcessor(write_tools=["action"])
        processor.client = Mock()

        trace = MockTrace(
            trace_id="trace_123",
            name="test-agent",
            group_id=None,
            metadata={},
            start_time=datetime.now(timezone.utc),
        )
        processor.on_trace_start(trace)

        # Add handoff span
        handoff_span = MockSpan(
            span_id="span_1",
            trace_id="trace_123",
            parent_span_id=None,
            span_type=MockSpanType.HANDOFF,
            name="handoff",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            attributes={
                "handoff.from_agent": "triage",
                "handoff.to_agent": "specialist",
                "handoff.reason": "needs expert",
            },
        )
        processor.on_span_end(handoff_span)

        # Add action
        action_span = MockSpan(
            span_id="span_2",
            trace_id="trace_123",
            parent_span_id=None,
            span_type=MockSpanType.FUNCTION,
            name="action",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            attributes={"function.name": "action"},
        )
        processor.on_span_end(action_span)

        trace.end_time = datetime.now(timezone.utc)
        processor.on_trace_end(trace)

        record = processor.client.ingest_decision.call_args[0][0]
        assert "handoffs" in record.metadata
        assert record.metadata["handoffs"][0]["from"] == "triage"
        assert record.metadata["handoffs"][0]["to"] == "specialist"

    def test_json_args_parsing(self):
        """Test JSON string arguments are parsed."""
        processor = ContextGraphTraceProcessor(write_tools=["send_email"])
        processor.client = Mock()

        trace = MockTrace(
            trace_id="trace_123",
            name="test-agent",
            group_id=None,
            metadata={},
            start_time=datetime.now(timezone.utc),
        )
        processor.on_trace_start(trace)

        # Arguments as JSON string (how SDK sends them)
        span = MockSpan(
            span_id="span_1",
            trace_id="trace_123",
            parent_span_id=None,
            span_type=MockSpanType.FUNCTION,
            name="send_email",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            attributes={
                "function.name": "send_email",
                "function.arguments": '{"to": "test@example.com", "subject": "Hello"}',
            },
        )
        processor.on_span_end(span)

        trace.end_time = datetime.now(timezone.utc)
        processor.on_trace_end(trace)

        record = processor.client.ingest_decision.call_args[0][0]
        assert record.actions[0].params == {"to": "test@example.com", "subject": "Hello"}

    def test_shutdown_calls_client_close(self):
        """Test shutdown closes the client."""
        processor = ContextGraphTraceProcessor()
        processor.client = Mock()

        processor.shutdown()

        processor.client.flush.assert_called_once()
        processor.client.close.assert_called_once()


class TestConfigWriteToolDetection:
    """Test the write tool detection heuristics."""

    def test_explicit_write_tools(self):
        """Test explicitly configured write tools."""
        config = Config(write_tools=["my_custom_tool"])
        assert config.is_write_tool("my_custom_tool")
        assert not config.is_write_tool("other_tool")

    def test_explicit_read_tools(self):
        """Test explicitly configured read tools."""
        config = Config(read_tools=["get_data"])
        assert not config.is_write_tool("get_data")

    def test_heuristic_detection(self):
        """Test heuristic-based write tool detection."""
        config = Config()

        # Should detect as write tools
        assert config.is_write_tool("create_user")
        assert config.is_write_tool("update_record")
        assert config.is_write_tool("delete_item")
        assert config.is_write_tool("send_email")
        assert config.is_write_tool("post_message")

        # Should detect as read tools
        assert not config.is_write_tool("get_user")
        assert not config.is_write_tool("fetch_data")
        assert not config.is_write_tool("search_records")
        assert not config.is_write_tool("list_items")
