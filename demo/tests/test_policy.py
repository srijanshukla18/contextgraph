"""Tests for the demo policy module."""

import pytest
from demo.policy import PolicyResult, PolicyEvaluation, ServiceCreditPolicy


class TestPolicyResult:
    """Tests for the PolicyResult enum."""

    def test_approved_value(self):
        """PolicyResult.APPROVED has correct value."""
        assert PolicyResult.APPROVED.value == "approved"

    def test_exception_required_value(self):
        """PolicyResult.EXCEPTION_REQUIRED has correct value."""
        assert PolicyResult.EXCEPTION_REQUIRED.value == "exception_required"

    def test_denied_value(self):
        """PolicyResult.DENIED has correct value."""
        assert PolicyResult.DENIED.value == "denied"


class TestServiceCreditPolicy:
    """Tests for the ServiceCreditPolicy class."""

    @pytest.fixture
    def policy(self):
        """Create a ServiceCreditPolicy instance."""
        return ServiceCreditPolicy()

    def test_policy_id_and_version(self, policy):
        """Policy has correct ID and version."""
        assert policy.POLICY_ID == "service_credit"
        assert policy.VERSION == "1.0"

    def test_default_cap_10_percent(self, policy):
        """Default cap is 10%."""
        assert policy.DEFAULT_CAP_PCT == 0.10

    def test_max_exception_25_percent(self, policy):
        """Maximum exception is 25%."""
        assert policy.MAX_EXCEPTION_PCT == 0.25


class TestServiceCreditPolicyEvaluate:
    """Tests for the evaluate method."""

    @pytest.fixture
    def policy(self):
        """Create a ServiceCreditPolicy instance."""
        return ServiceCreditPolicy()

    def test_within_default_cap_approved(self, policy):
        """Request within default cap is approved without exception."""
        result = policy.evaluate(
            requested_pct=0.05,  # 5% < 10%
            sev1_count=0,
            sev2_count=0,
            churn_risk="low",
            account_tier="growth",
        )

        assert result.result == PolicyResult.APPROVED
        assert result.requires_approval is False
        assert result.exception_route is None

    def test_exactly_default_cap_approved(self, policy):
        """Request exactly at default cap is approved."""
        result = policy.evaluate(
            requested_pct=0.10,  # Exactly 10%
            sev1_count=0,
            sev2_count=0,
            churn_risk="low",
            account_tier="growth",
        )

        assert result.result == PolicyResult.APPROVED
        assert result.requires_approval is False

    def test_exceeds_max_exception_denied(self, policy):
        """Request exceeding max exception is denied."""
        result = policy.evaluate(
            requested_pct=0.30,  # 30% > 25%
            sev1_count=5,  # Even with high incidents
            sev2_count=10,
            churn_risk="high",  # Even with high churn risk
            account_tier="enterprise",
        )

        assert result.result == PolicyResult.DENIED
        assert "exceeds maximum" in result.approval_reason.lower()

    def test_above_cap_without_exception_criteria_denied(self, policy):
        """Request above cap without exception criteria is denied."""
        result = policy.evaluate(
            requested_pct=0.15,  # 15% > 10%
            sev1_count=0,  # No SEV-1 incidents
            sev2_count=3,  # Only SEV-2
            churn_risk="low",  # Low churn risk
            account_tier="growth",
        )

        assert result.result == PolicyResult.DENIED
        assert "no exception criteria met" in result.approval_reason.lower()

    def test_sev1_threshold_triggers_exception(self, policy):
        """Two or more SEV-1 incidents triggers exception route."""
        result = policy.evaluate(
            requested_pct=0.20,  # 20% > 10%
            sev1_count=2,  # Exactly at threshold
            sev2_count=0,
            churn_risk="low",
            account_tier="enterprise",
        )

        assert result.result == PolicyResult.EXCEPTION_REQUIRED
        assert result.requires_approval is True
        assert result.exception_route == "service_impact_exception"
        assert "SEV-1" in result.approval_reason

    def test_sev1_above_threshold_triggers_exception(self, policy):
        """More than threshold SEV-1 incidents triggers exception."""
        result = policy.evaluate(
            requested_pct=0.20,
            sev1_count=5,  # Above threshold
            sev2_count=3,
            churn_risk="low",
            account_tier="enterprise",
        )

        assert result.result == PolicyResult.EXCEPTION_REQUIRED
        assert result.exception_route == "service_impact_exception"

    def test_high_churn_risk_triggers_exception(self, policy):
        """High churn risk triggers exception route."""
        result = policy.evaluate(
            requested_pct=0.15,
            sev1_count=0,
            sev2_count=0,
            churn_risk="high",  # High churn risk
            account_tier="enterprise",
        )

        assert result.result == PolicyResult.EXCEPTION_REQUIRED
        assert result.requires_approval is True
        assert result.exception_route == "churn_risk_exception"
        assert "churn" in result.approval_reason.lower()

    def test_both_criteria_met_uses_service_impact(self, policy):
        """When both criteria met, service_impact_exception takes precedence."""
        result = policy.evaluate(
            requested_pct=0.20,
            sev1_count=3,  # Above threshold
            sev2_count=5,
            churn_risk="high",  # Also high churn
            account_tier="enterprise",
        )

        assert result.result == PolicyResult.EXCEPTION_REQUIRED
        # service_impact_exception is set first
        assert result.exception_route == "service_impact_exception"
        # Reason includes both
        assert "SEV-1" in result.approval_reason
        assert "churn" in result.approval_reason.lower()


class TestPolicyEvaluationDetails:
    """Tests for PolicyEvaluation details field."""

    @pytest.fixture
    def policy(self):
        """Create a ServiceCreditPolicy instance."""
        return ServiceCreditPolicy()

    def test_details_contains_all_inputs(self, policy):
        """PolicyEvaluation details contains all input values."""
        result = policy.evaluate(
            requested_pct=0.15,
            sev1_count=2,
            sev2_count=3,
            churn_risk="medium",
            account_tier="enterprise",
        )

        assert result.details["requested_pct"] == 0.15
        assert result.details["sev1_count"] == 2
        assert result.details["sev2_count"] == 3
        assert result.details["churn_risk"] == "medium"
        assert result.details["account_tier"] == "enterprise"

    def test_evaluation_includes_caps(self, policy):
        """PolicyEvaluation includes cap values."""
        result = policy.evaluate(
            requested_pct=0.05,
            sev1_count=0,
            sev2_count=0,
            churn_risk="low",
            account_tier="growth",
        )

        assert result.cap_pct == 0.10
        assert result.max_exception_pct == 0.25

    def test_evaluation_includes_policy_metadata(self, policy):
        """PolicyEvaluation includes policy ID and version."""
        result = policy.evaluate(
            requested_pct=0.05,
            sev1_count=0,
            sev2_count=0,
            churn_risk="low",
            account_tier="growth",
        )

        assert result.policy_id == "service_credit"
        assert result.version == "1.0"


class TestPolicyEdgeCases:
    """Tests for edge cases in policy evaluation."""

    @pytest.fixture
    def policy(self):
        """Create a ServiceCreditPolicy instance."""
        return ServiceCreditPolicy()

    def test_zero_percent_request_approved(self, policy):
        """Zero percent request is approved."""
        result = policy.evaluate(
            requested_pct=0.0,
            sev1_count=0,
            sev2_count=0,
            churn_risk="low",
            account_tier="growth",
        )

        assert result.result == PolicyResult.APPROVED

    def test_exactly_max_exception_with_criteria_allowed(self, policy):
        """Request exactly at max exception with criteria is allowed for exception."""
        result = policy.evaluate(
            requested_pct=0.25,  # Exactly 25%
            sev1_count=3,
            sev2_count=0,
            churn_risk="low",
            account_tier="enterprise",
        )

        assert result.result == PolicyResult.EXCEPTION_REQUIRED

    def test_one_sev1_not_enough(self, policy):
        """One SEV-1 incident is not enough for exception."""
        result = policy.evaluate(
            requested_pct=0.15,
            sev1_count=1,  # Below threshold of 2
            sev2_count=5,
            churn_risk="low",
            account_tier="enterprise",
        )

        assert result.result == PolicyResult.DENIED

    def test_medium_churn_risk_not_exception(self, policy):
        """Medium churn risk does not trigger exception."""
        result = policy.evaluate(
            requested_pct=0.15,
            sev1_count=0,
            sev2_count=0,
            churn_risk="medium",
            account_tier="enterprise",
        )

        assert result.result == PolicyResult.DENIED

    def test_low_churn_risk_not_exception(self, policy):
        """Low churn risk does not trigger exception."""
        result = policy.evaluate(
            requested_pct=0.15,
            sev1_count=0,
            sev2_count=0,
            churn_risk="low",
            account_tier="enterprise",
        )

        assert result.result == PolicyResult.DENIED
