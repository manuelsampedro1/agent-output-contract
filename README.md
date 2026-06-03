# Agent Output Contract

Validate JSON outputs from coding-agent workflow tools before automation trusts them as evidence.

Agent stacks increasingly pass JSON between gates, ledgers, review packets, and CI jobs. A malformed or ambiguous output can cause downstream automation to treat weak evidence as a pass, hide blocking findings, or fail without actionable context. `agent-output-contract` is a small local checker for that boundary.

## What It Checks

- The file is valid JSON and the top-level value is an object.
- `schema_version` exists and is not placeholder text.
- The output has one clear outcome field: `status`, `verdict`, or `result`.
- Outcome values are recognized, such as `pass`, `fail`, `ready`, `needs-review`, or `blocked`.
- `score`, when present, is an integer from `0` to `100`.
- Issue, warning, blocker, and missing-evidence fields are lists.
- Passing outputs do not carry blocking findings.
- Optional `--require-checks` mode requires structured checks and reports
  `check_count`.
- Passing outputs cannot include non-passing checks.
- Failing or blocked outputs include actionable evidence.
- Obvious secret-looking values and local absolute paths are flagged before public artifacts reuse the output.

The tool is dependency-free and local-first. It does not decide whether the underlying claim is true; it checks whether the structured output is safe and usable enough for automation.

## Install

Run from a local checkout:

```sh
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

Or run without installing:

```sh
PYTHONPATH=src python3 -m agent_output_contract check examples/pass-output.json
```

## Usage

Check one output:

```sh
PYTHONPATH=src python3 -m agent_output_contract check examples/pass-output.json
```

Check multiple outputs:

```sh
PYTHONPATH=src python3 -m agent_output_contract check examples/pass-output.json examples/fail-output.json
```

JSON output for automation:

```sh
PYTHONPATH=src python3 -m agent_output_contract check examples/pass-output.json --format json
```

Require structured checks before a passing output can be trusted:

```sh
PYTHONPATH=src python3 -m agent_output_contract check examples/pass-output.json --require-checks
```

## Example Output

```text
Agent Output Contract
Status: pass
Files: 1
Score: 100/100

- examples/pass-output.json: pass, outcome=pass, checks=2

No blocking issues found.
```

If an output is not safe to consume:

```text
Agent Output Contract
Status: fail
Files: 1
Score: 52/100

Issues:
- output.json: missing required field: schema_version.
- output.json: failing outcome must include issues, blocking_findings, or missing_evidence.
```

## Exit Codes

- `0`: all outputs passed.
- `1`: one or more outputs failed the contract.
- `2`: invalid CLI input.

## Fit With The Agent Workflow Stack

- `agent-tool-schema-lint`: checks tool interfaces before agents call them.
- `agent-tool-call-replay`: checks captured calls against current schemas.
- `agent-output-contract`: checks JSON outputs before downstream automation trusts them.
- `agent-run-ledger`: can store outputs after they pass a usable evidence contract.
- `agent-claim-check`: can compare final claims against evidence once outputs are structurally reliable.

## Development

```sh
make test
make lint
make build
make smoke
```
