#!/usr/bin/env python3
"""Deterministic handoff only: invented revisions, evidence, and model replies.

No LLM, network, repository lookup, or command execution is performed.
Accepted replies remain inspection plans; they never authorize a merge.
"""
from copy import deepcopy
import json


CHECKS = {
    "observe_dynamic_target": "Observe the resolved callable and accepted arguments.",
    "run_combined_checkout": "Run checkout tests on the exact combined revisions.",
    "inspect_other_callers": "Inspect other callers before choosing further tests.",
}
TICKET_FIELDS = {"ticket_id", "revisions", "evidence", "local_checks", "send_allowed"}
REPLY_FIELDS = {"ticket_id", "revisions", "evidence_ids", "check_ids"}
REVISION_FIELDS = {"base", "head_a", "head_b"}
EVIDENCE_IDS = {"E-static", "E-history"}


def complete_revisions(value):
    return (type(value) is dict and set(value) == REVISION_FIELDS
            and all(type(label) is str and label.strip() for label in value.values()))


def valid_ids(value, allowed, *, required=False):
    return (type(value) is list and (not required or bool(value))
            and all(type(item) is str and item in allowed for item in value)
            and len(set(value)) == len(value))


def valid_ticket(ticket):
    if type(ticket) is not dict or set(ticket) != TICKET_FIELDS:
        return False
    evidence = ticket["evidence"]
    return (type(ticket["ticket_id"]) is str and bool(ticket["ticket_id"].strip())
            and complete_revisions(ticket["revisions"])
            and type(evidence) is dict and bool(evidence)
            and set(evidence) <= EVIDENCE_IDS
            and all(state in ("observed", "not_observed") for state in evidence.values())
            and valid_ids(ticket["local_checks"], CHECKS)
            and type(ticket["send_allowed"]) is bool)


def result(outcome, reason, check_ids=()):
    return {"outcome": outcome, "reason": reason, "check_ids": list(check_ids)}


def route(ticket):
    """Choose a next step using manually supplied facts, never a safety verdict."""
    if not valid_ticket(ticket):
        return result("rejected", "invalid_ticket")
    if ticket["local_checks"]:
        return result("local_test_plan", "local_evidence_sufficient",
                      ticket["local_checks"])
    if "observed" not in ticket["evidence"].values():
        return result("needs_local_observation", "not_observed_is_not_safe")
    if ticket["send_allowed"] is not True:
        return result("hold_local", "sending_not_allowed")
    return result("cloud_question_prepared", "additional_inspection_plan_needed")


def accept_reply(ticket, reply):
    """Check a reply against the current supplied ticket; do not run anything."""
    if route(ticket)["outcome"] != "cloud_question_prepared":
        return result("rejected", "reply_not_requested")
    if type(reply) is not dict or set(reply) != REPLY_FIELDS:
        return result("rejected", "unexpected_or_missing_fields")
    if reply["ticket_id"] != ticket["ticket_id"]:
        return result("rejected", "unknown_ticket_id")
    if not complete_revisions(reply["revisions"]):
        return result("rejected", "incomplete_revisions")
    if reply["revisions"] != ticket["revisions"]:
        return result("rejected", "revision_mismatch")
    if not valid_ids(reply["evidence_ids"], ticket["evidence"], required=True):
        return result("rejected", "unknown_or_missing_evidence_id")
    if not valid_ids(reply["check_ids"], CHECKS, required=True):
        return result("rejected", "unknown_or_missing_check_id")
    return result("inspection_plan_accepted", "human_review_and_execution_still_required",
                  reply["check_ids"])


def fixture():
    """All values are authored examples, not extractor or model observations."""
    ticket = {
        "ticket_id": "pair-A-B",
        "revisions": {"base": "B0", "head_a": "A1", "head_b": "B1"},
        "evidence": {"E-static": "not_observed", "E-history": "observed"},
        "local_checks": [],
        "send_allowed": True,
    }
    reply = {
        "ticket_id": "pair-A-B",
        "revisions": deepcopy(ticket["revisions"]),
        "evidence_ids": ["E-history"],
        "check_ids": ["observe_dynamic_target", "run_combined_checkout"],
    }
    return ticket, reply


def run_demo():
    ticket, reply = fixture()
    local = deepcopy(ticket)
    local["evidence"]["E-static"] = "observed"
    local["local_checks"] = ["run_combined_checkout", "inspect_other_callers"]
    denied = deepcopy(ticket)
    denied["send_allowed"] = False
    unobserved = deepcopy(ticket)
    unobserved["evidence"]["E-history"] = "not_observed"
    updated = deepcopy(ticket)
    updated["revisions"]["head_a"] = "A2"
    incomplete = deepcopy(reply)
    del incomplete["revisions"]["base"]
    wrong_base = deepcopy(reply)
    wrong_base["revisions"]["base"] = "B-other"
    unknown = deepcopy(reply)
    unknown["evidence_ids"] = ["E-invented"]
    executable = deepcopy(reply)
    executable["code"] = "print('untrusted reply: never executed')"
    cases = [
        ("local_evidence_sufficient", route(local)),
        ("dynamic_question", route(ticket)),
        ("sending_denied", route(denied)),
        ("no_relationship_observed", route(unobserved)),
        ("current_reply", accept_reply(ticket, reply)),
        ("stale_reply_after_A2", accept_reply(updated, reply)),
        ("missing_base", accept_reply(ticket, incomplete)),
        ("different_base", accept_reply(ticket, wrong_base)),
        ("unknown_evidence", accept_reply(ticket, unknown)),
        ("executable_field", accept_reply(ticket, executable)),
    ]
    return {"scope": "Invented labels and authored data; deterministic handoff only.",
            "external_calls": 0, "commands_executed": 0,
            "cases": [{"case": name, **outcome} for name, outcome in cases]}


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))
