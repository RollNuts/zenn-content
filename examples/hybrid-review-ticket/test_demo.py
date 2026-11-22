"""Boundary tests for authored inputs; no model or repository is accessed."""
from copy import deepcopy
import unittest

from demo import accept_reply, fixture, route, run_demo


class HandoffTests(unittest.TestCase):
    def test_routes_and_reply_cases(self):
        cases = {row["case"]: row["outcome"] for row in run_demo()["cases"]}
        self.assertEqual(cases, {
            "local_evidence_sufficient": "local_test_plan",
            "dynamic_question": "cloud_question_prepared",
            "sending_denied": "hold_local",
            "no_relationship_observed": "needs_local_observation",
            "current_reply": "inspection_plan_accepted",
            "stale_reply_after_A2": "rejected",
            "missing_base": "rejected",
            "different_base": "rejected",
            "unknown_evidence": "rejected",
            "executable_field": "rejected",
        })

    def test_every_revision_field_is_required_and_must_match(self):
        ticket, reply = fixture()
        for field in ("base", "head_a", "head_b"):
            for value in (None, "", "different"):
                with self.subTest(field=field, value=value):
                    bad = deepcopy(reply)
                    bad["revisions"][field] = value
                    self.assertEqual(accept_reply(ticket, bad)["outcome"], "rejected")
            bad = deepcopy(reply)
            del bad["revisions"][field]
            self.assertEqual(accept_reply(ticket, bad)["reason"], "incomplete_revisions")
            bad_ticket = deepcopy(ticket)
            del bad_ticket["revisions"][field]
            self.assertEqual(route(bad_ticket)["outcome"], "rejected")

    def test_unknown_or_missing_ids_are_rejected(self):
        ticket, reply = fixture()
        changes = [("ticket_id", "unknown"), ("evidence_ids", ["unknown"]),
                   ("check_ids", ["unknown"]), ("check_ids", []),
                   ("evidence_ids", []), ("check_ids", ["run_combined_checkout"] * 2),
                   ("check_ids", [["run_combined_checkout"]])]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                bad = deepcopy(reply)
                bad[field] = value
                self.assertEqual(accept_reply(ticket, bad)["outcome"], "rejected")

    def test_extra_fields_never_become_executable_instructions(self):
        ticket, reply = fixture()
        for field in ("code", "command", "merge_allowed", "explanation"):
            with self.subTest(field=field):
                bad = {**reply, field: "untrusted content"}
                self.assertEqual(accept_reply(ticket, bad)["reason"],
                                 "unexpected_or_missing_fields")
        bad = deepcopy(reply)
        bad["revisions"]["extra"] = "unknown"
        self.assertEqual(accept_reply(ticket, bad)["outcome"], "rejected")

    def test_no_reply_is_accepted_after_sending_is_denied(self):
        ticket, reply = fixture()
        ticket["send_allowed"] = False
        self.assertEqual(route(ticket)["outcome"], "hold_local")
        self.assertEqual(accept_reply(ticket, reply)["reason"], "reply_not_requested")
        for value in (None, 1, "true"):
            ticket["send_allowed"] = value
            self.assertEqual(route(ticket)["outcome"], "rejected")

    def test_missing_evidence_is_never_a_safety_verdict(self):
        ticket, reply = fixture()
        ticket["evidence"] = {"E-static": "not_observed", "E-history": "not_observed"}
        self.assertEqual(route(ticket)["outcome"], "needs_local_observation")
        self.assertEqual(accept_reply(ticket, reply)["outcome"], "rejected")


if __name__ == "__main__":
    unittest.main()
