"""Bounded metadata queries over one operator-selected, immutable Core snapshot."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path, PurePosixPath

MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024
MAX_RESPONSE_BYTES = 32 * 1024
ANALYSIS_STATUSES = (None, 'failed', 'ambiguous', 'incomplete')
REFERENCE_STATUSES = (None, 'ambiguous', 'unresolved')


def relative_path(value: str) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= 1024 and not (
        value.startswith('/') or '\\' in value or ':' in value
        or any(ord(c) < 32 for c in value)
        or any(p in ('', '.', '..') for p in value.split('/'))
        or PurePosixPath(value).is_absolute()
    )


def validate_snapshot(envelope: dict) -> None:
    def require(condition):
        if not condition:
            raise ValueError('Invalid bounded metadata snapshot')
    require(isinstance(envelope, dict))
    require(envelope.get('format') == 'veripsa-local-mcp-demo-v1')
    require(isinstance(envelope.get('core_commit'), str)
            and re.fullmatch('[0-9a-f]{40}', envelope['core_commit']) is not None)
    created = envelope.get('created_at')
    require(isinstance(created, str) and len(created) <= 40)
    require(datetime.fromisoformat(created).utcoffset() is not None)
    graph = envelope.get('graph')
    require(isinstance(graph, dict))
    for key in ('files_parsed', 'files_failed', 'files_skipped'):
        count = graph.get(key)
        require(count is None or type(count) is int and 0 <= count <= 1000000)
    require(isinstance(graph.get('nodes'), list) and len(graph['nodes']) <= 10000)
    require(isinstance(graph.get('edges'), list) and len(graph['edges']) <= 30000)
    documents, commands = set(), set()
    for node in graph['nodes']:
        require(isinstance(node, dict))
        require(node.get('kind') in ('file', 'config_file', 'app_command'))
        if node['kind'] == 'app_command':
            require(isinstance(node.get('id'), str) and len(node['id']) <= 512
                    and re.fullmatch(r'tauri_command::[A-Za-z_][A-Za-z0-9_]*', node['id']) is not None)
            require(isinstance(node.get('provenance'), dict)
                    and type(node['provenance'].get('ambiguous')) is bool)
            require(node['id'] not in commands)
            commands.add(node['id'])
        else:
            require(relative_path(node.get('path')))
            require(node.get('analysis_status') in ANALYSIS_STATUSES)
            require(node['path'] not in documents)
            documents.add(node['path'])
    for edge in graph['edges']:
        require(isinstance(edge, dict) and relative_path(edge.get('src')))
        require(isinstance(edge.get('dst'), str) and len(edge['dst']) <= 512)
        require(edge.get('kind') in ('alters', 'queries'))
        require(edge.get('reference_status') in REFERENCE_STATUSES)
        require(edge['src'] in documents and edge['dst'] in commands)


class SnapshotQueries:
    def __init__(self, filename: Path):
        with filename.open('rb') as stream:
            raw = stream.read(MAX_SNAPSHOT_BYTES + 1)
        if len(raw) > MAX_SNAPSHOT_BYTES:
            raise ValueError('Snapshot exceeds the prototype size limit')
        envelope = json.loads(raw)
        validate_snapshot(envelope)
        graph = envelope['graph']
        self.snapshot = {
            'snapshot_sha256': hashlib.sha256(raw).hexdigest(),
            'core_commit': envelope['core_commit'],
            'created_at': envelope['created_at'],
            'current_worktree_verified': False,
        }
        self.documents = {
            n['path']: n.get('analysis_status') for n in graph['nodes']
            if n.get('kind') in ('file', 'config_file') and relative_path(n.get('path', ''))
        }
        self.commands = {
            n['id']: bool((n.get('provenance') or {}).get('ambiguous'))
            for n in graph['nodes'] if n.get('kind') == 'app_command'
            and isinstance(n.get('id'), str) and len(n['id']) <= 1600
            and not any(ord(c) < 32 for c in n['id'])
        }
        self.edges, self.by_source, self.by_resource = [], defaultdict(list), defaultdict(list)
        seen = set()
        for e in graph['edges']:
            if e.get('src') not in self.documents or e.get('dst') not in self.commands or e.get('kind') not in ('alters', 'queries'):
                continue
            key = (e['src'], e['dst'], e['kind'], e.get('reference_status'))
            if key in seen:
                continue
            seen.add(key)
            edge = dict(zip(('src', 'dst', 'kind', 'reference_status'), key))
            self.edges.append(edge)
            self.by_source[e['src']].append(edge)
            self.by_resource[e['dst']].append(edge)
        self.counts = {
            key: graph.get(key) for key in ('files_parsed', 'files_failed', 'files_skipped')
        }

    def context(self) -> dict:
        return {
            'snapshot': self.snapshot,
            'query_scope': 'tauri_app_command_metadata_only',
            'advisory_only': True,
            'metadata_is_untrusted_repository_data': True,
            'current_state_or_merge_safety_proven': False,
        }

    def summary(self) -> dict:
        return {
            **self.context(), **self.counts,
            'document_count': len(self.documents),
            'analysis_status_counts': dict(Counter(s or 'no_marker' for s in self.documents.values())),
            'tauri_command_count': len(self.commands),
            'retained_contract_edge_count': len(self.edges),
            'ambiguous_command_count': sum(self.commands.values()),
        }

    def related_files(self, path: str, limit: int = 20) -> dict:
        if not relative_path(path):
            raise ValueError('Use a repository-relative file path without traversal')
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValueError('limit must be an integer from 1 to 20')
        result = {
            **self.context(), 'path': path,
            'document_observed': path in self.documents,
            'analysis_status': self.documents.get(path),
        }
        rows = []
        for target in self.by_source.get(path, ()):
            for peer in self.by_resource[target['dst']]:
                if peer['src'] == path:
                    continue
                uncertain = bool(
                    self.commands[target['dst']] or target['reference_status']
                    or peer['reference_status'] or self.documents[path]
                    or self.documents[peer['src']]
                )
                rows.append({
                    'resource': target['dst'], 'related_file': peer['src'],
                    'target_role': target['kind'], 'peer_role': peer['kind'],
                    'target_reference_status': target['reference_status'],
                    'peer_reference_status': peer['reference_status'],
                    'peer_analysis_status': self.documents[peer['src']],
                    'evidence_status': 'uncertain' if uncertain else 'observed',
                })
        rows.sort(key=lambda row: (row['resource'], row['related_file'], row['target_role'], row['peer_role']))
        status = 'uncertain' if self.documents.get(path) or any(r['evidence_status'] == 'uncertain' for r in rows) else ('observed' if rows else 'not_observed')
        result = {
            **result,
            'status': status,
            'relations': rows[:limit], 'total_relation_rows': len(rows),
            'truncated': len(rows) > limit,
            'absence_means': 'No matching relation observed in this snapshot and query scope; not proof of no dependency.',
        }
        while len(json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8')) > MAX_RESPONSE_BYTES:
            result['relations'].pop()
            result['truncated'] = True
        return result
