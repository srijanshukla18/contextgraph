"""Tests for the Claude Agent SDK integration."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from contextgraph.core.config import Config
from contextgraph.core.models import PolicyResult, Outcome
from contextgraph.integrations.claude_agent import (
    contextgraph_hooks,
    ContextGraphHooks,
    ContextGraphPreToolUseHook,
    ContextGraphPostToolUseHook,
    ContextGraphStopHook,
    _RunAccumulator,
)


@pytest.fixture
def mock_client():
    """Create a mock ContextGraphClient."""
    client = MagicMock()
    client.ingest_decision = MagicMock(return_value=True)
    return client


@pytest.fixture
def config():
    """Create a test config."""
    return Config(
        server_url="http://localhost:8080",
        write_tools=["Bash", "Write", "Edit"],
        read_tools=["Read", "Glob", "Grep"],
    )


@pytest.fixture
def accumulator():
    """Create a fresh accumulator."""
    return _RunAccumulator(
        run_id=str(uuid.uuid4()),
        start_time=datetime.now(timezone.utc),
        agent_name="test-agent",
    )


class TestContextGraphHooksFactory:
    """Tests for the contextgraph_hooks() factory function."""

    def test_creates_hooks_dict(self, mock_client):
        """Factory returns dict with all three hooks."""
        hooks = contextgraph_hooks(client=mock_client)

        assert "pre_tool_use" in hooks
        assert "post_tool_use" in hooks
        assert "stop" in hooks

    def test_configures_write_tools(self, mock_client):
        """Factory configures write tools correctly."""
        hooks = contextgraph_hooks(
            client=mock_client,
            write_tools=["CustomWrite"],
        )

        post_hook = hooks["post_tool_use"]
        assert "CustomWrite" in post_hook.config.write_tools

    def test_passes_policies_to_pre_hook(self, mock_client):
        """Factory passes policies to PreToolUse hook."""
        def my_policy(name, input, ctx):
            return {"passed": True}

        hooks = contextgraph_hooks(
            client=mock_client,
            policies={"test_policy": my_policy},
        )

        pre_hook = hooks["pre_tool_use"]
        assert "test_policy" in pre_hook.policies


class TestContextGraphHooksClass:
    """Tests for the ContextGraphHooks class."""

    def test_class_creates_hooks(self, mock_client):
        """Class creates hooks correctly."""
        hooks = ContextGraphHooks(
            client=mock_client,
            write_tools=["Bash"],
        )

        assert hooks.pre_tool_use is not None
        assert hooks.post_tool_use is not None
        assert hooks.stop is not None

    def test_as_dict_returns_hooks(self, mock_client):
        """as_dict() returns the hooks dictionary."""
        hooks = ContextGraphHooks(client=mock_client)
        hooks_dict = hooks.as_dict()

        assert isinstance(hooks_dict, dict)
        assert "pre_tool_use" in hooks_dict


class TestPreToolUseHook:
    """Tests for the PreToolUse hook."""

    @pytest.mark.asyncio
    async def test_allows_when_no_policies(self, config, accumulator):
        """Hook allows when no policies are configured."""
        hook = ContextGraphPreToolUseHook(accumulator, config, policies={})

        result = await hook("Read", {"file_path": "/tmp/test"})

        assert result["allow"] is True

    @pytest.mark.asyncio
    async def test_allows_when_policy_passes(self, config, accumulator):
        """Hook allows when policy returns passed=True."""
        def pass_policy(name, input, ctx):
            return {"passed": True}

        hook = ContextGraphPreToolUseHook(
            accumulator, config,
            policies={"pass_policy": pass_policy}
        )

        result = await hook("Read", {"file_path": "/tmp/test"})

        assert result["allow"] is True
        assert len(accumulator.policies) == 1
        assert accumulator.policies[0].result == PolicyResult.PASS

    @pytest.mark.asyncio
    async def test_blocks_when_policy_fails(self, config, accumulator):
        """Hook blocks when policy returns passed=False."""
        def fail_policy(name, input, ctx):
            return {"passed": False, "message": "Not allowed"}

        hook = ContextGraphPreToolUseHook(
            accumulator, config,
            policies={"fail_policy": fail_policy}
        )

        result = await hook("Bash", {"command": "rm -rf /"})

        assert result["allow"] is False
        assert "Not allowed" in result.get("reason", "")
        assert len(accumulator.blocked_tools) == 1

    @pytest.mark.asyncio
    async def test_records_policy_failures(self, config, accumulator):
        """Hook records failed policy evaluations."""
        def fail_policy(name, input, ctx):
            return {"passed": False, "message": "Blocked"}

        hook = ContextGraphPreToolUseHook(
            accumulator, config,
            policies={"fail_policy": fail_policy}
        )

        await hook("Write", {"content": "test"})

        assert len(accumulator.policies) == 1
        assert accumulator.policies[0].result == PolicyResult.FAIL
        assert accumulator.policies[0].message == "Blocked"

    @pytest.mark.asyncio
    async def test_handles_policy_exceptions(self, config, accumulator):
        """Hook handles policy exceptions gracefully."""
        def error_policy(name, input, ctx):
            raise ValueError("Policy error")

        hook = ContextGraphPreToolUseHook(
            accumulator, config,
            policies={"error_policy": error_policy}
        )

        result = await hook("Read", {})

        # Should allow (fail open) but record warning
        assert result["allow"] is True
        assert len(accumulator.policies) == 1
        assert accumulator.policies[0].result == PolicyResult.WARN

    @pytest.mark.asyncio
    async def test_runs_all_policies(self, config, accumulator):
        """Hook runs all configured policies."""
        def policy1(n, i, c):
            return {"passed": True}

        def policy2(n, i, c):
            return {"passed": True}

        hook = ContextGraphPreToolUseHook(
            accumulator, config,
            policies={"p1": policy1, "p2": policy2}
        )

        await hook("Read", {})

        assert len(accumulator.policies) == 2

    @pytest.mark.asyncio
    async def test_stops_on_first_failure(self, config, accumulator):
        """Hook stops running policies after first failure."""
        call_count = [0]

        def policy1(n, i, c):
            call_count[0] += 1
            return {"passed": False, "message": "First fails"}

        def policy2(n, i, c):
            call_count[0] += 1
            return {"passed": True}

        hook = ContextGraphPreToolUseHook(
            accumulator, config,
            policies={"p1": policy1, "p2": policy2}
        )

        await hook("Write", {})

        # Policy 2 should not be called
        assert call_count[0] == 1


class TestPostToolUseHook:
    """Tests for the PostToolUse hook."""

    @pytest.mark.asyncio
    async def test_records_write_tool_as_action(self, config, accumulator):
        """Hook records write tools as actions."""
        hook = ContextGraphPostToolUseHook(accumulator, config)

        await hook(
            "Write",
            {"file_path": "/tmp/test.txt", "content": "hello"},
            "File written",
        )

        assert len(accumulator.actions) == 1
        assert accumulator.actions[0].tool == "Write"
        assert "/tmp/test.txt" in str(accumulator.actions[0].params)

    @pytest.mark.asyncio
    async def test_records_read_tool_as_evidence(self, config, accumulator):
        """Hook records read tools as evidence."""
        hook = ContextGraphPostToolUseHook(accumulator, config)

        await hook(
            "Read",
            {"file_path": "/tmp/test.txt"},
            "file contents here",
        )

        assert len(accumulator.evidence) == 1
        assert accumulator.evidence[0].source == "Read"
        assert accumulator.evidence[0].tool_name == "Read"

    @pytest.mark.asyncio
    async def test_marks_failed_actions(self, config, accumulator):
        """Hook marks actions as failed when error provided."""
        hook = ContextGraphPostToolUseHook(accumulator, config)

        await hook(
            "Bash",
            {"command": "false"},
            "",
            error="Command failed",
        )

        assert len(accumulator.actions) == 1
        assert accumulator.actions[0].success is False
        assert accumulator.success is False

    @pytest.mark.asyncio
    async def test_parses_json_output(self, config, accumulator):
        """Hook parses JSON string output."""
        hook = ContextGraphPostToolUseHook(accumulator, config)

        await hook(
            "Read",
            {},
            '{"key": "value"}',
        )

        assert accumulator.evidence[0].snapshot == {"key": "value"}

    @pytest.mark.asyncio
    async def test_handles_non_json_output(self, config, accumulator):
        """Hook handles non-JSON output gracefully."""
        hook = ContextGraphPostToolUseHook(accumulator, config)

        await hook(
            "Read",
            {},
            "plain text output",
        )

        assert accumulator.evidence[0].snapshot == {"output": "plain text output"}


class TestStopHook:
    """Tests for the Stop hook."""

    @pytest.mark.asyncio
    async def test_creates_decision_record(self, mock_client, accumulator):
        """Hook creates DecisionRecord on stop."""
        # Add an action so record is created
        from contextgraph.core.models import Action
        accumulator.actions.append(Action(
            tool="Bash",
            committed_at=datetime.now(timezone.utc),
            params={"command": "echo hello"},
            success=True,
        ))

        hook = ContextGraphStopHook(accumulator, mock_client)
        result = await hook()

        assert result["allow"] is True
        mock_client.ingest_decision.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_when_no_actions(self, mock_client, accumulator):
        """Hook skips record creation when no actions."""
        hook = ContextGraphStopHook(accumulator, mock_client)
        result = await hook()

        assert result["allow"] is True
        mock_client.ingest_decision.assert_not_called()

    @pytest.mark.asyncio
    async def test_sets_denied_outcome_on_error(self, mock_client, accumulator):
        """Hook sets DENIED outcome when stop_reason is ERROR."""
        from contextgraph.core.models import Action
        accumulator.actions.append(Action(
            tool="Bash",
            committed_at=datetime.now(timezone.utc),
            success=False,
        ))

        hook = ContextGraphStopHook(accumulator, mock_client)
        await hook(stop_reason="ERROR")

        call_args = mock_client.ingest_decision.call_args
        record = call_args[0][0]
        assert record.outcome == Outcome.DENIED

    @pytest.mark.asyncio
    async def test_sets_denied_when_blocked(self, mock_client, accumulator):
        """Hook sets DENIED outcome when tools were blocked."""
        from contextgraph.core.models import Action
        accumulator.actions.append(Action(
            tool="Bash",
            committed_at=datetime.now(timezone.utc),
            success=True,
        ))
        accumulator.blocked_tools.append({"tool": "Write", "reason": "Blocked"})

        hook = ContextGraphStopHook(accumulator, mock_client)
        await hook()

        call_args = mock_client.ingest_decision.call_args
        record = call_args[0][0]
        assert record.outcome == Outcome.DENIED
        assert "Blocked" in record.outcome_reason

    @pytest.mark.asyncio
    async def test_includes_all_data(self, mock_client, accumulator):
        """Hook includes evidence, actions, policies in record."""
        from contextgraph.core.models import Action, Evidence, PolicyEval

        accumulator.evidence.append(Evidence(
            source="Read",
            retrieved_at=datetime.now(timezone.utc),
        ))
        accumulator.actions.append(Action(
            tool="Write",
            committed_at=datetime.now(timezone.utc),
            success=True,
        ))
        accumulator.policies.append(PolicyEval(
            policy_id="test",
            version="1.0",
            result=PolicyResult.PASS,
        ))

        hook = ContextGraphStopHook(accumulator, mock_client)
        await hook()

        call_args = mock_client.ingest_decision.call_args
        record = call_args[0][0]

        assert len(record.evidence) == 1
        assert len(record.actions) == 1
        assert len(record.policies) == 1


class TestPolicyPatterns:
    """Tests for common policy patterns."""

    @pytest.mark.asyncio
    async def test_destructive_command_blocking(self, config, accumulator):
        """Policy can block destructive commands."""
        def no_destructive(name, input, ctx):
            if name == "Bash":
                cmd = input.get("command", "")
                if "rm -rf" in cmd or "DROP TABLE" in cmd:
                    return {"passed": False, "message": "Destructive command blocked"}
            return {"passed": True}

        hook = ContextGraphPreToolUseHook(
            accumulator, config,
            policies={"no_destructive": no_destructive}
        )

        result = await hook("Bash", {"command": "rm -rf /"})
        assert result["allow"] is False

        result = await hook("Bash", {"command": "echo hello"})
        assert result["allow"] is True

    @pytest.mark.asyncio
    async def test_path_validation(self, config, accumulator):
        """Policy can validate file paths."""
        def valid_paths(name, input, ctx):
            if name in ["Write", "Edit"]:
                path = input.get("file_path", "")
                if path.startswith("/etc/") or path.startswith("/sys/"):
                    return {"passed": False, "message": "Cannot write to system paths"}
            return {"passed": True}

        hook = ContextGraphPreToolUseHook(
            accumulator, config,
            policies={"valid_paths": valid_paths}
        )

        result = await hook("Write", {"file_path": "/etc/passwd"})
        assert result["allow"] is False

        result = await hook("Write", {"file_path": "/home/user/test.txt"})
        assert result["allow"] is True


class TestIntegration:
    """Integration tests for the full hook flow."""

    @pytest.mark.asyncio
    async def test_full_flow(self, mock_client):
        """Test full pre -> post -> stop flow."""
        hooks = contextgraph_hooks(
            client=mock_client,
            write_tools=["Write"],
            read_tools=["Read"],
        )

        # Simulate a read
        result = await hooks["pre_tool_use"]("Read", {"file_path": "/tmp/test"})
        assert result["allow"] is True

        await hooks["post_tool_use"](
            "Read",
            {"file_path": "/tmp/test"},
            "file contents",
        )

        # Simulate a write
        result = await hooks["pre_tool_use"]("Write", {"file_path": "/tmp/out"})
        assert result["allow"] is True

        await hooks["post_tool_use"](
            "Write",
            {"file_path": "/tmp/out", "content": "output"},
            "success",
        )

        # Stop
        await hooks["stop"](stop_reason="COMPLETED")

        # Verify record was created
        mock_client.ingest_decision.assert_called_once()
        record = mock_client.ingest_decision.call_args[0][0]

        assert len(record.evidence) == 1
        assert len(record.actions) == 1
        assert record.outcome == Outcome.COMMITTED
