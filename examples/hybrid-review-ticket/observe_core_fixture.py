#!/usr/bin/env python3
"""Observe a trusted, pinned Core synthetic fixture; this is not a sandbox."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

CORE_REVISION = "2c6850617bacaaa5cd31e34a490983597a18086d"
INSPECT = '''import ast, inspect, json, os, sys
from pathlib import Path
sys.path.insert(0, os.getcwd())
from web.checkout import checkout
report = {}
tree = ast.parse(Path("web/checkout.py").read_text())
call = next(node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "calculator")
report["literal_call_arguments"] = {
    "positional": [ast.literal_eval(node) for node in call.args],
    "keyword": {node.arg: ast.literal_eval(node.value) for node in call.keywords}}
def trace(frame, event, arg):
    if frame.f_code is checkout.__code__ and event == "line" and "calculator" in frame.f_locals:
        target = frame.f_locals["calculator"]
        report["resolved_target"] = {"module": target.__module__, "name": target.__name__,
                                     "signature": str(inspect.signature(target))}
    return trace
sys.settrace(trace)
try:
    report["execution"] = {"status": "passed", "return_value": checkout()}
except TypeError:
    report["execution"] = {"status": "failed", "error_type": "TypeError"}
finally:
    sys.settrace(None)
print(json.dumps(report))
'''


def verify_checkout(root, git):
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")

    def read_git(*arguments):
        return subprocess.run([git, "-c", "core.fsmonitor=false", "-C", str(root), *arguments],
                              env=environment, capture_output=True, text=True, timeout=30,
                              stdin=subprocess.DEVNULL, check=True).stdout.strip()

    if read_git("rev-parse", "HEAD") != CORE_REVISION:
        raise ValueError("Core HEAD must match " + CORE_REVISION)
    if Path(read_git("rev-parse", "--show-toplevel")).resolve() != root:
        raise ValueError("--core-repo must name the repository root")
    if read_git("status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("Use a clean, trusted Core checkout without untracked files")


def observe(root, git):
    verify_checkout(root, git)
    # Imports execute the trusted pinned source. Disabling bytecode avoids writes
    # to that checkout; the synthetic Git repositories live in a temporary dir.
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(
        "pinned_demo", root / "examples/structural-overlap/demo.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    original_runtime = demo._runtime
    observations = []

    def observed_runtime(fixture_root):
        original = original_runtime(fixture_root)
        process = subprocess.run([sys.executable, "-B", "-I", "-S", "-c", INSPECT],
                                 cwd=fixture_root, capture_output=True, text=True, timeout=10,
                                 stdin=subprocess.DEVNULL, check=True)
        observation = json.loads(process.stdout)
        if observation["execution"] != original:
            raise ValueError("The observed execution differs from the original fixture")
        observation["state"] = ("change_a", "change_b", "integrated")[len(observations)]
        observations.append(observation)
        return original

    demo._runtime = observed_runtime
    with tempfile.TemporaryDirectory(prefix="core-dynamic-observation-") as directory:
        case = demo._case("dynamic_lookup", Path(directory), git)
    if (len(observations) != 3
            or case["integrated"] != {"status": "failed", "error_type": "TypeError"}):
        raise ValueError("The expected three-state observation is incomplete")
    verify_checkout(root, git)
    return {"scope": "Synthetic fixture only; callable observed with a trace hook; call literals read by AST.",
            "case": case["name"], "observations": observations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-repo", required=True, type=Path,
                        help="Clean, trusted Core repository at the pinned revision")
    args = parser.parse_args()
    git = shutil.which("git")
    if not git:
        parser.error("Git is required on PATH")
    try:
        report = observe(args.core_repo.resolve(), git)
    except ValueError as error:
        parser.exit(1, str(error) + "\n")
    except (OSError, subprocess.SubprocessError):
        parser.exit(1, "Could not complete the pinned Core observation; no result is claimed.\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
