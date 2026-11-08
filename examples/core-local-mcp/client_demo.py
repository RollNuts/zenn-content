"""Call the two prototype tools over a real stdio subprocess connection."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters


def tool_data(result) -> dict:
    if result.is_error:
        raise RuntimeError('A prototype tool failed')
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


async def call(snapshot: Path, path: str, legacy: bool = False) -> dict:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(__file__).with_name('server.py')), '--snapshot', str(snapshot.resolve())],
        env={'PYTHONDONTWRITEBYTECODE': '1'},
    )
    async with Client(params, mode='legacy' if legacy else 'auto', read_timeout_seconds=10) as client:
        tools = await client.list_tools()
        summary = await client.call_tool('graph_summary', {})
        related = await client.call_tool('tauri_related_files', {'path': path})
        if summary.is_error or related.is_error:
            raise RuntimeError('A prototype tool failed')
        return {'protocol_version': client.protocol_version,
                'tools': [tool.name for tool in tools.tools],
                'summary': tool_data(summary),
                'related': tool_data(related)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=Path(__file__).parent / 'demo/official-literal.json')
    parser.add_argument('--path', default='src-tauri/commands.rs')
    parser.add_argument('--legacy', action='store_true', help='Use the SDK initialize-handshake path')
    args = parser.parse_args()
    print(json.dumps(asyncio.run(call(args.snapshot, args.path, args.legacy)), ensure_ascii=False, indent=2))
