"""LangGraph integration - Checkpoint wrapper for DecisionRecords.

Usage:
    from langgraph.checkpoint.memory import MemorySaver
    from contextgraph.integrations.langgraph import ContextGraphCheckpointer

    cg_checkpointer = ContextGraphCheckpointer(
        underlying=MemorySaver(),
        write_tools=["send_email", "update_crm"],
        state_keys_as_evidence=["account_data", "customer_info"],
    )

    graph = builder.compile(checkpointer=cg_checkpointer)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Iterator, Sequence, TYPE_CHECKING
from dataclasses import dataclass, field

from contextgraph.core.client import ContextGraphClient
from contextgraph.core.models import (
    DecisionRecord, Evidence, Action, Approval, Outcome,
    Actor, ActorType
)
from contextgraph.core.config import Config

logger = logging.getLogger(__name__)

# Type checking - actual types from LangGraph
if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


@dataclass
class _ThreadAccumulator:
    """Internal state for accumulating checkpoint data into a DecisionRecord."""
    thread_id: str
    start_time: datetime
    evidence: list[Evidence] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    approvals: list[Approval] = field(default_factory=list)
    last_step: int = 0
    pending_interrupt: bool = False
    seen_ids: set = field(default_factory=set)


class ContextGraphCheckpointer:
    """Wrapper checkpointer that emits DecisionRecords from LangGraph state.

    This wraps any LangGraph checkpointer (like MemorySaver) and automatically
    captures tool calls from the graph execution into ContextGraph DecisionRecords.

    Example:
        >>> from langgraph.checkpoint.memory import MemorySaver
        >>> from contextgraph.integrations.langgraph import ContextGraphCheckpointer
        >>>
        >>> checkpointer = ContextGraphCheckpointer(
        ...     underlying=MemorySaver(),
        ...     write_tools=["send_email", "create_ticket"],
        ...     state_keys_as_evidence=["customer_data"],
        ... )
        >>>
        >>> graph = builder.compile(checkpointer=checkpointer)
        >>> result = graph.invoke({"messages": [...]}, config={"configurable": {"thread_id": "123"}})
        >>> checkpointer.finalize_thread({"configurable": {"thread_id": "123"}})
    """

    def __init__(
        self,
        underlying: Any,  # BaseCheckpointSaver from LangGraph
        client: Optional[ContextGraphClient] = None,
        config: Optional[Config] = None,
        write_tools: Optional[list[str]] = None,
        read_tools: Optional[list[str]] = None,
        server_url: Optional[str] = None,
        state_keys_as_evidence: Optional[list[str]] = None,
        action_node_names: Optional[list[str]] = None,
    ):
        """Initialize the checkpointer wrapper.

        Args:
            underlying: The actual LangGraph checkpointer to wrap (e.g., MemorySaver)
            client: Optional pre-configured ContextGraphClient
            config: Optional Config object
            write_tools: List of tool names that are write operations (actions)
            read_tools: List of tool names that are read operations (evidence)
            server_url: URL of the ContextGraph server
            state_keys_as_evidence: State keys to capture as evidence snapshots
            action_node_names: Node names that should be treated as actions
        """
        self.underlying = underlying
        self.cfg = config or Config()

        if write_tools:
            self.cfg.write_tools = write_tools
        if read_tools:
            self.cfg.read_tools = read_tools
        if server_url:
            self.cfg.server_url = server_url

        self.client = client or ContextGraphClient(self.cfg)
        self.state_keys_as_evidence = state_keys_as_evidence or []
        self.action_node_names = action_node_names or []
        self._threads: dict[str, _ThreadAccumulator] = {}

    def _get_thread_id(self, config: dict) -> str:
        """Extract thread_id from config."""
        return config.get("configurable", {}).get("thread_id", "default")

    def _get_accumulator(self, config: dict) -> _ThreadAccumulator:
        """Get or create accumulator for a thread."""
        thread_id = self._get_thread_id(config)
        if thread_id not in self._threads:
            self._threads[thread_id] = _ThreadAccumulator(
                thread_id=thread_id,
                start_time=datetime.now(timezone.utc),
            )
        return self._threads[thread_id]

    # ==========================================================================
    # Checkpointer interface methods (delegate to underlying)
    # ==========================================================================

    def get_tuple(self, config: dict) -> Optional[Any]:
        """Get checkpoint tuple - delegates to underlying."""
        return self.underlying.get_tuple(config)

    def list(
        self,
        config: Optional[dict],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[dict] = None,
        limit: Optional[int] = None,
    ) -> Iterator[Any]:
        """List checkpoints - delegates to underlying."""
        return self.underlying.list(config, filter=filter, before=before, limit=limit)

    def put(
        self,
        config: dict,
        checkpoint: dict,
        metadata: Any,  # CheckpointMetadata
        new_versions: dict[str, int],
    ) -> dict:
        """Store checkpoint and extract decision data."""
        try:
            accumulator = self._get_accumulator(config)

            # Get step from metadata (handle both dict and object)
            step = _safe_get(metadata, "step", 0)
            accumulator.last_step = step

            # Extract evidence from state
            channel_values = checkpoint.get("channel_values", {})
            self._extract_state_evidence(channel_values, accumulator)

            # Check for writes from action nodes
            writes = _safe_get(metadata, "writes", {})
            if writes:
                self._process_writes(writes, accumulator)

            # Extract tool calls from messages
            messages = channel_values.get("messages", [])
            if messages:
                self._extract_tool_calls(messages, accumulator)

        except Exception as e:
            logger.warning(f"Error processing checkpoint: {e}")

        return self.underlying.put(config, checkpoint, metadata, new_versions)

    def put_writes(
        self,
        config: dict,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
    ) -> None:
        """Store writes - delegates to underlying."""
        return self.underlying.put_writes(config, writes, task_id)

    # ==========================================================================
    # Decision extraction logic
    # ==========================================================================

    def _extract_state_evidence(self, channel_values: dict, accumulator: _ThreadAccumulator):
        """Extract configured state keys as evidence."""
        for key in self.state_keys_as_evidence:
            if key in channel_values:
                evidence_id = f"state:{key}:{accumulator.last_step}"
                if evidence_id not in accumulator.seen_ids:
                    accumulator.seen_ids.add(evidence_id)
                    accumulator.evidence.append(Evidence(
                        evidence_id=evidence_id,
                        source=f"state:{key}",
                        retrieved_at=datetime.now(timezone.utc),
                        snapshot=self._safe_serialize(channel_values[key]),
                    ))

    def _process_writes(self, writes: dict, accumulator: _ThreadAccumulator):
        """Process node writes for action detection."""
        for node_name, write_data in writes.items():
            if node_name in self.action_node_names or self._looks_like_action(node_name, write_data):
                action_id = f"node:{node_name}:{accumulator.last_step}"
                if action_id not in accumulator.seen_ids:
                    accumulator.seen_ids.add(action_id)
                    accumulator.actions.append(Action(
                        action_id=action_id,
                        tool=node_name,
                        committed_at=datetime.now(timezone.utc),
                        params=self._safe_serialize(write_data),
                        success=True,
                    ))

    def _extract_tool_calls(self, messages: list, accumulator: _ThreadAccumulator):
        """Extract tool calls from LangGraph message format."""
        for msg in messages:
            tool_calls = self._get_tool_calls(msg)

            for tc in tool_calls:
                tc_id = tc.get("id") or str(uuid.uuid4())
                if tc_id in accumulator.seen_ids:
                    continue
                accumulator.seen_ids.add(tc_id)

                tool_name = tc.get("name") or tc.get("function", {}).get("name", "unknown")
                tool_args = tc.get("args") or tc.get("function", {}).get("arguments", {})

                # Parse JSON args if string
                if isinstance(tool_args, str):
                    try:
                        tool_args = json.loads(tool_args)
                    except (json.JSONDecodeError, TypeError):
                        tool_args = {"raw": tool_args}

                if self.cfg.is_write_tool(tool_name):
                    accumulator.actions.append(Action(
                        action_id=tc_id,
                        tool=tool_name,
                        committed_at=datetime.now(timezone.utc),
                        params=tool_args,
                        success=True,
                    ))
                else:
                    accumulator.evidence.append(Evidence(
                        evidence_id=tc_id,
                        source=tool_name,
                        retrieved_at=datetime.now(timezone.utc),
                        tool_name=tool_name,
                        tool_args=tool_args,
                    ))

    def _get_tool_calls(self, msg: Any) -> list:
        """Extract tool_calls from various message formats."""
        if isinstance(msg, dict):
            return msg.get("tool_calls", [])

        # Handle LangChain message objects
        if hasattr(msg, "tool_calls"):
            return msg.tool_calls or []
        if hasattr(msg, "additional_kwargs"):
            return msg.additional_kwargs.get("tool_calls", [])

        return []

    def _looks_like_action(self, node_name: str, write_data: Any) -> bool:
        """Heuristic to detect action nodes."""
        action_patterns = ["write", "send", "create", "update", "delete", "post", "put", "execute"]
        return any(p in node_name.lower() for p in action_patterns)

    def _safe_serialize(self, obj: Any) -> dict:
        """Safely serialize an object to a dict."""
        if isinstance(obj, dict):
            return obj
        try:
            return {"value": json.loads(json.dumps(obj, default=str))}
        except Exception:
            return {"value": str(obj)}

    # ==========================================================================
    # Human-in-the-loop support
    # ==========================================================================

    def on_interrupt(self, config: dict, interrupt_value: Any):
        """Call this when an interrupt occurs (human-in-the-loop pause).

        Args:
            config: The graph config containing thread_id
            interrupt_value: The value that triggered the interrupt
        """
        accumulator = self._get_accumulator(config)
        accumulator.pending_interrupt = True
        accumulator.evidence.append(Evidence(
            source="interrupt",
            retrieved_at=datetime.now(timezone.utc),
            snapshot=self._safe_serialize(interrupt_value),
        ))
        logger.debug(f"Interrupt recorded for thread {accumulator.thread_id}")

    def on_resume(self, config: dict, approver_id: str, resume_value: Any = None):
        """Call this when resuming from an interrupt (human approved).

        Args:
            config: The graph config containing thread_id
            approver_id: ID of the human who approved
            resume_value: Optional value provided during resume
        """
        accumulator = self._get_accumulator(config)
        if accumulator.pending_interrupt:
            accumulator.approvals.append(Approval(
                approver=Actor(type=ActorType.HUMAN, id=approver_id),
                granted=True,
                granted_at=datetime.now(timezone.utc),
                reason=str(resume_value) if resume_value else None,
            ))
            accumulator.pending_interrupt = False
            logger.debug(f"Resume approved by {approver_id} for thread {accumulator.thread_id}")

    # ==========================================================================
    # Finalization
    # ==========================================================================

    def finalize_thread(self, config: dict, success: bool = True) -> Optional[DecisionRecord]:
        """Finalize and emit DecisionRecord for a thread.

        Call this when the graph execution is complete.

        Args:
            config: The graph config containing thread_id
            success: Whether the execution was successful

        Returns:
            The created DecisionRecord, or None if no actions were recorded
        """
        thread_id = self._get_thread_id(config)
        accumulator = self._threads.pop(thread_id, None)

        if not accumulator:
            logger.debug(f"No accumulator found for thread {thread_id}")
            return None

        # Only create record if there were actions
        if not accumulator.actions:
            logger.debug(f"No actions for thread {thread_id}, skipping DecisionRecord")
            return None

        record = DecisionRecord(
            run_id=thread_id,
            timestamp=accumulator.start_time,
            outcome=Outcome.COMMITTED if success else Outcome.DENIED,
            actor=Actor(type=ActorType.AGENT, id="langgraph"),
            evidence=accumulator.evidence,
            actions=accumulator.actions,
            approvals=accumulator.approvals,
            metadata={"steps": accumulator.last_step},
        )

        self.client.ingest_decision(record)
        logger.info(f"Created DecisionRecord {record.decision_id} for thread {thread_id}")
        return record


def _safe_get(obj: Any, attr: str, default: Any = None) -> Any:
    """Safely get an attribute from an object, supporting both dict and object access."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


# ==========================================================================
# Async version
# ==========================================================================

class AsyncContextGraphCheckpointer(ContextGraphCheckpointer):
    """Async wrapper for LangGraph checkpointer.

    Use this with async LangGraph graphs.
    """

    async def aget_tuple(self, config: dict) -> Optional[Any]:
        """Async get checkpoint tuple."""
        return await self.underlying.aget_tuple(config)

    async def alist(
        self,
        config: Optional[dict],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[dict] = None,
        limit: Optional[int] = None,
    ):
        """Async list checkpoints."""
        async for item in self.underlying.alist(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(
        self,
        config: dict,
        checkpoint: dict,
        metadata: Any,
        new_versions: dict[str, int],
    ) -> dict:
        """Async store checkpoint and extract decision data."""
        try:
            accumulator = self._get_accumulator(config)
            step = _safe_get(metadata, "step", 0)
            accumulator.last_step = step

            channel_values = checkpoint.get("channel_values", {})
            self._extract_state_evidence(channel_values, accumulator)

            writes = _safe_get(metadata, "writes", {})
            if writes:
                self._process_writes(writes, accumulator)

            messages = channel_values.get("messages", [])
            if messages:
                self._extract_tool_calls(messages, accumulator)

        except Exception as e:
            logger.warning(f"Error processing checkpoint: {e}")

        return await self.underlying.aput(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: dict,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
    ) -> None:
        """Async store writes."""
        return await self.underlying.aput_writes(config, writes, task_id)
