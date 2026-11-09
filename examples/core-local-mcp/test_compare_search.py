"""Boundary checks for the fixed comparison; no model or MCP subprocess is run."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

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


if __name__ == '__main__':
    unittest.main()
