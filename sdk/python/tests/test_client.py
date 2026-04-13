"""Tests for the ContextGraph client."""

import json
import urllib.error
import urllib.request
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest

from contextgraph.core.client import (
    ContextGraphClient,
    ContextGraphError,
    ConnectionError,
    IngestError,
    DecisionRecordBuilder,
)
from contextgraph.core.config import Config
from contextgraph.core.models import (
    DecisionRecord,
    Evidence,
    Action,
    Outcome,
    Actor,
    ActorType,
    PolicyEval,
    PolicyResult,
)


class TestContextGraphClient:
    """Tests for ContextGraphClient initialization and configuration."""

    def test_init_with_default_config(self):
        """Client initializes with default config if none provided."""
        client = ContextGraphClient()
        assert client.config is not None
        assert client.config.server_url == "http://localhost:8080"

    def test_init_with_custom_config(self):
        """Client uses provided config."""
        config = Config(server_url="http://custom:9000", api_key="test-key")
        client = ContextGraphClient(config)
        assert client.config.server_url == "http://custom:9000"
        assert client.config.api_key == "test-key"

    def test_init_pending_events_empty(self):
        """Client starts with no pending events."""
        client = ContextGraphClient()
        assert len(client._pending_events) == 0

    def test_init_failed_ingests_empty(self):
        """Client starts with no failed ingests."""
        client = ContextGraphClient()
        assert client.failed_count == 0


class TestLocalMode:
    """Tests for local mode (direct postgres connection)."""

    def test_local_mode_attempts_connection(self):
        """Local mode attempts postgres connection when configured."""
        config = Config(local_mode=True, postgres_url="postgresql://localhost/test")

        with patch("contextgraph.core.client.psycopg2") as mock_psycopg2:
            mock_conn = MagicMock()
            mock_psycopg2.connect.return_value = mock_conn

            client = ContextGraphClient(config)

            mock_psycopg2.connect.assert_called_once_with(config.postgres_url)
            assert client._connection == mock_conn

    def test_local_mode_handles_import_error(self):
        """Local mode handles missing psycopg2 gracefully."""
        config = Config(local_mode=True, postgres_url="postgresql://localhost/test")

        with patch.dict("sys.modules", {"psycopg2": None}):
            with patch("contextgraph.core.client.psycopg2", None):
                # Should not raise, just log warning
                client = ContextGraphClient(config)
                assert client._connection is None

    def test_local_mode_handles_connection_error(self):
        """Local mode handles connection errors gracefully."""
        config = Config(local_mode=True, postgres_url="postgresql://localhost/test")

        with patch("contextgraph.core.client.psycopg2") as mock_psycopg2:
            mock_psycopg2.connect.side_effect = Exception("Connection refused")

            client = ContextGraphClient(config)
            assert client._connection is None


class TestStartDecision:
    """Tests for the start_decision method."""

    def test_start_decision_returns_builder(self):
        """start_decision returns a DecisionRecordBuilder."""
        client = ContextGraphClient()
        builder = client.start_decision("run_123")

        assert isinstance(builder, DecisionRecordBuilder)
        assert builder.run_id == "run_123"

    def test_start_decision_with_actor(self):
        """start_decision accepts actor parameters."""
        client = ContextGraphClient()
        builder = client.start_decision("run_123", actor_id="my-agent", actor_type="agent")

        assert builder.actor_id == "my-agent"
        assert builder.actor_type == "agent"

    def test_start_decision_stores_current_builder(self):
        """start_decision stores the current builder."""
        client = ContextGraphClient()
        builder = client.start_decision("run_123")

        assert client._current_decision == builder


class TestIngestEvent:
    """Tests for the ingest_event method."""

    def test_ingest_event_adds_to_pending(self):
        """ingest_event adds event to pending list."""
        client = ContextGraphClient()
        event = {"type": "tool_call", "name": "test"}

        client.ingest_event(event)

        assert len(client._pending_events) == 1
        assert client._pending_events[0] == event

    def test_ingest_event_flushes_at_batch_size(self):
        """ingest_event flushes when batch size is reached."""
        config = Config(batch_size=3)
        client = ContextGraphClient(config)

        with patch.object(client, "flush") as mock_flush:
            client.ingest_event({"e": 1})
            client.ingest_event({"e": 2})
            mock_flush.assert_not_called()

            client.ingest_event({"e": 3})
            mock_flush.assert_called_once()


class TestIngestDecision:
    """Tests for the ingest_decision method."""

    @pytest.fixture
    def sample_decision(self):
        """Create a sample decision record."""
        return DecisionRecord(
            run_id="run_123",
            outcome=Outcome.COMMITTED,
            actor=Actor(type=ActorType.AGENT, id="test-agent"),
        )

    def test_ingest_decision_local_mode(self, sample_decision):
        """ingest_decision stores locally in local mode."""
        config = Config(local_mode=True, postgres_url="postgresql://localhost/test")

        with patch("contextgraph.core.client.psycopg2") as mock_psycopg2:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_psycopg2.connect.return_value = mock_conn

            client = ContextGraphClient(config)
            result = client.ingest_decision(sample_decision)

            assert result is True
            mock_cursor.execute.assert_called_once()
            mock_conn.commit.assert_called_once()

    def test_ingest_decision_server_mode(self, sample_decision):
        """ingest_decision sends to server in server mode."""
        config = Config(server_url="http://localhost:8080")
        client = ContextGraphClient(config)

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = b'{"status": "created"}'
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = client.ingest_decision(sample_decision)

            assert result is True
            mock_urlopen.assert_called_once()

    def test_ingest_decision_handles_http_error(self, sample_decision):
        """ingest_decision handles HTTP errors."""
        config = Config(server_url="http://localhost:8080")
        client = ContextGraphClient(config)

        with patch("urllib.request.urlopen") as mock_urlopen:
            error = urllib.error.HTTPError(
                "http://localhost:8080", 500, "Server Error", {}, None
            )
            error.fp = MagicMock()
            error.fp.read = MagicMock(return_value=b"error")
            mock_urlopen.side_effect = error

            result = client.ingest_decision(sample_decision)

            assert result is False
            assert client.failed_count == 1

    def test_ingest_decision_handles_url_error(self, sample_decision):
        """ingest_decision handles URL errors (connection refused)."""
        config = Config(server_url="http://localhost:8080")
        client = ContextGraphClient(config)

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

            result = client.ingest_decision(sample_decision)

            assert result is False
            assert client.failed_count == 1

    def test_ingest_decision_raises_on_error_when_configured(self, sample_decision):
        """ingest_decision raises exception when raise_on_error is True."""
        config = Config(server_url="http://localhost:8080", raise_on_error=True)
        client = ContextGraphClient(config)

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

            with pytest.raises(IngestError):
                client.ingest_decision(sample_decision)

    def test_ingest_decision_includes_api_key(self, sample_decision):
        """ingest_decision includes API key in Authorization header."""
        config = Config(server_url="http://localhost:8080", api_key="secret-key")
        client = ContextGraphClient(config)

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = b'{"status": "created"}'
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            client.ingest_decision(sample_decision)

            # Check the Request object passed to urlopen
            call_args = mock_urlopen.call_args
            request = call_args[0][0]
            assert request.get_header("Authorization") == "Bearer secret-key"


class TestRetryFailed:
    """Tests for the retry_failed method."""

    def test_retry_failed_no_failures(self):
        """retry_failed returns 0 when no failures."""
        client = ContextGraphClient()
        result = client.retry_failed()
        assert result == 0

    def test_retry_failed_success(self):
        """retry_failed successfully retries failed ingests."""
        config = Config(server_url="http://localhost:8080")
        client = ContextGraphClient(config)

        # Add a failed decision
        failed_decision = DecisionRecord(run_id="run_1", outcome=Outcome.COMMITTED)
        client._failed_ingests.append(failed_decision)

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = b'{"status": "created"}'
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            result = client.retry_failed()

            assert result == 1
            assert client.failed_count == 0

    def test_retry_failed_partial_success(self):
        """retry_failed handles partial success."""
        config = Config(server_url="http://localhost:8080")
        client = ContextGraphClient(config)

        # Add two failed decisions
        client._failed_ingests.append(DecisionRecord(run_id="run_1", outcome=Outcome.COMMITTED))
        client._failed_ingests.append(DecisionRecord(run_id="run_2", outcome=Outcome.COMMITTED))

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                mock_response = MagicMock()
                mock_response.status = 200
                mock_response.read.return_value = b'{"status": "created"}'
                mock_response.__enter__ = Mock(return_value=mock_response)
                mock_response.__exit__ = Mock(return_value=False)
                return mock_response
            else:
                raise urllib.error.URLError("Connection refused")

        with patch("urllib.request.urlopen", side_effect=side_effect):
            result = client.retry_failed()

            assert result == 1
            assert client.failed_count == 1


class TestFlushAndClose:
    """Tests for flush and close methods."""

    def test_flush_clears_pending_events(self):
        """flush clears pending events."""
        client = ContextGraphClient()
        client._pending_events = [{"e": 1}, {"e": 2}]

        client.flush()

        assert len(client._pending_events) == 0

    def test_close_flushes_and_closes_connection(self):
        """close flushes events and closes database connection."""
        config = Config(local_mode=True, postgres_url="postgresql://localhost/test")

        with patch("contextgraph.core.client.psycopg2") as mock_psycopg2:
            mock_conn = MagicMock()
            mock_psycopg2.connect.return_value = mock_conn

            client = ContextGraphClient(config)
            client._pending_events = [{"e": 1}]

            client.close()

            assert len(client._pending_events) == 0
            mock_conn.close.assert_called_once()
            assert client._connection is None


class TestDecisionRecordBuilder:
    """Tests for the DecisionRecordBuilder class."""

    @pytest.fixture
    def client(self):
        """Create a mock client."""
        client = MagicMock()
        client.ingest_decision = MagicMock(return_value=True)
        return client

    @pytest.fixture
    def builder(self, client):
        """Create a builder instance."""
        return DecisionRecordBuilder(client, "run_123", "test-agent", "agent")

    def test_add_evidence_returns_self(self, builder):
        """add_evidence returns self for chaining."""
        result = builder.add_evidence("get_data", {"id": "123"}, {"name": "Test"})
        assert result == builder

    def test_add_evidence_stores_evidence(self, builder):
        """add_evidence stores evidence data."""
        builder.add_evidence("get_account", {"id": "123"}, {"name": "Acme", "arr": 500000})

        assert len(builder.evidence) == 1
        assert builder.evidence[0].tool_name == "get_account"
        assert builder.evidence[0].tool_args == {"id": "123"}
        assert builder.evidence[0].snapshot["name"] == "Acme"

    def test_add_evidence_handles_non_dict_result(self, builder):
        """add_evidence wraps non-dict results."""
        builder.add_evidence("get_value", {}, "string_result")

        assert builder.evidence[0].snapshot == {"value": "string_result"}

    def test_add_action_returns_self(self, builder):
        """add_action returns self for chaining."""
        result = builder.add_action("send_email", {"to": "test@test.com"}, {"sent": True})
        assert result == builder

    def test_add_action_stores_action(self, builder):
        """add_action stores action data."""
        builder.add_action("create_ticket", {"title": "Bug"}, {"id": "T123"})

        assert len(builder.actions) == 1
        assert builder.actions[0].tool == "create_ticket"
        assert builder.actions[0].params == {"title": "Bug"}
        assert builder.actions[0].result["id"] == "T123"

    def test_add_action_with_failure(self, builder):
        """add_action records failed actions."""
        builder.add_action("send_email", {}, {}, success=False)

        assert builder.actions[0].success is False

    def test_add_policy_returns_self(self, builder):
        """add_policy returns self for chaining."""
        result = builder.add_policy("credit_policy", "1.0", "pass")
        assert result == builder

    def test_add_policy_stores_policy(self, builder):
        """add_policy stores policy evaluation."""
        builder.add_policy("credit_policy", "1.0", "pass", "Within limits")

        assert len(builder.policies) == 1
        assert builder.policies[0]["policy_id"] == "credit_policy"
        assert builder.policies[0]["result"] == "pass"

    def test_add_approval_returns_self(self, builder):
        """add_approval returns self for chaining."""
        result = builder.add_approval("manager@test.com", True)
        assert result == builder

    def test_add_approval_stores_approval(self, builder):
        """add_approval stores approval data."""
        builder.add_approval("manager@test.com", True, "Approved for customer impact")

        assert len(builder.approvals) == 1
        assert builder.approvals[0]["approver"]["id"] == "manager@test.com"
        assert builder.approvals[0]["granted"] is True
        assert builder.approvals[0]["reason"] == "Approved for customer impact"

    def test_commit_creates_decision_record(self, builder, client):
        """commit creates and ingests a DecisionRecord."""
        builder.add_evidence("read", {}, {"data": "test"})
        builder.add_action("write", {}, {"ok": True})

        record = builder.commit()

        assert isinstance(record, DecisionRecord)
        assert record.run_id == "run_123"
        assert record.outcome == Outcome.COMMITTED
        client.ingest_decision.assert_called_once()

    def test_commit_with_custom_outcome(self, builder, client):
        """commit accepts custom outcome."""
        builder.add_action("blocked", {}, {})

        record = builder.commit(outcome="denied", reason="Policy violation")

        assert record.outcome == Outcome.DENIED
        assert record.outcome_reason == "Policy violation"

    def test_commit_includes_all_data(self, builder, client):
        """commit includes all accumulated data."""
        builder.add_evidence("read", {"id": "1"}, {"name": "Test"})
        builder.add_action("write", {"data": "x"}, {"ok": True})
        builder.add_policy("policy1", "1.0", "pass")
        builder.add_approval("approver@test.com", True)

        record = builder.commit()

        assert len(record.evidence) == 1
        assert len(record.actions) == 1
        assert len(record.policies) == 1
        assert len(record.approvals) == 1

    def test_method_chaining(self, builder, client):
        """Builder supports method chaining."""
        record = (
            builder
            .add_evidence("read", {}, {})
            .add_action("write", {}, {})
            .add_policy("policy", "1.0", "pass")
            .commit()
        )

        assert record is not None


class TestStoreLocal:
    """Tests for _store_local method."""

    def test_store_local_without_connection_raises(self):
        """_store_local raises ConnectionError without connection."""
        client = ContextGraphClient()
        decision = DecisionRecord(run_id="run_1", outcome=Outcome.COMMITTED)

        with pytest.raises(ConnectionError):
            client._store_local(decision)

    def test_store_local_executes_insert(self):
        """_store_local executes INSERT query."""
        config = Config(local_mode=True, postgres_url="postgresql://localhost/test")

        with patch("contextgraph.core.client.psycopg2") as mock_psycopg2:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_psycopg2.connect.return_value = mock_conn

            client = ContextGraphClient(config)
            decision = DecisionRecord(run_id="run_1", outcome=Outcome.COMMITTED)

            client._store_local(decision)

            mock_cursor.execute.assert_called_once()
            # Check INSERT is in query
            call_args = mock_cursor.execute.call_args
            query = call_args[0][0]
            assert "INSERT INTO decision_records" in query

    def test_store_local_rolls_back_on_error(self):
        """_store_local rolls back transaction on error."""
        config = Config(local_mode=True, postgres_url="postgresql://localhost/test")

        with patch("contextgraph.core.client.psycopg2") as mock_psycopg2:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.execute.side_effect = Exception("DB error")
            mock_conn.cursor.return_value = mock_cursor
            mock_psycopg2.connect.return_value = mock_conn

            client = ContextGraphClient(config)
            decision = DecisionRecord(run_id="run_1", outcome=Outcome.COMMITTED)

            with pytest.raises(IngestError):
                client._store_local(decision)

            mock_conn.rollback.assert_called_once()


class TestSendToServer:
    """Tests for _send_to_server method."""

    def test_send_to_server_constructs_correct_url(self):
        """_send_to_server constructs correct URL."""
        config = Config(server_url="http://custom:9000")
        client = ContextGraphClient(config)
        decision = DecisionRecord(run_id="run_1", outcome=Outcome.COMMITTED)

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = b'{"status": "created"}'
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            client._send_to_server(decision)

            call_args = mock_urlopen.call_args
            request = call_args[0][0]
            assert request.full_url == "http://custom:9000/v1/decisions"

    def test_send_to_server_sets_content_type(self):
        """_send_to_server sets Content-Type header."""
        config = Config(server_url="http://localhost:8080")
        client = ContextGraphClient(config)
        decision = DecisionRecord(run_id="run_1", outcome=Outcome.COMMITTED)

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = b'{"status": "created"}'
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            client._send_to_server(decision)

            call_args = mock_urlopen.call_args
            request = call_args[0][0]
            assert request.get_header("Content-type") == "application/json"

    def test_send_to_server_uses_timeout(self):
        """_send_to_server uses configured timeout."""
        config = Config(server_url="http://localhost:8080", timeout=15.0)
        client = ContextGraphClient(config)
        decision = DecisionRecord(run_id="run_1", outcome=Outcome.COMMITTED)

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = b'{"status": "created"}'
            mock_response.__enter__ = Mock(return_value=mock_response)
            mock_response.__exit__ = Mock(return_value=False)
            mock_urlopen.return_value = mock_response

            client._send_to_server(decision)

            call_args = mock_urlopen.call_args
            assert call_args[1]["timeout"] == 15.0
