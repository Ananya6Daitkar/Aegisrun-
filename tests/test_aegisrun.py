import json
import tempfile
import unittest
from pathlib import Path

from aegisrun.core import ActionExecutor, approve, check_scenario, run_scenario, write_report


class AegisRunTests(unittest.TestCase):
    def test_scenarios_have_expected_policy_outcomes(self):
        self.assertEqual(check_scenario("clean")["status"], "clean")
        self.assertEqual(check_scenario("drift")["status"], "drift")
        report = check_scenario("blocked")
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["effects_executed"], [])


    def test_report_and_local_approval(self):
        import aegisrun.core as core
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            old_reports, old_state = core.REPORTS, core.STATE
            core.REPORTS, core.STATE = tmp_path / "reports", tmp_path / "state" / "approvals.json"
            try:
                paths = write_report(check_scenario("clean"))
                self.assertTrue(all(path.exists() for path in paths))
                self.assertEqual(json.loads(paths[0].read_text())["status"], "clean")
                self.assertEqual(approve("clean-demo")["effects_executed"], [])
                self.assertTrue(json.loads((tmp_path / "state" / "approvals.json").read_text())["approvals"][0]["approved"])
            finally:
                core.REPORTS, core.STATE = old_reports, old_state


    def test_unknown_scenario_rejected(self):
        with self.assertRaises(ValueError):
            check_scenario("unknown")

    def test_allowed_ticket_writes_one_ledger_record_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            executor = ActionExecutor(ledger)
            first = run_scenario("valid-ticket", executor)
            second = run_scenario("valid-ticket", executor)
            self.assertEqual(first["status"], "clean")
            self.assertEqual(first["checks"], {"structural": "passed", "semantic": "passed"})
            self.assertIn("contracts/valid-ticket.json", first["evidence"]["contract_fixture"])
            self.assertIn("responses/valid-ticket.json", first["evidence"]["response_fixture"])
            self.assertEqual(len(first["effects_attempted"]), 1)
            self.assertEqual(len(first["effects_executed"]), 1)
            self.assertEqual(second["effects_executed"], [])
            self.assertEqual(len(ledger.read_text().splitlines()), 1)

    def test_semantic_blocks_have_no_ledger_side_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.jsonl"
            executor = ActionExecutor(ledger)
            for scenario in ("external-email", "destructive-delete"):
                report = run_scenario(scenario, executor)
                self.assertEqual(report["status"], "blocked")
                self.assertEqual(report["checks"], {"structural": "passed", "semantic": "blocked"})
                self.assertIn("contract_fixture", report["evidence"])
                self.assertIn("response_fixture", report["evidence"])
                self.assertEqual(report["effects_executed"], [])
            self.assertFalse(ledger.exists())

    def test_drift_prevents_execution_and_reports_evidence(self):
        report = run_scenario("drift")
        self.assertEqual(report["status"], "drift")
        self.assertEqual(report["checks"], {"structural": "failed", "semantic": "skipped"})
        self.assertEqual(report["effects_executed"], [])
        self.assertEqual(report["effects_attempted"][0]["reason"], "contract_drift")
        self.assertIn("execution", report["evidence"])
