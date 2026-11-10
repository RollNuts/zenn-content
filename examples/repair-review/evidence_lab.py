"""Measure two synthetic evidence contrasts with trusted, pinned Core code.

Only generated fixtures are executed. The Core CLI parses them separately;
loading the supplied Core checkout is trusted-code execution, not a sandbox.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
from lab import CORE_PIN, LabError, git_environment, verify_core


REVIEW = '''import runpy, sys
core = sys.argv.pop(1)
sys.path.insert(0, core)
runpy.run_module("tools.review_file", run_name="__main__")
'''


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise LabError("invalid_arguments")


def _load_demo(core):
    spec = importlib.util.spec_from_file_location(
        "core_evidence_demo", core / "examples/structural-overlap/demo.py")
    module = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        spec.loader.exec_module(module)
    return module


def _git_path(git):
    executable = shutil.which(git)
    if executable is None:
        raise LabError("git_unavailable")
    return str(Path(executable).resolve())


def _fixture(demo, parent, name, git):
    root = parent / name
    root.mkdir()
    fixture_git = demo.FixtureGit(git, root)
    # Stable synthetic commits, independent of the current wall clock.
    fixture_git.environment.update(GIT_AUTHOR_DATE="2020-01-01T00:00:00Z",
                                   GIT_COMMITTER_DATE="2020-01-01T00:00:00Z")
    demo._write(root, {demo.PRICING: demo.BASE_PRICING,
                       demo.CHECKOUT: demo.BASE_CHECKOUT,
                       demo.BANNER: 'def banner():\n    return "Order summary"\n'})
    fixture_git.call("init", "--quiet")
    fixture_git.call("symbolic-ref", "HEAD", "refs/heads/main")
    fixture_git.commit()
    demo._seed_history("repeated_joint_updates", fixture_git)
    return fixture_git


def _review(core, fixture_git, target, binary_dir):
    env = git_environment()
    env["PATH"] = str(binary_dir) + os.pathsep + env.get("PATH", os.defpath)
    result = subprocess.run(
        [sys.executable, "-B", "-I", "-S", "-c", REVIEW,
         str(core), str(fixture_git.root), target], cwd=core, env=env,
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=45,
    )
    if result.returncode or result.stderr:
        raise LabError("core_review_failed")
    data = json.loads(result.stdout)
    if data.get("schema_version") != "local-file-review-v1":
        raise LabError("unexpected_core_report")
    # Explicit metadata projection: never emit input roots or source bodies.
    return {name: data[name] for name in ("target", "provenance", "static", "history")}


def _snapshot(core, demo, fixture_git, binary_dir):
    review = _review(core, fixture_git, demo.PRICING, binary_dir)
    # Separate executable check; review_file itself does not execute the fixture.
    return {"review": review, "runtime": demo._runtime(fixture_git.root)}


def _has_peer(snapshot, section, peer):
    return any(row["file"] == peer
               for row in snapshot["review"][section]["candidates"])


def _time_bases(core, demo, parent, git, binary_dir):
    fixture_git = _fixture(demo, parent, "time-bases", git)
    before = _snapshot(core, demo, fixture_git, binary_dir)
    demo._write(fixture_git.root, {demo.CHECKOUT: demo.DYNAMIC_CHECKOUT})
    after = _snapshot(core, demo, fixture_git, binary_dir)
    old, new = before["review"], after["review"]
    changed = sorted(key for key in set(old["provenance"]) | set(new["provenance"])
                     if old["provenance"].get(key) != new["provenance"].get(key))
    return {
        "target": demo.PRICING, "peer": demo.CHECKOUT,
        "before_uncommitted_edit": before, "after_uncommitted_edit": after,
        "comparison": {
            "same_runtime": before["runtime"] == after["runtime"],
            "static_peer_before": _has_peer(before, "static", demo.CHECKOUT),
            "static_peer_after": _has_peer(after, "static", demo.CHECKOUT),
            "same_history_section": old["history"] == new["history"],
            "same_head": old["provenance"]["head"] == new["provenance"]["head"],
            "changed_provenance_fields": changed,
        },
    }


def _semantic_tree(root, paths):
    return {path: ast.dump(ast.parse((root / path).read_text(encoding="utf-8")),
                           include_attributes=False) for path in paths}


def _more_coedits(core, demo, parent, git, binary_dir):
    fixture_git = _fixture(demo, parent, "more-coedits", git)
    paths = (demo.PRICING, demo.CHECKOUT)
    before_tree = _semantic_tree(fixture_git.root, paths)
    before = _snapshot(core, demo, fixture_git, binary_dir)
    raw_before = demo._cochange(fixture_git, [demo.PRICING], [demo.CHECKOUT])
    for index in range(8):
        for path in paths:
            file = fixture_git.root / path
            demo._write(fixture_git.root, {
                path: file.read_text(encoding="utf-8") + f"# Extra joint comment {index}\n"})
        fixture_git.commit()
    after = _snapshot(core, demo, fixture_git, binary_dir)
    raw_after = demo._cochange(fixture_git, [demo.PRICING], [demo.CHECKOUT])
    return {
        "target": demo.PRICING, "peer": demo.CHECKOUT,
        "extra_comment_only_joint_commits": 8,
        "before_extra_coedits": {**before, "pair_evidence": raw_before},
        "after_extra_coedits": {**after, "pair_evidence": raw_after},
        "comparison": {
            "same_python_ast_ignoring_comments": before_tree == _semantic_tree(fixture_git.root, paths),
            "same_runtime": before["runtime"] == after["runtime"],
            "same_static_section": before["review"]["static"] == after["review"]["static"],
            "history_peer_before": _has_peer(before, "history", demo.CHECKOUT),
            "history_peer_after": _has_peer(after, "history", demo.CHECKOUT),
        },
    }


def run(core, git):
    git = _git_path(git)
    verify_core(core, git)
    demo = _load_demo(core)
    with tempfile.TemporaryDirectory(prefix="core-evidence-exercise-") as directory:
        parent = Path(directory)
        binary_dir = parent / "selected-git"
        binary_dir.mkdir()
        # A launcher preserves the selected executable's own argv[0]; a symlink
        # can break Git distributions whose launcher locates siblings from it.
        launcher = binary_dir / "git"
        launcher.write_text("#!/bin/sh\nexec " + shlex.quote(git) + ' "$@"\n', encoding="utf-8")
        launcher.chmod(0o700)
        time_bases = _time_bases(core, demo, parent, git, binary_dir)
        more_coedits = _more_coedits(core, demo, parent, git, binary_dir)
    verify_core(core, git)
    return {
        "exercise": "evidence-contrasts-v1", "core_revision": CORE_PIN,
        "scope": "Two constructed evidence contrasts; not accuracy or merge-safety evaluation.",
        "execution_boundary": "Trusted pinned Core code; synthetic runtime checks are separate from Core CLI parsing. No sandbox claim.",
        "time_bases": time_bases, "more_coedits": more_coedits,
    }


def main():
    parser = Parser(description=__doc__)
    parser.add_argument("--core", required=True, type=Path)
    parser.add_argument("--git", default=shutil.which("git") or "git")
    try:
        args = parser.parse_args()
        report = run(args.core.resolve(), args.git)
    except LabError as error:
        print(json.dumps({"status": "error", "error": str(error)}))
        return 2
    except Exception:
        print('{"status":"error","error":"exercise_not_completed"}')
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
