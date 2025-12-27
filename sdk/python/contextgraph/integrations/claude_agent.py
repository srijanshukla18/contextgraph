"""Claude Agent SDK integration - Hooks for DecisionRecords.

Usage:
    from claude_agent_sdk import Agent, AgentConfig
    from contextgraph.integrations.claude_agent import contextgraph_hooks

    hooks = contextgraph_hooks(
        write_tools=["Bash", "Write", "Edit"],
        server_url="http://localhost:8080",
    )

    agent = Agent(config=AgentConfig(
        model="claude-sonnet-4-5-20250929",
        hooks=hooks
    ))

See: https://github.com/anthropics/claude-agent-sdk-python
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING
from dataclasses import dataclass, field

from contextgraph.core.client import ContextGraphClient
from contextgraph.core.models import (
    DecisionRecord, Evidence, Action, PolicyEval, Approval, Outcome, PolicyResult,
    Actor, ActorType
)
from contextgraph.core.config import Config

logger = logging.getLogger(__name__)

# Type checking - actual types come from Claude SDK
if TYPE_CHECKING:
    pass  # Claude SDK types would go here


@dataclass
class _RunAccumulator:
    """Internal state for accumulating tool calls into a DecisionRecord."""
    run_id: str
    start_time: datetime
    agent_name: str = "claude-agent"
    evidence: list[Evidence] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    policies: list[PolicyEval] = field(default_factory=list)
    approvals: list[Approval] = field(default_factory=list)
    blocked_tools: list[dict] = field(default_factory=list)
    success: bool = True
    outcome_reason: Optional[str] = None


class ContextGraphPreToolUseHook:
    """PreToolUse hook that captures intended actions and applies policies.

    This hook runs BEFORE a tool is executed. Use it to:
    - Apply policy checks (e.g., "don't allow sending emails without approval")
    - Log intended actions
    - Block dangerous operations
    """

    def __init__(
        self,
        accumulator: _RunAccumulator,
        config: Config,
        policies: Optional[dict[str, callable]] = None,
    ):
        self.accumulator = accumulator
        self.config = config
        self.policies = policies or {}

    async def __call__(
        self,
        tool_name: str,
        tool_input: dict,
        **kwargs,  # Accept additional context from SDK
    ) -> dict:
        """Called before tool execution.

        Returns:
            Dict with 'allow' (bool), optional 'reason' (str), optional 'modified_input' (dict)
        """
        try:
            # Run any registered policies
            for policy_id, policy_fn in self.policies.items():
                try:
                    result = policy_fn(tool_name, tool_input, kwargs)
                    passed = result.get("passed", True) if isinstance(result, dict) else bool(result)
                    message = result.get("message") if isinstance(result, dict) else None

                    self.accumulator.policies.append(PolicyEval(
                        policy_id=policy_id,
                        version="1.0",
                        result=PolicyResult.PASS if passed else PolicyResult.FAIL,
                        message=message,
                    ))

                    if not passed:
                        self.accumulator.blocked_tools.append({
                            "tool": tool_name,
                            "reason": message,
                        })
                        logger.info(f"Policy {policy_id} blocked tool {tool_name}: {message}")
                        return {"allow": False, "reason": message or "Policy check failed"}

                except Exception as e:
                    logger.warning(f"Policy {policy_id} error: {e}")
                    self.accumulator.policies.append(PolicyEval(
                        policy_id=policy_id,
                        version="1.0",
                        result=PolicyResult.WARN,
                        message=str(e),
                    ))

            return {"allow": True}

        except Exception as e:
            logger.error(f"PreToolUse hook error: {e}")
            return {"allow": True}  # Fail open


class ContextGraphPostToolUseHook:
    """PostToolUse hook that records evidence and actions.

    This hook runs AFTER a tool is executed. Use it to:
    - Record tool outputs as evidence (read operations)
    - Record tool outputs as actions (write operations)
    - Track errors
    """

    def __init__(self, accumulator: _RunAccumulator, config: Config):
        self.accumulator = accumulator
        self.config = config

    async def __call__(
        self,
        tool_name: str,
        tool_input: dict,
        tool_output: Any,
        error: Optional[str] = None,
        duration_ms: Optional[float] = None,
        **kwargs,
    ) -> dict:
        """Called after tool execution.

        Returns:
            Dict with optional 'modified_output' to change what the agent sees
        """
        try:
            now = datetime.now(timezone.utc)

            # Parse output
            output_data = tool_output
            if isinstance(tool_output, str):
                try:
                    import json
                    output_data = json.loads(tool_output)
                except (json.JSONDecodeError, TypeError):
                    output_data = {"output": tool_output}
            elif not isinstance(tool_output, dict):
                output_data = {"value": tool_output}

            if self.config.is_write_tool(tool_name):
                self.accumulator.actions.append(Action(
                    tool=tool_name,
                    committed_at=now,
                    params=tool_input,
                    result=output_data,
                    success=error is None,
                ))
                if error:
                    self.accumulator.success = False
                    self.accumulator.outcome_reason = f"Tool {tool_name} failed: {error}"
            else:
                self.accumulator.evidence.append(Evidence(
                    source=tool_name,
                    retrieved_at=now,
                    tool_name=tool_name,
                    tool_args=tool_input,
                    snapshot=output_data,
                ))

            return {}  # No modification

        except Exception as e:
            logger.error(f"PostToolUse hook error: {e}")
            return {}


class ContextGraphStopHook:
    """Stop hook that finalizes the DecisionRecord.

    This hook runs when the agent stops (either naturally or due to error).
    It creates and submits the final DecisionRecord.
    """

    def __init__(
        self,
        accumulator: _RunAccumulator,
        client: ContextGraphClient,
    ):
        self.accumulator = accumulator
        self.client = client

    async def __call__(
        self,
        stop_reason: str = "COMPLETED",
        **kwargs,
    ) -> dict:
        """Called when agent stops.

        Returns:
            Dict with optional 'continue_message' to keep the agent running
        """
        try:
            # Only create DecisionRecord if there were actions
            if not self.accumulator.actions:
                logger.debug("No actions recorded, skipping DecisionRecord")
                return {"allow": True}

            # Determine outcome
            outcome = Outcome.COMMITTED
            reason = stop_reason

            if stop_reason in ("ERROR", "TOOL_ERROR"):
                outcome = Outcome.DENIED
            elif stop_reason == "USER_CANCEL":
                outcome = Outcome.DENIED
            elif self.accumulator.blocked_tools:
                outcome = Outcome.DENIED
                reason = f"Blocked by policy: {self.accumulator.blocked_tools[0].get('reason')}"
            elif not self.accumulator.success:
                outcome = Outcome.DENIED

            if self.accumulator.outcome_reason:
                reason = self.accumulator.outcome_reason

            record = DecisionRecord(
                run_id=self.accumulator.run_id,
                timestamp=self.accumulator.start_time,
                outcome=outcome,
                outcome_reason=reason,
                actor=Actor(type=ActorType.AGENT, id=self.accumulator.agent_name),
                evidence=self.accumulator.evidence,
                actions=self.accumulator.actions,
                policies=self.accumulator.policies,
                approvals=self.accumulator.approvals,
            )

            self.client.ingest_decision(record)
            logger.info(f"Created DecisionRecord {record.decision_id}")

            return {"allow": True}

        except Exception as e:
            logger.error(f"Stop hook error: {e}")
            return {"allow": True}


def contextgraph_hooks(
    client: Optional[ContextGraphClient] = None,
    config: Optional[Config] = None,
    write_tools: Optional[list[str]] = None,
    read_tools: Optional[list[str]] = None,
    policies: Optional[dict[str, callable]] = None,
    server_url: Optional[str] = None,
    agent_name: str = "claude-agent",
) -> dict:
    """Create a hooks preset for Claude Agent SDK.

    This returns a dictionary of hooks that can be passed to AgentConfig.

    Args:
        client: Optional pre-configured ContextGraphClient
        config: Optional Config object
        write_tools: List of tool names that are write operations (actions)
        read_tools: List of tool names that are read operations (evidence)
        policies: Dict of policy_id -> policy_fn for pre-tool checks
            Policy functions receive (tool_name, tool_input, context) and return
            {"passed": bool, "message": str}
        server_url: URL of the ContextGraph server
        agent_name: Name to use for the agent actor

    Returns:
        Dict suitable for AgentConfig.hooks

    Example:
        >>> hooks = contextgraph_hooks(
        ...     write_tools=["Bash", "Write", "Edit"],
        ...     policies={
        ...         "no_destructive": lambda name, input, ctx: {
        ...             "passed": "rm -rf" not in str(input),
        ...             "message": "Destructive command blocked"
        ...         }
        ...     }
        ... )
        >>> agent = Agent(config=AgentConfig(hooks=hooks))
    """
    cfg = config or Config()

    if write_tools:
        cfg.write_tools = write_tools
    if read_tools:
        cfg.read_tools = read_tools
    if server_url:
        cfg.server_url = server_url

    cg_client = client or ContextGraphClient(cfg)

    accumulator = _RunAccumulator(
        run_id=str(uuid.uuid4()),
        start_time=datetime.now(timezone.utc),
        agent_name=agent_name,
    )

    return {
        "pre_tool_use": ContextGraphPreToolUseHook(accumulator, cfg, policies),
        "post_tool_use": ContextGraphPostToolUseHook(accumulator, cfg),
        "stop": ContextGraphStopHook(accumulator, cg_client),
    }


# Convenience class for those who prefer class-based hooks
class ContextGraphHooks:
    """Class-based hooks for Claude Agent SDK.

    Alternative to contextgraph_hooks() for those who prefer classes.

    Example:
        >>> hooks = ContextGraphHooks(write_tools=["Bash", "Write"])
        >>> agent = Agent(config=AgentConfig(hooks=hooks.as_dict()))
    """

    def __init__(
        self,
        client: Optional[ContextGraphClient] = None,
        config: Optional[Config] = None,
        write_tools: Optional[list[str]] = None,
        read_tools: Optional[list[str]] = None,
        policies: Optional[dict[str, callable]] = None,
        server_url: Optional[str] = None,
        agent_name: str = "claude-agent",
    ):
        self._hooks = contextgraph_hooks(
            client=client,
            config=config,
            write_tools=write_tools,
            read_tools=read_tools,
            policies=policies,
            server_url=server_url,
            agent_name=agent_name,
        )

    def as_dict(self) -> dict:
        """Return hooks as a dictionary."""
        return self._hooks

    @property
    def pre_tool_use(self):
        return self._hooks["pre_tool_use"]

    @property
    def post_tool_use(self):
        return self._hooks["post_tool_use"]

    @property
    def stop(self):
        return self._hooks["stop"]
