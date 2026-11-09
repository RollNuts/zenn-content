"""Non-model checks for the opt-in agent comparison and local data boundaries."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import compare_agents as C


class AgentComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def arguments(self, private=None):
        return ['--codex', str(self.root / 'codex'), '--tauri', str(self.root / 'tauri'),
                '--snapshot', str(self.root / 'snapshot.json'), '--git', str(self.root / 'git'),
                '--private-dir', str(private or self.root / 'private')]

    def test_default_preflight_cannot_reach_archive_or_model_trial(self):
        output = io.StringIO()
        with patch.object(C, 'preflight', return_value={'checked': True}), \
                patch.object(C, 'archive_api') as archive, \
                patch.object(C, 'run_trial') as model, redirect_stdout(output):
            self.assertEqual(C.main(self.arguments()), 0)
        self.assertEqual(json.loads(output.getvalue())['model_calls_started'], 0)
        archive.assert_not_called()
        model.assert_not_called()
        self.assertFalse((self.root / 'private').exists())

    def test_same_prompt_and_schema_never_include_the_scoring_checklist(self):
        args = SimpleNamespace(codex=self.root / 'codex', sdk_python=self.root / 'sdk',
                               server=self.root / 'server.py', snapshot=self.root / 'snapshot')
        b = C.command(args, 'B', self.root / 'B', self.root / 'schema', self.root / 'Banswer')
        c = C.command(args, 'C', self.root / 'C', self.root / 'schema', self.root / 'Canswer')
        self.assertEqual(b[-1], c[-1])
        for path in C.CHECKLIST:
            self.assertNotIn(path, C.PROMPT)
            self.assertNotIn(path, json.dumps(C.SCHEMA))
        self.assertFalse(any('mcp_servers.' in argument for argument in b))
        self.assertTrue(any('mcp_servers.core_contracts' in argument for argument in c))
        for arguments in (b, c):
            self.assertGreater(arguments.index('--ignore-user-config'), arguments.index('exec'))
            self.assertNotIn('--model', arguments)
            self.assertNotIn('-m', arguments)
            self.assertEqual(arguments[arguments.index('--sandbox') + 1], 'read-only')

    def test_sdk_interpreter_symlink_is_not_resolved(self):
        interpreter = self.root / 'sdk-python'
        interpreter.symlink_to(self.root / 'different-python')
        observed = []
        def preflight(args, env):
            observed.append(args.sdk_python)
            return {}
        with patch.object(C, 'preflight', side_effect=preflight), redirect_stdout(io.StringIO()):
            self.assertEqual(C.main(self.arguments() + ['--sdk-python', str(interpreter)]), 0)
        self.assertEqual(observed, [interpreter.absolute()])

    def test_input_failure_is_bounded_and_does_not_start_model_trial(self):
        errors = io.StringIO()
        with patch.object(C, 'preflight', side_effect=OSError('/private/input/secret')), \
                patch.object(C, 'run_trial') as model, redirect_stderr(errors):
            self.assertEqual(C.main(self.arguments() + ['--run']), 1)
        model.assert_not_called()
        self.assertNotIn('/private/input', errors.getvalue())
        self.assertNotIn('Traceback', errors.getvalue())

    def test_private_output_inside_a_git_worktree_fails_before_archive_or_model(self):
        repository = self.root / 'repository'
        repository.mkdir()
        (repository / '.git').write_text('gitdir: elsewhere\n')
        with patch.object(C, 'preflight', return_value={}), \
                patch.object(C, 'archive_api') as archive, \
                patch.object(C, 'run_trial') as model, redirect_stderr(io.StringIO()):
            self.assertEqual(C.main(self.arguments(repository / 'private') + ['--run']), 1)
        archive.assert_not_called()
        model.assert_not_called()
        file = self.root / 'raw.jsonl'
        C.private_write(file, 'dummy local log')
        self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)
        with self.assertRaises(FileExistsError):
            C.private_write(file, 'overwrite')

    def test_archive_rejects_traversal_links_and_duplicates_before_extracting(self):
        for names in [('../outside',), ('/outside',), ('duplicate', 'duplicate'), ('link',)]:
            data = io.BytesIO()
            with tarfile.open(fileobj=data, mode='w') as archive:
                for name in names:
                    member = tarfile.TarInfo(name)
                    if name == 'link':
                        member.type, member.linkname = tarfile.SYMTYPE, '../outside'
                    archive.addfile(member)
            with self.subTest(names=names), self.assertRaises(C.HarnessError):
                C.extract_api(data.getvalue(), self.root / 'out')
        self.assertFalse((self.root / 'out').exists())

    def test_per_run_environment_removes_api_keys_and_scrubs_git_redirects(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'dummy', 'CODEX_API_KEY': 'dummy',
                                    'OTHER_API_KEY': 'dummy', 'OPENAI_BASE_URL': 'dummy',
                                    'GIT_DIR': '/redirect', 'GIT_REPLACE_REF_BASE': 'refs/replace'}):
            environment = C.child_environment()
        self.assertFalse(any('API_KEY' in key.upper() for key in environment))
        self.assertFalse(any(key.startswith('GIT_') for key in environment))
        self.assertNotIn('OPENAI_BASE_URL', environment)
        self.assertEqual(environment.get('CODEX_HOME'), os.environ.get('CODEX_HOME'))
        args = SimpleNamespace(git=Path('git'), tauri=self.root)
        fake = subprocess.CompletedProcess([], 0, b'archive bytes', b'')
        with patch.object(C, 'local_command', return_value=C.TAURI_PIN), \
                patch.object(C.subprocess, 'run', return_value=fake) as run:
            C.archive_api(args, environment)
        self.assertEqual(run.call_args.kwargs['env']['GIT_NO_REPLACE_OBJECTS'], '1')
        self.assertEqual(run.call_args.kwargs['env']['GIT_CONFIG_GLOBAL'], os.devnull)

    def test_receipt_rejects_private_text_and_does_not_infer_a_default_model(self):
        answer = {'peers': [{'path': 'src/peer.rs', 'reason': '/tmp/private/path'}],
                  'uncertainty_notes': ['bounded'], 'claims_complete': False,
                  'merge_safety_proven': False}
        with self.assertRaises(C.HarnessError):
            C.public_answer(answer)
        for path in ('../outside', '/absolute/path', C.SEED):
            answer['peers'][0] = {'path': path, 'reason': 'A public source-based reason.'}
            with self.subTest(path=path), self.assertRaises(C.HarnessError):
                C.public_answer(answer)
        receipt = C.tool_receipt([{'type': 'thread.started', 'model': 'default'}])
        self.assertFalse(receipt['resolved_model_observed'])
        self.assertIsNone(receipt['resolved_model'])
        receipt = C.tool_receipt([{'type': 'thread.started'}])
        self.assertFalse(receipt['resolved_model_observed'])


if __name__ == '__main__':
    unittest.main()
