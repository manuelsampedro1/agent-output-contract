from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


OUTCOME_FIELDS = ["status", "verdict", "result"]
PASSING_OUTCOMES = {"ok", "pass", "passed", "success", "ready", "clean"}
NON_PASSING_OUTCOMES = {"fail", "failed", "error", "blocked", "needs-review", "needs_review", "partial"}
KNOWN_OUTCOMES = PASSING_OUTCOMES | NON_PASSING_OUTCOMES
EVIDENCE_FIELDS = ["issues", "blocking_findings", "missing_evidence"]
LIST_FIELDS = ["issues", "warnings", "blocking_findings", "missing_evidence", "checks"]
SECRET_KEY_PATTERN = re.compile(
    r"(api[_-]?key|token|secret|password|authorization|private[_-]?key)",
    re.IGNORECASE,
)
SECRET_VALUE_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9_]{12,}|xox[baprs]-[A-Za-z0-9-]{12,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)
LOCAL_PATH_PATTERN = re.compile(r"(/Users/[^\\s\"']+|/home/[^\\s\"']+|[A-Za-z]:\\\\Users\\\\[^\\s\"']+)")


@dataclass(frozen=True)
class FileReport:
    path: str
    status: str
    outcome: str
    score: int | None
    issues: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class ContractReport:
    schema_version: str
    status: str
    files: list[FileReport]
    score: int
    issues: list[str]
    warnings: list[str]


def read_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "file not found"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}"


def normalized_outcome(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def present_outcome_fields(data: dict[str, Any]) -> list[str]:
    return [field for field in OUTCOME_FIELDS if field in data]


def is_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return True
    normalized = value.strip().lower()
    return not normalized or normalized in {"todo", "tbd", "placeholder", "unknown", "schema"}


def list_issue(path: str, field: str) -> str:
    return f"{path}: `{field}` must be a list when present."


def walk_values(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    values = [(prefix, value)]
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            values.extend(walk_values(child, child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_prefix = f"{prefix}[{index}]"
            values.extend(walk_values(child, child_prefix))
    return values


def audit_sensitive_values(path: str, data: dict[str, Any], warnings: list[str]) -> None:
    for key_path, value in walk_values(data):
        key_name = key_path.split(".")[-1].split("[", 1)[0]
        if SECRET_KEY_PATTERN.search(key_name):
            warnings.append(f"{path}: sensitive-looking key `{key_path}` is present.")
        if isinstance(value, str):
            if SECRET_VALUE_PATTERN.search(value):
                warnings.append(f"{path}: sensitive-looking value found at `{key_path}`.")
            if LOCAL_PATH_PATTERN.search(value):
                warnings.append(f"{path}: local absolute path found at `{key_path}`.")


def audit_file(path: Path) -> FileReport:
    path_text = str(path)
    issues: list[str] = []
    warnings: list[str] = []
    data, read_error = read_json(path)
    if read_error is not None:
        return FileReport(path_text, "fail", "invalid", None, [f"{path_text}: {read_error}."], [])

    if not isinstance(data, dict):
        return FileReport(path_text, "fail", "invalid", None, [f"{path_text}: top-level JSON value must be an object."], [])

    if is_placeholder(data.get("schema_version")):
        issues.append(f"{path_text}: missing or placeholder `schema_version`.")

    outcome_fields = present_outcome_fields(data)
    if len(outcome_fields) != 1:
        issues.append(
            f"{path_text}: expected exactly one outcome field from {', '.join(OUTCOME_FIELDS)}; found {len(outcome_fields)}."
        )
        outcome = "unknown"
    else:
        outcome = normalized_outcome(data[outcome_fields[0]])
        if outcome not in KNOWN_OUTCOMES:
            issues.append(f"{path_text}: unrecognized outcome `{data[outcome_fields[0]]}`.")

    score = data.get("score")
    normalized_score: int | None
    if score is None:
        normalized_score = None
    elif isinstance(score, bool) or not isinstance(score, int):
        normalized_score = None
        issues.append(f"{path_text}: `score` must be an integer from 0 to 100 when present.")
    elif score < 0 or score > 100:
        normalized_score = score
        issues.append(f"{path_text}: `score` must be between 0 and 100.")
    else:
        normalized_score = score

    for field in LIST_FIELDS:
        if field in data and not isinstance(data[field], list):
            issues.append(list_issue(path_text, field))

    blocking_items = []
    for field in EVIDENCE_FIELDS:
        value = data.get(field)
        if isinstance(value, list):
            blocking_items.extend(value)

    if outcome in NON_PASSING_OUTCOMES and not blocking_items:
        issues.append(f"{path_text}: failing outcome must include issues, blocking_findings, or missing_evidence.")

    if outcome in PASSING_OUTCOMES and blocking_items:
        issues.append(f"{path_text}: passing outcome must not include blocking issues or missing evidence.")

    audit_sensitive_values(path_text, data, warnings)
    status = "pass" if not issues else "fail"
    return FileReport(path_text, status, outcome, normalized_score, issues, warnings)


def audit(paths: list[Path]) -> ContractReport:
    file_reports = [audit_file(path) for path in paths]
    issues = [issue for report in file_reports for issue in report.issues]
    warnings = [warning for report in file_reports for warning in report.warnings]
    score = max(0, 100 - len(issues) * 12 - len(warnings) * 4)
    status = "pass" if not issues else "fail"
    return ContractReport(
        schema_version="agent-output-contract.v1",
        status=status,
        files=file_reports,
        score=score,
        issues=issues,
        warnings=warnings,
    )


def render_text(report: ContractReport) -> str:
    lines = [
        "Agent Output Contract",
        f"Status: {report.status}",
        f"Files: {len(report.files)}",
        f"Score: {report.score}/100",
        "",
    ]
    if report.issues:
        lines.append("Issues:")
        lines.extend(f"- {issue}" for issue in report.issues)
    else:
        lines.append("No blocking issues found.")
    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in report.warnings)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate agent workflow JSON output contracts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check", help="check one or more JSON outputs")
    check_parser.add_argument("outputs", nargs="+", help="JSON output file(s)")
    check_parser.add_argument("--format", choices=["text", "json"], default="text")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "check":
        parser.error("unknown command")

    report = audit([Path(output) for output in args.outputs])
    if args.format == "json":
        print(json.dumps(asdict(report), indent=2))
    else:
        print(render_text(report))
    return 0 if report.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

