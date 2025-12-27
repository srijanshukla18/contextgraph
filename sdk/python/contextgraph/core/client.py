"""ContextGraph client for ingesting decision records."""

from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional, Any

from contextgraph.core.config import Config
from contextgraph.core.models import DecisionRecord, Evidence, Action, Outcome

logger = logging.getLogger(__name__)


class ContextGraphError(Exception):
    """Base exception for ContextGraph errors."""
    pass


class ConnectionError(ContextGraphError):
    """Failed to connect to ContextGraph server."""
    pass


class IngestError(ContextGraphError):
    """Failed to ingest a decision record."""
    pass


class ContextGraphClient:
    """Client for sending decision records to ContextGraph.

    Example:
        >>> from contextgraph import ContextGraphClient, Config
        >>> client = ContextGraphClient(Config(server_url="http://localhost:8080"))
        >>> decision = client.start_decision("run_123", actor_id="my-agent")
        >>> decision.add_evidence("get_account", {"id": "123"}, {"name": "Acme"})
        >>> decision.add_action("send_email", {"to": "user@example.com"}, {"sent": True})
        >>> decision.commit()
    """

    def __init__(self, config: Optional[Config] = None):
        """Initialize the client.

        Args:
            config: Configuration object. If None, uses defaults.
        """
        self.config = config or Config()
        self._pending_events: list[dict] = []
        self._current_decision: Optional[DecisionRecordBuilder] = None
        self._connection = None
        self._failed_ingests: list[DecisionRecord] = []

        if self.config.local_mode and self.config.postgres_url:
            self._init_local_storage()

    def _init_local_storage(self):
        """Initialize local postgres connection."""
        try:
            import psycopg2
            self._connection = psycopg2.connect(self.config.postgres_url)
            logger.info(f"Connected to local postgres: {self.config.postgres_url}")
        except ImportError:
            logger.warning("psycopg2 not installed, local mode disabled. Install with: pip install psycopg2-binary")
        except Exception as e:
            logger.error(f"Failed to connect to postgres: {e}")

    def start_decision(self, run_id: str, actor_id: Optional[str] = None, actor_type: str = "agent") -> "DecisionRecordBuilder":
        """Start building a new decision record.

        Args:
            run_id: Unique identifier for this run/execution
            actor_id: ID of the actor (agent) making the decision
            actor_type: Type of actor (agent, human, system)

        Returns:
            DecisionRecordBuilder for fluent API
        """
        self._current_decision = DecisionRecordBuilder(self, run_id, actor_id, actor_type)
        return self._current_decision

    def ingest_event(self, event: dict):
        """Ingest a raw event."""
        self._pending_events.append(event)
        if len(self._pending_events) >= self.config.batch_size:
            self.flush()

    def ingest_decision(self, decision: DecisionRecord) -> bool:
        """Ingest a complete decision record.

        Args:
            decision: The DecisionRecord to ingest

        Returns:
            True if successful, False otherwise

        Raises:
            IngestError: If ingestion fails and raise_on_error is True in config
        """
        try:
            if self.config.local_mode:
                self._store_local(decision)
            else:
                self._send_to_server(decision)
            logger.debug(f"Ingested decision {decision.decision_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to ingest decision {decision.decision_id}: {e}")
            self._failed_ingests.append(decision)
            if getattr(self.config, 'raise_on_error', False):
                raise IngestError(f"Failed to ingest decision: {e}") from e
            return False

    def _store_local(self, decision: DecisionRecord):
        """Store decision in local postgres."""
        if not self._connection:
            raise ConnectionError("No local database connection")

        cursor = self._connection.cursor()
        data = decision.to_dict()
        try:
            cursor.execute(
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
                """,
                (
                    data["decision_id"],
                    data["run_id"],
                    self.config.tenant_id,
                    data.get("trace_id"),
                    data["timestamp"],
                    data["actor"]["type"] if data.get("actor") else None,
                    data["actor"]["id"] if data.get("actor") else None,
                    data["outcome"],
                    data.get("outcome_reason"),
                    json.dumps(data.get("subject_entities", [])),
                    json.dumps(data.get("evidence", [])),
                    json.dumps(data.get("policies", [])),
                    json.dumps(data.get("approvals", [])),
                    json.dumps(data.get("actions", [])),
                    json.dumps(data.get("metadata", {})),
                )
            )
            self._connection.commit()
        except Exception as e:
            self._connection.rollback()
            raise IngestError(f"Database error: {e}") from e

    def _send_to_server(self, decision: DecisionRecord):
        """Send decision to ContextGraph server."""
        url = f"{self.config.server_url}/v1/decisions"
        data = json.dumps(decision.to_dict()).encode('utf-8')

        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as response:
                if response.status >= 400:
                    raise IngestError(f"Server returned {response.status}")
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8') if e.fp else ""
            raise IngestError(f"HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise ConnectionError(f"Failed to connect to {url}: {e.reason}") from e

    def retry_failed(self) -> int:
        """Retry failed ingests.

        Returns:
            Number of successfully retried ingests
        """
        if not self._failed_ingests:
            return 0

        succeeded = 0
        still_failed = []

        for decision in self._failed_ingests:
            try:
                if self.config.local_mode:
                    self._store_local(decision)
                else:
                    self._send_to_server(decision)
                succeeded += 1
                logger.info(f"Retry succeeded for decision {decision.decision_id}")
            except Exception as e:
                logger.warning(f"Retry failed for decision {decision.decision_id}: {e}")
                still_failed.append(decision)

        self._failed_ingests = still_failed
        return succeeded

    def flush(self):
        """Flush pending events."""
        self._pending_events.clear()

    def close(self):
        """Close the client and release resources."""
        self.flush()
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None

    @property
    def failed_count(self) -> int:
        """Number of failed ingests waiting for retry."""
        return len(self._failed_ingests)


class DecisionRecordBuilder:
    """Builder for constructing decision records incrementally.

    Example:
        >>> builder = client.start_decision("run_123", actor_id="my-agent")
        >>> builder.add_evidence("get_user", {"id": "123"}, {"name": "John"})
        >>> builder.add_action("send_email", {"to": "john@example.com"}, {"sent": True})
        >>> record = builder.commit()
    """

    def __init__(self, client: ContextGraphClient, run_id: str, actor_id: Optional[str], actor_type: str):
        self.client = client
        self.run_id = run_id
        self.actor_id = actor_id
        self.actor_type = actor_type
        self.evidence: list[Evidence] = []
        self.actions: list[Action] = []
        self.policies: list[dict] = []
        self.approvals: list[dict] = []
        self.metadata: dict[str, Any] = {}
        self._start_time = datetime.utcnow()

    def add_evidence(self, tool_name: str, tool_args: dict, result: Any, source: Optional[str] = None) -> "DecisionRecordBuilder":
        """Record evidence from a read operation.

        Args:
            tool_name: Name of the tool that retrieved the data
            tool_args: Arguments passed to the tool
            result: The data returned by the tool
            source: Optional source identifier (defaults to tool_name)

        Returns:
            self for method chaining
        """
        self.evidence.append(Evidence(
            source=source or tool_name,
            retrieved_at=datetime.utcnow(),
            tool_name=tool_name,
            tool_args=tool_args,
            snapshot=result if isinstance(result, dict) else {"value": result},
        ))
        return self

    def add_action(self, tool_name: str, tool_args: dict, result: Any, success: bool = True) -> "DecisionRecordBuilder":
        """Record an action (write operation).

        Args:
            tool_name: Name of the tool that performed the action
            tool_args: Arguments passed to the tool
            result: The result of the action
            success: Whether the action succeeded

        Returns:
            self for method chaining
        """
        self.actions.append(Action(
            tool=tool_name,
            committed_at=datetime.utcnow(),
            params=tool_args,
            result=result if isinstance(result, dict) else {"value": result},
            success=success,
        ))
        return self

    def add_policy(self, policy_id: str, version: str, result: str, message: Optional[str] = None) -> "DecisionRecordBuilder":
        """Record a policy evaluation.

        Args:
            policy_id: Identifier of the policy
            version: Version of the policy
            result: Result of evaluation (pass, fail, warn, skip)
            message: Optional message explaining the result

        Returns:
            self for method chaining
        """
        self.policies.append({
            "policy_id": policy_id,
            "version": version,
            "result": result,
            "message": message,
        })
        return self

    def add_approval(self, approver_id: str, granted: bool, reason: Optional[str] = None) -> "DecisionRecordBuilder":
        """Record an approval decision.

        Args:
            approver_id: ID of the approver
            granted: Whether approval was granted
            reason: Optional reason for the decision

        Returns:
            self for method chaining
        """
        self.approvals.append({
            "approver": {"type": "human", "id": approver_id},
            "granted": granted,
            "granted_at": datetime.utcnow().isoformat(),
            "reason": reason,
        })
        return self

    def commit(self, outcome: str = "committed", reason: Optional[str] = None) -> DecisionRecord:
        """Finalize and submit the decision record.

        Args:
            outcome: The outcome (committed, denied, escalated, pending)
            reason: Optional reason for the outcome

        Returns:
            The created DecisionRecord
        """
        from contextgraph.core.models import Actor, ActorType, PolicyEval, PolicyResult, Approval as ApprovalModel

        record = DecisionRecord(
            run_id=self.run_id,
            outcome=Outcome(outcome),
            timestamp=self._start_time,
            actor=Actor(type=ActorType(self.actor_type), id=self.actor_id) if self.actor_id else None,
            evidence=self.evidence,
            actions=self.actions,
            policies=[PolicyEval(
                policy_id=p["policy_id"],
                version=p["version"],
                result=PolicyResult(p["result"]),
                message=p.get("message")
            ) for p in self.policies],
            approvals=[ApprovalModel(
                approver=Actor(type=ActorType(a["approver"]["type"]), id=a["approver"]["id"]),
                granted=a["granted"],
                granted_at=datetime.fromisoformat(a["granted_at"]),
                reason=a.get("reason")
            ) for a in self.approvals],
            outcome_reason=reason,
            metadata=self.metadata,
        )
        self.client.ingest_decision(record)
        return record
