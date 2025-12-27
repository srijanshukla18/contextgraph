"""Exception Desk Agent - Service Credit Approval Workflow.

This agent processes service credit requests by:
1. Gathering evidence from multiple systems
2. Evaluating against policy
3. Requesting approval if needed
4. Issuing the credit if approved
5. Recording a complete DecisionRecord
"""

from datetime import datetime
from typing import Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import uuid
import sys
import os

# Add paths for imports
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "sdk", "python"))

from demo.tools import SupportTools, CRMTools, IncidentTools, BillingTools, ApprovalTools
from demo.policy import ServiceCreditPolicy, PolicyResult as DemoPolicyResult


# Inline models to avoid import issues
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
    message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "result": self.result.value,
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
    params: Optional[dict[str, Any]] = None
    result: Optional[dict[str, Any]] = None
    success: bool = True

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "tool": self.tool,
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
    actor: Optional[Actor] = None
    evidence: list[Evidence] = field(default_factory=list)
    policies: list[PolicyEval] = field(default_factory=list)
    approvals: list[Approval] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    outcome_reason: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor.to_dict() if self.actor else None,
            "evidence": [e.to_dict() for e in self.evidence],
            "policies": [p.to_dict() for p in self.policies],
            "approvals": [a.to_dict() for a in self.approvals],
            "actions": [a.to_dict() for a in self.actions],
            "outcome": self.outcome.value,
            "outcome_reason": self.outcome_reason,
            "metadata": self.metadata,
        }


class ExceptionDeskAgent:
    """Agent that processes service credit exception requests."""

    def __init__(self):
        self.support = SupportTools()
        self.crm = CRMTools()
        self.incidents = IncidentTools()
        self.billing = BillingTools()
        self.approvals = ApprovalTools()
        self.policy = ServiceCreditPolicy()

        # Accumulate for DecisionRecord
        self._evidence: list[Evidence] = []
        self._policies: list[PolicyEval] = []
        self._approvals: list[Approval] = []
        self._actions: list[Action] = []

    def process_ticket(self, ticket_id: str) -> dict:
        """Process a service credit request ticket end-to-end."""
        run_id = f"run_{ticket_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        start_time = datetime.utcnow()

        print(f"\n{'='*60}")
        print(f"EXCEPTION DESK AGENT - Processing {ticket_id}")
        print(f"{'='*60}")

        # Reset accumulators
        self._evidence = []
        self._policies = []
        self._approvals = []
        self._actions = []

        # Step 1: Get ticket details
        print("\n[1] Gathering evidence...")
        ticket_result = self.support.get_ticket(ticket_id)
        if not ticket_result.success:
            return self._finalize_decision(run_id, start_time, Outcome.DENIED, ticket_result.error)

        ticket = ticket_result.data
        self._add_evidence("support.get_ticket", {"ticket_id": ticket_id}, ticket)
        print(f"    Ticket: {ticket['subject']}")
        print(f"    Requested: {ticket['requested_credit_pct']:.0%} credit")

        account_id = ticket["account_id"]

        # Step 2: Get account details
        account_result = self.crm.get_account(account_id)
        if not account_result.success:
            return self._finalize_decision(run_id, start_time, Outcome.DENIED, account_result.error)

        account = account_result.data
        self._add_evidence("crm.get_account", {"account_id": account_id}, account)
        print(f"    Account: {account['name']} ({account['tier']}, ARR ${account['arr']:,})")
        print(f"    Churn Risk: {account['churn_risk']}, Health: {account['health_score']}")

        # Step 3: Get incident history
        incidents_result = self.incidents.get_recent(account_id, days=30)
        incidents = incidents_result.data
        self._add_evidence("incidents.get_recent", {"account_id": account_id, "days": 30}, incidents)
        print(f"    Incidents (30d): {incidents['sev1_count']} SEV-1, {incidents['sev2_count']} SEV-2")
        print(f"    Total downtime: {incidents['total_downtime_mins']} minutes")

        # Step 4: Evaluate policy
        print("\n[2] Evaluating policy...")
        policy_eval = self.policy.evaluate(
            requested_pct=ticket["requested_credit_pct"],
            sev1_count=incidents["sev1_count"],
            sev2_count=incidents["sev2_count"],
            churn_risk=account["churn_risk"],
            account_tier=account["tier"],
        )

        self._add_policy_eval(policy_eval)
        print(f"    Policy: {policy_eval.policy_id} v{policy_eval.version}")
        print(f"    Result: {policy_eval.result.value}")
        if policy_eval.exception_route:
            print(f"    Exception Route: {policy_eval.exception_route}")
        if policy_eval.approval_reason:
            print(f"    Reason: {policy_eval.approval_reason}")

        # Step 5: Handle based on policy result
        if policy_eval.result == DemoPolicyResult.DENIED:
            print("\n[3] Request DENIED by policy")
            self.support.update_ticket_status(ticket_id, "closed", "Denied - policy violation")
            return self._finalize_decision(run_id, start_time, Outcome.DENIED, policy_eval.approval_reason)

        credit_amount = account["monthly_invoice"] * ticket["requested_credit_pct"]

        if policy_eval.requires_approval:
            # Step 5a: Request approval
            print("\n[3] Requesting Finance approval...")
            approval_result = self.approvals.request_finance_approval(
                ticket_id=ticket_id,
                account_id=account_id,
                credit_pct=ticket["requested_credit_pct"],
                credit_amount=credit_amount,
                summary=f"Service credit request for {account['name']}",
                exception_reason=policy_eval.approval_reason,
            )

            self._add_approval(approval_result.data)
            print(f"    Approver: {approval_result.data['approver']}")
            print(f"    Decision: {'APPROVED' if approval_result.data['approved'] else 'DENIED'}")
            print(f"    Reason: {approval_result.data['reason']}")

            if not approval_result.data["approved"]:
                self.support.update_ticket_status(ticket_id, "closed", "Denied - approval rejected")
                return self._finalize_decision(run_id, start_time, Outcome.DENIED, "Approval denied")

        # Step 6: Issue the credit (COMMIT ACTION)
        print("\n[4] Issuing service credit...")
        credit_result = self.billing.create_service_credit(
            account_id=account_id,
            amount=credit_amount,
            credit_pct=ticket["requested_credit_pct"],
            memo=f"Service credit for ticket {ticket_id}. {policy_eval.exception_route or 'Standard approval'}.",
        )

        if not credit_result.success:
            return self._finalize_decision(run_id, start_time, Outcome.DENIED, credit_result.error)

        self._add_action("billing.create_service_credit", {
            "account_id": account_id,
            "amount": credit_amount,
            "credit_pct": ticket["requested_credit_pct"],
        }, credit_result.data, success=True)

        print(f"    Credit ID: {credit_result.data['credit_id']}")
        print(f"    Amount: ${credit_amount:,.2f} ({ticket['requested_credit_pct']:.0%})")

        # Step 7: Update ticket
        self.support.update_ticket_status(ticket_id, "resolved", f"Credit issued: {credit_result.data['credit_id']}")
        self.support.post_internal_note(
            ticket_id,
            f"Service credit of ${credit_amount:,.2f} issued via exception route: {policy_eval.exception_route}"
        )

        print("\n[5] Decision COMMITTED")
        return self._finalize_decision(
            run_id, start_time, Outcome.COMMITTED,
            f"Credit issued via {policy_eval.exception_route or 'standard'} route"
        )

    def _add_evidence(self, tool: str, args: dict, data: dict):
        self._evidence.append(Evidence(
            source=tool,
            retrieved_at=datetime.utcnow(),
            tool_name=tool,
            tool_args=args,
            snapshot=data,
        ))

    def _add_policy_eval(self, policy_eval):
        result_map = {
            DemoPolicyResult.APPROVED: PolicyResult.PASS,
            DemoPolicyResult.EXCEPTION_REQUIRED: PolicyResult.WARN,
            DemoPolicyResult.DENIED: PolicyResult.FAIL,
        }
        self._policies.append(PolicyEval(
            policy_id=policy_eval.policy_id,
            version=policy_eval.version,
            result=result_map[policy_eval.result],
            message=f"Requested {policy_eval.requested_pct:.0%}, cap {policy_eval.cap_pct:.0%}. "
                    f"{policy_eval.approval_reason or 'Within limits'}",
        ))

    def _add_approval(self, approval_data: dict):
        self._approvals.append(Approval(
            approver=Actor(
                type=ActorType.HUMAN,
                id=approval_data["approver"],
                name=approval_data["approver_role"],
            ),
            granted=approval_data["approved"],
            granted_at=datetime.fromisoformat(approval_data["decided_at"]),
            reason=approval_data["reason"],
        ))

    def _add_action(self, tool: str, params: dict, result: dict, success: bool):
        self._actions.append(Action(
            tool=tool,
            committed_at=datetime.utcnow(),
            params=params,
            result=result,
            success=success,
        ))

    def _finalize_decision(self, run_id: str, start_time: datetime, outcome: Outcome, reason: str) -> dict:
        """Create the DecisionRecord."""
        record = DecisionRecord(
            run_id=run_id,
            timestamp=start_time,
            outcome=outcome,
            outcome_reason=reason,
            actor=Actor(type=ActorType.AGENT, id="exception-desk-agent", name="Exception Desk Agent"),
            evidence=self._evidence,
            policies=self._policies,
            approvals=self._approvals,
            actions=self._actions,
            metadata={"workflow": "service_credit", "version": "1.0"},
        )

        print(f"\n{'='*60}")
        print(f"DecisionRecord: {record.decision_id}")
        print(f"Outcome: {outcome.value}")
        print(f"{'='*60}")

        return {
            "decision_id": record.decision_id,
            "run_id": run_id,
            "outcome": outcome.value,
            "reason": reason,
            "record": record.to_dict(),
        }


def run_demo(ticket_id: str = "SUP-4312"):
    """Run the demo with a specific ticket."""
    agent = ExceptionDeskAgent()
    result = agent.process_ticket(ticket_id)
    return result


if __name__ == "__main__":
    ticket = sys.argv[1] if len(sys.argv) > 1 else "SUP-4312"
    run_demo(ticket)
