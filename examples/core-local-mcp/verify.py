"""Behavioral and real-stdio checks for the local MCP feasibility example."""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from client_demo import tool_data
from query_service import MAX_RESPONSE_BYTES, SnapshotQueries

HERE = Path(__file__).resolve().parent
MARKER = 'FIXTURE_BODY_TEXT_SHOULD_STAY_OUT_OF_GRAPH'
CASES = {'official-literal': (1, 'observed'), 'local-invoke': (0, 'not_observed'),
         'dynamic-name': (0, 'not_observed'), 'duplicate-command': (2, 'uncertain')}


def many_utf8_paths_snapshot(original: dict) -> dict:
    many = copy.deepcopy(original)
    for index in range(60):
        path = 'src/' + ('長' * 900) + str(index) + '.ts'
        many['graph']['nodes'].append({'kind': 'file', 'path': path, 'analysis_status': None})
        many['graph']['edges'].append({'src': path, 'dst': 'tauri_command::receipt_label',
                                       'kind': 'queries', 'reference_status': None})
    return many


def local_checks() -> list[str]:
    original = json.loads((HERE / 'demo/official-literal.json').read_text())
    checks = []
    with tempfile.TemporaryDirectory() as directory:
        filename = Path(directory) / 'snapshot.json'
        for label, change in (
            ('non_sha_metadata_rejected', lambda d: d.update(core_commit='arbitrary text')),
            ('oversized_timestamp_rejected', lambda d: d.update(created_at='x' * 100)),
            ('unknown_analysis_status_rejected', lambda d: d['graph']['nodes'][0].update(analysis_status='not-a-status')),
            ('non_numeric_counter_rejected', lambda d: d['graph'].update(files_parsed={'arbitrary': 'body'})),
            ('duplicate_document_rejected', lambda d: d['graph']['nodes'].append(copy.deepcopy(d['graph']['nodes'][0]))),
            ('duplicate_command_rejected', lambda d: d['graph']['nodes'].append(copy.deepcopy(next(n for n in d['graph']['nodes'] if n['kind'] == 'app_command')))),
            ('dangling_edge_rejected', lambda d: d['graph']['edges'][0].update(src='not-in-the-snapshot.ts')),
        ):
            envelope = copy.deepcopy(original)
            change(envelope)
            filename.write_text(json.dumps(envelope))
            try:
                SnapshotQueries(filename)
            except ValueError:
                checks.append(label)
            else:
                raise AssertionError(label)
        incomplete = copy.deepcopy(original)
        for node in incomplete['graph']['nodes']:
            if node.get('kind') == 'file' and node['path'] == 'src/client.ts':
                node['analysis_status'] = 'incomplete'
        filename.write_text(json.dumps(incomplete))
        observed = SnapshotQueries(filename).related_files('src-tauri/commands.rs')
        assert observed['relations'][0]['evidence_status'] == 'uncertain'
        checks.append('incomplete_peer_retained_as_uncertain')
        many = many_utf8_paths_snapshot(original)
        filename.write_text(json.dumps(many, ensure_ascii=False))
        bounded = SnapshotQueries(filename).related_files('src-tauri/commands.rs')
        assert bounded['truncated'] and len(json.dumps(bounded, ensure_ascii=False, indent=2).encode()) <= MAX_RESPONSE_BYTES
        checks.append('utf8_response_byte_cap_and_truncation')
    queries = SnapshotQueries(HERE / 'demo/official-literal.json')
    size = len(queries.by_source)
    for index in range(100):
        assert queries.related_files('missing/' + str(index) + '.ts')['status'] == 'not_observed'
    assert len(queries.by_source) == size
    checks.append('unknown_path_queries_do_not_expand_snapshot_index')
    return checks


async def wire_checks() -> list[dict]:
    results = []
    for name, (expected_rows, expected_status) in CASES.items():
        snapshot = HERE / 'demo' / (name + '.json')
        params = StdioServerParameters(
            command=sys.executable, args=[str(HERE / 'server.py'), '--snapshot', str(snapshot)],
            env={'PYTHONDONTWRITEBYTECODE': '1'},
        )
        async with Client(params, read_timeout_seconds=10) as client:
            tools = await client.list_tools()
            assert sorted(tool.name for tool in tools.tools) == ['graph_summary', 'tauri_related_files']
            assert all(tool.annotations.read_only_hint for tool in tools.tools)
            summary = await client.call_tool('graph_summary', {})
            related = await client.call_tool('tauri_related_files', {'path': 'src/client.ts'})
            assert not summary.is_error and not related.is_error
            data = tool_data(related)
            queries = SnapshotQueries(snapshot)
            assert data == queries.related_files('src/client.ts')
            assert tool_data(summary) == queries.summary()
            assert data['status'] == expected_status and len(data['relations']) == expected_rows
            assert data['snapshot']['current_worktree_verified'] is False
            assert data['current_state_or_merge_safety_proven'] is False
            assert all(row['evidence_status'] == ('uncertain' if name == 'duplicate-command' else 'observed')
                       for row in data['relations'])
            for bad in ('../outside', '/outside', 'a\\outside'):
                denied = await client.call_tool('tauri_related_files', {'path': bad})
                assert denied.is_error
            invalid_limit = await client.call_tool('tauri_related_files', {'path': 'src/client.ts', 'limit': 21})
            assert invalid_limit.is_error
            payload = json.dumps([summary.model_dump(mode='json'), related.model_dump(mode='json')])
            assert MARKER not in payload and str(HERE) not in payload and str(Path.home()) not in payload
            results.append({'case': name, 'protocol_version': client.protocol_version,
                            'status': data['status'], 'relation_rows': len(data['relations']),
                            'snapshot_sha256': hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                            'path_rejections': 3, 'limit_rejected': True, 'passed': True})
    return results


async def wire_boundary_checks() -> list[dict]:
    original = json.loads((HERE / 'demo/official-literal.json').read_text())
    with tempfile.TemporaryDirectory(prefix='.wire-boundary-', dir=HERE) as directory:
        snapshot = Path(directory) / 'large-utf8-snapshot.json'
        snapshot.write_text(json.dumps(many_utf8_paths_snapshot(original), ensure_ascii=False),
                            encoding='utf-8')
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(HERE / 'server.py'), '--snapshot', str(snapshot)],
            env={'PYTHONDONTWRITEBYTECODE': '1'},
        )
        async with Client(params, read_timeout_seconds=10) as client:
            result = await client.call_tool('tauri_related_files',
                                            {'path': 'src-tauri/commands.rs', 'limit': 20})
            assert not result.is_error
            text_blocks = [block.text for block in result.content if block.type == 'text']
            assert len(text_blocks) == 1
            text_payload_bytes = len(text_blocks[0].encode('utf-8'))
            assert text_payload_bytes <= MAX_RESPONSE_BYTES
            data = tool_data(result)
            assert json.loads(text_blocks[0]) == data
            assert data['truncated'] is True
            assert data['total_relation_rows'] == 61  # Original client plus 60 added peers.
            assert 0 < len(data['relations']) < 20  # The byte cap, not only the row limit, applied.
            return [{
                'check': 'large_utf8_paths_respect_stdio_text_payload_cap',
                'protocol_version': client.protocol_version,
                'text_payload_utf8_bytes': text_payload_bytes,
                'text_payload_byte_limit': MAX_RESPONSE_BYTES,
                'total_relation_rows': data['total_relation_rows'],
                'returned_relation_rows': len(data['relations']),
                'truncated': data['truncated'], 'passed': True,
            }]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'local_checks': local_checks(), 'stdio_cases': asyncio.run(wire_checks()),
              'wire_boundary_checks': asyncio.run(wire_boundary_checks()),
              'scope': 'Synthetic fixed snapshots, official Python SDK client/server; no IDE-host installation or live repository freshness verification.'}
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
