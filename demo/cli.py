#!/usr/bin/env python3
"""Exception Desk CLI - Run the demo and explain decisions."""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demo.agent import ExceptionDeskAgent


def format_explain(record: dict) -> str:
    """Format a DecisionRecord as a readable explanation."""
    lines = []

    lines.append("")
    lines.append("=" * 70)
    lines.append("DECISION EXPLANATION")
    lines.append("=" * 70)
    lines.append("")

    # Header
    lines.append(f"Decision ID:  {record['decision_id']}")
    lines.append(f"Run ID:       {record['run_id']}")
    lines.append(f"Timestamp:    {record['timestamp']}")
    lines.append(f"Outcome:      {record['outcome'].upper()}")
    if record.get('outcome_reason'):
        lines.append(f"Reason:       {record['outcome_reason']}")
    lines.append("")

    # Evidence Chain
    evidence = record.get('evidence', [])
    lines.append(f"--- EVIDENCE CHAIN ({len(evidence)} items) ---")
    lines.append("")
    for i, e in enumerate(evidence, 1):
        lines.append(f"  [{i}] {e['source']}")
        lines.append(f"      Tool: {e.get('tool_name', 'N/A')}")
        lines.append(f"      Retrieved: {e['retrieved_at']}")
        if e.get('snapshot'):
            snapshot = e['snapshot']
            # Show key fields based on source
            if 'requested_credit_pct' in snapshot:
                lines.append(f"      -> Requested: {snapshot['requested_credit_pct']:.0%} credit")
                lines.append(f"      -> Subject: {snapshot.get('subject', 'N/A')}")
            elif 'arr' in snapshot:
                lines.append(f"      -> Account: {snapshot.get('name')} ({snapshot.get('tier')})")
                lines.append(f"      -> ARR: ${snapshot['arr']:,}, Churn Risk: {snapshot.get('churn_risk')}")
            elif 'sev1_count' in snapshot:
                lines.append(f"      -> SEV-1: {snapshot['sev1_count']}, SEV-2: {snapshot['sev2_count']}")
                lines.append(f"      -> Total downtime: {snapshot['total_downtime_mins']} mins")
        lines.append("")

    # Policy Chain
    policies = record.get('policies', [])
    lines.append(f"--- POLICY CHAIN ({len(policies)} evaluations) ---")
    lines.append("")
    for i, p in enumerate(policies, 1):
        result_symbol = {"pass": "✓", "warn": "⚠", "fail": "✗"}.get(p['result'], "?")
        lines.append(f"  [{i}] {result_symbol} {p['policy_id']} v{p['version']}")
        lines.append(f"      Result: {p['result'].upper()}")
        if p.get('message'):
            lines.append(f"      Details: {p['message']}")
        lines.append("")

    # Approval Chain
    approvals = record.get('approvals', [])
    lines.append(f"--- APPROVAL CHAIN ({len(approvals)} approvals) ---")
    lines.append("")
    if not approvals:
        lines.append("  (No approvals required)")
        lines.append("")
    for i, a in enumerate(approvals, 1):
        status = "APPROVED" if a['granted'] else "DENIED"
        symbol = "✓" if a['granted'] else "✗"
        approver = a.get('approver', {})
        lines.append(f"  [{i}] {symbol} {status}")
        lines.append(f"      Approver: {approver.get('id', 'Unknown')} ({approver.get('name', '')})")
        lines.append(f"      Decided: {a['granted_at']}")
        if a.get('reason'):
            lines.append(f"      Reason: {a['reason']}")
        lines.append("")

    # Action Chain
    actions = record.get('actions', [])
    lines.append(f"--- ACTION CHAIN ({len(actions)} commits) ---")
    lines.append("")
    if not actions:
        lines.append("  (No actions committed)")
        lines.append("")
    for i, a in enumerate(actions, 1):
        status = "SUCCESS" if a['success'] else "FAILED"
        symbol = "✓" if a['success'] else "✗"
        lines.append(f"  [{i}] {symbol} {a['tool']}")
        lines.append(f"      Status: {status}")
        lines.append(f"      Committed: {a['committed_at']}")
        if a.get('params'):
            params = a['params']
            if 'amount' in params:
                lines.append(f"      Amount: ${params['amount']:,.2f} ({params.get('credit_pct', 0):.0%})")
        if a.get('result'):
            result = a['result']
            if 'credit_id' in result:
                lines.append(f"      Credit ID: {result['credit_id']}")
        lines.append("")

    # Summary
    lines.append("--- SUMMARY ---")
    lines.append("")
    summary_parts = []
    if evidence:
        summary_parts.append(f"Gathered {len(evidence)} pieces of evidence")
    if policies:
        passed = sum(1 for p in policies if p['result'] == 'pass')
        summary_parts.append(f"Evaluated {len(policies)} policies ({passed} passed)")
    if approvals:
        approved = sum(1 for a in approvals if a['granted'])
        summary_parts.append(f"Received {approved}/{len(approvals)} approvals")
    if actions:
        succeeded = sum(1 for a in actions if a['success'])
        summary_parts.append(f"Executed {succeeded}/{len(actions)} actions")
    summary_parts.append(f"Final outcome: {record['outcome'].upper()}")

    for part in summary_parts:
        lines.append(f"  • {part}")
    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)


def cmd_run(args):
    """Run the agent on a ticket."""
    print(f"\nProcessing ticket: {args.ticket}")

    agent = ExceptionDeskAgent()
    result = agent.process_ticket(args.ticket)

    if args.explain:
        print(format_explain(result['record']))

    if args.json:
        print("\n--- RAW JSON ---")
        print(json.dumps(result['record'], indent=2, default=str))

    return result


def cmd_explain(args):
    """Explain a decision from JSON file or stdin."""
    if args.file:
        with open(args.file) as f:
            record = json.load(f)
    else:
        record = json.load(sys.stdin)

    if 'record' in record:
        record = record['record']

    print(format_explain(record))


def cmd_demo(args):
    """Run the full demo with both tickets."""
    print("\n" + "=" * 70)
    print("EXCEPTION DESK DEMO")
    print("Service Credit Approval Workflow")
    print("=" * 70)

    print("\n--- Demo 1: High-value enterprise with SEV-1 incidents ---")
    print("This ticket should PASS with exception approval (20% credit)")
    result1 = cmd_run(argparse.Namespace(ticket="SUP-4312", explain=True, json=False))

    print("\n\n--- Demo 2: Growth tier with no major incidents ---")
    print("This ticket should PASS without exception (8% < 10% cap)")
    result2 = cmd_run(argparse.Namespace(ticket="SUP-4400", explain=True, json=False))

    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print(f"\nDecision 1: {result1['decision_id']} -> {result1['outcome']}")
    print(f"Decision 2: {result2['decision_id']} -> {result2['outcome']}")
    print("\nTo query these decisions later:")
    print(f"  curl http://localhost:8080/v1/decisions/{result1['decision_id']}/explain")


def main():
    parser = argparse.ArgumentParser(
        description="Exception Desk - Service Credit Approval Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s demo                    Run full demo with example tickets
  %(prog)s run SUP-4312            Process a specific ticket
  %(prog)s run SUP-4312 --explain  Process and show explanation
  %(prog)s explain result.json     Explain a saved decision
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # demo command
    demo_parser = subparsers.add_parser("demo", help="Run full demo")
    demo_parser.set_defaults(func=cmd_demo)

    # run command
    run_parser = subparsers.add_parser("run", help="Process a ticket")
    run_parser.add_argument("ticket", help="Ticket ID (e.g., SUP-4312)")
    run_parser.add_argument("--explain", "-e", action="store_true", help="Show explanation")
    run_parser.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    run_parser.set_defaults(func=cmd_run)

    # explain command
    explain_parser = subparsers.add_parser("explain", help="Explain a decision")
    explain_parser.add_argument("file", nargs="?", help="JSON file (or stdin)")
    explain_parser.set_defaults(func=cmd_explain)

    args = parser.parse_args()

    if args.command is None:
        # Default to demo
        args.func = cmd_demo

    args.func(args)


if __name__ == "__main__":
    main()
