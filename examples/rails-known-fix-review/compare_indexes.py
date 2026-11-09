"""Project a pinned, known-fix-guided pair of Core indexes into public facts.

This checks recorded provenance, not the authenticity of arbitrary raw JSON.
It performs no live requests, source execution, or security classification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


INDEX_FILES = (
    "authorization_calls.json", "rails_routes.json", "execution_paths.json",
    "sidekiq_jobs.json", "warnings.json",
)
CASE_FILE = Path(__file__).with_name("case.json")
NESTED_SCOPE_REASON = (
    "scope nested inside a resource scope is not composed by the Phase 2 route index"
)


class ComparisonError(ValueError):
    """An input does not satisfy this fixed case's comparison contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ComparisonError(message)


def read_json(path: Path):
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError, UnicodeError):
        raise ComparisonError("cannot read expected JSON input") from None


def records(value, label: str) -> list[dict]:
    require(isinstance(value, list) and all(isinstance(x, dict) for x in value),
            f"invalid {label} records")
    return value


def validate_case(case: dict) -> None:
    require(isinstance(case, dict), "invalid case")
    for key in ("before", "after", "core"):
        require(isinstance(case.get(key), str) and
                re.fullmatch(r"[0-9a-f]{40}", case[key]) is not None,
                "invalid case commit identity")
    require(case["before"] != case["after"], "case commits must differ")
    for key in ("controller", "authorization_source", "route_source"):
        value = case.get(key)
        require(isinstance(value, str) and not Path(value).is_absolute() and
                ".." not in Path(value).parts and "\\" not in value,
                "invalid case relative source path")
    require(isinstance(case.get("method"), str) and
            re.fullmatch(r"[a-zA-Z_][a-zA-Z_0-9!?]*", case["method"]) is not None,
            "invalid case method")
    for key in ("authorization_line", "unsupported_scope_line"):
        require(type(case.get(key)) is int and case[key] > 0, "invalid case line")
    blobs = case.get("controller_blobs")
    require(isinstance(blobs, dict) and all(
        isinstance(blobs.get(role), str) and
        re.fullmatch(r"[0-9a-f]{40}", blobs[role]) is not None
        for role in ("before", "after")), "invalid case file identity")
    for key in ("include_patterns", "exclude_patterns"):
        require(isinstance(case.get(key), list) and
                all(isinstance(x, str) for x in case[key]), "invalid case scope")
    require(isinstance(case.get("extractor_versions"), dict) and
            isinstance(case.get("required_package_versions"), dict) and
            type(case.get("graph_schema_contract_version")) is int,
            "missing case parser contract")


def project(directory: Path, role: str, case: dict) -> tuple[dict, dict, dict]:
    manifest = read_json(directory / "run_manifest.json")
    require(isinstance(manifest, dict), "invalid manifest")
    require(manifest.get("target_commit_sha") == case[role], "target commit mismatch")
    require(manifest.get("veripsa_commit_sha") == case["core"], "Core commit mismatch")
    require(manifest.get("target_dirty_state") is False and
            manifest.get("veripsa_dirty_state") is False, "dirty or unrecorded source")
    for key in ("include_patterns", "exclude_patterns", "extractor_versions",
                "graph_schema_contract_version"):
        require(manifest.get(key) == case[key], f"{key} mismatch")
    versions = manifest.get("relevant_package_versions")
    require(isinstance(versions, dict), "missing package versions")
    require(all(versions.get(name) == version for name, version in
                case["required_package_versions"].items()), "required parser version mismatch")
    require(isinstance(manifest.get("python_version"), str), "missing Python version")
    nodes = records(read_json(directory / "nodes.json"), "node")
    files = [n for n in nodes if n.get("path") == case["controller"] and n.get("kind") == "file"]
    require(len(files) == 1 and files[0].get("content_hash") == case["controller_blobs"][role],
            "controller Git blob mismatch")
    definitions = []
    for node in nodes:
        if (node.get("path") == case["controller"] and node.get("kind") == "def"
                and node.get("name") == case["method"]):
            start, end = node.get("start_line"), node.get("end_line")
            require(type(start) is int and type(end) is int and 0 < start <= end,
                    "invalid method location")
            definitions.append({"start_line": start, "end_line": end})
    require(bool(definitions), "case method not observed")
    definitions.sort(key=lambda d: (d["start_line"], d["end_line"]))
    raw, indexes = {}, {}
    for name in INDEX_FILES:
        try:
            raw[name] = (directory / name).read_bytes()
            indexes[name] = json.loads(raw[name])
        except (OSError, ValueError, UnicodeError):
            raise ComparisonError("cannot read expected index JSON") from None
    auth = records(indexes["authorization_calls.json"], "authorization")
    routes = records(indexes["rails_routes.json"], "route")
    warnings = records(indexes["warnings.json"], "warning")
    records(indexes["execution_paths.json"], "execution path")
    require(isinstance(indexes["sidekiq_jobs.json"], dict), "invalid Sidekiq index")
    selected_auth = [x for x in auth if x.get("source_file") == case["authorization_source"]
                     and x.get("source_line") == case["authorization_line"]
                     and x.get("call_name") == "authorize"
                     and x.get("enclosing_class_or_module") == "Api::BaseController"
                     and x.get("enclosing_method") == "check_authorization"]
    target_class = "Api::V1::Accounts::AutomationRulesController"
    result = {
        "target_commit": case[role],
        "controller": {"file": case["controller"], "git_blob": case["controller_blobs"][role],
                       "method": case["method"], "definitions": definitions},
        "selected_observations": {
            "automation_route_observed": any(x.get("controller_file") == case["controller"]
                                              or x.get("controller") == target_class for x in routes),
            "authorization": {"file": case["authorization_source"],
                              "line": case["authorization_line"],
                              "single_authorize_call_observed": len(selected_auth) == 1,
                              "single_call_unresolved": len(selected_auth) == 1 and
                              bool(selected_auth[0].get("unresolved_reason"))},
            "unsupported_nested_resource_scope": {
                "file": case["route_source"], "line": case["unsupported_scope_line"],
                "warning_observed": any(x.get("file") == case["route_source"] and
                    x.get("line") == case["unsupported_scope_line"] and
                    x.get("category") == "rails_route_unresolved" and
                    x.get("reason") == NESTED_SCOPE_REASON for x in warnings)},
        },
    }
    return result, manifest, raw


def compare(before: Path, after: Path, case: dict | None = None) -> dict:
    case = read_json(CASE_FILE) if case is None else case
    validate_case(case)
    left, lm, lb = project(Path(before), "before", case)
    right, rm, rb = project(Path(after), "after", case)
    for key in ("python_version", "relevant_package_versions"):
        require(lm[key] == rm[key], f"paired {key} mismatch")
    return {
        "schema": "known-fix-index-comparison-v1",
        "analysis": "known-fix-guided retrospective source-index observation; no security verdict",
        "core_commit": case["core"],
        "before": left, "after": right,
        "index_bytes_equal": {name: lb[name] == rb[name] for name in INDEX_FILES},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = compare(args.before, args.after)
    except ComparisonError as exc:
        print(f"comparison refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
