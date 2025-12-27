"""Tests for the LangGraph integration."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from contextgraph.core.config import Config
from contextgraph.core.models import Outcome
from contextgraph.integrations.langgraph import (
    ContextGraphCheckpointer,
    AsyncContextGraphCheckpointer,
    _ThreadAccumulator,
    _safe_get,
)


@pytest.fixture
def mock_client():
    """Create a mock ContextGraphClient."""
    client = MagicMock()
    client.ingest_decision = MagicMock(return_value=True)
    return client


@pytest.fixture
def mock_underlying():
    """Create a mock underlying checkpointer."""
    underlying = MagicMock()
    underlying.get_tuple = MagicMock(return_value=None)
    underlying.list = MagicMock(return_value=iter([]))
    underlying.put = MagicMock(return_value={"configurable": {"thread_id": "test"}})
    underlying.put_writes = MagicMock(return_value=None)
    return underlying


@pytest.fixture
def checkpointer(mock_client, mock_underlying):
    """Create a ContextGraphCheckpointer for testing."""
    return ContextGraphCheckpointer(
        underlying=mock_underlying,
        client=mock_client,
        write_tools=["send_email", "update_db"],
        read_tools=["fetch_data", "search"],
        state_keys_as_evidence=["customer_data", "context"],
        action_node_names=["send_node", "commit_node"],
    )


@pytest.fixture
def thread_config():
    """Standard thread configuration."""
    return {"configurable": {"thread_id": "test-thread-123"}}


class TestContextGraphCheckpointer:
    """Tests for the main ContextGraphCheckpointer class."""

    def test_delegates_get_tuple(self, checkpointer, mock_underlying, thread_config):
        """get_tuple delegates to underlying checkpointer."""
        mock_underlying.get_tuple.return_value = {"id": "checkpoint-1"}

        result = checkpointer.get_tuple(thread_config)

        mock_underlying.get_tuple.assert_called_once_with(thread_config)
        assert result == {"id": "checkpoint-1"}

    def test_delegates_list(self, checkpointer, mock_underlying, thread_config):
        """list delegates to underlying checkpointer."""
        mock_underlying.list.return_value = iter([{"id": "1"}, {"id": "2"}])

        result = list(checkpointer.list(thread_config))

        mock_underlying.list.assert_called_once()
        assert len(result) == 2

    def test_put_extracts_state_evidence(self, checkpointer, mock_underlying, thread_config):
        """put extracts configured state keys as evidence."""
        checkpoint = {
            "channel_values": {
                "customer_data": {"name": "Acme", "arr": 500000},
                "context": {"source": "crm"},
                "other": "ignored",
            }
        }
        metadata = {"step": 1, "writes": {}}

        checkpointer.put(thread_config, checkpoint, metadata, {})

        accumulator = checkpointer._threads["test-thread-123"]
        assert len(accumulator.evidence) == 2

        sources = [e.source for e in accumulator.evidence]
        assert "state:customer_data" in sources
        assert "state:context" in sources

    def test_put_extracts_action_nodes(self, checkpointer, mock_underlying, thread_config):
        """put extracts configured action nodes as actions."""
        checkpoint = {"channel_values": {}}
        metadata = {
            "step": 1,
            "writes": {
                "send_node": {"recipient": "user@test.com"},
                "other_node": {"data": "ignored"},
            }
        }

        checkpointer.put(thread_config, checkpoint, metadata, {})

        accumulator = checkpointer._threads["test-thread-123"]
        assert len(accumulator.actions) == 1
        assert accumulator.actions[0].tool == "send_node"

    def test_put_extracts_tool_calls_from_messages(self, checkpointer, mock_underlying, thread_config):
        """put extracts tool calls from LangGraph messages."""
        checkpoint = {
            "channel_values": {
                "messages": [
                    {
                        "tool_calls": [
                            {"id": "tc1", "name": "send_email", "args": {"to": "test@test.com"}},
                            {"id": "tc2", "name": "fetch_data", "args": {"query": "test"}},
                        ]
                    }
                ]
            }
        }
        metadata = {"step": 1, "writes": {}}

        checkpointer.put(thread_config, checkpoint, metadata, {})

        accumulator = checkpointer._threads["test-thread-123"]

        # send_email is a write tool -> action
        # fetch_data is a read tool -> evidence
        assert len(accumulator.actions) == 1
        assert len(accumulator.evidence) == 1
        assert accumulator.actions[0].tool == "send_email"
        assert accumulator.evidence[0].source == "fetch_data"

    def test_put_handles_langchain_message_objects(self, checkpointer, mock_underlying, thread_config):
        """put handles LangChain message objects with tool_calls attribute."""
        class MockMessage:
            tool_calls = [{"id": "tc1", "name": "send_email", "args": {}}]

        checkpoint = {
            "channel_values": {
                "messages": [MockMessage()]
            }
        }
        metadata = {"step": 1, "writes": {}}

        checkpointer.put(thread_config, checkpoint, metadata, {})

        accumulator = checkpointer._threads["test-thread-123"]
        assert len(accumulator.actions) == 1

    def test_put_deduplicates_tool_calls(self, checkpointer, mock_underlying, thread_config):
        """put doesn't record the same tool call twice."""
        checkpoint = {
            "channel_values": {
                "messages": [
                    {"tool_calls": [{"id": "tc1", "name": "send_email", "args": {}}]},
                ]
            }
        }
        metadata = {"step": 1, "writes": {}}

        # Call put twice with same tool call
        checkpointer.put(thread_config, checkpoint, metadata, {})
        checkpointer.put(thread_config, checkpoint, metadata, {})

        accumulator = checkpointer._threads["test-thread-123"]
        assert len(accumulator.actions) == 1  # Not 2


class TestHITLSupport:
    """Tests for human-in-the-loop support."""

    def test_on_interrupt_records_evidence(self, checkpointer, thread_config):
        """on_interrupt records the interrupt as evidence."""
        checkpointer.on_interrupt(thread_config, {"pending": "credit_approval"})

        accumulator = checkpointer._threads["test-thread-123"]
        assert accumulator.pending_interrupt is True
        assert len(accumulator.evidence) == 1
        assert accumulator.evidence[0].source == "interrupt"

    def test_on_resume_records_approval(self, checkpointer, thread_config):
        """on_resume records approval when there was a pending interrupt."""
        checkpointer.on_interrupt(thread_config, {"pending": "approval"})
        checkpointer.on_resume(thread_config, "manager@company.com", "Approved: customer impact")

        accumulator = checkpointer._threads["test-thread-123"]
        assert accumulator.pending_interrupt is False
        assert len(accumulator.approvals) == 1
        assert accumulator.approvals[0].approver.id == "manager@company.com"
        assert accumulator.approvals[0].granted is True

    def test_on_resume_without_interrupt_does_nothing(self, checkpointer, thread_config):
        """on_resume without prior interrupt doesn't record approval."""
        checkpointer.on_resume(thread_config, "manager@company.com", "Approved")

        accumulator = checkpointer._threads["test-thread-123"]
        assert len(accumulator.approvals) == 0


class TestFinalization:
    """Tests for the finalize_thread method."""

    def test_finalize_creates_decision_record(self, checkpointer, mock_client, thread_config):
        """finalize_thread creates and ingests a DecisionRecord."""
        # Add some data
        checkpointer._threads["test-thread-123"] = _ThreadAccumulator(
            thread_id="test-thread-123",
            start_time=datetime.now(timezone.utc),
        )
        from contextgraph.core.models import Action
        checkpointer._threads["test-thread-123"].actions.append(Action(
            tool="send_email",
            committed_at=datetime.now(timezone.utc),
            success=True,
        ))

        record = checkpointer.finalize_thread(thread_config)

        assert record is not None
        mock_client.ingest_decision.assert_called_once()
        assert record.run_id == "test-thread-123"

    def test_finalize_returns_none_without_actions(self, checkpointer, mock_client, thread_config):
        """finalize_thread returns None when no actions were recorded."""
        checkpointer._threads["test-thread-123"] = _ThreadAccumulator(
            thread_id="test-thread-123",
            start_time=datetime.now(timezone.utc),
        )

        record = checkpointer.finalize_thread(thread_config)

        assert record is None
        mock_client.ingest_decision.assert_not_called()

    def test_finalize_returns_none_for_unknown_thread(self, checkpointer, mock_client):
        """finalize_thread returns None for unknown thread."""
        config = {"configurable": {"thread_id": "unknown"}}

        record = checkpointer.finalize_thread(config)

        assert record is None
        mock_client.ingest_decision.assert_not_called()

    def test_finalize_sets_denied_on_failure(self, checkpointer, mock_client, thread_config):
        """finalize_thread sets DENIED outcome when success=False."""
        checkpointer._threads["test-thread-123"] = _ThreadAccumulator(
            thread_id="test-thread-123",
            start_time=datetime.now(timezone.utc),
        )
        from contextgraph.core.models import Action
        checkpointer._threads["test-thread-123"].actions.append(Action(
            tool="send_email",
            committed_at=datetime.now(timezone.utc),
            success=True,
        ))

        record = checkpointer.finalize_thread(thread_config, success=False)

        assert record.outcome == Outcome.DENIED

    def test_finalize_includes_approvals(self, checkpointer, mock_client, thread_config):
        """finalize_thread includes approvals from HITL flow."""
        checkpointer.on_interrupt(thread_config, {"pending": "approval"})
        checkpointer.on_resume(thread_config, "approver@test.com")

        from contextgraph.core.models import Action
        checkpointer._threads["test-thread-123"].actions.append(Action(
            tool="send_email",
            committed_at=datetime.now(timezone.utc),
            success=True,
        ))

        record = checkpointer.finalize_thread(thread_config)

        assert len(record.approvals) == 1
        assert record.approvals[0].approver.id == "approver@test.com"

    def test_finalize_removes_thread(self, checkpointer, mock_client, thread_config):
        """finalize_thread removes the thread accumulator."""
        checkpointer._threads["test-thread-123"] = _ThreadAccumulator(
            thread_id="test-thread-123",
            start_time=datetime.now(timezone.utc),
        )
        from contextgraph.core.models import Action
        checkpointer._threads["test-thread-123"].actions.append(Action(
            tool="send_email",
            committed_at=datetime.now(timezone.utc),
            success=True,
        ))

        checkpointer.finalize_thread(thread_config)

        assert "test-thread-123" not in checkpointer._threads


class TestHeuristics:
    """Tests for heuristic detection."""

    def test_looks_like_action_detects_write_patterns(self, checkpointer):
        """_looks_like_action detects common write patterns."""
        assert checkpointer._looks_like_action("write_file", {}) is True
        assert checkpointer._looks_like_action("send_email", {}) is True
        assert checkpointer._looks_like_action("create_ticket", {}) is True
        assert checkpointer._looks_like_action("update_record", {}) is True
        assert checkpointer._looks_like_action("delete_user", {}) is True
        assert checkpointer._looks_like_action("execute_command", {}) is True

    def test_looks_like_action_rejects_read_patterns(self, checkpointer):
        """_looks_like_action rejects common read patterns."""
        assert checkpointer._looks_like_action("get_user", {}) is False
        assert checkpointer._looks_like_action("fetch_data", {}) is False
        assert checkpointer._looks_like_action("search_records", {}) is False
        assert checkpointer._looks_like_action("list_items", {}) is False


class TestSafeGet:
    """Tests for the _safe_get helper."""

    def test_safe_get_dict(self):
        """_safe_get works with dicts."""
        assert _safe_get({"key": "value"}, "key") == "value"
        assert _safe_get({"key": "value"}, "missing", "default") == "default"

    def test_safe_get_object(self):
        """_safe_get works with objects."""
        class Obj:
            attr = "value"

        assert _safe_get(Obj(), "attr") == "value"
        assert _safe_get(Obj(), "missing", "default") == "default"

    def test_safe_get_none(self):
        """_safe_get handles None."""
        assert _safe_get(None, "key", "default") == "default"


class TestAsyncCheckpointer:
    """Tests for the async checkpointer variant."""

    @pytest.fixture
    def async_underlying(self):
        """Create a mock async underlying checkpointer."""
        from unittest.mock import AsyncMock
        underlying = MagicMock()
        underlying.aget_tuple = AsyncMock(return_value=None)
        underlying.aput = AsyncMock(return_value={"configurable": {"thread_id": "test"}})
        underlying.aput_writes = AsyncMock(return_value=None)
        return underlying

    @pytest.fixture
    def async_checkpointer(self, mock_client, async_underlying):
        """Create an AsyncContextGraphCheckpointer for testing."""
        return AsyncContextGraphCheckpointer(
            underlying=async_underlying,
            client=mock_client,
            write_tools=["send_email"],
        )

    @pytest.mark.asyncio
    async def test_aget_tuple(self, async_checkpointer, async_underlying, thread_config):
        """aget_tuple delegates to underlying."""
        async_underlying.aget_tuple.return_value = {"id": "checkpoint-1"}

        result = await async_checkpointer.aget_tuple(thread_config)

        async_underlying.aget_tuple.assert_called_once_with(thread_config)
        assert result == {"id": "checkpoint-1"}

    @pytest.mark.asyncio
    async def test_aput_extracts_data(self, async_checkpointer, async_underlying, thread_config):
        """aput extracts tool calls like sync version."""
        checkpoint = {
            "channel_values": {
                "messages": [
                    {"tool_calls": [{"id": "tc1", "name": "send_email", "args": {}}]}
                ]
            }
        }
        metadata = {"step": 1, "writes": {}}

        await async_checkpointer.aput(thread_config, checkpoint, metadata, {})

        accumulator = async_checkpointer._threads["test-thread-123"]
        assert len(accumulator.actions) == 1


class TestIntegration:
    """Integration tests for realistic workflows."""

    def test_full_workflow(self, checkpointer, mock_client, mock_underlying, thread_config):
        """Test a complete workflow from start to finalize."""
        # Step 1: Initial state with evidence
        checkpoint1 = {
            "channel_values": {
                "customer_data": {"name": "Acme", "tier": "enterprise"},
                "messages": [],
            }
        }
        checkpointer.put(thread_config, checkpoint1, {"step": 1, "writes": {}}, {})

        # Step 2: Tool call to fetch more data
        checkpoint2 = {
            "channel_values": {
                "customer_data": {"name": "Acme", "tier": "enterprise"},
                "messages": [
                    {"tool_calls": [{"id": "tc1", "name": "fetch_data", "args": {"query": "billing"}}]}
                ],
            }
        }
        checkpointer.put(thread_config, checkpoint2, {"step": 2, "writes": {}}, {})

        # Interrupt for approval
        checkpointer.on_interrupt(thread_config, {"amount": 1000})

        # Resume after approval
        checkpointer.on_resume(thread_config, "manager@acme.com", "Approved")

        # Step 3: Action
        checkpoint3 = {
            "channel_values": {
                "customer_data": {"name": "Acme", "tier": "enterprise"},
                "messages": [
                    {"tool_calls": [{"id": "tc1", "name": "fetch_data", "args": {"query": "billing"}}]},
                    {"tool_calls": [{"id": "tc2", "name": "send_email", "args": {"to": "customer@acme.com"}}]},
                ],
            }
        }
        checkpointer.put(thread_config, checkpoint3, {"step": 3, "writes": {}}, {})

        # Finalize
        record = checkpointer.finalize_thread(thread_config)

        # Verify record
        assert record is not None
        mock_client.ingest_decision.assert_called_once()

        # Check contents
        assert len(record.evidence) >= 2  # customer_data + fetch_data + interrupt
        assert len(record.actions) == 1  # send_email
        assert len(record.approvals) == 1  # manager approval
        assert record.outcome == Outcome.COMMITTED
