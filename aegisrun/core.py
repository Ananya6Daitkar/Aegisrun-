from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
REPORTS = ROOT / "reports"
STATE = ROOT / "state" / "approvals.json"
LEDGER = ROOT / "state" / "sandbox-ledger.jsonl"


@dataclass
class Finding:
    tool: str
    kind: str
    message: str
    severity: str
    side_effect: str

    def as_dict(self) -> dict[str, str]:
        return self.__dict__.copy()


class ActionExecutor:
    """A deliberately small, offline executor backed by an append-only ledger."""

    def __init__(self, ledger: Path = LEDGER) -> None:
        self.ledger = ledger

    def execute(self, action: dict[str, Any]) -> dict[str, Any]:
        action_id = action["id"]
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        existing = []
        if self.ledger.exists():
            existing = [json.loads(line) for line in self.ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
        for record in existing:
            if record.get("action_id") == action_id:
                return {"action_id": action_id, "executed": False, "idempotent": True, "record": record}
        record = {"action_id": action_id, "action": action["name"], "payload": action.get("payload", {})}
        with self.ledger.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
        return {"action_id": action_id, "executed": True, "idempotent": False, "record": record}


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _type_matches(value: Any, expected: str) -> bool:
    return {"object": isinstance(value, dict), "array": isinstance(value, list),
            "string": isinstance(value, str), "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool), "null": value is None}.get(expected, True)


def validate_response(response: Any, schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not _type_matches(response, schema.get("type", "object")):
        return [f"expected {schema.get('type')}, got {type(response).__name__}"]
    if isinstance(response, dict):
        for key in schema.get("required", []):
            if key not in response:
                errors.append(f"missing required field '{key}'")
        for key, expected in schema.get("properties", {}).items():
            if key in response and isinstance(expected, str) and not _type_matches(response[key], expected):
                errors.append(f"field '{key}' expected {expected}, got {type(response[key]).__name__}")
        if schema.get("additionalProperties", False) is False:
            declared = set(schema.get("properties", {}))
            for key in sorted(set(response) - declared):
                errors.append(f"unexpected field '{key}'")
    return errors


def _load_action_contract(scenario: str, action: dict[str, Any]) -> tuple[Path, Path, dict[str, Any]]:
    contract_path = FIXTURES / "contracts" / f"{scenario}.json"
    response_path = FIXTURES / "responses" / f"{scenario}.json"
    if not contract_path.exists() or not response_path.exists():
        raise ValueError(f"unknown scenario: {scenario}")
    contracts = load_json(contract_path)
    contract = next((item for item in contracts if item.get("tool") == action["name"]), None)
    if contract is None:
        raise ValueError(f"no contract for action {action['name']!r} in scenario {scenario!r}")
    return contract_path, response_path, contract


def check_scenario(scenario: str) -> dict[str, Any]:
    contract_path = FIXTURES / "contracts" / f"{scenario}.json"
    response_path = FIXTURES / "responses" / f"{scenario}.json"
    if not contract_path.exists() or not response_path.exists():
        raise ValueError(f"unknown scenario: {scenario}")
    contracts = load_json(contract_path)
    responses = load_json(response_path)
    findings: list[Finding] = []
    for contract in contracts:
        tool = contract["tool"]
        side_effect = contract.get("side_effect", "read")
        response = responses.get(tool)
        if response is None:
            findings.append(Finding(tool, "missing_response", "No response fixture found", "error", side_effect))
            continue
        errors = validate_response(response, contract.get("response", {}))
        for error in errors:
            findings.append(Finding(tool, "contract_drift", error, "error", side_effect))
        if side_effect in {"write", "destructive"}:
            findings.append(Finding(tool, "side_effect_blocked", f"{side_effect} operation requires explicit approval", "blocked", side_effect))
    has_drift = any(f.kind in {"contract_drift", "missing_response"} for f in findings)
    has_policy_block = any(f.severity == "blocked" for f in findings)
    status = "blocked" if has_policy_block else ("drift" if has_drift else "clean")
    run_id = f"{scenario}-demo"
    return {"run_id": run_id, "scenario": scenario, "status": status, "contracts": len(contracts),
            "findings": [f.as_dict() for f in findings], "effects_attempted": [], "effects_executed": [],
            "evidence": {"contract_fixture": str(contract_path), "response_fixture": str(response_path), "ledger": None},
            "checks": {"structural": "failed" if has_drift else "passed",
                       "semantic": "blocked" if has_policy_block else ("skipped" if has_drift else "passed")},
            "policy": "fail-closed: read is inspectable; write/destructive is blocked without approval"}


SCENARIOS = ("valid-ticket", "external-email", "destructive-delete", "drift", "clean", "blocked")
ALLOWED_RECIPIENT_DOMAINS = {"example.com", "internal.test"}


def _scenario_action(scenario: str) -> dict[str, Any]:
    actions = {
        "valid-ticket": {"id": "valid-ticket-create-1", "name": "create_ticket", "side_effect": "write", "approval": True,
                         "payload": {"title": "Printer offline", "requester": "ops@example.com"}},
        "external-email": {"id": "external-email-send-1", "name": "send_email", "side_effect": "write", "approval": True,
                           "payload": {"recipient": "customer@outside.example.net", "subject": "Notice"}},
        "destructive-delete": {"id": "destructive-delete-1", "name": "delete_record", "side_effect": "destructive", "approval": True,
                               "payload": {"record_id": "r-17"}},
    }
    return actions[scenario]


def run_scenario(scenario: str, executor: ActionExecutor | None = None) -> dict[str, Any]:
    """Validate a deterministic scenario, apply policy, and execute only allowed actions."""
    if scenario == "drift":
        report = check_scenario("drift")
        report["checks"] = {"structural": "failed", "semantic": "skipped"}
        report["effects_attempted"] = [{"action": "inventory.read", "executed": False, "reason": "contract_drift"}]
        report["evidence"]["execution"] = "contract validation failed before execution"
        return report
    if scenario in {"clean", "blocked"}:
        return check_scenario(scenario)
    if scenario not in {"valid-ticket", "external-email", "destructive-delete"}:
        raise ValueError(f"unknown scenario: {scenario}")
    action = _scenario_action(scenario)
    contract_path, response_path, contract = _load_action_contract(scenario, action)
    input_errors = validate_response(action.get("payload", {}), contract.get("input", {}))
    structural_findings = [
        Finding(action["name"], "input_contract_drift", error, "error", action["side_effect"])
        for error in input_errors
    ]
    if structural_findings:
        attempted = {"action_id": action["id"], "action": action["name"], "reason": "contract_drift"}
        return {"run_id": f"{scenario}-run", "scenario": scenario, "status": "drift", "contracts": 1,
                "findings": [f.as_dict() for f in structural_findings], "effects_attempted": [attempted],
                "effects_executed": [], "policy": "structural contract validation failed before semantic policy",
                "checks": {"structural": "failed", "semantic": "skipped"},
                "evidence": {"action": action, "contract_fixture": str(contract_path),
                             "response_fixture": str(response_path), "execution": "contract validation failed before execution",
                             "ledger": None}}
    findings: list[Finding] = []
    recipient = action.get("payload", {}).get("recipient", "")
    if action["side_effect"] not in {"read", "write", "destructive", "network"}:
        findings.append(Finding(action["name"], "unknown_side_effect", "Unknown side-effect classification; execution denied", "blocked", action["side_effect"]))
    if not action.get("approval"):
        findings.append(Finding(action["name"], "approval_required", "Side effect requires approval", "blocked", action["side_effect"]))
    if action["side_effect"] == "destructive":
        findings.append(Finding(action["name"], "destructive_denied", "Destructive actions are denied by policy", "blocked", "destructive"))
    if action["side_effect"] == "network":
        findings.append(Finding(action["name"], "offline_network_denied", "Network actions are denied in offline mode", "blocked", "network"))
    if recipient:
        domain = recipient.rsplit("@", 1)[-1].lower()
        if domain not in ALLOWED_RECIPIENT_DOMAINS:
            findings.append(Finding(action["name"], "recipient_denied", f"Recipient domain '{domain}' is not allowed", "blocked", action["side_effect"]))
    attempted = {"action_id": action["id"], "action": action["name"]}
    report = {"run_id": f"{scenario}-run", "scenario": scenario, "status": "blocked" if findings else "clean",
              "contracts": 1, "findings": [f.as_dict() for f in findings], "effects_attempted": [attempted],
              "effects_executed": [], "policy": "offline, fail-closed semantic policy; allowed recipient domains: example.com, internal.test",
              "checks": {"structural": "passed", "semantic": "blocked" if findings else "passed"},
              "evidence": {"action": action, "contract_fixture": str(contract_path),
                           "response_fixture": str(response_path), "ledger": None}}
    if not findings:
        active_executor = executor or ActionExecutor()
        result = active_executor.execute(action)
        report["effects_executed"] = [result] if result["executed"] else []
        report["evidence"]["ledger"] = str(active_executor.ledger)
        report["evidence"]["execution"] = result
    else:
        report["evidence"]["execution"] = "policy denied before executor"
    return report


def write_report(report: dict[str, Any]) -> tuple[Path, Path]:
    REPORTS.mkdir(exist_ok=True)
    stem = f"{report['run_id']}.json"
    json_path = REPORTS / stem
    md_path = REPORTS / (stem.removesuffix(".json") + ".md")
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    checks = report.get("checks", {})
    lines = [f"# AegisRun report: `{report['run_id']}`", "", f"- **Scenario:** `{report['scenario']}`", f"- **Status:** **{report['status'].upper()}**", f"- **Contracts checked:** {report['contracts']}", "", "## Checks", f"- Structural contract validation: **{checks.get('structural', 'not reported')}**", f"- Semantic policy validation: **{checks.get('semantic', 'not reported')}**", "", "## Policy", report["policy"], "", "## Findings"]
    if report["findings"]:
        lines += [f"- **{x['severity'].upper()}** `{x['tool']}` — {x['message']}" for x in report["findings"]]
    else:
        lines.append("- No findings. All response fixtures match their contracts.")
    lines += ["", "## Effects", f"- Attempted: **{len(report.get('effects_attempted', []))}**", f"- Executed: **{len(report.get('effects_executed', []))}**", "", "## Evidence", "```json", json.dumps(report.get("evidence", {}), indent=2), "```"]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def approve(run_id: str) -> dict[str, Any]:
    STATE.parent.mkdir(exist_ok=True)
    state = load_json(STATE) if STATE.exists() else {"approvals": []}
    if not any(item["run_id"] == run_id for item in state["approvals"]):
        state["approvals"].append({"run_id": run_id, "approved": True})
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return {"run_id": run_id, "approved": True, "effects_executed": []}
