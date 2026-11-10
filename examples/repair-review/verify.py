"""Run the actual repair contrast and a wrong-revision negative control."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from lab import CORE_PIN, git_environment


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core", required=True, type=Path)
    parser.add_argument("--git", default=shutil.which("git") or "git")
    args = parser.parse_args()
    lab = Path(__file__).with_name("lab.py")
    def invoke(core):
        return subprocess.run([sys.executable, "-B", str(lab), "--core", str(core),
                               "--git", args.git], capture_output=True, text=True, timeout=90)
    result = invoke(args.core.resolve())
    require(result.returncode == 0, "The actual exercise did not complete")
    observed = json.loads(result.stdout)
    expected = json.loads(lab.with_name("expected-output.json").read_text(encoding="utf-8"))
    require(observed == expected, "Observed output differs from the recorded fixed-version result")
    a, b = observed["repair_a_relax_callee"], observed["repair_b_adapt_caller"]
    require(a["runtime"] == b["runtime"] == {"status": "passed", "return_value": 105},
            "The runtime contrast was not reproduced")
    require(not a["stated_requirements_met"] and b["stated_requirements_met"],
            "The stated contract contrast was not reproduced")
    require(observed["core_revision"] == CORE_PIN, "Wrong recorded Core revision")
    print("PASS: actual synthetic repairs both return105, but only B preserves the stated contract")
    with tempfile.TemporaryDirectory(prefix="repair-negative-control-") as directory:
        root = Path(directory)
        env = git_environment()
        for command in (["init", "--quiet"], ["-c", "user.name=Lab Reader", "-c",
                         "user.email=reader@example.invalid", "-c", "commit.gpgsign=false",
                         "commit", "--allow-empty", "--quiet", "-m", "Synthetic wrong revision"]):
            subprocess.run([args.git, "-C", str(root), *command], env=env,
                           check=True, capture_output=True, timeout=20)
        result = invoke(root)
        require(result.returncode == 2, "A wrong revision was not rejected")
        require(json.loads(result.stdout) == {"status": "error", "error": "core_revision_mismatch"},
                "Wrong revision returned an unexpected error")
        require(not result.stderr, "Wrong revision exposed unexpected stderr")
    print("PASS: a different Core revision is rejected before fixture execution")


if __name__ == "__main__":
    main()
