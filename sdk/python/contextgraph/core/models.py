"""Core data models for ContextGraph."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
from enum import Enum
import hashlib
import json
import uuid


def generate_id() -> str:
    return str(uuid.uuid4())


def generate_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:16]


class ActorType(str, Enum):
    AGENT = "agent"
    HUMAN = "human"
    SYSTEM = "system"


class Outcome(str, Enum):
    COMMITTED = "committed"
    DENIED = "denied"
    ESCALATED = "escalated"
    PENDING = "pending"


class PolicyResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


@dataclass
class EntityRef:
    namespace: str
    type: str
    id: str
    aliases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"namespace": self.namespace, "type": self.type, "id": self.id, "aliases": self.aliases}


@dataclass
class Actor:
    type: ActorType
    id: str
    name: Optional[str] = None

    def to_dict(self) -> dict:
        return {"type": self.type.value, "id": self.id, "name": self.name}


@dataclass
class Evidence:
    source: str
    retrieved_at: datetime
    evidence_id: str = field(default_factory=generate_id)
    entity_ref: Optional[EntityRef] = None
    snapshot: Optional[dict[str, Any]] = None
    snapshot_hash: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None

    def __post_init__(self):
        if self.snapshot and not self.snapshot_hash:
            self.snapshot_hash = generate_hash(self.snapshot)

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "source": self.source,
            "entity_ref": self.entity_ref.to_dict() if self.entity_ref else None,
            "snapshot": self.snapshot,
            "snapshot_hash": self.snapshot_hash,
            "retrieved_at": self.retrieved_at.isoformat(),
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
        }


@dataclass
class PolicyEval:
    policy_id: str
    version: str
    result: PolicyResult
    inputs_hash: Optional[str] = None
    message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "result": self.result.value,
            "inputs_hash": self.inputs_hash,
            "message": self.message,
        }


@dataclass
class Approval:
    approver: Actor
    granted: bool
    granted_at: datetime
    approval_id: str = field(default_factory=generate_id)
    reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "approval_id": self.approval_id,
            "approver": self.approver.to_dict(),
            "granted": self.granted,
            "granted_at": self.granted_at.isoformat(),
            "reason": self.reason,
        }


@dataclass
class Action:
    tool: str
    committed_at: datetime
    action_id: str = field(default_factory=generate_id)
    operation: Optional[str] = None
    target_entity: Optional[EntityRef] = None
    params: Optional[dict[str, Any]] = None
    result: Optional[dict[str, Any]] = None
    success: bool = True

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "tool": self.tool,
            "operation": self.operation,
            "target_entity": self.target_entity.to_dict() if self.target_entity else None,
            "params": self.params,
            "result": self.result,
            "committed_at": self.committed_at.isoformat(),
            "success": self.success,
        }


@dataclass
class DecisionRecord:
    run_id: str
    outcome: Outcome
    decision_id: str = field(default_factory=generate_id)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    actor: Optional[Actor] = None
    subject_entities: list[EntityRef] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    policies: list[PolicyEval] = field(default_factory=list)
    approvals: list[Approval] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    outcome_reason: Optional[str] = None
    precedent_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor.to_dict() if self.actor else None,
            "subject_entities": [e.to_dict() for e in self.subject_entities],
            "evidence": [e.to_dict() for e in self.evidence],
            "policies": [p.to_dict() for p in self.policies],
            "approvals": [a.to_dict() for a in self.approvals],
            "actions": [a.to_dict() for a in self.actions],
            "outcome": self.outcome.value,
            "outcome_reason": self.outcome_reason,
            "precedent_refs": self.precedent_refs,
            "metadata": self.metadata,
        }
