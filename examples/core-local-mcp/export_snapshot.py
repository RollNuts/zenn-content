"""Project a pinned public Core graph into the local MCP demo's metadata schema."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from query_service import MAX_SNAPSHOT_BYTES, validate_snapshot

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def load_core(core: Path, git: str):
    core = core.resolve()
    lock = json.loads((HERE / 'core-source-lock.json').read_text())
    head = subprocess.run([git, '-C', str(core), 'rev-parse', 'HEAD'],
                          check=True, capture_output=True, text=True, timeout=10).stdout.strip()
    if head != lock['commit']:
        raise ValueError('Core HEAD does not match the pinned public commit')
    for path, expected in lock['files'].items():
        body = (core / path).read_bytes()
        if hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest() != expected:
            raise ValueError('A pinned Core source blob differs')
    sys.path.insert(0, str(core))
    import code_graph_extract as engine
    if Path(engine.__file__).resolve() != core / 'code_graph_extract.py':
        raise ValueError('Wrong Core module loaded')
    if not {'rust', 'typescript', 'tsx', 'javascript'} <= set(engine._ts_languages()):
        raise ValueError('Missing compatible grammars; install requirements-extract.txt')
    return engine, lock['commit']


def extract_snapshot(engine, commit: str, repo: Path) -> dict:
    graph = engine.build_graph(str(repo.resolve()))
    nodes = []
    for node in graph['nodes']:
        if node.get('kind') in ('file', 'config_file'):
            nodes.append({key: node.get(key) for key in ('kind', 'path', 'analysis_status')})
        elif node.get('kind') == 'app_command':
            nodes.append({'kind': 'app_command', 'id': node['id'],
                          'provenance': {'ambiguous': bool((node.get('provenance') or {}).get('ambiguous'))}})
    commands = {node['id'] for node in nodes if node['kind'] == 'app_command'}
    edges = [{key: edge.get(key) for key in ('src', 'dst', 'kind', 'reference_status')}
             for edge in graph['edges'] if edge.get('dst') in commands
             and edge.get('kind') in ('alters', 'queries')]
    projected = {key: graph.get(key) for key in ('files_parsed', 'files_failed', 'files_skipped')}
    projected.update(nodes=nodes, edges=edges)
    return {'format': 'veripsa-local-mcp-demo-v1', 'core_commit': commit,
            'created_at': datetime.now(timezone.utc).isoformat(), 'graph': projected}


def write_snapshot(snapshot: dict, output: Path) -> None:
    """Check the consumer contract and exact UTF-8 bytes before touching output."""
    validate_snapshot(snapshot)
    payload = (json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise ValueError(
            f'Serialized snapshot exceeds the server size limit '
            f'({len(payload)} > {MAX_SNAPSHOT_BYTES} UTF-8 bytes)')
    output.write_bytes(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', type=Path, required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--git', default='git')
    args = parser.parse_args()
    engine, commit = load_core(args.core, args.git)
    if not args.repo.is_dir():
        parser.error('--repo must be an existing local directory')
    snapshot = extract_snapshot(engine, commit, args.repo)
    try:
        write_snapshot(snapshot, args.out)
    except ValueError as error:
        parser.error(f'Cannot export a snapshot the server would reject: {error}')


if __name__ == '__main__':
    main()
