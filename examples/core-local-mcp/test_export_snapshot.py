"""Producer/consumer boundary checks for exported metadata snapshots."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from export_snapshot import extract_snapshot, write_snapshot
from query_service import MAX_SNAPSHOT_BYTES, SnapshotQueries

HERE = Path(__file__).resolve().parent
COMMIT = 'd22d44f12112784d34d5ea7ba20755ca995adad2'


class FixtureEngine:
    def __init__(self, graph: dict):
        self.graph = graph

    def build_graph(self, _root: str) -> dict:
        return copy.deepcopy(self.graph)


def fixture_graph(client_path: str = 'src/表示.ts') -> dict:
    return {
        'files_parsed': 2, 'files_failed': 0, 'files_skipped': 0,
        'nodes': [
            {'kind': 'file', 'path': 'src-tauri/commands.rs', 'analysis_status': None},
            {'kind': 'file', 'path': client_path, 'analysis_status': None},
            {'kind': 'app_command', 'id': 'tauri_command::receipt_label',
             'provenance': {'ambiguous': False}},
        ],
        'edges': [
            {'src': 'src-tauri/commands.rs', 'dst': 'tauri_command::receipt_label',
             'kind': 'alters', 'reference_status': None},
            {'src': client_path, 'dst': 'tauri_command::receipt_label',
             'kind': 'queries', 'reference_status': None},
        ],
    }


class ExportSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='.export-test-', dir=HERE)
        self.addCleanup(self.directory.cleanup)
        self.workspace = Path(self.directory.name)
        self.output = self.workspace / 'snapshot.json'

    def envelope(self, graph: dict | None = None) -> dict:
        return extract_snapshot(
            FixtureEngine(graph if graph is not None else fixture_graph()),
            COMMIT, self.workspace,
        )

    def test_valid_export_is_consumable_and_utf8(self):
        write_snapshot(self.envelope(), self.output)
        data = SnapshotQueries(self.output).related_files('src-tauri/commands.rs')
        self.assertEqual(data['status'], 'observed')
        self.assertEqual([row['related_file'] for row in data['relations']], ['src/表示.ts'])
        self.assertIn('表示'.encode('utf-8'), self.output.read_bytes())

    def test_invalid_path_neither_creates_nor_overwrites_output(self):
        envelope = self.envelope(fixture_graph('src/client:reader.ts'))
        previous = b'previous export must survive\n'
        for existing in (False, True):
            with self.subTest(existing_output=existing):
                if existing:
                    self.output.write_bytes(previous)
                with self.assertRaises(ValueError):
                    write_snapshot(envelope, self.output)
                if existing:
                    self.assertEqual(self.output.read_bytes(), previous)
                else:
                    self.assertFalse(self.output.exists())

    def test_oversized_utf8_serialization_preserves_existing_output(self):
        # Legal relative paths and a valid projected shape. Unicode makes the
        # character count smaller than 5MiB while encoded bytes exceed it.
        envelope = self.envelope()
        envelope['graph'] = {
            'files_parsed': 2000, 'files_failed': 0, 'files_skipped': 0,
            'nodes': [
                {'kind': 'file', 'path': 'src/' + '長' * 900 + '/' + str(index) + '.ts',
                 'analysis_status': None}
                for index in range(2000)
            ],
            'edges': [],
        }
        payload = json.dumps(envelope, ensure_ascii=False, indent=2) + '\n'
        self.assertLess(len(payload), MAX_SNAPSHOT_BYTES)
        self.assertGreater(len(payload.encode('utf-8')), MAX_SNAPSHOT_BYTES)
        previous = b'previous export must survive\n'
        self.output.write_bytes(previous)
        with self.assertRaisesRegex(ValueError, 'UTF-8 bytes'):
            write_snapshot(envelope, self.output)
        self.assertEqual(self.output.read_bytes(), previous)

    def test_malformed_projection_is_rejected_before_write(self):
        graph = fixture_graph()
        graph['edges'][1]['src'] = 'src/not-in-the-projection.ts'
        envelope = self.envelope(graph)
        with self.assertRaises(ValueError):
            write_snapshot(envelope, self.output)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()

