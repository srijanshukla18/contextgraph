#!/usr/bin/env python3
"""Demo: End-to-end ContextGraph usage.

This demo simulates an agent making a decision (approving a discount),
captures it as a DecisionRecord, and queries the explain endpoint.

Run:
    # Start postgres and create schema first:
    # psql -c "CREATE DATABASE contextgraph"
    # psql contextgraph < storage/postgres/schema.sql

    # Start server:
    # DATABASE_URL=postgresql://localhost/contextgraph uvicorn server.main:app --port 8080

    # Run demo:
    # python examples/demo.py
"""

import json
from datetime import datetime
import urllib.request

SERVER_URL = "http://localhost:8080"


def create_sample_decision():
    """Create a sample decision record simulating an agent discount approval flow."""
    decision = {
        "decision_id": f"dec_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "run_id": "run_discount_review_001",
        "trace_id": "otel-trace-abc123",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "actor": {
            "type": "agent",
            "id": "discount-review-agent",
            "name": "Discount Review Agent"
        },
        "subject_entities": [
            {
                "namespace": "crm",
                "type": "Opportunity",
                "id": "OPP-2024-001",
                "aliases": ["salesforce:006xx00000ABC"]
            }
        ],
        "evidence": [
            {
                "evidence_id": "ev_001",
                "source": "crm",
                "entity_ref": {
                    "namespace": "crm",
                    "type": "Account",
                    "id": "ACC-100",
                    "aliases": []
                },
                "snapshot": {
                    "arr": 500000,
                    "tier": "enterprise",
                    "health_score": 85
                },
                "retrieved_at": datetime.utcnow().isoformat() + "Z",
                "tool_name": "get_account",
                "tool_args": {"account_id": "ACC-100"}
            },
            {
                "evidence_id": "ev_002",
                "source": "pagerduty",
                "snapshot": {
                    "incidents_last_90d": 3,
                    "sev1_count": 1,
                    "mttr_hours": 2.5
                },
                "retrieved_at": datetime.utcnow().isoformat() + "Z",
                "tool_name": "get_incidents",
                "tool_args": {"account_id": "ACC-100", "days": 90}
            }
        ],
        "policies": [
            {
                "policy_id": "discount_cap",
                "version": "3.2",
                "result": "fail",
                "message": "Requested 20% exceeds standard cap of 15%"
            },
            {
                "policy_id": "service_impact_exception",
                "version": "1.0",
                "result": "pass",
                "message": "SEV-1 incident qualifies for exception route"
            }
        ],
        "approvals": [
            {
                "approval_id": "apr_001",
                "approver": {
                    "type": "human",
                    "id": "finance-lead@company.com",
                    "name": "Finance Lead"
                },
                "granted": True,
                "granted_at": datetime.utcnow().isoformat() + "Z",
                "reason": "Approved due to service impact and retention risk"
            }
        ],
        "actions": [
            {
                "action_id": "act_001",
                "tool": "update_opportunity",
                "operation": "set_discount",
                "target_entity": {
                    "namespace": "crm",
                    "type": "Opportunity",
                    "id": "OPP-2024-001",
                    "aliases": []
                },
                "params": {"discount_percent": 20},
                "result": {"status": "updated", "new_value": 20},
                "committed_at": datetime.utcnow().isoformat() + "Z",
                "success": True
            }
        ],
        "outcome": "committed",
        "outcome_reason": "Exception approved via service_impact route",
        "precedent_refs": [],
        "metadata": {
            "framework": "demo",
            "version": "0.1.0"
        }
    }
    return decision


def post_decision(decision: dict) -> dict:
    """Post a decision to the server."""
    req = urllib.request.Request(
        f"{SERVER_URL}/v1/decisions",
        data=json.dumps(decision).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get_explain(decision_id: str) -> dict:
    """Get explanation for a decision."""
    with urllib.request.urlopen(f"{SERVER_URL}/v1/decisions/{decision_id}/explain") as resp:
        return json.loads(resp.read())


def main():
    print("=" * 60)
    print("ContextGraph Demo: Discount Approval Decision Trace")
    print("=" * 60)

    # Create and submit decision
    decision = create_sample_decision()
    print(f"\n1. Creating decision: {decision['decision_id']}")
    print(f"   Run ID: {decision['run_id']}")
    print(f"   Actor: {decision['actor']['name']}")

    try:
        result = post_decision(decision)
        print(f"   -> Submitted: {result}")
    except Exception as e:
        print(f"   -> Error (is server running?): {e}")
        print("\n   To run server:")
        print("   DATABASE_URL=postgresql://localhost/contextgraph uvicorn server.main:app --port 8080")
        return

    # Get explanation
    print(f"\n2. Querying explanation...")
    try:
        explain = get_explain(decision["decision_id"])

        print(f"\n{'=' * 60}")
        print("DECISION EXPLANATION")
        print("=" * 60)
        print(f"\nSummary: {explain['summary']}")

        print(f"\n--- Evidence Chain ({len(explain['evidence_chain'])} items) ---")
        for e in explain["evidence_chain"]:
            print(f"  [{e['step']}] {e['summary']} at {e['retrieved_at']}")

        print(f"\n--- Policy Chain ({len(explain['policy_chain'])} items) ---")
        for p in explain["policy_chain"]:
            print(f"  [{p['step']}] {p['summary']}: {p['message']}")

        print(f"\n--- Approval Chain ({len(explain['approval_chain'])} items) ---")
        for a in explain["approval_chain"]:
            print(f"  [{a['step']}] {a['summary']}: {a['reason']}")

        print(f"\n--- Action Chain ({len(explain['action_chain'])} items) ---")
        for a in explain["action_chain"]:
            status = "success" if a["success"] else "failed"
            print(f"  [{a['step']}] {a['summary']} ({status})")

        print(f"\n--- Outcome ---")
        print(f"  {explain['outcome']}: {explain['outcome_reason']}")

    except Exception as e:
        print(f"   -> Error: {e}")

    print("\n" + "=" * 60)
    print("Demo complete!")


if __name__ == "__main__":
    main()
