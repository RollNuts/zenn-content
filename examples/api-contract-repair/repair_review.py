"""Compare two synthetic repairs against explicitly stated API requirements.

No third-party packages, files, network requests, or target repositories are used.
The rollback variant deliberately fails two contract checks in the full suite.
"""

import argparse
import inspect
import unittest


def total_rollback(amount, fee=5):
    return amount + fee


def total_keyword(amount, *, fee=5):
    return amount + fee


def checkout_rollback():
    return total_rollback(100, 5)


def checkout_keyword():
    return total_keyword(100, fee=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair", choices=("rollback", "keyword"), required=True)
    parser.add_argument(
        "--value-only", action="store_true", help="Check only checkout() == 105."
    )
    args = parser.parse_args()
    total, checkout = {
        "rollback": (total_rollback, checkout_rollback),
        "keyword": (total_keyword, checkout_keyword),
    }[args.repair]

    class RepairReview(unittest.TestCase):
        def test_checkout_value(self):
            self.assertEqual(checkout(), 105)

        def test_keyword_call(self):
            self.assertEqual(total(100, fee=5), 105)

        def test_fee_is_keyword_only(self):
            parameter = inspect.signature(total).parameters["fee"]
            self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)

        def test_positional_fee_is_rejected(self):
            with self.assertRaises(TypeError):
                total(100, 5)

    if args.value_only:
        suite = unittest.TestSuite([RepairReview("test_checkout_value")])
    else:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(RepairReview)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
