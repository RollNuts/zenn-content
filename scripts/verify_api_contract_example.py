"""Verify all four documented CLI results, including the intentional failures."""

from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "api-contract-repair" / "repair_review.py"
TESTS = (
    "test_checkout_value",
    "test_fee_is_keyword_only",
    "test_keyword_call",
    "test_positional_fee_is_rejected",
)
ROLLBACK_FAILURES = ("test_fee_is_keyword_only", "test_positional_fee_is_rejected")


def verify(repair, value_only):
    flags = ["--repair", repair] + (["--value-only"] if value_only else [])
    label = " ".join(flags)
    expected = dict.fromkeys(TESTS[:1] if value_only else TESTS, "ok")
    expected_code, expected_summary = 0, "OK"
    if repair == "rollback" and not value_only:
        expected.update(dict.fromkeys(ROLLBACK_FAILURES, "FAIL"))
        expected_code, expected_summary = 1, "FAILED (failures=2)"
    try:
        result = subprocess.run(
            [sys.executable, str(EXAMPLE), *flags],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"FAIL {label}: {error}", file=sys.stderr)
        return False

    output = result.stdout
    tests = re.findall(r"^(test_\w+) \([^\n]+\) \.\.\. (.+)$", output, re.MULTILINE)
    counts = re.findall(r"^Ran (\d+) tests? in [0-9.]+s$", output, re.MULTILINE)
    summaries = re.findall(r"^(?:OK\b.*|FAILED\b.*)$", output, re.MULTILINE)
    if (
        sorted(tests) != sorted(expected.items())
        or counts != [str(len(expected))]
        or summaries != [expected_summary]
        or result.returncode != expected_code
    ):
        print(
            f"FAIL {label}: expected {expected}, count={len(expected)}, "
            f"summary={expected_summary!r}, exit={expected_code}; "
            f"observed {tests}, counts={counts}, summaries={summaries}, "
            f"exit={result.returncode}\n{output}",
            file=sys.stderr,
        )
        return False
    print(f"PASS {label}: count={len(expected)}, {expected_summary}, exit={expected_code}")
    return True


def main():
    success = True
    for value_only in (True, False):
        for repair in ("rollback", "keyword"):
            success = verify(repair, value_only) and success
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
