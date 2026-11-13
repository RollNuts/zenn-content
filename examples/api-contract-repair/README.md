# Two passing values, two different API contracts

This synthetic Python exercise compares two repairs under three stated requirements:
`checkout()` returns105, `fee` is keyword-only, and positional `fee` is rejected.
These are teaching requirements, not a real application's agreed specification.

Use Python3.12 and save or download `repair_review.py` into an empty working directory.
No Git checkout, Core, model, account, network access, or additional package is needed
to run this file.

```sh
python3.12 repair_review.py --repair rollback --value-only
python3.12 repair_review.py --repair keyword --value-only
python3.12 repair_review.py --repair rollback
python3.12 repair_review.py --repair keyword
```

| Selection | Tests run | Failures | Exit code |
| --- | ---: | ---: | ---: |
| rollback, value-only | 1 | 0 | 0 |
| keyword, value-only | 1 | 0 | 0 |
| rollback, full | 4 | 2 | 1 |
| keyword, full | 4 | 0 | 0 |

The full rollback run is expected to fail: it accepts positional `fee`, breaking two
of the stated API requirements. Do not weaken these checks to turn it green. If the
actual requirement were to preserve positional callers, the desired API would differ.

From a repository checkout, run `python3.12 scripts/verify_api_contract_example.py`
to verify all four CLI results automatically. The verifier uses only the standard
library, resolves the example relative to its own file, and gives each run 10 seconds.
It requires the exact test names and statuses, test count, summary, and exit code;
the full rollback must fail only `test_fee_is_keyword_only` and
`test_positional_fee_is_rejected`. A syntax/import error or an unexpectedly passing
rollback fails verification. The read-only GitHub Actions workflow runs this check
for pull requests and pushes to `main` affecting the example, verifier, or workflow
files. Exercise execution needs no packages, network access, or secrets. This checks
the documented exercise behavior; article claims and teaching quality still need
editorial review.

The checks cover these synthetic functions and inputs only. They do not establish
general correctness, merge safety, bug prevention, or any AI model's behavior.
The code and article were prepared with a coding agent.
