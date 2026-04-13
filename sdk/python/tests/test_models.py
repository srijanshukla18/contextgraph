"""Tests for the ContextGraph data models."""

import json
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest

from contextgraph.core.models import (
    generate_id,
    generate_hash,
    ActorType,
    Outcome,
    PolicyResult,
    EntityRef,
    Actor,
    Evidence,
    PolicyEval,
    Approval,
    Action,
    DecisionRecord,
)


class TestGenerateId:
    """Tests for the generate_id function."""

    def test_returns_uuid_string(self):
        """generate_id returns a valid UUID string."""
        result = generate_id()
        assert isinstance(result, str)
        # Should be parseable as UUID
        uuid.UUID(result)

    def test_generates_unique_ids(self):
        """generate_id generates unique IDs each call."""
        ids = [generate_id() for _ in range(100)]
        assert len(set(ids)) == 100


class TestGenerateHash:
    """Tests for the generate_hash function."""

    def test_returns_string(self):
        """generate_hash returns a string."""
        result = generate_hash({"key": "value"})
        assert isinstance(result, str)

    def test_returns_16_char_hash(self):
        """generate_hash returns 16-character hash."""
        result = generate_hash({"key": "value"})
        assert len(result) == 16

    def test_deterministic_for_same_data(self):
        """generate_hash returns same hash for same data."""
        data = {"name": "test", "value": 123}
        hash1 = generate_hash(data)
        hash2 = generate_hash(data)
        assert hash1 == hash2

    def test_different_for_different_data(self):
        """generate_hash returns different hash for different data."""
        hash1 = generate_hash({"key": "value1"})
        hash2 = generate_hash({"key": "value2"})
        assert hash1 != hash2

    def test_handles_nested_data(self):
        """generate_hash handles nested data structures."""
        data = {
            "level1": {
                "level2": {
                    "value": "nested"
                }
            }
        }
        result = generate_hash(data)
        assert isinstance(result, str)

    def test_handles_datetime_in_data(self):
        """generate_hash handles datetime objects via default=str."""
        data = {"timestamp": datetime(2025, 1, 1, 12, 0, 0)}
        result = generate_hash(data)
        assert isinstance(result, str)


class TestActorType:
    """Tests for the ActorType enum."""

    def test_agent_value(self):
        """ActorType.AGENT has correct value."""
        assert ActorType.AGENT.value == "agent"

    def test_human_value(self):
        """ActorType.HUMAN has correct value."""
        assert ActorType.HUMAN.value == "human"

    def test_system_value(self):
        """ActorType.SYSTEM has correct value."""
        assert ActorType.SYSTEM.value == "system"

    def test_is_string_enum(self):
        """ActorType is a string enum."""
        assert str(ActorType.AGENT) == "agent"


class TestOutcome:
    """Tests for the Outcome enum."""

    def test_committed_value(self):
        """Outcome.COMMITTED has correct value."""
        assert Outcome.COMMITTED.value == "committed"

    def test_denied_value(self):
        """Outcome.DENIED has correct value."""
        assert Outcome.DENIED.value == "denied"

    def test_escalated_value(self):
        """Outcome.ESCALATED has correct value."""
        assert Outcome.ESCALATED.value == "escalated"

    def test_pending_value(self):
        """Outcome.PENDING has correct value."""
        assert Outcome.PENDING.value == "pending"


class TestPolicyResult:
    """Tests for the PolicyResult enum."""

    def test_pass_value(self):
        """PolicyResult.PASS has correct value."""
        assert PolicyResult.PASS.value == "pass"

    def test_fail_value(self):
        """PolicyResult.FAIL has correct value."""
        assert PolicyResult.FAIL.value == "fail"

    def test_warn_value(self):
        """PolicyResult.WARN has correct value."""
        assert PolicyResult.WARN.value == "warn"

    def test_skip_value(self):
        """PolicyResult.SKIP has correct value."""
        assert PolicyResult.SKIP.value == "skip"


class TestEntityRef:
    """Tests for the EntityRef dataclass."""

    def test_basic_creation(self):
        """EntityRef can be created with required fields."""
        ref = EntityRef(namespace="crm", type="account", id="ACC-123")
        assert ref.namespace == "crm"
        assert ref.type == "account"
        assert ref.id == "ACC-123"

    def test_default_aliases_empty(self):
        """EntityRef defaults to empty aliases list."""
        ref = EntityRef(namespace="crm", type="account", id="ACC-123")
        assert ref.aliases == []

    def test_custom_aliases(self):
        """EntityRef accepts custom aliases."""
        ref = EntityRef(
            namespace="crm",
            type="account",
            id="ACC-123",
            aliases=["acme", "acme-corp"]
        )
        assert ref.aliases == ["acme", "acme-corp"]

    def test_to_dict(self):
        """EntityRef.to_dict returns correct structure."""
        ref = EntityRef(
            namespace="crm",
            type="account",
            id="ACC-123",
            aliases=["acme"]
        )
        result = ref.to_dict()

        assert result == {
            "namespace": "crm",
            "type": "account",
            "id": "ACC-123",
            "aliases": ["acme"],
        }


class TestActor:
    """Tests for the Actor dataclass."""

    def test_basic_creation(self):
        """Actor can be created with required fields."""
        actor = Actor(type=ActorType.AGENT, id="my-agent")
        assert actor.type == ActorType.AGENT
        assert actor.id == "my-agent"

    def test_default_name_is_none(self):
        """Actor defaults to no name."""
        actor = Actor(type=ActorType.AGENT, id="my-agent")
        assert actor.name is None

    def test_custom_name(self):
        """Actor accepts custom name."""
        actor = Actor(type=ActorType.HUMAN, id="user@test.com", name="John Doe")
        assert actor.name == "John Doe"

    def test_to_dict(self):
        """Actor.to_dict returns correct structure."""
        actor = Actor(type=ActorType.AGENT, id="my-agent", name="Test Agent")
        result = actor.to_dict()

        assert result == {
            "type": "agent",
            "id": "my-agent",
            "name": "Test Agent",
        }

    def test_to_dict_with_none_name(self):
        """Actor.to_dict handles None name."""
        actor = Actor(type=ActorType.AGENT, id="my-agent")
        result = actor.to_dict()

        assert result["name"] is None


class TestEvidence:
    """Tests for the Evidence dataclass."""

    def test_basic_creation(self):
        """Evidence can be created with required fields."""
        now = datetime.utcnow()
        evidence = Evidence(source="crm.get_account", retrieved_at=now)
        assert evidence.source == "crm.get_account"
        assert evidence.retrieved_at == now

    def test_auto_generates_evidence_id(self):
        """Evidence auto-generates evidence_id."""
        evidence = Evidence(source="test", retrieved_at=datetime.utcnow())
        assert evidence.evidence_id is not None
        uuid.UUID(evidence.evidence_id)

    def test_snapshot_hash_auto_generated(self):
        """Evidence auto-generates snapshot_hash from snapshot."""
        evidence = Evidence(
            source="test",
            retrieved_at=datetime.utcnow(),
            snapshot={"key": "value"}
        )
        assert evidence.snapshot_hash is not None
        assert len(evidence.snapshot_hash) == 16

    def test_snapshot_hash_not_overwritten(self):
        """Evidence doesn't overwrite provided snapshot_hash."""
        evidence = Evidence(
            source="test",
            retrieved_at=datetime.utcnow(),
            snapshot={"key": "value"},
            snapshot_hash="custom_hash_123"
        )
        assert evidence.snapshot_hash == "custom_hash_123"

    def test_to_dict(self):
        """Evidence.to_dict returns correct structure."""
        now = datetime.utcnow()
        entity_ref = EntityRef(namespace="crm", type="account", id="123")
        evidence = Evidence(
            source="crm.get_account",
            retrieved_at=now,
            entity_ref=entity_ref,
            snapshot={"name": "Acme"},
            tool_name="get_account",
            tool_args={"id": "123"},
        )
        result = evidence.to_dict()

        assert result["source"] == "crm.get_account"
        assert result["retrieved_at"] == now.isoformat()
        assert result["entity_ref"] == entity_ref.to_dict()
        assert result["snapshot"] == {"name": "Acme"}
        assert result["tool_name"] == "get_account"
        assert result["tool_args"] == {"id": "123"}

    def test_to_dict_without_entity_ref(self):
        """Evidence.to_dict handles None entity_ref."""
        evidence = Evidence(
            source="test",
            retrieved_at=datetime.utcnow(),
        )
        result = evidence.to_dict()

        assert result["entity_ref"] is None


class TestPolicyEval:
    """Tests for the PolicyEval dataclass."""

    def test_basic_creation(self):
        """PolicyEval can be created with required fields."""
        policy_eval = PolicyEval(
            policy_id="credit_policy",
            version="1.0",
            result=PolicyResult.PASS,
        )
        assert policy_eval.policy_id == "credit_policy"
        assert policy_eval.version == "1.0"
        assert policy_eval.result == PolicyResult.PASS

    def test_optional_fields_default_none(self):
        """PolicyEval optional fields default to None."""
        policy_eval = PolicyEval(
            policy_id="test",
            version="1.0",
            result=PolicyResult.PASS,
        )
        assert policy_eval.inputs_hash is None
        assert policy_eval.message is None

    def test_to_dict(self):
        """PolicyEval.to_dict returns correct structure."""
        policy_eval = PolicyEval(
            policy_id="credit_policy",
            version="1.0",
            result=PolicyResult.FAIL,
            inputs_hash="abc123",
            message="Exceeded limit",
        )
        result = policy_eval.to_dict()

        assert result == {
            "policy_id": "credit_policy",
            "version": "1.0",
            "result": "fail",
            "inputs_hash": "abc123",
            "message": "Exceeded limit",
        }


class TestApproval:
    """Tests for the Approval dataclass."""

    def test_basic_creation(self):
        """Approval can be created with required fields."""
        approver = Actor(type=ActorType.HUMAN, id="manager@test.com")
        now = datetime.utcnow()
        approval = Approval(
            approver=approver,
            granted=True,
            granted_at=now,
        )
        assert approval.approver == approver
        assert approval.granted is True
        assert approval.granted_at == now

    def test_auto_generates_approval_id(self):
        """Approval auto-generates approval_id."""
        approval = Approval(
            approver=Actor(type=ActorType.HUMAN, id="test"),
            granted=True,
            granted_at=datetime.utcnow(),
        )
        assert approval.approval_id is not None
        uuid.UUID(approval.approval_id)

    def test_optional_reason(self):
        """Approval accepts optional reason."""
        approval = Approval(
            approver=Actor(type=ActorType.HUMAN, id="test"),
            granted=True,
            granted_at=datetime.utcnow(),
            reason="Customer impact justifies credit",
        )
        assert approval.reason == "Customer impact justifies credit"

    def test_to_dict(self):
        """Approval.to_dict returns correct structure."""
        approver = Actor(type=ActorType.HUMAN, id="manager@test.com", name="Manager")
        now = datetime.utcnow()
        approval = Approval(
            approver=approver,
            granted=False,
            granted_at=now,
            reason="Insufficient justification",
        )
        result = approval.to_dict()

        assert result["approver"] == approver.to_dict()
        assert result["granted"] is False
        assert result["granted_at"] == now.isoformat()
        assert result["reason"] == "Insufficient justification"


class TestAction:
    """Tests for the Action dataclass."""

    def test_basic_creation(self):
        """Action can be created with required fields."""
        now = datetime.utcnow()
        action = Action(tool="send_email", committed_at=now)
        assert action.tool == "send_email"
        assert action.committed_at == now

    def test_auto_generates_action_id(self):
        """Action auto-generates action_id."""
        action = Action(tool="test", committed_at=datetime.utcnow())
        assert action.action_id is not None
        uuid.UUID(action.action_id)

    def test_default_success_is_true(self):
        """Action defaults to success=True."""
        action = Action(tool="test", committed_at=datetime.utcnow())
        assert action.success is True

    def test_optional_fields(self):
        """Action accepts optional fields."""
        entity_ref = EntityRef(namespace="billing", type="credit", id="CR-123")
        now = datetime.utcnow()
        action = Action(
            tool="create_credit",
            committed_at=now,
            operation="create",
            target_entity=entity_ref,
            params={"amount": 1000},
            result={"credit_id": "CR-123"},
            success=True,
        )
        assert action.operation == "create"
        assert action.target_entity == entity_ref
        assert action.params == {"amount": 1000}
        assert action.result == {"credit_id": "CR-123"}

    def test_to_dict(self):
        """Action.to_dict returns correct structure."""
        entity_ref = EntityRef(namespace="billing", type="credit", id="CR-123")
        now = datetime.utcnow()
        action = Action(
            tool="create_credit",
            committed_at=now,
            operation="create",
            target_entity=entity_ref,
            params={"amount": 1000},
            result={"credit_id": "CR-123"},
            success=True,
        )
        result = action.to_dict()

        assert result["tool"] == "create_credit"
        assert result["committed_at"] == now.isoformat()
        assert result["operation"] == "create"
        assert result["target_entity"] == entity_ref.to_dict()
        assert result["params"] == {"amount": 1000}
        assert result["result"] == {"credit_id": "CR-123"}
        assert result["success"] is True

    def test_to_dict_without_target_entity(self):
        """Action.to_dict handles None target_entity."""
        action = Action(tool="test", committed_at=datetime.utcnow())
        result = action.to_dict()

        assert result["target_entity"] is None


class TestDecisionRecord:
    """Tests for the DecisionRecord dataclass."""

    def test_basic_creation(self):
        """DecisionRecord can be created with required fields."""
        record = DecisionRecord(run_id="run_123", outcome=Outcome.COMMITTED)
        assert record.run_id == "run_123"
        assert record.outcome == Outcome.COMMITTED

    def test_auto_generates_decision_id(self):
        """DecisionRecord auto-generates decision_id."""
        record = DecisionRecord(run_id="run_123", outcome=Outcome.COMMITTED)
        assert record.decision_id is not None
        uuid.UUID(record.decision_id)

    def test_auto_generates_timestamp(self):
        """DecisionRecord auto-generates timestamp."""
        before = datetime.utcnow()
        record = DecisionRecord(run_id="run_123", outcome=Outcome.COMMITTED)
        after = datetime.utcnow()

        assert before <= record.timestamp <= after

    def test_default_lists_empty(self):
        """DecisionRecord defaults to empty lists."""
        record = DecisionRecord(run_id="run_123", outcome=Outcome.COMMITTED)
        assert record.subject_entities == []
        assert record.evidence == []
        assert record.policies == []
        assert record.approvals == []
        assert record.actions == []
        assert record.precedent_refs == []

    def test_default_metadata_empty(self):
        """DecisionRecord defaults to empty metadata."""
        record = DecisionRecord(run_id="run_123", outcome=Outcome.COMMITTED)
        assert record.metadata == {}

    def test_full_creation(self):
        """DecisionRecord can be created with all fields."""
        actor = Actor(type=ActorType.AGENT, id="test-agent")
        entity = EntityRef(namespace="crm", type="account", id="123")
        evidence = Evidence(source="test", retrieved_at=datetime.utcnow())
        policy = PolicyEval(policy_id="test", version="1.0", result=PolicyResult.PASS)
        approval = Approval(
            approver=Actor(type=ActorType.HUMAN, id="approver"),
            granted=True,
            granted_at=datetime.utcnow(),
        )
        action = Action(tool="test", committed_at=datetime.utcnow())

        record = DecisionRecord(
            run_id="run_123",
            outcome=Outcome.COMMITTED,
            trace_id="trace_456",
            span_id="span_789",
            actor=actor,
            subject_entities=[entity],
            evidence=[evidence],
            policies=[policy],
            approvals=[approval],
            actions=[action],
            outcome_reason="All checks passed",
            precedent_refs=["dec_prev_1"],
            metadata={"workflow": "test"},
        )

        assert record.trace_id == "trace_456"
        assert record.span_id == "span_789"
        assert record.actor == actor
        assert len(record.subject_entities) == 1
        assert len(record.evidence) == 1
        assert len(record.policies) == 1
        assert len(record.approvals) == 1
        assert len(record.actions) == 1
        assert record.outcome_reason == "All checks passed"
        assert record.precedent_refs == ["dec_prev_1"]
        assert record.metadata == {"workflow": "test"}

    def test_to_dict(self):
        """DecisionRecord.to_dict returns correct structure."""
        actor = Actor(type=ActorType.AGENT, id="test-agent")
        now = datetime.utcnow()

        record = DecisionRecord(
            run_id="run_123",
            outcome=Outcome.COMMITTED,
            timestamp=now,
            actor=actor,
            outcome_reason="Success",
            metadata={"key": "value"},
        )
        result = record.to_dict()

        assert result["run_id"] == "run_123"
        assert result["outcome"] == "committed"
        assert result["timestamp"] == now.isoformat()
        assert result["actor"] == actor.to_dict()
        assert result["outcome_reason"] == "Success"
        assert result["metadata"] == {"key": "value"}
        assert result["evidence"] == []
        assert result["actions"] == []
        assert result["policies"] == []
        assert result["approvals"] == []

    def test_to_dict_without_actor(self):
        """DecisionRecord.to_dict handles None actor."""
        record = DecisionRecord(run_id="run_123", outcome=Outcome.COMMITTED)
        result = record.to_dict()

        assert result["actor"] is None

    def test_to_dict_with_nested_data(self):
        """DecisionRecord.to_dict correctly serializes nested data."""
        now = datetime.utcnow()
        evidence = Evidence(
            source="test",
            retrieved_at=now,
            snapshot={"nested": {"key": "value"}},
        )
        action = Action(
            tool="test_tool",
            committed_at=now,
            params={"arg": 1},
            result={"status": "ok"},
        )
        policy = PolicyEval(
            policy_id="policy1",
            version="1.0",
            result=PolicyResult.PASS,
            message="OK",
        )

        record = DecisionRecord(
            run_id="run_123",
            outcome=Outcome.COMMITTED,
            evidence=[evidence],
            actions=[action],
            policies=[policy],
        )
        result = record.to_dict()

        # Verify nested serialization
        assert len(result["evidence"]) == 1
        assert result["evidence"][0]["source"] == "test"
        assert result["evidence"][0]["snapshot"]["nested"]["key"] == "value"

        assert len(result["actions"]) == 1
        assert result["actions"][0]["tool"] == "test_tool"
        assert result["actions"][0]["params"]["arg"] == 1

        assert len(result["policies"]) == 1
        assert result["policies"][0]["policy_id"] == "policy1"
        assert result["policies"][0]["result"] == "pass"

    def test_to_dict_is_json_serializable(self):
        """DecisionRecord.to_dict output is JSON serializable."""
        actor = Actor(type=ActorType.AGENT, id="test-agent")
        evidence = Evidence(source="test", retrieved_at=datetime.utcnow())
        action = Action(tool="test", committed_at=datetime.utcnow())

        record = DecisionRecord(
            run_id="run_123",
            outcome=Outcome.COMMITTED,
            actor=actor,
            evidence=[evidence],
            actions=[action],
        )

        # Should not raise
        json_str = json.dumps(record.to_dict())
        parsed = json.loads(json_str)

        assert parsed["run_id"] == "run_123"
        assert parsed["outcome"] == "committed"


class TestListImmutability:
    """Tests verifying dataclass default list behavior."""

    def test_decision_record_lists_not_shared(self):
        """Each DecisionRecord has its own lists."""
        record1 = DecisionRecord(run_id="run_1", outcome=Outcome.COMMITTED)
        record2 = DecisionRecord(run_id="run_2", outcome=Outcome.COMMITTED)

        action = Action(tool="test", committed_at=datetime.utcnow())
        record1.actions.append(action)

        assert len(record1.actions) == 1
        assert len(record2.actions) == 0

    def test_entity_ref_aliases_not_shared(self):
        """Each EntityRef has its own aliases list."""
        ref1 = EntityRef(namespace="ns", type="type", id="1")
        ref2 = EntityRef(namespace="ns", type="type", id="2")

        ref1.aliases.append("alias1")

        assert len(ref1.aliases) == 1
        assert len(ref2.aliases) == 0
