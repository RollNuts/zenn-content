"""No model calls: verify the public receipt rejects guesses and extra activity."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from codex_demo import run, verify_events
from query_service import SnapshotQueries


class ReceiptBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.queries = SnapshotQueries(Path(__file__).parent / 'demo/official-literal.json')
        self.answer = {'query_status': 'observed', 'related_files': ['src/client.ts'],
                       'current_state_or_merge_safety_proven': False}
        self.events = []
        for tool, arguments, data in (
            ('graph_summary', {}, self.queries.summary()),
            ('tauri_related_files', {'path': 'src-tauri/commands.rs'},
             self.queries.related_files('src-tauri/commands.rs')),
        ):
            self.events.append({'type': 'item.completed', 'item': {
                'type': 'mcp_tool_call', 'server': 'core_contracts', 'tool': tool,
                'arguments': arguments, 'status': 'completed', 'error': None,
                'result': {'content': [{'text': json.dumps(data)}]},
            }})

    def test_extra_raw_fields_do_not_enter_public_receipt(self):
        marker = 'UNPUBLISHED_EVENT_FIELD'
        self.events[0]['unrelated_metadata'] = marker
        self.events[0]['item']['unrelated_metadata'] = marker
        receipt = verify_events(self.events, self.answer, self.queries)
        self.assertNotIn(marker, json.dumps(receipt))
        self.assertEqual({r['tool'] for r in receipt}, {'graph_summary', 'tauri_related_files'})

    def test_started_other_tool_is_rejected_even_without_completion(self):
        self.events.insert(0, {'type': 'item.started', 'item': {'type': 'command_execution'}})
        with self.assertRaises(ValueError):
            verify_events(self.events, self.answer, self.queries)

    def test_model_answer_without_observed_calls_is_rejected(self):
        with self.assertRaises(ValueError):
            verify_events([], self.answer, self.queries)

    def test_malformed_or_forged_tool_payload_is_rejected(self):
        for result in (None, {'content': []}, {'content': [{'text': '{"status":"guessed"}'}]}):
            events = copy.deepcopy(self.events)
            events[1]['item']['result'] = result
            with self.subTest(result=result), self.assertRaises(ValueError):
                verify_events(events, self.answer, self.queries)


class SelectedSnapshotReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = 'src-tauri/src/cmd.rs'
        self.peer = 'src/views/Communication.svelte'
        data = json.loads((Path(__file__).parent / 'demo/official-literal.json').read_text())
        graph = data['graph']
        graph['nodes'] = [
            {'kind': 'file', 'path': self.path, 'analysis_status': None},
            {'kind': 'file', 'path': self.peer, 'analysis_status': 'incomplete'},
        ]
        graph['edges'] = []
        for name in ('echo', 'log_operation', 'perform_request', 'spam'):
            resource = 'tauri_command::' + name
            graph['nodes'].append({'kind': 'app_command', 'id': resource,
                                   'provenance': {'ambiguous': False}})
            for source, kind in ((self.path, 'alters'), (self.peer, 'queries')):
                graph['edges'].append({'src': source, 'dst': resource, 'kind': kind,
                                       'reference_status': None})
        self.snapshot = Path(self.temporary.name) / 'snapshot.json'
        self.snapshot.write_text(json.dumps(data))
        self.queries = SnapshotQueries(self.snapshot)
        self.related = self.queries.related_files(self.path)
        self.answer = {'query_status': 'uncertain', 'related_files': [self.peer],
                       'current_state_or_merge_safety_proven': False}
        self.events = []
        for tool, arguments, result in (
            ('graph_summary', {}, self.queries.summary()),
            ('tauri_related_files', {'path': self.path}, self.related),
        ):
            self.events.append({'type': 'item.completed', 'item': {
                'type': 'mcp_tool_call', 'server': 'core_contracts', 'tool': tool,
                'arguments': arguments, 'status': 'completed', 'error': None,
                'result': {'structured_content': result},
            }})

    def test_selected_path_preserves_uncertainty_and_deduplicates_peer_paths(self):
        self.assertEqual(self.related['total_relation_rows'], 4)
        receipt = verify_events(self.events, self.answer, self.queries, self.path)
        self.assertEqual(len(receipt), 2)

    def test_forged_status_missing_peer_and_safety_claim_are_rejected(self):
        for replacement in ({'query_status': 'observed'}, {'related_files': []},
                            {'related_files': [self.peer] * 4},
                            {'current_state_or_merge_safety_proven': True}):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                verify_events(self.events, {**self.answer, **replacement}, self.queries, self.path)

    def test_call_for_a_different_path_is_rejected(self):
        events = copy.deepcopy(self.events)
        events[1]['item']['arguments']['path'] = 'src-tauri/commands.rs'
        with self.assertRaises(ValueError):
            verify_events(events, self.answer, self.queries, self.path)

    def test_selected_snapshot_is_passed_to_the_server_and_query_path_to_prompt(self):
        def fake_subprocess(arguments, **kwargs):
            if arguments[1] == '--version':
                return subprocess.CompletedProcess(arguments, 0, 'codex-cli 0.167.0', '')
            server_option = next(a for a in arguments
                                 if a.startswith('mcp_servers.core_contracts.args='))
            server_arguments = json.loads(server_option.split('=', 1)[1])
            self.assertEqual(server_arguments[-2:], ['--snapshot', str(self.snapshot.resolve())])
            self.assertEqual(json.loads(arguments[-1].split('QUERY_PATH_JSON = ', 1)[1]), self.path)
            output = Path(arguments[arguments.index('--output-last-message') + 1])
            output.write_text(json.dumps(self.answer))
            return subprocess.CompletedProcess(arguments, 0,
                                               '\n'.join(json.dumps(e) for e in self.events), '')

        with patch('codex_demo.subprocess.run', side_effect=fake_subprocess):
            report = run('unused-codex', self.snapshot, self.path)
        self.assertTrue(report['passed'])
        self.assertEqual(report['answer'], self.answer)

    def test_invalid_query_path_is_rejected_before_codex_starts(self):
        with patch('codex_demo.subprocess.run') as child:
            with self.assertRaises(ValueError):
                run('unused-codex', self.snapshot, '../outside.rs')
            child.assert_not_called()


if __name__ == '__main__':
    unittest.main()
