"""Tests for the demo tools module."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from demo.tools import (
    ToolResult,
    SupportTools,
    CRMTools,
    IncidentTools,
    BillingTools,
    ApprovalTools,
    TICKETS,
    ACCOUNTS,
    INCIDENTS,
    CREDITS_ISSUED,
    APPROVAL_QUEUE,
)


class TestToolResult:
    """Tests for the ToolResult dataclass."""

    def test_successful_result(self):
        """ToolResult can represent success."""
        result = ToolResult(success=True, data={"key": "value"})
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None

    def test_failed_result(self):
        """ToolResult can represent failure."""
        result = ToolResult(success=False, data={}, error="Not found")
        assert result.success is False
        assert result.data == {}
        assert result.error == "Not found"


class TestSupportTools:
    """Tests for SupportTools class."""

    def test_get_ticket_success(self):
        """get_ticket returns ticket data for valid ID."""
        with patch("time.sleep"):  # Skip sleep for faster tests
            result = SupportTools.get_ticket("SUP-4312")

        assert result.success is True
        assert result.data["id"] == "SUP-4312"
        assert result.data["account_id"] == "ACC-ACME-001"
        assert result.data["requested_credit_pct"] == 0.20

    def test_get_ticket_not_found(self):
        """get_ticket returns error for invalid ID."""
        with patch("time.sleep"):
            result = SupportTools.get_ticket("INVALID-ID")

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_get_ticket_returns_copy(self):
        """get_ticket returns a copy, not the original."""
        with patch("time.sleep"):
            result1 = SupportTools.get_ticket("SUP-4312")
            result1.data["modified"] = True
            result2 = SupportTools.get_ticket("SUP-4312")

        assert "modified" not in result2.data

    def test_post_internal_note_success(self):
        """post_internal_note succeeds for valid ticket."""
        with patch("time.sleep"):
            result = SupportTools.post_internal_note("SUP-4312", "Test note")

        assert result.success is True
        assert "note_id" in result.data
        assert result.data["note_id"].startswith("NOTE-")
        assert result.data["ticket_id"] == "SUP-4312"

    def test_post_internal_note_not_found(self):
        """post_internal_note fails for invalid ticket."""
        with patch("time.sleep"):
            result = SupportTools.post_internal_note("INVALID-ID", "Note")

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_update_ticket_status_success(self):
        """update_ticket_status succeeds for valid ticket."""
        original_status = TICKETS["SUP-4312"]["status"]
        try:
            with patch("time.sleep"):
                result = SupportTools.update_ticket_status(
                    "SUP-4312", "resolved", "Credit issued"
                )

            assert result.success is True
            assert result.data["status"] == "resolved"
            assert TICKETS["SUP-4312"]["status"] == "resolved"
        finally:
            # Restore original status
            TICKETS["SUP-4312"]["status"] = original_status

    def test_update_ticket_status_not_found(self):
        """update_ticket_status fails for invalid ticket."""
        with patch("time.sleep"):
            result = SupportTools.update_ticket_status(
                "INVALID-ID", "resolved", "Done"
            )

        assert result.success is False
        assert "not found" in result.error.lower()


class TestCRMTools:
    """Tests for CRMTools class."""

    def test_get_account_success(self):
        """get_account returns account data for valid ID."""
        with patch("time.sleep"):
            result = CRMTools.get_account("ACC-ACME-001")

        assert result.success is True
        assert result.data["id"] == "ACC-ACME-001"
        assert result.data["name"] == "Acme Corporation"
        assert result.data["tier"] == "enterprise"
        assert result.data["arr"] == 500000

    def test_get_account_not_found(self):
        """get_account returns error for invalid ID."""
        with patch("time.sleep"):
            result = CRMTools.get_account("INVALID-ID")

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_get_account_includes_churn_risk(self):
        """get_account includes churn risk information."""
        with patch("time.sleep"):
            result = CRMTools.get_account("ACC-ACME-001")

        assert "churn_risk" in result.data
        assert result.data["churn_risk"] == "high"

    def test_get_account_includes_health_score(self):
        """get_account includes health score."""
        with patch("time.sleep"):
            result = CRMTools.get_account("ACC-ACME-001")

        assert "health_score" in result.data
        assert isinstance(result.data["health_score"], int)


class TestIncidentTools:
    """Tests for IncidentTools class."""

    def test_get_recent_returns_incident_summary(self):
        """get_recent returns incident summary for account."""
        with patch("time.sleep"):
            result = IncidentTools.get_recent("ACC-ACME-001", days=30)

        assert result.success is True
        assert "sev1_count" in result.data
        assert "sev2_count" in result.data
        assert "total_downtime_mins" in result.data
        assert "incidents" in result.data

    def test_get_recent_filters_by_date(self):
        """get_recent filters incidents by date range."""
        with patch("time.sleep"):
            # All incidents should be within 30 days for test data
            result30 = IncidentTools.get_recent("ACC-ACME-001", days=30)
            # Very short window should have fewer
            result1 = IncidentTools.get_recent("ACC-ACME-001", days=1)

        assert result30.data["sev1_count"] >= result1.data["sev1_count"]

    def test_get_recent_calculates_total_downtime(self):
        """get_recent calculates total downtime correctly."""
        with patch("time.sleep"):
            result = IncidentTools.get_recent("ACC-ACME-001", days=30)

        # Should be sum of durations for filtered incidents
        incidents = result.data["incidents"]
        expected_downtime = sum(inc["duration_mins"] for inc in incidents)
        assert result.data["total_downtime_mins"] == expected_downtime

    def test_get_recent_empty_for_unknown_account(self):
        """get_recent returns zeros for unknown account."""
        with patch("time.sleep"):
            result = IncidentTools.get_recent("UNKNOWN-ACCOUNT", days=30)

        assert result.success is True
        assert result.data["sev1_count"] == 0
        assert result.data["sev2_count"] == 0
        assert result.data["total_downtime_mins"] == 0


class TestBillingTools:
    """Tests for BillingTools class."""

    def setup_method(self):
        """Clear credits before each test."""
        CREDITS_ISSUED.clear()

    def test_create_service_credit_success(self):
        """create_service_credit creates credit for valid account."""
        with patch("time.sleep"):
            result = BillingTools.create_service_credit(
                account_id="ACC-ACME-001",
                amount=5000.0,
                credit_pct=0.12,
                memo="Test credit",
            )

        assert result.success is True
        assert "credit_id" in result.data
        assert result.data["credit_id"].startswith("CREDIT-")
        assert result.data["amount"] == 5000.0
        assert result.data["credit_pct"] == 0.12

    def test_create_service_credit_stores_in_list(self):
        """create_service_credit stores credit in CREDITS_ISSUED."""
        with patch("time.sleep"):
            BillingTools.create_service_credit(
                account_id="ACC-ACME-001",
                amount=1000.0,
                credit_pct=0.05,
                memo="Test",
            )

        assert len(CREDITS_ISSUED) == 1
        assert CREDITS_ISSUED[0]["account_id"] == "ACC-ACME-001"

    def test_create_service_credit_invalid_account(self):
        """create_service_credit fails for invalid account."""
        with patch("time.sleep"):
            result = BillingTools.create_service_credit(
                account_id="INVALID-ID",
                amount=1000.0,
                credit_pct=0.05,
                memo="Test",
            )

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_create_service_credit_includes_timestamp(self):
        """create_service_credit includes issued_at timestamp."""
        with patch("time.sleep"):
            result = BillingTools.create_service_credit(
                account_id="ACC-ACME-001",
                amount=1000.0,
                credit_pct=0.05,
                memo="Test",
            )

        assert "issued_at" in result.data

    def test_get_credits_returns_account_credits(self):
        """get_credits returns credits for specific account."""
        with patch("time.sleep"):
            BillingTools.create_service_credit(
                account_id="ACC-ACME-001",
                amount=1000.0,
                credit_pct=0.05,
                memo="Credit 1",
            )
            BillingTools.create_service_credit(
                account_id="ACC-ACME-001",
                amount=2000.0,
                credit_pct=0.10,
                memo="Credit 2",
            )
            BillingTools.create_service_credit(
                account_id="ACC-STARTUP-002",
                amount=500.0,
                credit_pct=0.03,
                memo="Other account",
            )

        result = BillingTools.get_credits("ACC-ACME-001")

        assert result.success is True
        assert len(result.data["credits"]) == 2

    def test_get_credits_empty_for_account_without_credits(self):
        """get_credits returns empty list for account without credits."""
        result = BillingTools.get_credits("ACC-NO-CREDITS")

        assert result.success is True
        assert result.data["credits"] == []


class TestApprovalTools:
    """Tests for ApprovalTools class."""

    def setup_method(self):
        """Clear approval queue before each test."""
        APPROVAL_QUEUE.clear()

    def test_request_finance_approval_success(self):
        """request_finance_approval creates approval request."""
        with patch("time.sleep"):
            result = ApprovalTools.request_finance_approval(
                ticket_id="SUP-4312",
                account_id="ACC-ACME-001",
                credit_pct=0.20,
                credit_amount=5000.0,
                summary="Service credit request",
                exception_reason="3 SEV-1 incidents in last 30 days",
            )

        assert result.success is True
        assert "request_id" in result.data
        assert result.data["ticket_id"] == "SUP-4312"
        assert "approved" in result.data
        assert "approver" in result.data

    def test_request_finance_approval_sev1_auto_approves(self):
        """request_finance_approval auto-approves for SEV-1 reason."""
        with patch("time.sleep"):
            result = ApprovalTools.request_finance_approval(
                ticket_id="SUP-4312",
                account_id="ACC-ACME-001",
                credit_pct=0.20,
                credit_amount=5000.0,
                summary="Service credit",
                exception_reason="Multiple SEV-1 incidents",
            )

        assert result.data["approved"] is True
        assert result.data["approver"] == "finance-lead@ourcompany.com"

    def test_request_finance_approval_churn_auto_approves(self):
        """request_finance_approval auto-approves for churn risk reason."""
        with patch("time.sleep"):
            result = ApprovalTools.request_finance_approval(
                ticket_id="SUP-4312",
                account_id="ACC-ACME-001",
                credit_pct=0.15,
                credit_amount=3000.0,
                summary="Service credit",
                exception_reason="High churn risk customer",
            )

        assert result.data["approved"] is True

    def test_request_finance_approval_denies_without_criteria(self):
        """request_finance_approval denies without valid reason."""
        with patch("time.sleep"):
            result = ApprovalTools.request_finance_approval(
                ticket_id="SUP-4312",
                account_id="ACC-ACME-001",
                credit_pct=0.15,
                credit_amount=3000.0,
                summary="Service credit",
                exception_reason="Customer requested it",  # Not a valid reason
            )

        assert result.data["approved"] is False
        assert result.data["approver"] == "finance-review@ourcompany.com"

    def test_request_finance_approval_stores_in_queue(self):
        """request_finance_approval stores result in APPROVAL_QUEUE."""
        with patch("time.sleep"):
            ApprovalTools.request_finance_approval(
                ticket_id="SUP-4312",
                account_id="ACC-ACME-001",
                credit_pct=0.15,
                credit_amount=3000.0,
                summary="Test",
                exception_reason="Test reason",
            )

        assert len(APPROVAL_QUEUE) == 1
        assert APPROVAL_QUEUE[0]["ticket_id"] == "SUP-4312"

    def test_request_finance_approval_includes_timestamp(self):
        """request_finance_approval includes decided_at timestamp."""
        with patch("time.sleep"):
            result = ApprovalTools.request_finance_approval(
                ticket_id="SUP-4312",
                account_id="ACC-ACME-001",
                credit_pct=0.15,
                credit_amount=3000.0,
                summary="Test",
                exception_reason="Test",
            )

        assert "decided_at" in result.data


class TestMockDataIntegrity:
    """Tests to verify mock data integrity."""

    def test_tickets_have_required_fields(self):
        """All tickets have required fields."""
        required_fields = [
            "id", "account_id", "subject", "requested_credit_pct", "status"
        ]
        for ticket_id, ticket in TICKETS.items():
            for field in required_fields:
                assert field in ticket, f"{ticket_id} missing {field}"

    def test_accounts_have_required_fields(self):
        """All accounts have required fields."""
        required_fields = [
            "id", "name", "tier", "arr", "monthly_invoice", "churn_risk"
        ]
        for account_id, account in ACCOUNTS.items():
            for field in required_fields:
                assert field in account, f"{account_id} missing {field}"

    def test_ticket_account_ids_valid(self):
        """All ticket account_ids reference valid accounts."""
        for ticket_id, ticket in TICKETS.items():
            account_id = ticket["account_id"]
            assert account_id in ACCOUNTS, f"{ticket_id} references invalid {account_id}"

    def test_incident_account_ids_valid(self):
        """All incident account_ids reference valid accounts."""
        for account_id in INCIDENTS.keys():
            assert account_id in ACCOUNTS, f"Incident references invalid {account_id}"
