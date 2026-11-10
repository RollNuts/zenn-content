"""Compare two passing repairs against a requirement stated before the repair.

Executes only the pinned Core demo's synthetic fixture in temporary directories.
The supplied Core checkout is trusted executable code, not untrusted input.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
CORE_PIN = "2c6850617bacaaa5cd31e34a490983597a18086d"
CHECK = '''import inspect, json, os, sys
sys.path.insert(0, os.getcwd())
from billing.pricing import calculate_total
from web.checkout import checkout
try:
    value = checkout()
    runtime = {"status": "passed", "return_value": value}
except TypeError:
    runtime = {"status": "failed", "error_type": "TypeError"}
keyword_only = inspect.signature(calculate_total).parameters["fee"].kind == inspect.Parameter.KEYWORD_ONLY
try:
    calculate_total(100, 5)
except TypeError:
    positional_rejected = True
else:
    positional_rejected = False
requirements = {
    "checkout_returns_105": runtime == {"status": "passed", "return_value": 105},
    "fee_is_keyword_only": keyword_only,
    "positional_fee_is_rejected": positional_rejected,
}
print(json.dumps({"runtime": runtime, "requirements": requirements,
                  "stated_requirements_met": all(requirements.values())}))
'''


class LabError(ValueError):
    pass


def git_environment():
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0",
               GIT_ALLOW_PROTOCOL="", GIT_NO_LAZY_FETCH="1")
    return env


def verify_core(core: Path, git: str):
    def read(*args):
        result = subprocess.run(
            [git, "-c", "core.fsmonitor=false", "-c", "core.hooksPath=" + os.devnull,
             "-C", str(core), *args], capture_output=True, text=True,
            stdin=subprocess.DEVNULL, timeout=20, env=git_environment(),
        )
        if result.returncode:
            raise LabError("core_git_read_failed")
        return result.stdout.strip()
    if read("rev-parse", "HEAD") != CORE_PIN:
        raise LabError("core_revision_mismatch")
    if read("status", "--porcelain", "--untracked-files=all"):
        raise LabError("core_checkout_not_clean")


def check_fixture(root: Path):
    result = subprocess.run(
        [sys.executable, "-B", "-I", "-S", "-c", CHECK], cwd=root,
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=15,
    )
    if result.returncode:
        raise LabError("fixture_check_failed")
    return json.loads(result.stdout)


def run(core: Path, git: str):
    verify_core(core, git)
    spec = importlib.util.spec_from_file_location(
        "core_repair_demo", core / "examples/structural-overlap/demo.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    # Private helpers are deliberately bound to CORE_PIN; no stable Core API is claimed.
    with tempfile.TemporaryDirectory(prefix="core-repair-exercise-") as directory:
        parent = Path(directory)
        original = demo._case("function_contract", parent, git)
        fixture = parent / "function_contract"
        pricing = (fixture / demo.PRICING).read_text(encoding="utf-8")
        checkout = (fixture / demo.CHECKOUT).read_text(encoding="utf-8")
        before = check_fixture(fixture)

        relaxed = pricing.replace("amount, *, fee=5", "amount, fee=5")
        adapted = checkout.replace("calculate_total(100, 5)", "calculate_total(100, fee=5)")
        if relaxed == pricing or adapted == checkout:
            raise LabError("unexpected_pinned_fixture")
        demo._write(fixture, {demo.PRICING: relaxed})
        repair_a = check_fixture(fixture)
        demo._write(fixture, {demo.PRICING: pricing, demo.CHECKOUT: adapted})
        repair_b = check_fixture(fixture)
    verify_core(core, git)
    return {
        "exercise": "repair-review-v1", "core_revision": CORE_PIN,
        "scope": "One synthetic requirement exercise; not bug prediction or merge approval.",
        "executed": "Only generated synthetic Python fixture code and trusted pinned Core code.",
        "original_evidence": {
            "git_merge": original["git_merge"],
            "static": original["relationship"]["status"],
            "history": original["cochange"]["status"],
        },
        "before_repair": before, "repair_a_relax_callee": repair_a,
        "repair_b_adapt_caller": repair_b,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", required=True, type=Path,
                        help="Trusted, clean Core checkout at the documented fixed revision")
    parser.add_argument("--git", default=shutil.which("git") or "git")
    args = parser.parse_args()
    try:
        report = run(args.core.resolve(), args.git)
    except LabError as error:
        print(json.dumps({"status": "error", "error": str(error)}))
        return 2
    except (OSError, ValueError, ImportError, KeyError, TypeError,
            AttributeError, subprocess.SubprocessError):
        print(json.dumps({"status": "error", "error": "exercise_not_completed"}))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
