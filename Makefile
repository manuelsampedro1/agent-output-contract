.PHONY: test lint build smoke

test:
	PYTHONPATH=src python3 -m unittest discover -s tests

lint:
	python3 -m py_compile src/agent_output_contract/*.py tests/test_cli.py

build:
	python3 -m py_compile src/agent_output_contract/*.py tests/test_cli.py

smoke:
	PYTHONPATH=src python3 -m agent_output_contract check examples/pass-output.json
	PYTHONPATH=src python3 -m agent_output_contract check examples/fail-output.json
	PYTHONPATH=src python3 -m agent_output_contract check examples/pass-output.json --format json > /tmp/agent-output-contract.json
	! PYTHONPATH=src python3 -m agent_output_contract check examples/invalid-output.json
