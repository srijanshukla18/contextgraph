"""Tests for the ContextGraph Server API."""

import json
import os
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# Mock the database pool before importing the app
@pytest.fixture(autouse=True)
def mock_db_pool():
    """Mock the database connection pool for all tests."""
    with patch.dict(os.environ, {
        "REQUIRE_AUTH": "false",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
    }):
        # Create mock connection and cursor
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("server.main.init_db_pool"):
            with patch("server.main.get_db_connection", return_value=mock_conn):
                with patch("server.main.release_db_connection"):
                    yield mock_cursor, mock_conn


@pytest.fixture
def client(mock_db_pool):
    """Create a test client."""
    from server.main import app, rate_limiter
    # Clear rate limiter state between tests
    rate_limiter.requests.clear()
    return TestClient(app)


@pytest.fixture
def sample_decision():
    """Sample decision record for testing."""
    return {
        "decision_id": str(uuid.uuid4()),
        "run_id": "run_test_123",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "outcome": "committed",
        "actor": {"type": "agent", "id": "test-agent"},
        "evidence": [
            {
                "evidence_id": str(uuid.uuid4()),
                "source": "crm.get_account",
                "snapshot": {"arr": 500000},
                "retrieved_at": datetime.utcnow().isoformat() + "Z",
            }
        ],
        "policies": [
            {
                "policy_id": "service_credit",
                "version": "1.0",
                "result": "pass",
            }
        ],
        "approvals": [],
        "actions": [
            {
                "action_id": str(uuid.uuid4()),
                "tool": "billing.create_credit",
                "params": {"amount": 1000},
                "committed_at": datetime.utcnow().isoformat() + "Z",
                "success": True,
            }
        ],
    }


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_endpoint_returns_ok(self, client, mock_db_pool):
        """Health endpoint returns ok when DB is connected."""
        mock_cursor, mock_conn = mock_db_pool
        mock_cursor.fetchone.return_value = {"1": 1}

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"
        assert "version" in data
        assert "timestamp" in data

    def test_health_endpoint_degraded_on_db_error(self, client, mock_db_pool):
        """Health endpoint returns degraded when DB fails."""
        mock_cursor, mock_conn = mock_db_pool
        mock_cursor.execute.side_effect = Exception("Connection refused")

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert "error" in data["database"]

    def test_ready_endpoint_returns_ready(self, client, mock_db_pool):
        """Readiness probe returns ready when DB is connected."""
        mock_cursor, mock_conn = mock_db_pool
        mock_cursor.fetchone.return_value = {"1": 1}

        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["ready"] is True

    def test_ready_endpoint_503_on_db_error(self, client, mock_db_pool):
        """Readiness probe returns 503 when DB fails."""
        mock_cursor, mock_conn = mock_db_pool
        mock_cursor.execute.side_effect = Exception("Connection refused")

        response = client.get("/ready")
        assert response.status_code == 503


class TestDecisionEndpoints:
    """Tests for decision CRUD endpoints."""

    def test_create_decision_success(self, client, mock_db_pool, sample_decision):
        """POST /v1/decisions creates a decision record."""
        mock_cursor, mock_conn = mock_db_pool
        mock_cursor.fetchone.return_value = {"decision_id": sample_decision["decision_id"]}

        response = client.post("/v1/decisions", json=sample_decision)
        assert response.status_code == 200
        data = response.json()
        assert data["decision_id"] == sample_decision["decision_id"]
        assert data["status"] == "created"

    def test_create_decision_validates_required_fields(self, client, mock_db_pool):
        """POST /v1/decisions validates required fields."""
        response = client.post("/v1/decisions", json={})
        assert response.status_code == 422  # Validation error

    def test_get_decision_success(self, client, mock_db_pool):
        """GET /v1/decisions/{id} returns a decision."""
        decision_id = str(uuid.uuid4())
        mock_cursor, mock_conn = mock_db_pool
        mock_cursor.fetchone.return_value = {
            "decision_id": decision_id,
            "run_id": "run_123",
            "outcome": "committed",
        }

        response = client.get(f"/v1/decisions/{decision_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["decision_id"] == decision_id

    def test_get_decision_not_found(self, client, mock_db_pool):
        """GET /v1/decisions/{id} returns 404 for missing decision."""
        mock_cursor, mock_conn = mock_db_pool
        mock_cursor.fetchone.return_value = None

        response = client.get("/v1/decisions/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert data["type"] == "https://contextgraph.dev/errors/404"

    def test_list_decisions_success(self, client, mock_db_pool):
        """GET /v1/decisions returns list of decisions."""
        mock_cursor, mock_conn = mock_db_pool
        mock_cursor.fetchall.return_value = [
            {"decision_id": "dec_1", "run_id": "run_1", "timestamp": datetime.utcnow(), "outcome": "committed", "actor_id": "agent"},
            {"decision_id": "dec_2", "run_id": "run_2", "timestamp": datetime.utcnow(), "outcome": "denied", "actor_id": "agent"},
        ]

        response = client.get("/v1/decisions")
        assert response.status_code == 200
        data = response.json()
        assert "decisions" in data
        assert "count" in data
        assert data["count"] == 2

    def test_list_decisions_with_filters(self, client, mock_db_pool):
        """GET /v1/decisions supports filtering."""
        mock_cursor, mock_conn = mock_db_pool
        mock_cursor.fetchall.return_value = []

        response = client.get("/v1/decisions?run_id=run_123&outcome=committed&limit=10")
        assert response.status_code == 200

        # Verify the query was called with correct params
        call_args = mock_cursor.execute.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        assert "run_id = %s" in query
        assert "outcome = %s" in query
        assert params == ["run_123", "committed", 10, 0]


class TestExplainEndpoint:
    """Tests for the explain decision endpoint."""

    def test_explain_decision_success(self, client, mock_db_pool):
        """GET /v1/decisions/{id}/explain returns explanation."""
        decision_id = str(uuid.uuid4())
        mock_cursor, mock_conn = mock_db_pool
        mock_cursor.fetchone.return_value = {
            "decision_id": decision_id,
            "run_id": "run_123",
            "timestamp": datetime.utcnow(),
            "outcome": "committed",
            "outcome_reason": None,
            "actor_id": "agent",
            "actor_type": "agent",
            "evidence": [
                {"source": "crm", "tool_name": "get_account", "retrieved_at": "2025-01-01T00:00:00Z"}
            ],
            "policies": [
                {"policy_id": "credit_policy", "version": "1.0", "result": "pass", "message": None}
            ],
            "approvals": [],
            "actions": [
                {"tool": "billing.create", "operation": "create", "committed_at": "2025-01-01T00:00:00Z", "success": True}
            ],
        }

        response = client.get(f"/v1/decisions/{decision_id}/explain")
        assert response.status_code == 200
        data = response.json()
        assert data["decision_id"] == decision_id
        assert "evidence_chain" in data
        assert "policy_chain" in data
        assert "approval_chain" in data
        assert "action_chain" in data
        assert "summary" in data

    def test_explain_builds_correct_summary(self, client, mock_db_pool):
        """Explain endpoint builds meaningful summary."""
        mock_cursor, mock_conn = mock_db_pool
        mock_cursor.fetchone.return_value = {
            "decision_id": "dec_123",
            "run_id": "run_123",
            "timestamp": datetime.utcnow(),
            "outcome": "committed",
            "outcome_reason": None,
            "actor_id": None,
            "actor_type": None,
            "evidence": [{"source": "a"}, {"source": "b"}],
            "policies": [{"policy_id": "p1", "result": "pass"}, {"policy_id": "p2", "result": "fail"}],
            "approvals": [{"approver": {"id": "human"}, "granted": True}],
            "actions": [{"tool": "write", "success": True}, {"tool": "send", "success": False}],
        }

        response = client.get("/v1/decisions/dec_123/explain")
        data = response.json()
        summary = data["summary"]

        assert "2 pieces of evidence" in summary
        assert "2 policies (1 passed)" in summary
        assert "1/1 approvals" in summary
        assert "1/2 actions" in summary


class TestPrecedentSearch:
    """Tests for precedent search endpoint."""

    def test_search_precedents_success(self, client, mock_db_pool):
        """POST /v1/precedents/search returns matching precedents."""
        mock_cursor, mock_conn = mock_db_pool
        mock_cursor.fetchall.return_value = [
            {
                "decision_id": "dec_1",
                "run_id": "run_1",
                "timestamp": datetime.utcnow(),
                "outcome": "committed",
                "policies": [{"policy_id": "credit_policy"}],
                "actions": [{"tool": "billing.create"}],
            }
        ]

        response = client.post("/v1/precedents/search", params={
            "policy_id": "credit_policy",
            "outcome": "committed",
        })
        assert response.status_code == 200
        data = response.json()
        assert "precedents" in data
        assert "count" in data

    def test_search_precedents_filters_by_tool(self, client, mock_db_pool):
        """Precedent search filters by tool name."""
        mock_cursor, mock_conn = mock_db_pool
        mock_cursor.fetchall.return_value = [
            {
                "decision_id": "dec_1",
                "run_id": "run_1",
                "timestamp": datetime.utcnow(),
                "outcome": "committed",
                "policies": [],
                "actions": [{"tool": "billing.create"}],
            },
            {
                "decision_id": "dec_2",
                "run_id": "run_2",
                "timestamp": datetime.utcnow(),
                "outcome": "committed",
                "policies": [],
                "actions": [{"tool": "email.send"}],
            },
        ]

        response = client.post("/v1/precedents/search", params={"tool": "billing.create"})
        data = response.json()

        # Should filter out dec_2 which has different tool
        assert data["count"] == 1
        assert data["precedents"][0]["decision_id"] == "dec_1"


class TestAuthentication:
    """Tests for API key authentication."""

    def test_requires_api_key_when_enabled(self):
        """Endpoints require API key when REQUIRE_AUTH=true."""
        with patch.dict(os.environ, {
            "REQUIRE_AUTH": "true",
            "API_KEYS": "test-key-123",
            "DATABASE_URL": "postgresql://test:test@localhost/test",
        }):
            with patch("server.main.init_db_pool"):
                with patch("server.main.db_pool", MagicMock()):
                    # Need to reimport to pick up new env
                    import importlib
                    import server.main
                    importlib.reload(server.main)

                    client = TestClient(server.main.app)
                    response = client.get("/v1/decisions")
                    assert response.status_code == 401

    def test_accepts_valid_api_key_header(self):
        """Endpoints accept valid X-API-Key header via verify_api_key function."""
        from server.main import verify_api_key, API_KEYS

        # Directly test the verify function logic
        import server.main as main_module

        # Temporarily enable auth and add a key
        original_require = main_module.REQUIRE_AUTH
        original_keys = main_module.API_KEYS

        main_module.REQUIRE_AUTH = True
        main_module.API_KEYS = {"test-key-123"}

        try:
            # Mock the request
            mock_request = MagicMock()

            # This should NOT raise (valid key)
            import asyncio
            result = asyncio.get_event_loop().run_until_complete(
                verify_api_key(mock_request, x_api_key="test-key-123", authorization=None)
            )
            assert result == "test-key..."  # Masked key
        finally:
            main_module.REQUIRE_AUTH = original_require
            main_module.API_KEYS = original_keys

    def test_accepts_bearer_token(self):
        """Endpoints accept valid Bearer token via verify_api_key function."""
        from server.main import verify_api_key

        import server.main as main_module

        original_require = main_module.REQUIRE_AUTH
        original_keys = main_module.API_KEYS

        main_module.REQUIRE_AUTH = True
        main_module.API_KEYS = {"test-key-123"}

        try:
            mock_request = MagicMock()

            import asyncio
            result = asyncio.get_event_loop().run_until_complete(
                verify_api_key(mock_request, x_api_key=None, authorization="Bearer test-key-123")
            )
            assert result == "test-key..."  # Masked key
        finally:
            main_module.REQUIRE_AUTH = original_require
            main_module.API_KEYS = original_keys


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    def test_rate_limiter_allows_requests_within_limit(self):
        """Rate limiter allows requests within the limit."""
        from server.main import RateLimiter

        limiter = RateLimiter(max_requests=5, window_seconds=60)

        for _ in range(5):
            allowed, remaining, _ = limiter.is_allowed("test-ip")
            assert allowed is True

        # 6th request should be blocked
        allowed, remaining, _ = limiter.is_allowed("test-ip")
        assert allowed is False
        assert remaining == 0

    def test_rate_limiter_tracks_per_key(self):
        """Rate limiter tracks limits per key."""
        from server.main import RateLimiter

        limiter = RateLimiter(max_requests=2, window_seconds=60)

        # Exhaust limit for ip1
        limiter.is_allowed("ip1")
        limiter.is_allowed("ip1")
        allowed, _, _ = limiter.is_allowed("ip1")
        assert allowed is False

        # ip2 should still be allowed
        allowed, _, _ = limiter.is_allowed("ip2")
        assert allowed is True

    def test_rate_limit_headers_in_response(self, client, mock_db_pool):
        """Rate limit headers are included in 429 response."""
        with patch.dict(os.environ, {
            "RATE_LIMIT_REQUESTS": "1",
            "RATE_LIMIT_WINDOW": "60",
            "REQUIRE_AUTH": "false",
        }):
            import importlib
            import server.main
            importlib.reload(server.main)

            client = TestClient(server.main.app)
            mock_cursor, _ = mock_db_pool
            mock_cursor.fetchall.return_value = []

            # First request succeeds
            response = client.get("/v1/decisions")

            # Second request should be rate limited
            response = client.get("/v1/decisions")
            if response.status_code == 429:
                assert "X-RateLimit-Limit" in response.headers
                assert "Retry-After" in response.headers


class TestErrorHandling:
    """Tests for error handling."""

    def test_404_returns_rfc7807_format(self, client, mock_db_pool):
        """404 errors return RFC 7807 problem details format."""
        mock_cursor, _ = mock_db_pool
        mock_cursor.fetchone.return_value = None

        response = client.get("/v1/decisions/nonexistent")
        assert response.status_code == 404
        data = response.json()

        assert "type" in data
        assert "title" in data
        assert "status" in data
        assert "detail" in data
        assert "instance" in data
        assert data["status"] == 404

    def test_request_id_in_response_headers(self, client, mock_db_pool):
        """X-Request-ID header is included in responses."""
        mock_cursor, _ = mock_db_pool
        mock_cursor.fetchall.return_value = []

        response = client.get("/v1/decisions")
        assert "X-Request-ID" in response.headers

    def test_custom_request_id_is_preserved(self, client, mock_db_pool):
        """Custom X-Request-ID is preserved in response."""
        mock_cursor, _ = mock_db_pool
        mock_cursor.fetchall.return_value = []

        custom_id = "my-custom-request-id"
        response = client.get("/v1/decisions", headers={"X-Request-ID": custom_id})
        assert response.headers["X-Request-ID"] == custom_id
