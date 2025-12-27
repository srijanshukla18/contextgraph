"""ContextGraph Server - FastAPI-based ingest and query API."""

from datetime import datetime
from typing import Optional, Any
import json
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(
    title="ContextGraph",
    description="Decision traces as data. Context as a graph.",
    version="0.1.0",
)

# Enable CORS for UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/contextgraph")


def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


# Pydantic models
class EntityRef(BaseModel):
    namespace: str
    type: str
    id: str
    aliases: list[str] = []


class Actor(BaseModel):
    type: str
    id: str
    name: Optional[str] = None


class Evidence(BaseModel):
    evidence_id: str
    source: str
    entity_ref: Optional[EntityRef] = None
    snapshot: Optional[dict] = None
    snapshot_hash: Optional[str] = None
    retrieved_at: str
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None


class PolicyEval(BaseModel):
    policy_id: str
    version: str
    result: str
    inputs_hash: Optional[str] = None
    message: Optional[str] = None


class Approval(BaseModel):
    approval_id: str
    approver: Actor
    granted: bool
    granted_at: str
    reason: Optional[str] = None


class Action(BaseModel):
    action_id: str
    tool: str
    operation: Optional[str] = None
    target_entity: Optional[EntityRef] = None
    params: Optional[dict] = None
    result: Optional[dict] = None
    committed_at: str
    success: bool = True


class DecisionRecordCreate(BaseModel):
    decision_id: str
    run_id: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    timestamp: str
    actor: Optional[Actor] = None
    subject_entities: list[EntityRef] = []
    evidence: list[Evidence] = []
    policies: list[PolicyEval] = []
    approvals: list[Approval] = []
    actions: list[Action] = []
    outcome: str
    outcome_reason: Optional[str] = None
    precedent_refs: list[str] = []
    metadata: dict = {}


class ExplainResponse(BaseModel):
    decision_id: str
    run_id: str
    timestamp: str
    outcome: str
    outcome_reason: Optional[str]
    actor: Optional[dict]
    evidence_chain: list[dict]
    policy_chain: list[dict]
    approval_chain: list[dict]
    action_chain: list[dict]
    summary: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/decisions")
def create_decision(decision: DecisionRecordCreate):
    """Ingest a decision record."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO decision_records
            (decision_id, run_id, tenant_id, trace_id, timestamp, actor_type, actor_id,
             outcome, outcome_reason, subject_entities, evidence, policies, approvals, actions, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (decision_id) DO UPDATE SET
                outcome = EXCLUDED.outcome,
                outcome_reason = EXCLUDED.outcome_reason,
                evidence = EXCLUDED.evidence,
                policies = EXCLUDED.policies,
                approvals = EXCLUDED.approvals,
                actions = EXCLUDED.actions,
                updated_at = NOW()
            RETURNING decision_id
            """,
            (
                decision.decision_id,
                decision.run_id,
                "default",
                decision.trace_id,
                decision.timestamp,
                decision.actor.type if decision.actor else None,
                decision.actor.id if decision.actor else None,
                decision.outcome,
                decision.outcome_reason,
                json.dumps([e.model_dump() for e in decision.subject_entities]),
                json.dumps([e.model_dump() for e in decision.evidence]),
                json.dumps([p.model_dump() for p in decision.policies]),
                json.dumps([a.model_dump() for a in decision.approvals]),
                json.dumps([a.model_dump() for a in decision.actions]),
                json.dumps(decision.metadata),
            )
        )
        conn.commit()
        return {"decision_id": decision.decision_id, "status": "created"}
    finally:
        conn.close()


@app.get("/v1/decisions/{decision_id}")
def get_decision(decision_id: str):
    """Get a decision record by ID."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM decision_records WHERE decision_id = %s",
            (decision_id,)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Decision not found")
        return dict(row)
    finally:
        conn.close()


@app.get("/v1/decisions/{decision_id}/explain", response_model=ExplainResponse)
def explain_decision(decision_id: str):
    """Get a structured explanation of why a decision was made."""
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM decision_records WHERE decision_id = %s",
            (decision_id,)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Decision not found")

        evidence = row.get("evidence", [])
        policies = row.get("policies", [])
        approvals = row.get("approvals", [])
        actions = row.get("actions", [])

        # Build explanation chains
        evidence_chain = []
        for e in evidence:
            evidence_chain.append({
                "step": len(evidence_chain) + 1,
                "type": "observation",
                "source": e.get("source"),
                "tool": e.get("tool_name"),
                "retrieved_at": e.get("retrieved_at"),
                "summary": f"Read from {e.get('source')}",
            })

        policy_chain = []
        for p in policies:
            policy_chain.append({
                "step": len(policy_chain) + 1,
                "type": "policy_check",
                "policy_id": p.get("policy_id"),
                "version": p.get("version"),
                "result": p.get("result"),
                "message": p.get("message"),
                "summary": f"Policy {p.get('policy_id')} {p.get('result')}",
            })

        approval_chain = []
        for a in approvals:
            approver = a.get("approver", {})
            approval_chain.append({
                "step": len(approval_chain) + 1,
                "type": "approval",
                "approver_id": approver.get("id"),
                "approver_type": approver.get("type"),
                "granted": a.get("granted"),
                "granted_at": a.get("granted_at"),
                "reason": a.get("reason"),
                "summary": f"{'Approved' if a.get('granted') else 'Denied'} by {approver.get('id')}",
            })

        action_chain = []
        for a in actions:
            action_chain.append({
                "step": len(action_chain) + 1,
                "type": "action",
                "tool": a.get("tool"),
                "operation": a.get("operation"),
                "committed_at": a.get("committed_at"),
                "success": a.get("success"),
                "summary": f"Executed {a.get('tool')}",
            })

        # Generate summary
        summary_parts = []
        if evidence_chain:
            summary_parts.append(f"Gathered {len(evidence_chain)} pieces of evidence")
        if policy_chain:
            passed = sum(1 for p in policies if p.get("result") == "pass")
            summary_parts.append(f"Evaluated {len(policy_chain)} policies ({passed} passed)")
        if approval_chain:
            approved = sum(1 for a in approvals if a.get("granted"))
            summary_parts.append(f"Received {approved}/{len(approval_chain)} approvals")
        if action_chain:
            succeeded = sum(1 for a in actions if a.get("success"))
            summary_parts.append(f"Executed {succeeded}/{len(action_chain)} actions")
        summary_parts.append(f"Outcome: {row.get('outcome')}")

        return ExplainResponse(
            decision_id=row.get("decision_id"),
            run_id=row.get("run_id"),
            timestamp=row.get("timestamp").isoformat() if row.get("timestamp") else "",
            outcome=row.get("outcome"),
            outcome_reason=row.get("outcome_reason"),
            actor={"type": row.get("actor_type"), "id": row.get("actor_id")} if row.get("actor_id") else None,
            evidence_chain=evidence_chain,
            policy_chain=policy_chain,
            approval_chain=approval_chain,
            action_chain=action_chain,
            summary=". ".join(summary_parts) + ".",
        )
    finally:
        conn.close()


@app.get("/v1/decisions")
def list_decisions(
    run_id: Optional[str] = None,
    outcome: Optional[str] = None,
    limit: int = Query(default=50, le=100),
    offset: int = 0,
):
    """List decision records with optional filters."""
    conn = get_db()
    try:
        cur = conn.cursor()
        query = "SELECT decision_id, run_id, timestamp, outcome, actor_id FROM decision_records WHERE 1=1"
        params = []

        if run_id:
            query += " AND run_id = %s"
            params.append(run_id)
        if outcome:
            query += " AND outcome = %s"
            params.append(outcome)

        query += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cur.execute(query, params)
        rows = cur.fetchall()
        return {"decisions": [dict(r) for r in rows], "count": len(rows)}
    finally:
        conn.close()


@app.post("/v1/precedents/search")
def search_precedents(
    policy_id: Optional[str] = None,
    tool: Optional[str] = None,
    outcome: Optional[str] = None,
    limit: int = Query(default=10, le=50),
):
    """Search for similar past decisions (precedents)."""
    conn = get_db()
    try:
        cur = conn.cursor()

        # Simple filter-based search (embeddings would go here later)
        query = """
            SELECT decision_id, run_id, timestamp, outcome, policies, actions
            FROM decision_records
            WHERE 1=1
        """
        params = []

        if outcome:
            query += " AND outcome = %s"
            params.append(outcome)

        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)

        cur.execute(query, params)
        rows = cur.fetchall()

        # Filter by policy/tool in application layer
        results = []
        for row in rows:
            policies = row.get("policies", [])
            actions = row.get("actions", [])

            if policy_id:
                if not any(p.get("policy_id") == policy_id for p in policies):
                    continue
            if tool:
                if not any(a.get("tool") == tool for a in actions):
                    continue

            results.append({
                "decision_id": row.get("decision_id"),
                "run_id": row.get("run_id"),
                "timestamp": row.get("timestamp").isoformat() if row.get("timestamp") else "",
                "outcome": row.get("outcome"),
                "matching_policies": [p.get("policy_id") for p in policies],
                "matching_tools": [a.get("tool") for a in actions],
            })

        return {"precedents": results, "count": len(results)}
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
