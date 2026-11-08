"""Observe four synthetic Tauri contracts with a pinned public Core extractor."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
from collections import Counter
import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def git_blob_sha(body: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(body)).encode("ascii") + b"\0" + body).hexdigest()


def verify_core(core: Path, git: str) -> dict:
    lock = json.loads((HERE / "core-source-lock.json").read_text(encoding="utf-8"))
    require(core.is_dir(), "--core must point to a local public Veripsa checkout")
    try:
        result = subprocess.run(
            [git, "-C", str(core), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise VerificationError("Could not read Core git HEAD; provide a working git binary with --git") from error
    head = result.stdout.strip()
    require(head == lock["commit"], "Core HEAD must be " + lock["commit"] + "; observed " + head)
    for relative, expected in lock["files"].items():
        source = core / relative
        require(source.is_file(), "Core source is missing: " + relative)
        require(git_blob_sha(source.read_bytes()) == expected,
                "Core source differs from the pinned blob: " + relative)
    return {"repository": lock["repository"], "commit": head,
            "verified_blob_count": len(lock["files"]), "verified_blobs": lock["files"]}


def grammar_preflight() -> dict:
    packages = (
        ("tree-sitter", "tree_sitter"),
        ("tree-sitter-javascript", "tree_sitter_javascript"),
        ("tree-sitter-typescript", "tree_sitter_typescript"),
        ("tree-sitter-rust", "tree_sitter_rust"),
        ("PyYAML", "yaml"),
    )
    modules, versions, problems = {}, {}, []
    for distribution, module in packages:
        try:
            modules[module] = importlib.import_module(module)
            versions[distribution] = importlib.metadata.version(distribution)
        except (ImportError, importlib.metadata.PackageNotFoundError) as error:
            problems.append(distribution + " is missing or cannot be imported (" + type(error).__name__ + ")")
    require(not problems,
            "Grammar preflight failed before fixture analysis: " + "; ".join(problems)
            + ". Install this example's requirements.txt with the same Python interpreter.")
    require(versions["tree-sitter"] == "0.23.2",
            "Grammar preflight needs tree-sitter 0.23.2; observed " + versions["tree-sitter"])
    ts = modules["tree_sitter"]
    grammars = (
        ("javascript", modules["tree_sitter_javascript"].language, b"function f() { return 1; }"),
        ("typescript", modules["tree_sitter_typescript"].language_typescript, b"const n: number = 1;"),
        ("tsx", modules["tree_sitter_typescript"].language_tsx, b"const view = <div />;"),
        ("rust", modules["tree_sitter_rust"].language, b"pub fn value() -> u32 { 1 }"),
    )
    try:
        for name, factory, text in grammars:
            parser = ts.Parser(ts.Language(factory()))
            require(not parser.parse(text).root_node.has_error,
                    "Grammar preflight could not parse its " + name + " smoke input")
        require(modules["yaml"].safe_load("answer: 1") == {"answer": 1},
                "PyYAML preflight did not return the expected mapping")
    except (TypeError, ValueError, AttributeError) as error:
        raise VerificationError("Grammar ABI preflight failed; use this example's requirements.txt") from error
    return versions


def status_counts(records: list[dict], field: str) -> dict:
    return dict(sorted(Counter(
        "null" if record.get(field) is None else str(record[field])
        for record in records
    ).items()))


def observe_case(engine, name: str, expected: dict, specification: dict) -> dict:
    source = HERE / "fixtures" / name
    require(source.is_dir(), "Missing fixture directory: " + name)
    input_files = sorted(path for path in source.rglob("*") if path.is_file())
    require(input_files and all(not path.is_symlink() for path in input_files),
            "Fixtures must contain regular local files")
    fixture_hashes = {
        path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in input_files
    }
    # Only a synthetic copy is passed to build_graph, never the Core checkout.
    with tempfile.TemporaryDirectory(prefix=".verify-", dir=HERE) as temporary:
        fixture = Path(temporary) / "fixture"
        shutil.copytree(source, fixture)
        graph = engine.build_graph(str(fixture))

    command_id = specification["command_id"]
    nodes = [node for node in graph["nodes"] if node.get("kind") == "app_command"]
    edges = [edge for edge in graph["edges"] if edge.get("dst") == command_id
             and edge.get("kind") in {"alters", "queries"}]
    documents = [node for node in graph["nodes"]
                 if node.get("kind") in {"file", "config_file"}]
    counts = Counter(edge["kind"] for edge in edges)
    require(len(nodes) == expected["command_node_count"], name + ": command node count differs")
    require(all(node.get("id") == command_id and node.get("name") == specification["command_name"]
                for node in nodes), name + ": wrong command identity")
    require(counts["alters"] == expected["alters"] and counts["queries"] == expected["queries"],
            name + ": contract edge counts differ")
    for kind, key in (("alters", "definition_paths"), ("queries", "reference_paths")):
        require(sorted(edge["src"] for edge in edges if edge["kind"] == kind) == expected[key],
                name + ": contract " + kind + " endpoints differ")
    observed_reference = status_counts(edges, "reference_status")
    observed_analysis = status_counts(documents, "analysis_status")
    require(observed_reference == expected["reference_status_counts"],
            name + ": reference statuses differ: " + json.dumps(observed_reference))
    require(observed_analysis == expected["analysis_status_counts"],
            name + ": document analysis statuses differ: " + json.dumps(observed_analysis))
    require({node["path"] for node in documents} == set(fixture_hashes),
            name + ": document paths differ from the fixture")
    for node in nodes:
        ambiguous = (node.get("provenance") or {}).get("ambiguous") is True
        require(ambiguous == expected["ambiguous_command"], name + ": command ambiguity differs")
    require(specification["body_marker"] not in json.dumps(graph, ensure_ascii=False),
            name + ": synthetic body text appeared in the graph")
    return {
        "case": name, "passed": True, "fixture_sha256": fixture_hashes,
        "command_node_count": len(nodes), "ambiguous_command": expected["ambiguous_command"],
        "contract_edge_counts": {"alters": counts["alters"], "queries": counts["queries"]},
        "reference_status_counts": observed_reference,
        "analysis_status_counts": observed_analysis,
        "contract_edges": [
            {key: edge.get(key) for key in ("src", "dst", "kind", "reference_status")}
            for edge in sorted(edges, key=lambda edge: (edge["kind"], edge["src"]))
        ],
        "documents": [
            {"path": node["path"], "analysis_status": node.get("analysis_status")}
            for node in sorted(documents, key=lambda node: node["path"])
        ],
        "body_marker_absent": True,
    }


def verify(core: Path, git: str) -> dict:
    identity = verify_core(core, git)
    dependencies = grammar_preflight()
    sys.path.insert(0, str(core))
    engine = importlib.import_module("code_graph_extract")
    require(Path(engine.__file__).resolve() == core / "code_graph_extract.py",
            "Imported a graph extractor outside --core")
    loaded = engine._ts_languages()
    require({"javascript", "typescript", "tsx", "rust"} <= set(loaded),
            "Core's loader could not load all fixture grammars despite preflight")
    specification = json.loads((HERE / "expectations.json").read_text(encoding="utf-8"))
    results = [observe_case(engine, name, expected, specification)
               for name, expected in specification["cases"].items()]
    return {
        "core": identity, "python": sys.version.split()[0], "dependencies": dependencies,
        "passed_cases": len(results), "results": results,
        "scope": "Static graph extraction of four synthetic Rust/TypeScript fixtures; no Tauri build, database, server or hosted-service test.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", type=Path, required=True, help="Pinned public Core git checkout")
    parser.add_argument("--git", default="git", help="Git executable for read-only HEAD verification")
    parser.add_argument("--report", type=Path, help="Optionally save JSON observations")
    args = parser.parse_args()
    try:
        report = verify(args.core.resolve(), args.git)
        if args.report is not None:
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
    except (VerificationError, OSError, ValueError, ImportError) as error:
        parser.exit(1, "Verification failed: " + str(error) + "\n")
    print("Core " + report["core"]["commit"] + " (" + str(report["core"]["verified_blob_count"]) + " source blobs verified)")
    for case in report["results"]:
        edges = case["contract_edge_counts"]
        print("PASS " + case["case"] + ": alters=" + str(edges["alters"])
              + ", queries=" + str(edges["queries"])
              + ", reference=" + json.dumps(case["reference_status_counts"], sort_keys=True)
              + ", analysis=" + json.dumps(case["analysis_status_counts"], sort_keys=True))
    print(str(report["passed_cases"]) + "/4 synthetic cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

