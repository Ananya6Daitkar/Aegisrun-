# AegisRun

A local-first pressure-test runner for deterministic JSON tool contracts and controlled actions. AegisRun validates contracts before execution, applies semantic fail-closed policy, and emits portable Markdown + JSON evidence distinguishing attempted from executed effects. The only executor is an offline sandbox ledger; it never calls a network or an external API.

## Quick start

Requires Python 3.12. There are no runtime dependencies; tests use the standard-library `unittest` runner.

```bash
python -m aegisrun run --scenario valid-ticket       # exit 0; one ledger record
python -m aegisrun run --scenario external-email      # exit 2; recipient policy blocks
python -m aegisrun run --scenario destructive-delete  # exit 2; destructive policy blocks
python -m aegisrun run --scenario drift               # exit 2; contract mismatch blocks
python -m aegisrun check --scenario clean
python -m aegisrun explain --report reports/clean-demo.json
python -m aegisrun approve --run blocked-demo
python -m unittest discover -s tests -q
```

`approve` records a local decision in `state/approvals.json`; approval is intentionally not an execution mechanism. Reports are written to `reports/`, and allowed actions append exactly one idempotent record to `state/sandbox-ledger.jsonl`. Exit codes are 0 for clean/allowed, 2 for drift or policy blocks, and 3 for invalid CLI input. Contracts live in `fixtures/contracts/`, with matching responses in `fixtures/responses/`.

Action runs report two ordered checks: structural validation loads the scenario's contract and response fixtures and validates the action payload against the contract's `input` schema; semantic validation then applies the offline policy. A structural drift stops before policy and the executor, while a structurally valid but disallowed action is reported as a semantic block.

## Offline Docker demo

```bash
docker build -t aegisrun .
docker run --rm aegisrun
# The image has no runtime dependencies and can run its tests offline:
docker run --rm --entrypoint python aegisrun -m unittest discover -s tests -q
```
