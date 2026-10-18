from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import SCENARIOS, approve, check_scenario, run_scenario, write_report


class InputParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(__import__("sys").stderr)
        self.exit(3, f"{self.prog}: invalid input: {message}\n")


def main(argv: list[str] | None = None) -> int:
    parser = InputParser(prog="aegisrun", description="Local-first contract safety checks")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=InputParser)
    check = sub.add_parser("check", help="check a deterministic demo scenario")
    check.add_argument("--scenario", choices=SCENARIOS, required=True)
    run = sub.add_parser("run", help="execute a deterministic scenario through the local policy")
    run.add_argument("--scenario", choices=SCENARIOS, required=True)
    explain = sub.add_parser("explain", help="summarize a JSON evidence report")
    explain.add_argument("--report", required=True)
    approval = sub.add_parser("approve", help="record approval locally; never executes effects")
    approval.add_argument("--run", required=True)
    args = parser.parse_args(argv)
    if args.command == "check":
        report = check_scenario(args.scenario)
        json_path, md_path = write_report(report)
        print(f"AegisRun {report['status'].upper()} — {report['run_id']}")
        print(f"Evidence: {md_path} and {json_path}")
        return 0 if report["status"] == "clean" else 2
    if args.command == "run":
        report = run_scenario(args.scenario)
        json_path, md_path = write_report(report)
        print(f"AegisRun {report['status'].upper()} — {report['run_id']}")
        print(f"Attempted: {len(report.get('effects_attempted', []))}; executed: {len(report.get('effects_executed', []))}")
        print(f"Evidence: {md_path} and {json_path}")
        return 0 if report["status"] == "clean" else 2
    if args.command == "explain":
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        print(f"Run {report['run_id']} ({report['scenario']}): {report['status'].upper()}")
        print(report["policy"])
        for finding in report["findings"]:
            print(f"- {finding['severity'].upper()}: {finding['tool']} — {finding['message']}")
        return 0
    result = approve(args.run)
    print(f"Approval recorded for {result['run_id']} (local only; no effects executed)")
    return 0
