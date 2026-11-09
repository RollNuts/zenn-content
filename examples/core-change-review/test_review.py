"""Local boundary checks; the full fixed-corpus audit is a separate command."""
from __future__ import annotations

import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import review


class ReviewBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def manifest(self):
        return {'cases': [
            {'id': f'case-{i}', 'target': str(i) * 40, 'base': 'a' * 40,
             'seed': 'src/flask/app.py', 'review_targets': [
                 {'path': 'tests/test_basic.py', 'symbol': 'test_example',
                  'reason': 'A selected public review target.',
                  'evidence_url': 'https://github.com/pallets/flask/commit/' + str(i) * 40} ]}
            for i in range(1, 4)]}

    def test_manifest_requires_fixed_hashes_public_paths_and_unique_cases(self):
        file = self.root / 'cases.json'
        value = self.manifest()
        file.write_text(json.dumps(value))
        self.assertEqual(len(review.load_cases(file)), 3)
        for field, replacement in [('seed', '../private.py'), ('target', 'HEAD'),
                                   ('id', '../case')]:
            altered = copy.deepcopy(value)
            altered['cases'][0][field] = replacement
            file.write_text(json.dumps(altered))
            with self.subTest(field=field), self.assertRaises(review.ReviewError):
                review.load_cases(file)
        altered = copy.deepcopy(value)
        altered['cases'][1]['id'] = altered['cases'][0]['id']
        file.write_text(json.dumps(altered))
        with self.assertRaises(review.ReviewError):
            review.load_cases(file)

    def test_projection_keeps_all_candidates_and_excludes_seed_or_outside_universe(self):
        seed, a, b, outside = 'src/flask/app.py', 'tests/test_a.py', 'tests/test_b.py', 'docs/a.py'
        pairs = {frozenset((seed, a)): {'call', 'import'},
                 frozenset((seed, outside)): {'config'}}
        history = [{'a': seed, 'b': a}, {'a': b, 'b': seed},
                   {'a': seed, 'b': outside}, {'a': seed, 'b': seed}]
        result = review.project_candidates(seed, {seed, a, b}, pairs, history)
        self.assertEqual(result['candidates'], {'graph': [a], 'history': [a, b],
                                               'union': [a, b], 'intersection': [a]})
        self.assertEqual(result['graph_evidence'], [{'path': a, 'kinds': ['call', 'import']}])

    def test_review_target_inclusion_is_file_level_and_missing_targets_are_explicit(self):
        case = self.manifest()['cases'][0]
        path = case['review_targets'][0]['path']
        data = {'candidate_universe': [path],
                'candidates': {'graph': [path], 'history': [], 'union': [path], 'intersection': []},
                'graph_evidence': [{'path': path, 'kinds': ['call']}]}
        row = review._review_targets(case, data)[0]
        self.assertTrue(row['in_candidate_universe'])
        self.assertEqual(row['contained_by'], {'graph': True, 'history': False,
                                              'union': True, 'intersection': False})
        self.assertEqual(row['graph_evidence_kinds'], ['call'])
        data['candidate_universe'] = []
        self.assertFalse(review._review_targets(case, data)[0]['in_candidate_universe'])

    def test_archive_rejects_traversal_links_and_duplicate_paths(self):
        for names in [('../outside',), ('/outside',), ('same', 'same'), ('link',)]:
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode='w') as archive:
                for name in names:
                    item = tarfile.TarInfo(name)
                    if name == 'link':
                        item.type, item.linkname = tarfile.SYMTYPE, '../outside'
                    archive.addfile(item)
            with self.subTest(names=names), self.assertRaises(review.ReviewError):
                review.extract_archive(buffer.getvalue(), self.root / 'out')
        self.assertFalse((self.root / 'out').exists())

    def test_history_preflight_uses_producer_log_flags_and_rejects_future_input(self):
        class FakeGit:
            def call(self, root, *args, **kwargs):
                self.arguments = args
                return '\x01' + 'a' * 40 + '\nM\tsrc/flask/app.py\n'
        git = FakeGit()
        self.assertEqual(review.history_preflight(git, self.root, 800, 'b' * 40, 60), ['a' * 40])
        self.assertEqual(git.arguments, ('log', '--no-merges', '--name-status', '-M',
                                         '--pretty=format:\x01%H', '-n', '800'))
        with self.assertRaises(review.ReviewError):
            review.history_preflight(git, self.root, 800, 'a' * 40, 60)

    def test_invalid_git_and_cli_failure_do_not_expose_paths_or_success(self):
        with self.assertRaises(review.ReviewError):
            review.LocalGit('/missing/private/binary', self.root / 'hooks')
        result = subprocess.run([sys.executable, '-B', str(Path(review.__file__)),
                                 '--core', '/missing/private/core', '--flask', '/missing/private/flask',
                                 '--git', '/missing/private/git'], capture_output=True, text=True,
                                stdin=subprocess.DEVNULL, timeout=10, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertNotIn('/missing/private', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertIn('No successful result is claimed', result.stderr)

    def test_producer_git_failure_or_timeout_cannot_become_an_empty_success(self):
        class FakeProcess:
            SubprocessError = subprocess.SubprocessError

            def run(self, *args, **kwargs):
                return subprocess.CompletedProcess(args, 1, '', 'private failure')

        checked = review.CheckedSubprocess(FakeProcess())
        with self.assertRaises(review.ReviewError):
            checked.run(['git', 'log'])
        with patch.object(checked.module, 'run', side_effect=subprocess.TimeoutExpired('git', 60)):
            with self.assertRaises(review.ReviewError):
                checked.run(['git', 'log'])

    @unittest.skipUnless(os.name == 'posix', 'Local shared clone test uses POSIX.')
    def test_local_replace_refs_cannot_substitute_the_pinned_source(self):
        executable = os.environ.get('VERIPSA_REVIEW_GIT') or shutil.which('git')
        if not executable:
            self.skipTest('Git unavailable')
        git = review.LocalGit(executable, self.root / 'hooks')
        source = self.root / 'source'
        source.mkdir()
        git.call(source, 'init', '--quiet')
        for body in ('original\n', 'replacement\n'):
            (source / 'tracked.txt').write_text(body)
            git.call(source, 'add', '--all')
            git.call(source, '-c', 'user.name=Local Test',
                     '-c', 'user.email=test@example.invalid',
                     '-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'Synthetic local test')
            if body == 'original\n':
                original = git.call(source, 'rev-parse', 'HEAD')
        replacement = git.call(source, 'rev-parse', 'HEAD')
        git.call(source, 'replace', original, replacement)
        ref_before = git.call(source, 'for-each-ref', '--format=%(objectname)', 'refs/replace')
        self.assertEqual(ref_before, replacement)
        self.assertEqual(git.call(source, 'show', original + ':tracked.txt'), 'original')
        archived = self.root / 'archived'
        review.extract_archive(git.call(source, 'archive', '--format=tar', original, binary=True), archived)
        self.assertEqual((archived / 'tracked.txt').read_text(), 'original\n')
        self.assertEqual(git.call(source, 'for-each-ref', '--format=%(objectname)', 'refs/replace'), ref_before)

    @unittest.skipUnless(os.name == 'posix', 'Local shared clone test uses POSIX.')
    def test_shared_checkout_preserves_source_head_config_dirty_files_and_git_environment(self):
        executable = os.environ.get('VERIPSA_REVIEW_GIT') or shutil.which('git')
        if not executable:
            self.skipTest('Git unavailable')
        git = review.LocalGit(executable, self.root / 'hooks')
        source, copy_root = self.root / 'source', self.root / 'copy'
        source.mkdir()
        git.call(source, 'init', '--quiet')
        (source / 'tracked.txt').write_text('original\n')
        git.call(source, 'add', '--all')
        git.call(source, '-c', 'user.name=Local Test', '-c', 'user.email=test@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '--quiet', '-m', 'Synthetic local test')
        base = git.call(source, 'rev-parse', 'HEAD')
        (source / 'tracked.txt').write_text('dirty\n')
        (source / 'untracked.txt').write_text('keep\n')
        before = (git.call(source, 'rev-parse', 'HEAD'),
                  git.call(source, 'status', '--porcelain=v1'),
                  (source / '.git/config').read_bytes())
        with patch.dict(os.environ, {'GIT_DIR': '/wrong/private', 'GIT_WORK_TREE': '/wrong/private'}):
            clean_git = review.LocalGit(executable, self.root / 'hooks')
            review.temporary_clone(clean_git, source, copy_root, base)
        self.assertEqual((copy_root / 'tracked.txt').read_text(), 'original\n')
        self.assertFalse((copy_root / 'untracked.txt').exists())
        after = (git.call(source, 'rev-parse', 'HEAD'),
                 git.call(source, 'status', '--porcelain=v1'),
                 (source / '.git/config').read_bytes())
        self.assertEqual(before, after)
        self.assertEqual((source / 'tracked.txt').read_text(), 'dirty\n')


if __name__ == '__main__':
    unittest.main()
