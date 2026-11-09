"""Boundary checks for the fixed comparison; no model or MCP subprocess is run."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import compare_search as C
from query_service import SnapshotQueries


class ComparisonTests(unittest.TestCase):
    def test_literal_projection_keeps_line_evidence_and_excludes_definition(self):
        data = C.parse_search('./src-tauri/src/cmd.rs:44:private body\n'
                              './src/views/Communication.svelte:28:source body\n')
        self.assertEqual(data['candidates'], ['src/views/Communication.svelte'])
        self.assertEqual(data['excluded_seed_lines'], [44])
        self.assertEqual(data['hits'][0]['line'], 28)
        self.assertNotIn('source body', json.dumps(data))
        self.assertNotIn('private body', json.dumps(data))
        for output in ('/private/file:1:body', '../private:1:body', 'file:bad:body'):
            with self.subTest(output=output), self.assertRaises(C.ComparisonError):
                C.parse_search(output)

    def test_followup_uses_discovered_allow_mapping_and_requires_literal_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / C.PERMISSION_FILE
            file.parent.mkdir(parents=True)
            file.write_text('[[permission]]\nidentifier = "allow-perform-request"\n'
                            'commands.allow = ["perform_request"]\n')
            self.assertIsNone(C.follow_allow_identifier(root, []))
            found = C.follow_allow_identifier(root, [C.PERMISSION_FILE])
            self.assertEqual(found['identifier'], 'allow-perform-request')
            self.assertEqual(found['identifier_line'], 2)

    def test_checklist_miss_is_retained_and_extra_candidates_are_unassessed(self):
        result = C.assess(['src/a.rs', 'src/extra.rs'], [{'path': 'src/a.rs'}, {'path': 'src/b.rs'}])
        self.assertEqual(result['included_checklist_paths'], ['src/a.rs'])
        self.assertEqual(result['not_included_checklist_paths'], ['src/b.rs'])
        self.assertEqual(result['outside_known_checklist_paths'], ['src/extra.rs'])

    def test_mcp_projection_preserves_uncertainty_and_rejects_wrong_wire_results(self):
        with tempfile.TemporaryDirectory() as directory:
            data = json.loads((C.HERE / 'demo/official-literal.json').read_text())
            data['core_commit'] = C.CORE_PIN
            data['graph']['nodes'] = [
                {'kind': 'file', 'path': C.SEED, 'analysis_status': None},
                {'kind': 'file', 'path': 'src/client.ts', 'analysis_status': 'incomplete'},
                {'kind': 'app_command', 'id': C.RESOURCE, 'provenance': {'ambiguous': False}},
            ]
            data['graph']['edges'] = [
                {'src': C.SEED, 'dst': C.RESOURCE, 'kind': 'alters', 'reference_status': None},
                {'src': 'src/client.ts', 'dst': C.RESOURCE, 'kind': 'queries', 'reference_status': None},
            ]
            file = Path(directory) / 'snapshot.json'
            file.write_text(json.dumps(data))
            queries = SnapshotQueries(file)
            result = {'tools': ['graph_summary', 'tauri_related_files'],
                      'protocol_version': '2026-07-28',
                      'summary': queries.summary(), 'related': queries.related_files(C.SEED)}
            projected = C.project_mcp(result, queries)
            self.assertEqual(projected['query_status'], 'uncertain')
            self.assertEqual(projected['matched_command_rows'][0]['evidence_status'], 'uncertain')
            self.assertFalse(projected['current_state_or_merge_safety_proven'])
            forged = copy.deepcopy(result)
            forged['related']['status'] = 'observed'
            with self.assertRaises(C.ComparisonError):
                C.project_mcp(forged, queries)


class SourceCheckoutChecks:
    """The same behavioral boundaries run on invented and optional fixed source."""

    def prepare(self, fixed_source=None):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.temporary_root = Path(self.temporary.name)
        self.root = self.temporary_root / 'source'
        self.root.mkdir()
        self.git_binary = os.environ.get('VERIPSA_COMPARISON_GIT') or shutil.which('git') or 'git'
        self.environment = C.source_git_environment()
        self.git('init', '--quiet')
        if fixed_source:
            common = subprocess.check_output(C.source_git_prefix(fixed_source, self.git_binary)
                                             + ['rev-parse', '--git-common-dir'],
                                             env=self.environment, text=True).strip()
            objects = ((fixed_source / common) if not Path(common).is_absolute()
                       else Path(common)) / 'objects'
            (self.root / '.git/objects/info/alternates').write_text(str(objects.resolve()) + '\n')
            self.git('update-ref', 'refs/heads/main', C.TAURI_PIN)
            self.git('symbolic-ref', 'HEAD', 'refs/heads/main')
            self.git('read-tree', 'HEAD')
            self.git('checkout', 'HEAD', '--', 'examples/api')
            self.path = 'examples/api/src/views/Communication.svelte'
        else:
            self.path = 'examples/api/src/client.txt'
            path = self.root / self.path
            path.parent.mkdir(parents=True)
            path.write_text('value = 1\n')
            self.git('add', '--all')
            self.git('-c', 'user.name=Source Fixture', '-c', 'user.email=fixture@example.invalid',
                     '-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'Synthetic source')
            self.pin_patch = patch.object(C, 'TAURI_PIN', self.git('rev-parse', 'HEAD'))
            self.pin_patch.start()
            self.addCleanup(self.pin_patch.stop)
        self.target = self.root / self.path

    def git(self, *arguments):
        completed = subprocess.run(C.source_git_prefix(self.root, self.git_binary) + list(arguments),
                                   capture_output=True, text=True, env=self.environment, check=True)
        return completed.stdout.strip()

    def helper(self, name):
        marker = self.temporary_root / (name + '-ran')
        path = self.temporary_root / name
        path.write_text('#!/bin/sh\ntouch ' + shlex.quote(str(marker)) + '\n'
                        'printf "fixture-token\\0"\n')
        path.chmod(0o700)
        return path, marker

    def test_clean_full_subtree_matches_the_fixed_blob_bytes(self):
        source = C.validate_source(self.root, self.git_binary)
        self.assertEqual(source['commit'], C.TAURI_PIN)
        self.assertEqual(source['api_tree'], self.git('rev-parse', 'HEAD:examples/api'))

    def test_repo_local_fsmonitor_cannot_execute(self):
        helper, marker = self.helper('fsmonitor')
        self.git('config', 'core.fsmonitor', str(helper))
        self.assertEqual(C.validate_source(self.root, self.git_binary)['commit'], C.TAURI_PIN)
        self.assertFalse(marker.exists())

    def test_source_check_does_not_invoke_clean_filters(self):
        helper, marker = self.helper('clean-filter')
        (self.root / '.git/info/attributes').write_text('* filter=review-fixture\n')
        self.git('config', 'filter.review-fixture.clean', str(helper))
        os.utime(self.target, None)
        C.validate_source(self.root, self.git_binary)
        self.assertFalse(marker.exists())

    def test_hidden_index_flags_reject_changed_input(self):
        original = self.target.read_bytes()
        for flag, undo in [('--assume-unchanged', '--no-assume-unchanged'),
                           ('--skip-worktree', '--no-skip-worktree')]:
            with self.subTest(flag=flag):
                self.git('update-index', flag, self.path)
                self.target.write_bytes(original + b'\nfixture change\n')
                with self.assertRaises(C.ComparisonError):
                    C.validate_source(self.root, self.git_binary)
                self.target.write_bytes(original)
                self.git('update-index', undo, self.path)

    def test_raw_byte_comparison_rejects_a_same_size_edit(self):
        body = self.target.read_bytes()
        self.target.write_bytes(bytes([body[0] ^ 1]) + body[1:])
        with self.assertRaises(C.ComparisonError):
            C.validate_source(self.root, self.git_binary)

    def test_missing_sparse_input_is_rejected_but_scope_outside_api_is_not_required(self):
        self.git('config', 'core.sparseCheckout', 'true')
        C.validate_source(self.root, self.git_binary)
        self.git('update-index', '--skip-worktree', self.path)
        self.target.unlink()
        with self.assertRaises(C.ComparisonError):
            C.validate_source(self.root, self.git_binary)

    def test_ignored_extra_file_and_symlink_input_are_rejected(self):
        extra = self.root / 'examples/api/ignored-fixture.txt'
        (self.root / '.git/info/exclude').write_text('examples/api/ignored-fixture.txt\n')
        extra.write_text('synthetic extra input\n')
        with self.assertRaises(C.ComparisonError):
            C.validate_source(self.root, self.git_binary)
        extra.unlink()
        original = self.target.read_bytes()
        outside = self.temporary_root / 'outside.txt'
        outside.write_bytes(original)
        self.target.unlink()
        self.target.symlink_to(outside)
        with self.assertRaises(C.ComparisonError):
            C.validate_source(self.root, self.git_binary)

    def test_agent_archive_uses_same_guard_and_rejects_local_export_attributes(self):
        import compare_agents as A
        original = self.target.read_bytes()
        args = SimpleNamespace(git=Path(self.git_binary), tauri=self.root)
        with patch.object(A, 'TAURI_PIN', C.TAURI_PIN):
            self.assertTrue(A.archive_api(args, self.environment))
            self.git('update-index', '--assume-unchanged', self.path)
            self.target.write_bytes(self.target.read_bytes() + b'\nfixture change\n')
            with self.assertRaises(C.ComparisonError):
                A.archive_api(args, self.environment)
        # Archive-local attributes can change files independently of Git blobs.
        self.target.write_bytes(original)
        self.git('update-index', '--no-assume-unchanged', self.path)
        (self.root / '.git/info/attributes').write_text('* export-ignore\n')
        with patch.object(A, 'TAURI_PIN', C.TAURI_PIN), self.assertRaises(A.HarnessError):
            A.archive_api(args, self.environment)


@unittest.skipUnless(os.name == 'posix', 'Source-checkout fixtures require POSIX Git.')
class SyntheticSourceValidationTests(SourceCheckoutChecks, unittest.TestCase):
    def setUp(self):
        self.prepare()


@unittest.skipUnless(os.name == 'posix', 'Source-checkout fixtures require POSIX Git.')
class FixedTauriSourceValidationTests(SourceCheckoutChecks, unittest.TestCase):
    def setUp(self):
        source = Path(os.environ.get('VERIPSA_COMPARISON_TAURI', str(C.HERE / 'tauri-source'))).absolute()
        if not source.is_dir():
            self.skipTest('Set VERIPSA_COMPARISON_TAURI to the local pinned public Tauri checkout.')
        self.prepare(source)


if __name__ == '__main__':
    unittest.main()
