# AGENTS.md

- Goal: keep `agent-output-contract` as a small local gate for validating JSON outputs from agent workflow tools before automation trusts them as evidence.
- Product scope: command-line JSON checker only; no hosted service, telemetry, schema registry, network calls, or runtime dependencies.
- Prefer standard-library Python, deterministic checks, explicit exit codes, and concise reviewer-facing output.
- Run `make test`, `make lint`, `make build`, and `make smoke` before publishing changes.
- Commit only after the working tree is clean, examples still match the CLI, and README commands remain executable.
- Do not claim this proves semantic truth; it only checks that structured outputs are usable and not obviously unsafe.

