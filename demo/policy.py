"""Policy engine for service credit approvals.

Policy: service_credit v1.0
- Default cap: 10% of monthly invoice
- Exception allowed up to 25% only if:
  - >= 2 SEV-1 incidents in last 30 days OR
  - churn_risk = high
- If requesting > 10% -> Finance approval required
"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum


class PolicyResult(str, Enum):
    APPROVED = "approved"
    EXCEPTION_REQUIRED = "exception_required"
    DENIED = "denied"


@dataclass
class PolicyEvaluation:
    policy_id: str
    version: str
    result: PolicyResult
    requested_pct: float
    cap_pct: float
    max_exception_pct: float
    exception_route: Optional[str]
    requires_approval: bool
    approval_reason: Optional[str]
    details: dict


class ServiceCreditPolicy:
    """Service credit policy evaluator."""

    POLICY_ID = "service_credit"
    VERSION = "1.0"
    DEFAULT_CAP_PCT = 0.10  # 10%
    MAX_EXCEPTION_PCT = 0.25  # 25%
    SEV1_THRESHOLD = 2

    def evaluate(
        self,
        requested_pct: float,
        sev1_count: int,
        sev2_count: int,
        churn_risk: str,
        account_tier: str,
    ) -> PolicyEvaluation:
        """Evaluate a service credit request against policy."""

        details = {
            "requested_pct": requested_pct,
            "sev1_count": sev1_count,
            "sev2_count": sev2_count,
            "churn_risk": churn_risk,
            "account_tier": account_tier,
        }

        # Check if within default cap
        if requested_pct <= self.DEFAULT_CAP_PCT:
            return PolicyEvaluation(
                policy_id=self.POLICY_ID,
                version=self.VERSION,
                result=PolicyResult.APPROVED,
                requested_pct=requested_pct,
                cap_pct=self.DEFAULT_CAP_PCT,
                max_exception_pct=self.MAX_EXCEPTION_PCT,
                exception_route=None,
                requires_approval=False,
                approval_reason=None,
                details=details,
            )

        # Check if exceeds maximum exception
        if requested_pct > self.MAX_EXCEPTION_PCT:
            return PolicyEvaluation(
                policy_id=self.POLICY_ID,
                version=self.VERSION,
                result=PolicyResult.DENIED,
                requested_pct=requested_pct,
                cap_pct=self.DEFAULT_CAP_PCT,
                max_exception_pct=self.MAX_EXCEPTION_PCT,
                exception_route=None,
                requires_approval=False,
                approval_reason=f"Requested {requested_pct:.0%} exceeds maximum allowed {self.MAX_EXCEPTION_PCT:.0%}",
                details=details,
            )

        # Check exception eligibility
        exception_eligible = False
        exception_route = None
        exception_reasons = []

        if sev1_count >= self.SEV1_THRESHOLD:
            exception_eligible = True
            exception_route = "service_impact_exception"
            exception_reasons.append(f"{sev1_count} SEV-1 incidents in last 30 days")

        if churn_risk == "high":
            exception_eligible = True
            exception_route = exception_route or "churn_risk_exception"
            exception_reasons.append("High churn risk")

        if not exception_eligible:
            return PolicyEvaluation(
                policy_id=self.POLICY_ID,
                version=self.VERSION,
                result=PolicyResult.DENIED,
                requested_pct=requested_pct,
                cap_pct=self.DEFAULT_CAP_PCT,
                max_exception_pct=self.MAX_EXCEPTION_PCT,
                exception_route=None,
                requires_approval=False,
                approval_reason=f"Requested {requested_pct:.0%} exceeds cap ({self.DEFAULT_CAP_PCT:.0%}) "
                               f"and no exception criteria met",
                details=details,
            )

        # Exception route available, requires approval
        return PolicyEvaluation(
            policy_id=self.POLICY_ID,
            version=self.VERSION,
            result=PolicyResult.EXCEPTION_REQUIRED,
            requested_pct=requested_pct,
            cap_pct=self.DEFAULT_CAP_PCT,
            max_exception_pct=self.MAX_EXCEPTION_PCT,
            exception_route=exception_route,
            requires_approval=True,
            approval_reason="; ".join(exception_reasons),
            details=details,
        )
