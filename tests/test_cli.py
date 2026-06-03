from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from agent_output_contract.cli import audit, audit_file, main, render_text


PASS_OUTPUT = {
    "schema_version": "example.v1",
    "status": "pass",
    "score": 100,
    "issues": [],
    "warnings": [],
}

PASS_OUTPUT_WITH_CHECKS = {
    **PASS_OUTPUT,
    "checks": [
        {"name": "unit tests", "status": "pass"},
        {"name": "lint", "status": "pass"},
    ],
}


class AgentOutputContractTests(unittest.TestCase):
    def write_json(self, directory: str, name: str, value: object) -> Path:
        path = Path(directory) / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_valid_output_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "output.json", PASS_OUTPUT)

            report = audit_file(path)

        self.assertEqual(report.status, "pass")
        self.assertEqual(report.issues, [])
        self.assertEqual(report.check_count, 0)

    def test_valid_output_with_checks_passes_required_checks_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "output.json", PASS_OUTPUT_WITH_CHECKS)

            report = audit_file(path, require_checks=True)

        self.assertEqual(report.status, "pass")
        self.assertEqual(report.issues, [])
        self.assertEqual(report.check_count, 2)

    def test_required_checks_gate_blocks_missing_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "output.json", PASS_OUTPUT)

            report = audit_file(path, require_checks=True)

        self.assertEqual(report.status, "fail")
        self.assertIn(
            f"{path}: `checks` must include at least one check when --require-checks is used.",
            report.issues,
        )

    def test_required_checks_gate_requires_structured_check_objects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            value = {**PASS_OUTPUT, "checks": ["make test"]}
            path = self.write_json(tmp, "output.json", value)

            report = audit_file(path, require_checks=True)

        self.assertEqual(report.status, "fail")
        self.assertIn(f"{path}: check 1 must be an object with a name and outcome.", report.issues)

    def test_required_checks_gate_requires_check_name_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            value = {**PASS_OUTPUT, "checks": [{"status": "pass"}, {"name": "unit tests"}]}
            path = self.write_json(tmp, "output.json", value)

            report = audit_file(path, require_checks=True)

        self.assertEqual(report.status, "fail")
        self.assertIn(f"{path}: check 1 must include a non-empty name, check, command, or id.", report.issues)
        self.assertTrue(any("check 2 must include exactly one outcome field" in issue for issue in report.issues))

    def test_passing_output_cannot_include_non_passing_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            value = {**PASS_OUTPUT, "checks": [{"name": "unit tests", "status": "fail"}]}
            path = self.write_json(tmp, "output.json", value)

            report = audit_file(path)

        self.assertEqual(report.status, "fail")
        self.assertIn(f"{path}: passing output must not include non-passing check 1.", report.issues)

    def test_missing_schema_version_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            value = dict(PASS_OUTPUT)
            value.pop("schema_version")
            path = self.write_json(tmp, "output.json", value)

            report = audit_file(path)

        self.assertEqual(report.status, "fail")
        self.assertIn(f"{path}: missing or placeholder `schema_version`.", report.issues)

    def test_requires_single_outcome_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            value = dict(PASS_OUTPUT)
            value["verdict"] = "ready"
            path = self.write_json(tmp, "output.json", value)

            report = audit_file(path)

        self.assertEqual(report.status, "fail")
        self.assertTrue(any("expected exactly one outcome field" in issue for issue in report.issues))

    def test_failing_output_requires_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            value = {
                "schema_version": "example.v1",
                "status": "fail",
                "score": 70,
                "issues": [],
            }
            path = self.write_json(tmp, "output.json", value)

            report = audit_file(path)

        self.assertEqual(report.status, "fail")
        self.assertIn(
            f"{path}: failing outcome must include issues, blocking_findings, or missing_evidence.",
            report.issues,
        )

    def test_passing_output_cannot_include_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            value = dict(PASS_OUTPUT)
            value["issues"] = ["missing tests"]
            path = self.write_json(tmp, "output.json", value)

            report = audit_file(path)

        self.assertEqual(report.status, "fail")
        self.assertIn(f"{path}: passing outcome must not include blocking issues or missing evidence.", report.issues)

    def test_score_must_be_in_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            value = dict(PASS_OUTPUT)
            value["score"] = 101
            path = self.write_json(tmp, "output.json", value)

            report = audit_file(path)

        self.assertEqual(report.status, "fail")
        self.assertIn(f"{path}: `score` must be between 0 and 100.", report.issues)

    def test_warns_on_sensitive_key_and_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            value = dict(PASS_OUTPUT)
            value["api_key"] = "redacted"
            value["summary"] = "read /Users/example/project/output.json"
            path = self.write_json(tmp, "output.json", value)

            report = audit_file(path)

        self.assertEqual(report.status, "pass")
        self.assertEqual(len(report.warnings), 2)

    def test_invalid_json_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{", encoding="utf-8")

            report = audit_file(path)

        self.assertEqual(report.status, "fail")
        self.assertTrue(any("invalid JSON" in issue for issue in report.issues))

    def test_aggregate_multiple_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pass_path = self.write_json(tmp, "pass.json", PASS_OUTPUT)
            fail_path = self.write_json(tmp, "fail.json", {"schema_version": "x.v1", "status": "fail"})

            report = audit([pass_path, fail_path])

        self.assertEqual(report.status, "fail")
        self.assertEqual(len(report.files), 2)
        self.assertLess(report.score, 100)

    def test_json_cli_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "output.json", PASS_OUTPUT_WITH_CHECKS)
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                code = main(["check", str(path), "--format", "json", "--require-checks"])

            self.assertEqual(code, 0)
            parsed = json.loads(stdout.getvalue())
            self.assertEqual(parsed["status"], "pass")
            self.assertEqual(parsed["score"], 100)
            self.assertEqual(parsed["files"][0]["check_count"], 2)

    def test_text_renderer_lists_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "output.json", {"status": "fail"})
            report = audit([path])
            rendered = render_text(report)

        self.assertIn("Status: fail", rendered)
        self.assertIn("Issues:", rendered)


if __name__ == "__main__":
    unittest.main()
