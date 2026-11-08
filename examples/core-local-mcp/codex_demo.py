"""Optional live Codex check. Uses the signed-in account's model usage allowance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from query_service import SnapshotQueries

HERE = Path(__file__).resolve().parent
PROMPT = (
    'Use only the core_contracts MCP tools. First call graph_summary. Then call '
    'tauri_related_files with path src-tauri/commands.rs. Do not use shell, '
    'file-read, browser, or other tools. Do not edit files. Return only JSON with '
    'query_status from the tool, related_files from relations, and '
    'current_state_or_merge_safety_proven from the tool. If an MCP call fails, '
    'report failure rather than guessing.'
)
SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {'query_status': {'type': 'string'},
                   'related_files': {'type': 'array', 'items': {'type': 'string'}},
                   'current_state_or_merge_safety_proven': {'type': 'boolean'}},
    'required': ['query_status', 'related_files', 'current_state_or_merge_safety_proven'],
}


def verify_events(events: list[dict], answer: dict, queries: SnapshotQueries) -> list[dict]:
    if any(not isinstance(event, dict) for event in events):
        raise ValueError('Invalid Codex event')
    if any(event.get('type') in ('error', 'turn.failed') for event in events):
        raise ValueError('Codex reported a failed turn')
    all_items = [event.get('item') for event in events if str(event.get('type', '')).startswith('item.')]
    if any(not isinstance(item, dict) or item.get('type') not in ('mcp_tool_call', 'agent_message', 'reasoning') for item in all_items):
        raise ValueError('Unexpected tool activity in the Codex run')
    completed = [event['item'] for event in events
                 if event.get('type') == 'item.completed' and isinstance(event.get('item'), dict)]
    if any(item.get('type') not in ('mcp_tool_call', 'agent_message', 'reasoning') for item in completed):
        raise ValueError('Unexpected tool activity in the Codex run')
    calls = [item for item in completed if item.get('type') == 'mcp_tool_call']
    by_tool = {call.get('tool'): call for call in calls}
    if len(calls) != 2 or set(by_tool) != {'graph_summary', 'tauri_related_files'}:
        raise ValueError('The two required MCP calls were not observed')
    for tool in ('graph_summary', 'tauri_related_files'):
        call = by_tool[tool]
        if not (call.get('server') == 'core_contracts' and call.get('tool') == tool
                and call.get('status') == 'completed'
                and call.get('error') is None):
            raise ValueError('Unexpected or failed MCP call')
        arguments = call.get('arguments')
        if not isinstance(arguments, dict):
            raise ValueError('Invalid MCP arguments')
        if tool == 'graph_summary':
            if arguments:
                raise ValueError('Unexpected summary arguments')
            result = queries.summary()
        else:
            if set(arguments) - {'path', 'limit'} or arguments.get('path') != 'src-tauri/commands.rs':
                raise ValueError('Unexpected related-file arguments')
            result = queries.related_files(arguments['path'], arguments.get('limit', 20))
        raw = call['result']
        if not isinstance(raw, dict):
            raise ValueError('Invalid MCP result')
        data = raw.get('structured_content')
        if data is None:
            content = raw.get('content')
            if not (isinstance(content, list) and content and isinstance(content[0], dict)
                    and isinstance(content[0].get('text'), str)):
                raise ValueError('Invalid MCP text content')
            data = json.loads(raw['content'][0]['text'])
        if data != result:
            raise ValueError('MCP result differed from the fixed snapshot query')
    expected_answer = {'query_status': 'observed', 'related_files': ['src/client.ts'],
                       'current_state_or_merge_safety_proven': False}
    if answer != expected_answer:
        raise ValueError('Final answer differed from the observed MCP result')
    # Return an allow-listed receipt, never the raw transcript, arbitrary fields or arguments.
    return [{'server': 'core_contracts', 'tool': tool, 'status': 'completed'}
            for tool in ('graph_summary', 'tauri_related_files')]


def run(codex: str) -> dict:
    version = subprocess.run([codex, '--version'], check=True, capture_output=True,
                             text=True, stdin=subprocess.DEVNULL, timeout=10).stdout.strip()
    if re.fullmatch(r'codex-cli [0-9]+\.[0-9]+\.[0-9]+', version) is None:
        raise ValueError('Could not determine the Codex CLI version')
    queries = SnapshotQueries(HERE / 'demo/official-literal.json')
    with tempfile.TemporaryDirectory(prefix='core-mcp-codex-') as temporary:
        workspace = Path(temporary)
        schema, output = workspace / 'schema.json', workspace / 'answer.json'
        schema.write_text(json.dumps(SCHEMA))
        arguments = [
            codex, 'exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
            '--sandbox', 'read-only', '--cd', str(workspace), '--json', '--color', 'never',
            '--output-schema', str(schema), '--output-last-message', str(output),
            '-c', 'approval_policy="never"',
            '-c', 'mcp_servers.core_contracts.command=' + json.dumps(sys.executable),
            '-c', 'mcp_servers.core_contracts.args=' + json.dumps([
                str(HERE / 'server.py'), '--snapshot', str(HERE / 'demo/official-literal.json')]),
            '-c', 'mcp_servers.core_contracts.enabled_tools=["graph_summary","tauri_related_files"]',
            '-c', 'mcp_servers.core_contracts.required=true', PROMPT,
        ]
        result = subprocess.run(arguments, capture_output=True, text=True,
                                stdin=subprocess.DEVNULL, timeout=120)
        if result.returncode != 0:
            raise ValueError('Codex did not complete. Check its version, sign-in and account allowance.')
        events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        answer = json.loads(output.read_text())
        calls = verify_events(events, answer, queries)
    return {'codex_cli': version, 'tools': calls, 'answer': answer,
            'execution': 'one ephemeral read-only invocation with per-run MCP configuration',
            'transcript_published': False, 'passed': True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex', default='codex', help='Codex executable; tested with 0.167.0')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        report = run(args.codex)
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError, subprocess.SubprocessError):
        # CLI errors can carry local paths, account details and arbitrary output.
        print('Codex check failed; inspect your own CLI setup. No successful MCP-host result is claimed.', file=sys.stderr)
        return 1
    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
