# AegisRun

A local-first pressure-test runner for deterministic JSON tool contracts and controlled actions. AegisRun validates contracts before execution, applies semantic fail-closed policy, and emits portable Markdown + JSON evidence distinguishing attempted from executed effects. The only executor is an offline sandbox ledger; it never calls a network or an external API.

## Setup

Requires Python **3.12.8** (the version is pinned in `.python-version`). There are no third-party runtime dependencies; `requirements.lock` is intentionally empty and tests use the standard-library `unittest` runner.

```bash
python3.12 --version  # expected: Python 3.12.8
```

No package installation is required for the local runner or tests; all runtime code uses the Python standard library.

## Run and test

```bash
python3.12 -m aegisrun run --scenario valid-ticket       # exit 0; one ledger record
python3.12 -m aegisrun run --scenario external-email      # exit 2; recipient policy blocks
python3.12 -m aegisrun run --scenario destructive-delete  # exit 2; destructive policy blocks
python3.12 -m aegisrun run --scenario drift               # exit 2; contract mismatch blocks
python3.12 -m aegisrun check --scenario clean
python3.12 -m aegisrun explain --report reports/clean-demo.json
python3.12 -m aegisrun approve --run blocked-demo
python3.12 -m unittest discover -s tests -q
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

## Clean Linux rebuild

From a fresh clone, run the single offline test command:

```bash
git clone https://github.com/Ananya6Daitkar/Aegisrun-.git
cd Aegisrun-
python3.12 --version  # expected: Python 3.12.8
python3.12 -m unittest discover -s tests -q
python3.12 -m aegisrun run --scenario valid-ticket
```

The Docker rebuild does not install packages or require network access after the base image is available:

```bash
docker build -t aegisrun:latest .
docker run --rm --network none aegisrun:latest
docker run --rm --network none --entrypoint python aegisrun:latest \
  -m unittest discover -s tests -q
```

Runtime reports and sandbox state are generated locally and ignored by Git. No credentials are required; `.env.example` documents that the application has no settings or secrets.
