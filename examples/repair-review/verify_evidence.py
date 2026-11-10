"""Check measured contrasts and bounded negative controls, also under python -O."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
from lab import CORE_PIN, LabError, git_environment


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise LabError("invalid_arguments")


def require(condition, code):
    if not condition:
        raise LabError(code)


def has_peer(snapshot, section, peer):
    return any(row["file"] == peer for row in snapshot["review"][section]["candidates"])


def check_observations(report):
    require(report["core_revision"] == CORE_PIN, "wrong_recorded_core_revision")
    time = report["time_bases"]
    a, b = time["before_uncommitted_edit"], time["after_uncommitted_edit"]
    success = {"status": "passed", "return_value": 105}
    require(a["runtime"] == b["runtime"] == success, "time_bases_runtime_changed")
    old, new = a["review"], b["review"]
    old_prov, new_prov = old["provenance"], new["provenance"]
    require(old_prov["head"] == new_prov["head"], "raw_time_head_changed")
    require(old_prov["target_sha256"] == new_prov["target_sha256"], "raw_time_target_hash_changed")
    require(old_prov["status_sha256"] != new_prov["status_sha256"], "raw_time_status_hash_not_changed")
    changed = sorted(key for key in set(old_prov) | set(new_prov)
                     if old_prov.get(key) != new_prov.get(key))
    require(changed == ["dirty", "status_sha256"], "unexpected_time_bases_provenance_change")
    require(old_prov["dirty"] is False and new_prov["dirty"] is True, "dirty_transition_missing")
    require(has_peer(a, "static", time["peer"]) and not has_peer(b, "static", time["peer"]),
            "time_bases_static_contrast_not_observed")
    require(old["history"] == new["history"], "history_equality_not_measured")
    require(has_peer(a, "history", time["peer"]) and has_peer(b, "history", time["peer"]),
            "time_bases_history_peer_missing")
    require(time["comparison"] == {
        "same_runtime": a["runtime"] == b["runtime"],
        "static_peer_before": has_peer(a, "static", time["peer"]),
        "static_peer_after": has_peer(b, "static", time["peer"]),
        "same_history_section": old["history"] == new["history"],
        "same_head": old_prov["head"] == new_prov["head"],
        "changed_provenance_fields": changed,
    }, "time_comparison_inconsistent_with_raw")

    more = report["more_coedits"]
    a, b = more["before_extra_coedits"], more["after_extra_coedits"]
    require(a["runtime"] == b["runtime"] == success, "coedits_runtime_changed")
    c = more["comparison"]
    require(c["same_python_ast_ignoring_comments"] is True, "coedits_python_ast_changed")
    require(a["review"]["static"] == b["review"]["static"], "raw_coedits_static_changed")
    require(has_peer(a, "static", more["peer"]) and has_peer(b, "static", more["peer"]),
            "coedits_static_peer_missing")
    require(has_peer(a, "history", more["peer"]) and not has_peer(b, "history", more["peer"]),
            "coedits_filter_contrast_not_observed")
    require(c == {
        "same_python_ast_ignoring_comments": True,
        "same_runtime": a["runtime"] == b["runtime"],
        "same_static_section": a["review"]["static"] == b["review"]["static"],
        "history_peer_before": has_peer(a, "history", more["peer"]),
        "history_peer_after": has_peer(b, "history", more["peer"]),
    }, "coedits_comparison_inconsistent_with_raw")
    require(len(a["pair_evidence"]["file_pairs"]) == len(b["pair_evidence"]["file_pairs"]) == 1,
            "unexpected_raw_pair_count")
    x, y = a["pair_evidence"]["file_pairs"][0], b["pair_evidence"]["file_pairs"][0]
    require((x["co"], x["n_a"], x["n_b"], x["n_total"]) == (6, 6, 6, 14),
            "unexpected_initial_counts")
    require((y["co"], y["n_a"], y["n_b"], y["n_total"]) == (14, 14, 14, 22),
            "unexpected_extra_coedit_counts")
    require(x["lift"] > 2 and y["lift"] < 2
            and x["passes_default_filters"] and not y["passes_default_filters"],
            "lift_threshold_contrast_not_observed")
    require((a["review"]["history"]["target_change_count"], a["review"]["history"]["commits_retained"])
            == (6, 14) and
            (b["review"]["history"]["target_change_count"], b["review"]["history"]["commits_retained"])
            == (14, 22), "raw_history_counts_inconsistent")
    require(a["review"]["provenance"]["dirty"] is False
            and b["review"]["provenance"]["dirty"] is False, "coedits_checkout_dirty")


def verify(core, git):
    script = Path(__file__).with_name("evidence_lab.py")
    def invoke(arguments):
        flags = ["-O"] if sys.flags.optimize else []
        return subprocess.run([sys.executable, "-B", *flags, str(script), *arguments],
                              capture_output=True, text=True, timeout=120,
                              stdin=subprocess.DEVNULL, env=git_environment())
    arguments = ["--core", str(core), "--git", git]
    result = invoke(arguments)
    require(result.returncode == 0 and not result.stderr, "actual_exercise_failed")
    report = json.loads(result.stdout)
    check_observations(report)

    altered = copy.deepcopy(report)
    altered["more_coedits"]["after_extra_coedits"]["pair_evidence"]["file_pairs"][0]["co"] = 13
    try:
        check_observations(altered)
    except LabError as error:
        require(str(error) == "unexpected_extra_coedit_counts", "unexpected_negative_check_result")
    else:
        raise LabError("tampered_counts_were_accepted")

    # Each mutation keeps the collector's comparison summary untouched.
    # Reject the raw contradiction directly, including under python -O.
    raw_controls = [
        ("raw_head_change_rejected", "raw_time_head_changed",
         ("time_bases", "after_uncommitted_edit", "review", "provenance"), "head", "0" * 40),
        ("raw_target_hash_change_rejected", "raw_time_target_hash_changed",
         ("time_bases", "after_uncommitted_edit", "review", "provenance"), "target_sha256", "0" * 64),
        ("raw_status_hash_equality_rejected", "raw_time_status_hash_not_changed",
         ("time_bases", "after_uncommitted_edit", "review", "provenance"), "status_sha256",
         report["time_bases"]["before_uncommitted_edit"]["review"]["provenance"]["status_sha256"]),
        ("raw_static_change_rejected", "raw_coedits_static_changed",
         ("more_coedits", "after_extra_coedits", "review", "static"), "candidates", []),
    ]
    for label, expected_error, path, key, value in raw_controls:
        altered = copy.deepcopy(report)
        destination = altered
        for part in path:
            destination = destination[part]
        destination[key] = value
        try:
            check_observations(altered)
        except LabError as error:
            require(str(error) == expected_error, "unexpected_raw_negative_check_result")
        else:
            raise LabError(label.replace("_rejected", "_accepted"))

    altered = copy.deepcopy(report)
    altered["time_bases"]["comparison"]["same_head"] = False
    try:
        check_observations(altered)
    except LabError as error:
        require(str(error) == "time_comparison_inconsistent_with_raw", "unexpected_summary_check_result")
    else:
        raise LabError("inconsistent_summary_accepted")

    with tempfile.TemporaryDirectory(prefix="evidence-negative-control-") as directory:
        root = Path(directory)
        for command in (["init", "--quiet"],
                        ["-c", "user.name=Lab Reader", "-c", "user.email=reader@example.invalid",
                         "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + str(root / "no-hooks"),
                         "commit", "--allow-empty", "--quiet", "-m", "Synthetic wrong revision"]):
            subprocess.run([git, "-C", str(root), *command], env=git_environment(), check=True,
                           capture_output=True, timeout=20, stdin=subprocess.DEVNULL)
        result = invoke(["--core", str(root), "--git", git])
        require(result.returncode == 2 and not result.stderr
                and json.loads(result.stdout) == {"status": "error", "error": "core_revision_mismatch"},
                "wrong_revision_not_bounded")
    result = invoke(["--unexpected-option"])
    require(result.returncode == 2 and not result.stderr
            and json.loads(result.stdout) == {"status": "error", "error": "invalid_arguments"},
            "invalid_arguments_not_bounded")
    result = invoke(["--core", str(core), "--git", "missing-evidence-lab-git-executable"])
    require(result.returncode == 2 and not result.stderr
            and json.loads(result.stdout) == {"status": "error", "error": "git_unavailable"},
            "invalid_git_not_bounded")
    return {"status": "passed", "core_revision": CORE_PIN,
            "optimization_enabled": bool(sys.flags.optimize),
            "checks": ["actual_time_bases", "actual_more_coedits", "tampered_counts_rejected",
                       *[control[0] for control in raw_controls], "inconsistent_summary_rejected",
                       "wrong_revision_rejected", "invalid_arguments_bounded", "invalid_git_bounded"]}


def main():
    parser = Parser(description=__doc__)
    parser.add_argument("--core", required=True, type=Path)
    parser.add_argument("--git", default=shutil.which("git") or "git")
    try:
        args = parser.parse_args()
        report = verify(args.core.resolve(), args.git)
    except LabError as error:
        print(json.dumps({"status": "error", "error": str(error)}))
        return 2
    except Exception:
        print('{"status":"error","error":"verification_not_completed"}')
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
