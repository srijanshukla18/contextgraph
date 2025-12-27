"""OpenAI Agents SDK integration - Trace processor for DecisionRecords.

Usage:
    from agents import set_tracing_processor
    from contextgraph.integrations.openai_agents import ContextGraphTraceProcessor

    processor = ContextGraphTraceProcessor(
        write_tools=["send_email", "update_crm"],
        server_url="http://localhost:8080",
    )
    set_tracing_processor(processor)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING
from dataclasses import dataclass, field

from contextgraph.core.client import ContextGraphClient
from contextgraph.core.models import (
    DecisionRecord, Evidence, Action, PolicyEval, Outcome, PolicyResult,
    Actor, ActorType,
)
from contextgraph.core.config import Config

logger = logging.getLogger(__name__)

# Type checking imports - these are the REAL types from OpenAI Agents SDK
# At runtime, we duck-type to avoid hard dependency
if TYPE_CHECKING:
    from agents.tracing import Trace, Span


class ContextGraphTraceProcessor:
    """Trace processor that converts OpenAI Agent traces to DecisionRecords.

    This processor implements the TracingProcessor protocol from the OpenAI Agents SDK.
    It automatically captures tool calls and converts them into ContextGraph DecisionRecords.

    Example:
        >>> from agents import set_tracing_processor
        >>> processor = ContextGraphTraceProcessor(
        ...     write_tools=["send_email", "create_ticket"],
        ...     server_url="http://localhost:8080",
        ... )
        >>> set_tracing_processor(processor)
    """

    def __init__(
        self,
        client: Optional[ContextGraphClient] = None,
        config: Optional[Config] = None,
        write_tools: Optional[list[str]] = None,
        read_tools: Optional[list[str]] = None,
        server_url: Optional[str] = None,
        local_mode: bool = False,
        postgres_url: Optional[str] = None,
    ):
        """Initialize the trace processor.

        Args:
            client: Optional pre-configured ContextGraphClient
            config: Optional Config object
            write_tools: List of tool names that are write operations (actions)
            read_tools: List of tool names that are read operations (evidence)
            server_url: URL of the ContextGraph server (default: http://localhost:8080)
            local_mode: If True, write directly to local postgres instead of server
            postgres_url: Postgres connection URL for local mode
        """
        self.config = config or Config()

        if write_tools:
            self.config.write_tools = write_tools
        if read_tools:
            self.config.read_tools = read_tools
        if server_url:
            self.config.server_url = server_url
        if local_mode:
            self.config.local_mode = local_mode
        if postgres_url:
            self.config.postgres_url = postgres_url

        self.client = client or ContextGraphClient(self.config)
        self._active_traces: dict[str, _TraceAccumulator] = {}

    def on_trace_start(self, trace: "Trace") -> None:
        """Called when a new trace begins."""
        try:
            trace_id = _safe_get(trace, "trace_id", str(id(trace)))
            self._active_traces[trace_id] = _TraceAccumulator(
                trace_id=trace_id,
                run_id=trace_id,
                name=_safe_get(trace, "name", "unknown"),
                start_time=_safe_get(trace, "start_time", datetime.now(timezone.utc)),
                metadata=_safe_get(trace, "metadata", {}),
            )
        except Exception as e:
            logger.warning(f"Error in on_trace_start: {e}")

    def on_trace_end(self, trace: "Trace") -> None:
        """Called when a trace completes. Creates DecisionRecord if actions were taken."""
        try:
            trace_id = _safe_get(trace, "trace_id", str(id(trace)))
            accumulator = self._active_traces.pop(trace_id, None)
            if not accumulator:
                return

            # Only create DecisionRecord if there were actions (writes)
            if not accumulator.actions:
                logger.debug(f"Trace {trace_id} had no actions, skipping DecisionRecord")
                return

            record = DecisionRecord(
                run_id=accumulator.run_id,
                trace_id=trace_id,
                timestamp=accumulator.start_time,
                outcome=Outcome.COMMITTED if accumulator.success else Outcome.DENIED,
                outcome_reason=accumulator.outcome_reason,
                actor=Actor(type=ActorType.AGENT, id=accumulator.name),
                evidence=accumulator.evidence,
                actions=accumulator.actions,
                policies=accumulator.policies,
                metadata=accumulator.metadata,
            )

            self.client.ingest_decision(record)
            logger.info(f"Created DecisionRecord {record.decision_id} for trace {trace_id}")

        except Exception as e:
            logger.error(f"Error in on_trace_end: {e}", exc_info=True)

    def on_span_start(self, span: "Span") -> None:
        """Called when a span begins."""
        pass  # We process spans on completion

    def on_span_end(self, span: "Span") -> None:
        """Called when a span completes. Processes tool calls, guardrails, handoffs."""
        try:
            trace_id = _safe_get(span, "trace_id")
            if not trace_id:
                return

            accumulator = self._active_traces.get(trace_id)
            if not accumulator:
                return

            span_type = _safe_get(span, "span_type")
            # Handle both enum and string types
            span_type_str = span_type.value if hasattr(span_type, 'value') else str(span_type)

            if span_type_str in ("function", "tool"):
                self._handle_tool_span(span, accumulator)
            elif span_type_str == "guardrail":
                self._handle_guardrail_span(span, accumulator)
            elif span_type_str == "handoff":
                self._handle_handoff_span(span, accumulator)

        except Exception as e:
            logger.warning(f"Error in on_span_end: {e}")

    def _handle_tool_span(self, span: "Span", accumulator: "_TraceAccumulator"):
        """Process a tool/function call span."""
        attributes = _safe_get(span, "attributes", {})
        tool_name = attributes.get("function.name") or _safe_get(span, "name", "unknown")
        tool_args = attributes.get("function.arguments", {})
        tool_output = attributes.get("function.output")

        # Parse JSON args if string
        if isinstance(tool_args, str):
            try:
                tool_args = json.loads(tool_args)
            except (json.JSONDecodeError, TypeError):
                tool_args = {"raw": tool_args}

        # Parse JSON output if string
        if isinstance(tool_output, str):
            try:
                tool_output = json.loads(tool_output)
            except (json.JSONDecodeError, TypeError):
                pass  # Keep as string

        span_status = _safe_get(span, "status", "ok")
        status_str = span_status.value if hasattr(span_status, 'value') else str(span_status)
        success = status_str.lower() in ("ok", "unset", "")

        end_time = _safe_get(span, "end_time") or datetime.now(timezone.utc)
        start_time = _safe_get(span, "start_time") or end_time

        if self.config.is_write_tool(tool_name):
            accumulator.actions.append(Action(
                tool=tool_name,
                committed_at=end_time,
                params=tool_args,
                result={"output": tool_output} if tool_output else None,
                success=success,
            ))
            if not success:
                accumulator.success = False
                accumulator.outcome_reason = f"Tool {tool_name} failed"
        else:
            # Treat as evidence (read operation)
            accumulator.evidence.append(Evidence(
                source=tool_name,
                retrieved_at=start_time,
                tool_name=tool_name,
                tool_args=tool_args,
                snapshot={"output": tool_output} if tool_output else None,
            ))

    def _handle_guardrail_span(self, span: "Span", accumulator: "_TraceAccumulator"):
        """Process a guardrail check span."""
        attributes = _safe_get(span, "attributes", {})
        passed = attributes.get("guardrail.passed", True)

        accumulator.policies.append(PolicyEval(
            policy_id=attributes.get("guardrail.name") or _safe_get(span, "name", "guardrail"),
            version="1.0",
            result=PolicyResult.PASS if passed else PolicyResult.FAIL,
            message=str(attributes.get("guardrail.triggered_rules", [])),
        ))

        if not passed:
            accumulator.success = False
            accumulator.outcome_reason = f"Guardrail {attributes.get('guardrail.name', 'unknown')} blocked"

    def _handle_handoff_span(self, span: "Span", accumulator: "_TraceAccumulator"):
        """Process an agent handoff span."""
        attributes = _safe_get(span, "attributes", {})
        handoffs = accumulator.metadata.setdefault("handoffs", [])
        handoffs.append({
            "from": attributes.get("handoff.from_agent"),
            "to": attributes.get("handoff.to_agent"),
            "reason": attributes.get("handoff.reason"),
        })

    def shutdown(self) -> None:
        """Cleanup resources. Call this before application exit."""
        self.force_flush()
        self.client.close()
        logger.debug("ContextGraphTraceProcessor shutdown complete")

    def force_flush(self) -> None:
        """Force flush any pending data."""
        self.client.flush()


def _safe_get(obj: Any, attr: str, default: Any = None) -> Any:
    """Safely get an attribute from an object, supporting both dict and object access."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


@dataclass
class _TraceAccumulator:
    """Internal state for accumulating span data into a DecisionRecord."""
    trace_id: str
    run_id: str
    name: str
    start_time: datetime
    metadata: dict[str, Any]
    evidence: list[Evidence] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    policies: list[PolicyEval] = field(default_factory=list)
    success: bool = True
    outcome_reason: Optional[str] = None
