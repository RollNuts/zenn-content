"""Compare local previews and run two caller checks. Python 3.12, standard library."""

import json

from contracts import argument_required, before, result_is_text


# Local lookup for this example. The two cases are alternatives for the same edit.
FILES = {"F01": "contracts.py", "F02": "compare.py"}
CALL = {"caller": "F02", "definition": "F01"}
# The change labels are supplied by the author. No program infers them from code.
CASES = {
    "A": (argument_required, "optional_argument_becomes_required"),
    "B": (result_is_text, "number_result_becomes_text"),
}


def omit_argument(definition):
    return definition()


def add_one_to_result(definition):
    return definition(2) + 1


def local_checks(definition):
    results = []
    for caller in (omit_argument, add_one_to_result):
        try:
            caller(definition)
        except TypeError:
            outcome = "TypeError"
        else:
            outcome = "ok"
        results.append(f"{caller.__name__}={outcome}")
    return ", ".join(results)


def preview(level, change):
    if level == "count":
        return {"relations": 1}
    if level == "relation":
        return CALL
    if level == "contract":
        return {**CALL, "change": change}
    return None


def main():
    print("Local lookup:", json.dumps(FILES, sort_keys=True))
    print("Local checks before:", local_checks(before))
    for case, (definition, _) in CASES.items():
        print(f"Local checks {case}:", local_checks(definition))

    for level in ("withheld", "count", "relation", "contract"):
        previews = [preview(level, change) for _, change in CASES.values()]
        print(f"\n{level} | A == B: {previews[0] == previews[1]}")
        for case, payload in zip(CASES, previews, strict=True):
            print(f"  {case}:", json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
