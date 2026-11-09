"""Boundary checks for the public, allowlisted comparison (no Core install)."""
import json
from pathlib import Path
import tempfile
import unittest

from compare_indexes import CASE_FILE, ComparisonError, INDEX_FILES, NESTED_SCOPE_REASON, compare


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.case = json.loads(CASE_FILE.read_text())
        self.before, self.after = self.root / "before", self.root / "after"
        for role, path in (("before", self.before), ("after", self.after)):
            path.mkdir()
            manifest = {
                "target_commit_sha": self.case[role], "veripsa_commit_sha": self.case["core"],
                "target_dirty_state": False, "veripsa_dirty_state": False,
                "python_version": "3.12.13",
                "relevant_package_versions": self.case["required_package_versions"],
                "target_absolute_path": "/PRIVATE_SENTINEL/source",
                "exact_command": ["/PRIVATE_SENTINEL/python"],
            }
            for key in ("include_patterns", "exclude_patterns", "extractor_versions", "graph_schema_contract_version"):
                manifest[key] = self.case[key]
            self.write(path, "run_manifest.json", manifest)
            self.write(path, "nodes.json", [
                {"kind": "file", "path": self.case["controller"], "content_hash": self.case["controller_blobs"][role]},
                {"kind": "def", "path": self.case["controller"], "name": self.case["method"],
                 "start_line": 66, "end_line": 72, "body": "PRIVATE_SENTINEL"},
                {"kind": "file", "path": "/PRIVATE_SENTINEL/unrelated"},
            ])
            self.write(path, "authorization_calls.json", [{
                "source_file": self.case["authorization_source"], "source_line": self.case["authorization_line"],
                "call_name": "authorize", "enclosing_class_or_module": "Api::BaseController",
                "enclosing_method": "check_authorization", "unresolved_reason": "PRIVATE_SENTINEL",
                "raw_arguments": "PRIVATE_SENTINEL", "receiver": "PRIVATE_SENTINEL",
            }])
            self.write(path, "rails_routes.json", [])
            self.write(path, "execution_paths.json", [])
            self.write(path, "sidekiq_jobs.json", {"workers": [], "enqueue_sites": []})
            self.write(path, "warnings.json", [{"file": self.case["route_source"],
                "line": self.case["unsupported_scope_line"], "category": "rails_route_unresolved",
                "reason": NESTED_SCOPE_REASON, "private": "PRIVATE_SENTINEL"}])

    def write(self, directory, name, value):
        (directory / name).write_text(json.dumps(value))

    def mutate(self, directory, name, mutate):
        value = json.loads((directory / name).read_text())
        mutate(value)
        self.write(directory, name, value)

    def test_pinned_pair_and_private_metadata_projection(self):
        result = compare(self.before, self.after, self.case)
        self.assertTrue(all(result["index_bytes_equal"].values()))
        obs = result["before"]["selected_observations"]
        self.assertFalse(obs["automation_route_observed"])
        self.assertTrue(obs["authorization"]["single_call_unresolved"])
        self.assertTrue(obs["unsupported_nested_resource_scope"]["warning_observed"])
        serialized = json.dumps(result)
        for forbidden in ("PRIVATE_SENTINEL", "raw_arguments", "receiver", "unresolved_reason", "exact_command"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(result["before"]["controller"]["definitions"], [{"start_line": 66, "end_line": 72}])

    def test_wrong_core_or_target_sha_and_reversed_pair_refused(self):
        with self.assertRaises(ComparisonError):
            compare(self.after, self.before, self.case)
        for key in ("target_commit_sha", "veripsa_commit_sha"):
            with self.subTest(key=key):
                original = json.loads((self.before / "run_manifest.json").read_text())
                self.mutate(self.before, "run_manifest.json", lambda m: m.update({key: "0" * 40}))
                with self.assertRaises(ComparisonError):
                    compare(self.before, self.after, self.case)
                self.write(self.before, "run_manifest.json", original)

    def test_dirty_scope_and_parser_mismatch_refused(self):
        changes = {"target_dirty_state": True, "veripsa_dirty_state": True,
                   "include_patterns": [], "exclude_patterns": ["private/*"],
                   "extractor_versions": {}, "graph_schema_contract_version": 999,
                   "relevant_package_versions": {"tree-sitter-ruby": "wrong"},
                   "python_version": "different"}
        for key, value in changes.items():
            with self.subTest(key=key):
                original = json.loads((self.before / "run_manifest.json").read_text())
                self.mutate(self.before, "run_manifest.json", lambda m: m.update({key: value}))
                with self.assertRaises(ComparisonError):
                    compare(self.before, self.after, self.case)
                self.write(self.before, "run_manifest.json", original)

    def test_controller_blob_and_missing_method_refused(self):
        original = json.loads((self.before / "nodes.json").read_text())
        self.mutate(self.before, "nodes.json", lambda ns: ns[0].update(content_hash="0" * 40))
        with self.assertRaises(ComparisonError):
            compare(self.before, self.after, self.case)
        self.write(self.before, "nodes.json", original[:1])
        with self.assertRaises(ComparisonError):
            compare(self.before, self.after, self.case)

    def test_differences_are_preserved_without_security_classification(self):
        self.write(self.after, "rails_routes.json", [{"controller_file": self.case["controller"],
                                                     "raw_arguments": "PRIVATE_SENTINEL"}])
        result = compare(self.before, self.after, self.case)
        self.assertFalse(result["index_bytes_equal"]["rails_routes.json"])
        self.assertTrue(result["after"]["selected_observations"]["automation_route_observed"])
        self.assertFalse(result["before"]["selected_observations"]["automation_route_observed"])
        self.assertNotIn("vulnerable", json.dumps(result))
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(result))

    def test_byte_difference_is_not_normalized_away(self):
        (self.after / INDEX_FILES[0]).write_bytes((self.after / INDEX_FILES[0]).read_bytes() + b"\n")
        result = compare(self.before, self.after, self.case)
        self.assertFalse(result["index_bytes_equal"][INDEX_FILES[0]])


if __name__ == "__main__":
    unittest.main()
