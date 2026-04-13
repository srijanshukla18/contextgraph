"""Tests for the demo agent module."""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from demo.agent import (
    ExceptionDeskAgent,
    run_demo,
    Actor,
    ActorType,
    Evidence,
    PolicyEval as PolicyCheck,
    Approval,
    Action,
    DecisionRecord,
    Outcome,
    PolicyResult,
)


class TestExceptionDeskAgent:
    """Tests for the ExceptionDeskAgent class."""

    @pytest.fixture
    def agent(self):
        """Create an ExceptionDeskAgent instance."""
        return ExceptionDeskAgent()

    def test_agent_initialization(self, agent):
        """Agent initializes with all required tools."""
        assert agent.support is not None
        assert agent.crm is not None
        assert agent.incidents is not None
        assert agent.billing is not None
        assert agent.approvals is not None
        assert agent.policy is not None

    def test_agent_accumulators_initialized(self, agent):
        """Agent initializes with empty accumulators."""
        assert agent._evidence == []
        assert agent._policies == []
        assert agent._approvals == []
        assert agent._actions == []


class TestProcessTicket:
    """Tests for the process_ticket method."""

    @pytest.fixture
    def agent(self):
        """Create an ExceptionDeskAgent instance."""
        return ExceptionDeskAgent()

    @patch("time.sleep")
    def test_process_ticket_success_within_cap(self, mock_sleep, agent):
        """Process ticket within default cap succeeds without exception."""
        result = agent.process_ticket("SUP-4400")  # 8% request

        assert result["outcome"] == "committed"
        assert "decision_id" in result
        assert "run_id" in result

    @patch("time.sleep")
    def test_process_ticket_with_exception_approval(self, mock_sleep, agent):
        """Process ticket with exception gets approval and succeeds."""
        result = agent.process_ticket("SUP-4312")  # 20% request with SEV-1s

        # Should be committed after exception approval
        assert result["outcome"] == "committed"

    @patch("time.sleep")
    def test_process_ticket_gathers_evidence(self, mock_sleep, agent):
        """Process ticket gathers evidence from multiple sources."""
        result = agent.process_ticket("SUP-4400")

        record = result["record"]
        evidence_sources = [e["source"] for e in record["evidence"]]

        assert "support.get_ticket" in evidence_sources
        assert "crm.get_account" in evidence_sources
        assert "incidents.get_recent" in evidence_sources

    @patch("time.sleep")
    def test_process_ticket_checks_policy(self, mock_sleep, agent):
        """Process ticket checks policy."""
        result = agent.process_ticket("SUP-4400")

        record = result["record"]
        assert len(record["policies"]) == 1
        assert record["policies"][0]["policy_id"] == "service_credit"

    @patch("time.sleep")
    def test_process_ticket_creates_action_on_commit(self, mock_sleep, agent):
        """Process ticket creates action when credit is issued."""
        result = agent.process_ticket("SUP-4400")

        record = result["record"]
        if result["outcome"] == "committed":
            assert len(record["actions"]) >= 1
            action_tools = [a["tool"] for a in record["actions"]]
            assert "billing.create_service_credit" in action_tools

    @patch("time.sleep")
    def test_process_ticket_invalid_ticket_denied(self, mock_sleep, agent):
        """Process invalid ticket returns denied outcome."""
        result = agent.process_ticket("INVALID-TICKET")

        assert result["outcome"] == "denied"
        assert "not found" in result["reason"].lower()

    @patch("time.sleep")
    def test_process_ticket_generates_run_id(self, mock_sleep, agent):
        """Process ticket generates unique run ID."""
        result = agent.process_ticket("SUP-4400")

        assert result["run_id"].startswith("run_SUP-4400_")


class TestAddEvidence:
    """Tests for the _add_evidence method."""

    @pytest.fixture
    def agent(self):
        """Create an ExceptionDeskAgent instance."""
        return ExceptionDeskAgent()

    def test_add_evidence_stores_evidence(self, agent):
        """_add_evidence stores evidence correctly."""
        agent._add_evidence(
            tool="test_tool",
            args={"arg1": "value1"},
            data={"result": "data"},
        )

        assert len(agent._evidence) == 1
        assert agent._evidence[0].tool_name == "test_tool"
        assert agent._evidence[0].tool_args == {"arg1": "value1"}
        assert agent._evidence[0].snapshot == {"result": "data"}

    def test_add_evidence_sets_source(self, agent):
        """_add_evidence sets source from tool name."""
        agent._add_evidence("my.tool.name", {}, {})

        assert agent._evidence[0].source == "my.tool.name"

    def test_add_evidence_sets_timestamp(self, agent):
        """_add_evidence sets retrieved_at timestamp."""
        before = datetime.utcnow()
        agent._add_evidence("tool", {}, {})
        after = datetime.utcnow()

        assert before <= agent._evidence[0].retrieved_at <= after


class TestAddPolicyCheck:
    """Tests for the _add_policy_eval method."""

    @pytest.fixture
    def agent(self):
        """Create an ExceptionDeskAgent instance."""
        return ExceptionDeskAgent()

    def test_add_policy_check_maps_approved(self, agent):
        """_add_policy_eval maps APPROVED to PASS."""
        from demo.policy import PolicyEvaluation, PolicyResult as DemoPolicyResult

        policy_check = PolicyEvaluation(
            policy_id="test",
            version="1.0",
            result=DemoPolicyResult.APPROVED,
            requested_pct=0.05,
            cap_pct=0.10,
            max_exception_pct=0.25,
            exception_route=None,
            requires_approval=False,
            approval_reason=None,
            details={},
        )

        agent._add_policy_eval(policy_check)

        assert agent._policies[0].result == PolicyResult.PASS

    def test_add_policy_check_maps_exception_required(self, agent):
        """_add_policy_eval maps EXCEPTION_REQUIRED to WARN."""
        from demo.policy import PolicyEvaluation, PolicyResult as DemoPolicyResult

        policy_check = PolicyEvaluation(
            policy_id="test",
            version="1.0",
            result=DemoPolicyResult.EXCEPTION_REQUIRED,
            requested_pct=0.15,
            cap_pct=0.10,
            max_exception_pct=0.25,
            exception_route="test_route",
            requires_approval=True,
            approval_reason="Test reason",
            details={},
        )

        agent._add_policy_eval(policy_check)

        assert agent._policies[0].result == PolicyResult.WARN

    def test_add_policy_check_maps_denied(self, agent):
        """_add_policy_eval maps DENIED to FAIL."""
        from demo.policy import PolicyEvaluation, PolicyResult as DemoPolicyResult

        policy_check = PolicyEvaluation(
            policy_id="test",
            version="1.0",
            result=DemoPolicyResult.DENIED,
            requested_pct=0.30,
            cap_pct=0.10,
            max_exception_pct=0.25,
            exception_route=None,
            requires_approval=False,
            approval_reason="Exceeds max",
            details={},
        )

        agent._add_policy_eval(policy_check)

        assert agent._policies[0].result == PolicyResult.FAIL


class TestAddApproval:
    """Tests for the _add_approval method."""

    @pytest.fixture
    def agent(self):
        """Create an ExceptionDeskAgent instance."""
        return ExceptionDeskAgent()

    def test_add_approval_granted(self, agent):
        """_add_approval correctly stores granted approval."""
        approval_data = {
            "approver": "manager@test.com",
            "approver_role": "Finance Lead",
            "approved": True,
            "decided_at": "2025-01-01T12:00:00",
            "reason": "Approved",
        }

        agent._add_approval(approval_data)

        assert len(agent._approvals) == 1
        assert agent._approvals[0].granted is True
        assert agent._approvals[0].approver.id == "manager@test.com"
        assert agent._approvals[0].approver.type == ActorType.HUMAN

    def test_add_approval_denied(self, agent):
        """_add_approval correctly stores denied approval."""
        approval_data = {
            "approver": "manager@test.com",
            "approver_role": "Finance Lead",
            "approved": False,
            "decided_at": "2025-01-01T12:00:00",
            "reason": "Insufficient justification",
        }

        agent._add_approval(approval_data)

        assert agent._approvals[0].granted is False
        assert agent._approvals[0].reason == "Insufficient justification"


class TestAddAction:
    """Tests for the _add_action method."""

    @pytest.fixture
    def agent(self):
        """Create an ExceptionDeskAgent instance."""
        return ExceptionDeskAgent()

    def test_add_action_success(self, agent):
        """_add_action stores successful action."""
        agent._add_action(
            tool="billing.create_credit",
            params={"amount": 1000},
            result={"credit_id": "CR-123"},
            success=True,
        )

        assert len(agent._actions) == 1
        assert agent._actions[0].tool == "billing.create_credit"
        assert agent._actions[0].success is True

    def test_add_action_failure(self, agent):
        """_add_action stores failed action."""
        agent._add_action(
            tool="billing.create_credit",
            params={"amount": 1000},
            result={},
            success=False,
        )

        assert agent._actions[0].success is False

    def test_add_action_sets_timestamp(self, agent):
        """_add_action sets committed_at timestamp."""
        before = datetime.utcnow()
        agent._add_action("tool", {}, {}, True)
        after = datetime.utcnow()

        assert before <= agent._actions[0].committed_at <= after


class TestFinalizeDecision:
    """Tests for the _finalize_decision method."""

    @pytest.fixture
    def agent(self):
        """Create an ExceptionDeskAgent instance."""
        return ExceptionDeskAgent()

    def test_finalize_creates_decision_record(self, agent):
        """_finalize_decision creates complete DecisionRecord."""
        start_time = datetime.utcnow()
        result = agent._finalize_decision(
            run_id="run_123",
            start_time=start_time,
            outcome=Outcome.COMMITTED,
            reason="Success",
        )

        assert "decision_id" in result
        assert result["run_id"] == "run_123"
        assert result["outcome"] == "committed"
        assert "record" in result

    def test_finalize_includes_accumulated_data(self, agent):
        """_finalize_decision includes all accumulated data."""
        # Add some data
        agent._add_evidence("tool", {}, {"data": True})
        agent._add_action("action", {}, {}, True)

        result = agent._finalize_decision(
            run_id="run_123",
            start_time=datetime.utcnow(),
            outcome=Outcome.COMMITTED,
            reason="Success",
        )

        record = result["record"]
        assert len(record["evidence"]) == 1
        assert len(record["actions"]) == 1

    def test_finalize_sets_actor(self, agent):
        """_finalize_decision sets correct actor."""
        result = agent._finalize_decision(
            run_id="run_123",
            start_time=datetime.utcnow(),
            outcome=Outcome.COMMITTED,
            reason="Success",
        )

        record = result["record"]
        assert record["actor"]["id"] == "exception-desk-agent"
        assert record["actor"]["type"] == "agent"

    def test_finalize_includes_metadata(self, agent):
        """_finalize_decision includes workflow metadata."""
        result = agent._finalize_decision(
            run_id="run_123",
            start_time=datetime.utcnow(),
            outcome=Outcome.COMMITTED,
            reason="Success",
        )

        record = result["record"]
        assert record["metadata"]["workflow"] == "service_credit"


class TestRunDemo:
    """Tests for the run_demo function."""

    @patch("time.sleep")
    def test_run_demo_default_ticket(self, mock_sleep):
        """run_demo processes default ticket."""
        result = run_demo()

        assert "decision_id" in result
        assert "outcome" in result

    @patch("time.sleep")
    def test_run_demo_custom_ticket(self, mock_sleep):
        """run_demo processes custom ticket."""
        result = run_demo("SUP-4400")

        assert "decision_id" in result


class TestModelDataclasses:
    """Tests for inline model dataclasses in agent module."""

    def test_actor_to_dict(self):
        """Actor.to_dict returns correct structure."""
        actor = Actor(type=ActorType.AGENT, id="test", name="Test Agent")
        result = actor.to_dict()

        assert result["type"] == "agent"
        assert result["id"] == "test"
        assert result["name"] == "Test Agent"

    def test_evidence_to_dict(self):
        """Evidence.to_dict returns correct structure."""
        evidence = Evidence(
            source="test",
            retrieved_at=datetime.utcnow(),
            snapshot={"key": "value"},
        )
        result = evidence.to_dict()

        assert result["source"] == "test"
        assert result["snapshot"] == {"key": "value"}
        assert "retrieved_at" in result

    def test_policy_check_to_dict(self):
        """PolicyCheck.to_dict returns correct structure."""
        policy = PolicyCheck(
            policy_id="test",
            version="1.0",
            result=PolicyResult.PASS,
            message="OK",
        )
        result = policy.to_dict()

        assert result["policy_id"] == "test"
        assert result["result"] == "pass"

    def test_action_to_dict(self):
        """Action.to_dict returns correct structure."""
        action = Action(
            tool="test_tool",
            committed_at=datetime.utcnow(),
            params={"arg": 1},
            result={"ok": True},
            success=True,
        )
        result = action.to_dict()

        assert result["tool"] == "test_tool"
        assert result["success"] is True

    def test_decision_record_to_dict(self):
        """DecisionRecord.to_dict returns correct structure."""
        record = DecisionRecord(
            run_id="run_123",
            outcome=Outcome.COMMITTED,
            outcome_reason="Success",
        )
        result = record.to_dict()

        assert result["run_id"] == "run_123"
        assert result["outcome"] == "committed"
        assert result["outcome_reason"] == "Success"
