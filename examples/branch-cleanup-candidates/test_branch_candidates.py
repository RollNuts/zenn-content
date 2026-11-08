import copy
from datetime import datetime, timezone
import unittest

from branch_candidates import candidates


REPO = "example/project"
CUTOFF = datetime(2026, 11, 7, 9, 25, 18, tzinfo=timezone.utc)


def branch(name="feature", sha="original", protected=False):
    return {"name": name, "commit": {"sha": sha}, "protected": protected}


def pr(number=1, name="feature", sha="original", repo=REPO, merged="2026-11-06T12:00:00Z", state="closed"):
    return {"number": number, "state": state, "merged_at": merged,
            "head": {"ref": name, "sha": sha, "repo": {"full_name": repo}},
            "base": {"ref": "main", "repo": {"full_name": REPO}}}


class CandidateTests(unittest.TestCase):
    def select(self, branches, prs):
        return candidates(branches, prs, REPO, "main", CUTOFF)

    def test_matching_old_merged_head_is_a_candidate(self):
        self.assertEqual(self.select([branch()], [pr()]),
                         [{"branch": "feature", "sha": "original", "merged_pr": 1}])

    def test_advanced_head_is_kept(self):
        self.assertEqual(self.select([branch(sha="new-work")], [pr()]), [])

    def test_an_open_pr_keeps_the_branch_even_with_an_older_merge(self):
        self.assertEqual(self.select([branch()], [pr(), pr(2, state="open", merged=None)]), [])

    def test_same_name_from_a_fork_is_not_a_match(self):
        self.assertEqual(self.select([branch()], [pr(repo="someone/fork")]), [])

    def test_an_open_pr_using_the_branch_as_base_is_kept_even_from_a_fork(self):
        for head_repo in [REPO, "someone/fork"]:
            with self.subTest(head_repo=head_repo):
                child = pr(2, name="child", repo=head_repo, state="open", merged=None)
                child["base"]["ref"] = "feature"
                self.assertEqual(self.select([branch()], [pr(), child]), [])

    def test_recent_or_closed_unmerged_prs_are_kept(self):
        for item in [pr(merged="2026-11-07T09:25:19Z"), pr(merged=None)]:
            with self.subTest(item=item):
                self.assertEqual(self.select([branch()], [item]), [])

    def test_main_protected_and_unknown_protection_are_kept(self):
        for item in [branch("main"), branch(protected=True), branch(protected=None)]:
            with self.subTest(item=item):
                self.assertEqual(self.select([item], [pr(name=item["name"])]), [])

    def test_merge_to_another_base_is_kept(self):
        item = pr()
        item["base"]["ref"] = "release"
        self.assertEqual(self.select([branch()], [item]), [])

    def test_deleted_fork_and_empty_input_are_kept(self):
        item = pr()
        item["head"]["repo"] = None
        self.assertEqual(self.select([branch()], [item]), [])
        self.assertEqual(self.select([], []), [])

    def test_input_records_are_not_mutated(self):
        branches, prs = [branch()], [pr()]
        before = copy.deepcopy((branches, prs))
        self.select(branches, prs)
        self.assertEqual((branches, prs), before)


if __name__ == "__main__":
    unittest.main()
