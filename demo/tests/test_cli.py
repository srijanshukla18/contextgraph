"""Tests for the demo CLI module."""

import argparse
import json
import pytest
from io import StringIO
from unittest.mock import patch, MagicMock
from datetime import datetime

from demo.cli import format_explain, cmd_run, cmd_explain, cmd_demo, main


class TestFormatExplain:
    """Tests for the format_explain function."""

    @pytest.fixture
    def sample_record(self):
        """Create a sample decision record for testing."""
        return {
            "decision_id": "dec_123",
            "run_id": "run_456",
            "timestamp": "2025-01-01T12:00:00",
            "outcome": "committed",
            "outcome_reason": "All checks passed",
            "evidence": [
                {
                    "source": "crm.get_account",
                    "tool_name": "get_account",
                    "retrieved_at": "2025-01-01T11:55:00",
                    "snapshot": {"arr": 500000, "name": "Acme Corp"},
                }
            ],
            "policies": [
                {
                    "policy_id": "service_credit",
                    "version": "1.0",
                    "result": "pass",
                    "message": "Within limits",
                }
            ],
            "approvals": [],
            "actions": [
                {
                    "tool": "billing.create_credit",
                    "committed_at": "2025-01-01T12:00:00",
                    "success": True,
                    "params": {"amount": 5000, "credit_pct": 0.12},
                    "result": {"credit_id": "CR-789"},
                }
            ],
        }

    def test_format_explain_returns_string(self, sample_record):
        """format_explain returns a string."""
        result = format_explain(sample_record)
        assert isinstance(result, str)

    def test_format_explain_includes_header(self, sample_record):
        """format_explain includes header section."""
        result = format_explain(sample_record)

        assert "DECISION EXPLANATION" in result
        assert "dec_123" in result
        assert "run_456" in result

    def test_format_explain_includes_outcome(self, sample_record):
        """format_explain includes outcome."""
        result = format_explain(sample_record)

        assert "COMMITTED" in result
        assert "All checks passed" in result

    def test_format_explain_includes_evidence_chain(self, sample_record):
        """format_explain includes evidence chain."""
        result = format_explain(sample_record)

        assert "EVIDENCE CHAIN" in result
        assert "crm.get_account" in result

    def test_format_explain_includes_policy_chain(self, sample_record):
        """format_explain includes policy chain."""
        result = format_explain(sample_record)

        assert "POLICY CHAIN" in result
        assert "service_credit" in result

    def test_format_explain_includes_action_chain(self, sample_record):
        """format_explain includes action chain."""
        result = format_explain(sample_record)

        assert "ACTION CHAIN" in result
        assert "billing.create_credit" in result

    def test_format_explain_includes_summary(self, sample_record):
        """format_explain includes summary section."""
        result = format_explain(sample_record)

        assert "SUMMARY" in result

    def test_format_explain_no_approvals_message(self, sample_record):
        """format_explain shows message when no approvals."""
        result = format_explain(sample_record)

        assert "No approvals required" in result

    def test_format_explain_with_approvals(self, sample_record):
        """format_explain formats approvals correctly."""
        sample_record["approvals"] = [
            {
                "approver": {"id": "manager@test.com", "name": "Manager"},
                "granted": True,
                "granted_at": "2025-01-01T11:58:00",
                "reason": "Approved for impact",
            }
        ]

        result = format_explain(sample_record)

        assert "APPROVED" in result
        assert "manager@test.com" in result

    def test_format_explain_denied_approval(self, sample_record):
        """format_explain formats denied approvals correctly."""
        sample_record["approvals"] = [
            {
                "approver": {"id": "manager@test.com", "name": ""},
                "granted": False,
                "granted_at": "2025-01-01T11:58:00",
                "reason": "Insufficient justification",
            }
        ]

        result = format_explain(sample_record)

        assert "DENIED" in result

    def test_format_explain_ticket_evidence(self, sample_record):
        """format_explain formats ticket evidence with credit info."""
        sample_record["evidence"][0]["snapshot"] = {
            "requested_credit_pct": 0.20,
            "subject": "Credit request",
        }

        result = format_explain(sample_record)

        assert "20%" in result
        assert "Credit request" in result

    def test_format_explain_incident_evidence(self, sample_record):
        """format_explain formats incident evidence."""
        sample_record["evidence"][0]["snapshot"] = {
            "sev1_count": 3,
            "sev2_count": 5,
            "total_downtime_mins": 120,
        }

        result = format_explain(sample_record)

        assert "SEV-1: 3" in result
        assert "SEV-2: 5" in result
        assert "120" in result

    def test_format_explain_empty_evidence(self):
        """format_explain handles empty evidence."""
        record = {
            "decision_id": "dec_123",
            "run_id": "run_456",
            "timestamp": "2025-01-01T12:00:00",
            "outcome": "denied",
            "evidence": [],
            "policies": [],
            "approvals": [],
            "actions": [],
        }

        result = format_explain(record)

        assert "EVIDENCE CHAIN (0 items)" in result

    def test_format_explain_failed_action(self, sample_record):
        """format_explain shows failed action status."""
        sample_record["actions"][0]["success"] = False

        result = format_explain(sample_record)

        assert "FAILED" in result


class TestCmdRun:
    """Tests for the cmd_run function."""

    @patch("time.sleep")
    def test_cmd_run_processes_ticket(self, mock_sleep):
        """cmd_run processes the specified ticket."""
        args = argparse.Namespace(ticket="SUP-4400", explain=False, json=False)

        result = cmd_run(args)

        assert "decision_id" in result
        assert "outcome" in result

    @patch("time.sleep")
    @patch("builtins.print")
    def test_cmd_run_with_explain(self, mock_print, mock_sleep):
        """cmd_run shows explanation when --explain flag set."""
        args = argparse.Namespace(ticket="SUP-4400", explain=True, json=False)

        cmd_run(args)

        # Check that format_explain output was printed
        calls = [str(c) for c in mock_print.call_args_list]
        printed_text = " ".join(calls)
        assert "DECISION EXPLANATION" in printed_text

    @patch("time.sleep")
    @patch("builtins.print")
    def test_cmd_run_with_json(self, mock_print, mock_sleep):
        """cmd_run shows JSON when --json flag set."""
        args = argparse.Namespace(ticket="SUP-4400", explain=False, json=True)

        cmd_run(args)

        # Check that JSON was printed
        calls = [str(c) for c in mock_print.call_args_list]
        printed_text = " ".join(calls)
        assert "RAW JSON" in printed_text


class TestCmdExplain:
    """Tests for the cmd_explain function."""

    def test_cmd_explain_from_file(self, tmp_path):
        """cmd_explain reads from file."""
        record = {
            "decision_id": "dec_123",
            "run_id": "run_456",
            "timestamp": "2025-01-01T12:00:00",
            "outcome": "committed",
            "evidence": [],
            "policies": [],
            "approvals": [],
            "actions": [],
        }

        file_path = tmp_path / "record.json"
        file_path.write_text(json.dumps(record))

        args = argparse.Namespace(file=str(file_path))

        with patch("builtins.print") as mock_print:
            cmd_explain(args)

            calls = [str(c) for c in mock_print.call_args_list]
            printed_text = " ".join(calls)
            assert "DECISION EXPLANATION" in printed_text

    def test_cmd_explain_extracts_nested_record(self, tmp_path):
        """cmd_explain extracts 'record' key if present."""
        data = {
            "decision_id": "dec_outer",
            "record": {
                "decision_id": "dec_123",
                "run_id": "run_456",
                "timestamp": "2025-01-01T12:00:00",
                "outcome": "committed",
                "evidence": [],
                "policies": [],
                "approvals": [],
                "actions": [],
            }
        }

        file_path = tmp_path / "record.json"
        file_path.write_text(json.dumps(data))

        args = argparse.Namespace(file=str(file_path))

        with patch("builtins.print") as mock_print:
            cmd_explain(args)

            calls = [str(c) for c in mock_print.call_args_list]
            printed_text = " ".join(calls)
            # Should use the nested record's decision_id
            assert "dec_123" in printed_text


class TestCmdDemo:
    """Tests for the cmd_demo function."""

    @patch("time.sleep")
    @patch("builtins.print")
    def test_cmd_demo_runs_both_tickets(self, mock_print, mock_sleep):
        """cmd_demo runs demo for both tickets."""
        args = argparse.Namespace()

        cmd_demo(args)

        calls = [str(c) for c in mock_print.call_args_list]
        printed_text = " ".join(calls)

        # Check both demos were run
        assert "Demo 1" in printed_text
        assert "Demo 2" in printed_text

    @patch("time.sleep")
    @patch("builtins.print")
    def test_cmd_demo_shows_summary(self, mock_print, mock_sleep):
        """cmd_demo shows summary at end."""
        args = argparse.Namespace()

        cmd_demo(args)

        calls = [str(c) for c in mock_print.call_args_list]
        printed_text = " ".join(calls)

        assert "DEMO COMPLETE" in printed_text


class TestMain:
    """Tests for the main function."""

    @patch("time.sleep")
    @patch("sys.argv", ["cli.py", "demo"])
    def test_main_demo_command(self, mock_sleep):
        """main handles 'demo' command."""
        with patch("builtins.print"):
            main()  # Should not raise

    @patch("time.sleep")
    @patch("sys.argv", ["cli.py", "run", "SUP-4400"])
    def test_main_run_command(self, mock_sleep):
        """main handles 'run' command."""
        with patch("builtins.print"):
            main()  # Should not raise

    @patch("time.sleep")
    @patch("sys.argv", ["cli.py"])
    def test_main_default_to_demo(self, mock_sleep):
        """main defaults to demo when no command given."""
        with patch("builtins.print") as mock_print:
            main()

            calls = [str(c) for c in mock_print.call_args_list]
            printed_text = " ".join(calls)
            assert "EXCEPTION DESK DEMO" in printed_text


class TestSummaryCalculations:
    """Tests for summary calculations in format_explain."""

    def test_summary_counts_evidence(self):
        """Summary correctly counts evidence items."""
        record = {
            "decision_id": "dec_123",
            "run_id": "run_456",
            "timestamp": "2025-01-01T12:00:00",
            "outcome": "committed",
            "evidence": [{"source": "a"}, {"source": "b"}, {"source": "c"}],
            "policies": [],
            "approvals": [],
            "actions": [],
        }

        result = format_explain(record)
        assert "3 pieces of evidence" in result

    def test_summary_counts_passed_policies(self):
        """Summary correctly counts passed policies."""
        record = {
            "decision_id": "dec_123",
            "run_id": "run_456",
            "timestamp": "2025-01-01T12:00:00",
            "outcome": "committed",
            "evidence": [],
            "policies": [
                {"policy_id": "p1", "result": "pass"},
                {"policy_id": "p2", "result": "fail"},
                {"policy_id": "p3", "result": "pass"},
            ],
            "approvals": [],
            "actions": [],
        }

        result = format_explain(record)
        assert "3 policies (2 passed)" in result

    def test_summary_counts_approvals(self):
        """Summary correctly counts approvals."""
        record = {
            "decision_id": "dec_123",
            "run_id": "run_456",
            "timestamp": "2025-01-01T12:00:00",
            "outcome": "committed",
            "evidence": [],
            "policies": [],
            "approvals": [
                {"approver": {}, "granted": True, "granted_at": "2025-01-01T00:00:00"},
                {"approver": {}, "granted": False, "granted_at": "2025-01-01T00:00:00"},
            ],
            "actions": [],
        }

        result = format_explain(record)
        assert "1/2 approvals" in result

    def test_summary_counts_successful_actions(self):
        """Summary correctly counts successful actions."""
        record = {
            "decision_id": "dec_123",
            "run_id": "run_456",
            "timestamp": "2025-01-01T12:00:00",
            "outcome": "committed",
            "evidence": [],
            "policies": [],
            "approvals": [],
            "actions": [
                {"tool": "a", "success": True, "committed_at": "2025-01-01T00:00:00"},
                {"tool": "b", "success": False, "committed_at": "2025-01-01T00:00:00"},
                {"tool": "c", "success": True, "committed_at": "2025-01-01T00:00:00"},
            ],
        }

        result = format_explain(record)
        assert "2/3 actions" in result
