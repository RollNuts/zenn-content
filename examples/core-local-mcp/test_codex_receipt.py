"""No model calls: verify the public receipt rejects guesses and extra activity."""
import copy
import json
from pathlib import Path
import unittest

from codex_demo import verify_events
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


if __name__ == '__main__':
    unittest.main()
