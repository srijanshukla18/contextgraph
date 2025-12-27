"""ContextGraph Server - Production-ready FastAPI ingest and query API."""

import json
import logging
import os
import secrets
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor


# =============================================================================
# Configuration from Environment
# =============================================================================

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/contextgraph")
API_KEYS = set(os.environ.get("API_KEYS", "").split(",")) - {""}  # Filter empty strings
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "100"))
RATE_LIMIT_WINDOW = int(os.environ.get("RATE_LIMIT_WINDOW", "60"))  # seconds
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
REQUIRE_AUTH = os.environ.get("REQUIRE_AUTH", "true").lower() == "true"


# =============================================================================
# Structured Logging
# =============================================================================

class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)


def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    return logging.getLogger("contextgraph")


logger = setup_logging()


# =============================================================================
# Database Connection Pool
# =============================================================================

db_pool: Optional[pool.ThreadedConnectionPool] = None


def init_db_pool():
    global db_pool
    try:
        db_pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=20,
            dsn=DATABASE_URL,
            cursor_factory=RealDictCursor,
        )
        logger.info("Database connection pool initialized", extra={"extra_data": {"pool_size": 20}})
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        raise


def close_db_pool():
    global db_pool
    if db_pool:
        db_pool.closeall()
        logger.info("Database connection pool closed")


def get_db_connection():
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database pool not initialized")
    try:
        return db_pool.getconn()
    except pool.PoolError as e:
        logger.error(f"Failed to get connection from pool: {e}")
        raise HTTPException(status_code=503, detail="Database connection unavailable")


def release_db_connection(conn):
    if db_pool and conn:
        db_pool.putconn(conn)


# =============================================================================
# Rate Limiting (In-Memory, upgrade to Redis for production clusters)
# =============================================================================

class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> tuple[bool, int, int]:
        """Returns (allowed, remaining, reset_in_seconds)."""
        now = time.time()
        window_start = now - self.window

        # Clean old requests
        self.requests[key] = [t for t in self.requests[key] if t > window_start]

        remaining = max(0, self.max_requests - len(self.requests[key]))
        reset_in = int(self.window - (now - self.requests[key][0])) if self.requests[key] else self.window

        if len(self.requests[key]) >= self.max_requests:
            return False, remaining, reset_in

        self.requests[key].append(now)
        return True, remaining - 1, reset_in


rate_limiter = RateLimiter(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW)


# =============================================================================
# Application Lifecycle
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db_pool()
    logger.info("ContextGraph server started", extra={
        "extra_data": {
            "auth_required": REQUIRE_AUTH,
            "allowed_origins": ALLOWED_ORIGINS,
            "rate_limit": f"{RATE_LIMIT_REQUESTS}/{RATE_LIMIT_WINDOW}s",
        }
    })
    yield
    # Shutdown
    close_db_pool()


app = FastAPI(
    title="ContextGraph",
    description="Decision traces as data. Context as a graph.",
    version="0.1.0",
    lifespan=lifespan,
)


# =============================================================================
# CORS Middleware (Configurable Origins)
# =============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


# =============================================================================
# Request ID Middleware
# =============================================================================

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id

    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000

    response.headers["X-Request-ID"] = request_id

    # Log request
    logger.info(
        f"{request.method} {request.url.path}",
        extra={
            "request_id": request_id,
            "extra_data": {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "client_ip": request.client.host if request.client else "unknown",
            }
        }
    )

    return response


# =============================================================================
# Authentication Dependency
# =============================================================================

async def verify_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
):
    """Verify API key from header. Skip if REQUIRE_AUTH=false."""
    if not REQUIRE_AUTH:
        return "anonymous"

    if not API_KEYS:
        # No API keys configured - log warning and allow (for dev)
        logger.warning("No API_KEYS configured, authentication disabled")
        return "anonymous"

    # Check X-API-Key header
    if x_api_key and x_api_key in API_KEYS:
        return x_api_key[:8] + "..."  # Return masked key for logging

    # Check Authorization: Bearer <key>
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        if token in API_KEYS:
            return token[:8] + "..."

    raise HTTPException(
        status_code=401,
        detail="Invalid or missing API key",
        headers={"WWW-Authenticate": "Bearer"},
    )


# =============================================================================
# Rate Limiting Dependency
# =============================================================================

async def check_rate_limit(request: Request):
    """Check rate limit based on client IP or API key."""
    key = request.client.host if request.client else "unknown"
    allowed, remaining, reset_in = rate_limiter.is_allowed(key)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(rate_limiter.max_requests),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(reset_in),
                "Retry-After": str(reset_in),
            }
        )

    return {"remaining": remaining, "reset_in": reset_in}


# =============================================================================
# Pydantic Models
# =============================================================================

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


class HealthResponse(BaseModel):
    status: str
    database: str
    version: str
    timestamp: str


class ErrorResponse(BaseModel):
    """RFC 7807 Problem Details."""
    type: str
    title: str
    status: int
    detail: str
    instance: Optional[str] = None


# =============================================================================
# Exception Handler
# =============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": f"https://contextgraph.dev/errors/{exc.status_code}",
            "title": "Error",
            "status": exc.status_code,
            "detail": exc.detail,
            "instance": str(request.url.path),
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(f"Unhandled exception: {exc}", exc_info=True, extra={"request_id": request_id})
    return JSONResponse(
        status_code=500,
        content={
            "type": "https://contextgraph.dev/errors/internal",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "An unexpected error occurred",
            "instance": str(request.url.path),
        }
    )


# =============================================================================
# Health Check (with DB connectivity)
# =============================================================================

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health():
    """Health check endpoint with database connectivity verification."""
    db_status = "unknown"
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)[:50]}"
        logger.warning(f"Health check database error: {e}")
    finally:
        if conn:
            release_db_connection(conn)

    return HealthResponse(
        status="ok" if db_status == "connected" else "degraded",
        database=db_status,
        version="0.1.0",
        timestamp=datetime.utcnow().isoformat() + "Z",
    )


@app.get("/ready", tags=["System"])
def readiness():
    """Kubernetes readiness probe - checks if server can accept traffic."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        return {"ready": True}
    except Exception:
        raise HTTPException(status_code=503, detail="Database not ready")
    finally:
        if conn:
            release_db_connection(conn)


# =============================================================================
# API Endpoints
# =============================================================================

@app.post(
    "/v1/decisions",
    tags=["Decisions"],
    dependencies=[Depends(verify_api_key), Depends(check_rate_limit)],
)
def create_decision(decision: DecisionRecordCreate, request: Request):
    """Ingest a decision record."""
    conn = None
    try:
        conn = get_db_connection()
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
        logger.info(
            f"Decision created: {decision.decision_id}",
            extra={
                "request_id": getattr(request.state, "request_id", None),
                "extra_data": {"decision_id": decision.decision_id, "outcome": decision.outcome},
            }
        )
        return {"decision_id": decision.decision_id, "status": "created"}
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Failed to create decision: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create decision record")
    finally:
        if conn:
            release_db_connection(conn)


@app.get(
    "/v1/decisions/{decision_id}",
    tags=["Decisions"],
    dependencies=[Depends(verify_api_key), Depends(check_rate_limit)],
)
def get_decision(decision_id: str):
    """Get a decision record by ID."""
    conn = None
    try:
        conn = get_db_connection()
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
        if conn:
            release_db_connection(conn)


@app.get(
    "/v1/decisions/{decision_id}/explain",
    response_model=ExplainResponse,
    tags=["Decisions"],
    dependencies=[Depends(verify_api_key), Depends(check_rate_limit)],
)
def explain_decision(decision_id: str):
    """Get a structured explanation of why a decision was made."""
    conn = None
    try:
        conn = get_db_connection()
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
        if conn:
            release_db_connection(conn)


@app.get(
    "/v1/decisions",
    tags=["Decisions"],
    dependencies=[Depends(verify_api_key), Depends(check_rate_limit)],
)
def list_decisions(
    run_id: Optional[str] = None,
    outcome: Optional[str] = None,
    limit: int = Query(default=50, le=100),
    offset: int = 0,
):
    """List decision records with optional filters."""
    conn = None
    try:
        conn = get_db_connection()
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
        if conn:
            release_db_connection(conn)


@app.post(
    "/v1/precedents/search",
    tags=["Precedents"],
    dependencies=[Depends(verify_api_key), Depends(check_rate_limit)],
)
def search_precedents(
    policy_id: Optional[str] = None,
    tool: Optional[str] = None,
    outcome: Optional[str] = None,
    limit: int = Query(default=10, le=50),
):
    """Search for similar past decisions (precedents)."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

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
        if conn:
            release_db_connection(conn)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
