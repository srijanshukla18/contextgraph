"""Mock tools simulating real integrations.

These tools simulate:
- Zendesk (support tickets)
- Salesforce (CRM accounts)
- PagerDuty (incidents)
- Stripe/Zuora (billing)
- Slack (approvals)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import random
import time


# Mock data stores
TICKETS = {
    "SUP-4312": {
        "id": "SUP-4312",
        "account_id": "ACC-ACME-001",
        "subject": "Request for service credit due to outages",
        "description": "We experienced multiple severe outages this month affecting our production systems. "
                       "Our team had to work overtime to mitigate impact. We are requesting a 20% service credit.",
        "requested_credit_pct": 0.20,
        "status": "open",
        "priority": "high",
        "created_at": (datetime.now() - timedelta(hours=2)).isoformat(),
        "requester": "ops-lead@acme.com",
    },
    "SUP-4400": {
        "id": "SUP-4400",
        "account_id": "ACC-STARTUP-002",
        "subject": "Billing dispute - overcharged",
        "description": "We were charged for 50 seats but only have 30 active users. Requesting 8% credit.",
        "requested_credit_pct": 0.08,
        "status": "open",
        "priority": "medium",
        "created_at": (datetime.now() - timedelta(hours=5)).isoformat(),
        "requester": "billing@startup.io",
    },
}

ACCOUNTS = {
    "ACC-ACME-001": {
        "id": "ACC-ACME-001",
        "name": "Acme Corporation",
        "tier": "enterprise",
        "arr": 500000,
        "monthly_invoice": 41667,
        "churn_risk": "high",
        "health_score": 45,
        "csm": "sarah@ourcompany.com",
        "renewal_date": (datetime.now() + timedelta(days=60)).isoformat(),
    },
    "ACC-STARTUP-002": {
        "id": "ACC-STARTUP-002",
        "name": "StartupIO",
        "tier": "growth",
        "arr": 24000,
        "monthly_invoice": 2000,
        "churn_risk": "low",
        "health_score": 82,
        "csm": "mike@ourcompany.com",
        "renewal_date": (datetime.now() + timedelta(days=180)).isoformat(),
    },
}

INCIDENTS = {
    "ACC-ACME-001": [
        {"id": "INC-901", "severity": "SEV-1", "title": "API Gateway Complete Outage", "duration_mins": 45, "date": (datetime.now() - timedelta(days=5)).isoformat()},
        {"id": "INC-887", "severity": "SEV-1", "title": "Database Failover Failure", "duration_mins": 90, "date": (datetime.now() - timedelta(days=12)).isoformat()},
        {"id": "INC-892", "severity": "SEV-1", "title": "Authentication Service Down", "duration_mins": 30, "date": (datetime.now() - timedelta(days=18)).isoformat()},
        {"id": "INC-856", "severity": "SEV-2", "title": "Elevated Latency", "duration_mins": 120, "date": (datetime.now() - timedelta(days=8)).isoformat()},
        {"id": "INC-861", "severity": "SEV-2", "title": "Partial Feature Degradation", "duration_mins": 60, "date": (datetime.now() - timedelta(days=22)).isoformat()},
    ],
    "ACC-STARTUP-002": [
        {"id": "INC-899", "severity": "SEV-2", "title": "Slow Dashboard Loading", "duration_mins": 30, "date": (datetime.now() - timedelta(days=10)).isoformat()},
    ],
}

CREDITS_ISSUED: list[dict] = []
APPROVAL_QUEUE: list[dict] = []


@dataclass
class ToolResult:
    success: bool
    data: dict
    error: Optional[str] = None


class SupportTools:
    """Zendesk-like support ticket tools."""

    @staticmethod
    def get_ticket(ticket_id: str) -> ToolResult:
        """Retrieve support ticket details."""
        time.sleep(0.1)  # Simulate API latency
        ticket = TICKETS.get(ticket_id)
        if not ticket:
            return ToolResult(success=False, data={}, error=f"Ticket {ticket_id} not found")
        return ToolResult(success=True, data=ticket.copy())

    @staticmethod
    def post_internal_note(ticket_id: str, note: str) -> ToolResult:
        """Post an internal note to the ticket."""
        time.sleep(0.1)
        if ticket_id not in TICKETS:
            return ToolResult(success=False, data={}, error=f"Ticket {ticket_id} not found")
        note_id = f"NOTE-{random.randint(1000, 9999)}"
        return ToolResult(
            success=True,
            data={"note_id": note_id, "ticket_id": ticket_id, "posted_at": datetime.now().isoformat()}
        )

    @staticmethod
    def update_ticket_status(ticket_id: str, status: str, resolution: str) -> ToolResult:
        """Update ticket status and resolution."""
        time.sleep(0.1)
        if ticket_id not in TICKETS:
            return ToolResult(success=False, data={}, error=f"Ticket {ticket_id} not found")
        TICKETS[ticket_id]["status"] = status
        return ToolResult(
            success=True,
            data={"ticket_id": ticket_id, "status": status, "resolution": resolution}
        )


class CRMTools:
    """Salesforce-like CRM tools."""

    @staticmethod
    def get_account(account_id: str) -> ToolResult:
        """Retrieve account details including tier, ARR, and churn risk."""
        time.sleep(0.1)
        account = ACCOUNTS.get(account_id)
        if not account:
            return ToolResult(success=False, data={}, error=f"Account {account_id} not found")
        return ToolResult(success=True, data=account.copy())


class IncidentTools:
    """PagerDuty-like incident tools."""

    @staticmethod
    def get_recent(account_id: str, days: int = 30) -> ToolResult:
        """Get recent incidents for an account."""
        time.sleep(0.1)
        incidents = INCIDENTS.get(account_id, [])
        cutoff = datetime.now() - timedelta(days=days)

        recent = [inc for inc in incidents if datetime.fromisoformat(inc["date"]) > cutoff]
        sev1_count = sum(1 for inc in recent if inc["severity"] == "SEV-1")
        sev2_count = sum(1 for inc in recent if inc["severity"] == "SEV-2")
        total_downtime = sum(inc["duration_mins"] for inc in recent)

        return ToolResult(
            success=True,
            data={
                "account_id": account_id,
                "period_days": days,
                "incidents": recent,
                "sev1_count": sev1_count,
                "sev2_count": sev2_count,
                "total_downtime_mins": total_downtime,
            }
        )


class BillingTools:
    """Stripe/Zuora-like billing tools."""

    @staticmethod
    def create_service_credit(account_id: str, amount: float, credit_pct: float, memo: str) -> ToolResult:
        """Issue a service credit to an account. THIS IS THE COMMIT ACTION."""
        time.sleep(0.2)  # Slightly longer for "important" action

        account = ACCOUNTS.get(account_id)
        if not account:
            return ToolResult(success=False, data={}, error=f"Account {account_id} not found")

        credit_id = f"CREDIT-{random.randint(10000, 99999)}"
        credit = {
            "credit_id": credit_id,
            "account_id": account_id,
            "amount": amount,
            "credit_pct": credit_pct,
            "memo": memo,
            "issued_at": datetime.now().isoformat(),
            "applies_to_invoice": f"INV-{datetime.now().strftime('%Y%m')}",
        }
        CREDITS_ISSUED.append(credit)

        return ToolResult(success=True, data=credit)

    @staticmethod
    def get_credits(account_id: str) -> ToolResult:
        """Get all credits for an account."""
        credits = [c for c in CREDITS_ISSUED if c["account_id"] == account_id]
        return ToolResult(success=True, data={"credits": credits})


class ApprovalTools:
    """Slack-like approval workflow tools."""

    @staticmethod
    def request_finance_approval(
        ticket_id: str,
        account_id: str,
        credit_pct: float,
        credit_amount: float,
        summary: str,
        exception_reason: str,
    ) -> ToolResult:
        """Request approval from Finance for an exception. Simulates Slack approval flow."""
        time.sleep(0.3)  # Simulate human thinking time

        # Auto-approve for demo (in reality this would block until human responds)
        # Approval logic: approve if exception_reason is compelling
        approved = "SEV-1" in exception_reason or "churn" in exception_reason.lower()

        approver = "finance-lead@ourcompany.com" if approved else "finance-review@ourcompany.com"

        result = {
            "request_id": f"APR-{random.randint(1000, 9999)}",
            "ticket_id": ticket_id,
            "account_id": account_id,
            "credit_pct": credit_pct,
            "credit_amount": credit_amount,
            "approved": approved,
            "approver": approver,
            "approver_role": "Finance Lead",
            "decided_at": datetime.now().isoformat(),
            "reason": "Exception justified by service impact" if approved else "Insufficient justification",
        }
        APPROVAL_QUEUE.append(result)

        return ToolResult(success=True, data=result)
