#!/usr/bin/env python3
"""Audit file-level review candidates at three fixed public Flask pre-change states.

Python 3.12 / POSIX, local full clones only. Flask source is parsed, never imported
or executed. The pinned Core producers supply adjacency and historical evidence;
this script only projects their output onto a declared candidate universe.
"""
from __future__ import annotations

import argparse
import inspect
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

HERE = Path(__file__).resolve().parent
CORE_PIN = '4236848504c8cb2cc3c14db22408fb519b06f754'
FLASK_PIN = '49943b5a94413a530761350f04e896f76e8d620e'
SHA = re.compile(r'[0-9a-f]{40}\Z')
METHODS = ('graph', 'history', 'union', 'intersection')
PARAMETERS = ('window', 'max_commit_files', 'min_support', 'min_prob', 'min_lift',
              'max_pairs', 'timeout')
WORKER = ('import sys; sys.path.insert(0, sys.argv[1]); import review; '
          'review._worker(*sys.argv[2:])')


class ReviewError(RuntimeError):
    """A bounded failure; raw Git, parser, and filesystem errors stay private."""


def relative_python_path(value: object) -> bool:
    if not isinstance(value, str) or not value or '\\' in value:
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        return False
    path = PurePosixPath(value)
    return (not path.is_absolute() and str(path) == value
            and '..' not in path.parts and value.endswith('.py')
            and value.startswith(('src/flask/', 'tests/')))


def load_cases(path: Path = HERE / 'cases.json') -> list[dict]:
    data = json.loads(path.read_text(encoding='utf-8'))
    allowed = {'cases', 'schema', 'repository', 'core_commit', 'flask_history_pin',
               'selection', 'review_authorship', 'question'}
    if not isinstance(data, dict) or 'cases' not in data or set(data) - allowed:
        raise ReviewError('Invalid case manifest.')
    for key, expected in {'schema': 'core-change-review-cases-v1',
                          'repository': 'https://github.com/pallets/flask',
                          'core_commit': CORE_PIN, 'flask_history_pin': FLASK_PIN}.items():
        if key in data and data[key] != expected:
            raise ReviewError('Case manifest identity differs from the fixed corpus.')
    cases = data['cases']
    if not isinstance(cases, list) or len(cases) != 3:
        raise ReviewError('Exactly three fixed cases are required.')
    ids, targets = set(), set()
    for case in cases:
        required = {'id', 'target', 'base', 'seed', 'review_targets'}
        if (not isinstance(case, dict) or not required <= set(case)
                or set(case) - required - {'change'}):
            raise ReviewError('Invalid case fields.')
        if 'change' in case and (not isinstance(case['change'], str) or not case['change']
                                 or len(case['change']) > 2000
                                 or any(ord(c) < 32 for c in case['change'])):
            raise ReviewError('Invalid change description.')
        identifier = case['id']
        if (not isinstance(identifier, str)
                or re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,79}', identifier) is None
                or identifier in ids):
            raise ReviewError('Invalid or duplicate case identifier.')
        ids.add(identifier)
        if any(not isinstance(case[k], str) or not SHA.fullmatch(case[k])
               for k in ('target', 'base')) or case['target'] in targets:
            raise ReviewError('Invalid or duplicate commit pin.')
        targets.add(case['target'])
        if not relative_python_path(case['seed']):
            raise ReviewError('Invalid seed path.')
        reviews = case['review_targets']
        if not isinstance(reviews, list) or not reviews:
            raise ReviewError('Review targets are required.')
        seen = set()
        for target in reviews:
            if not isinstance(target, dict) or set(target) != {
                    'path', 'symbol', 'reason', 'evidence_url'}:
                raise ReviewError('Invalid review target fields.')
            if not relative_python_path(target['path']):
                raise ReviewError('Invalid review target path.')
            symbol = target['symbol']
            if (not isinstance(symbol, str) or not symbol or len(symbol) > 200
                    or any(ord(c) < 32 for c in symbol)):
                raise ReviewError('Invalid review symbol.')
            if (not isinstance(target['reason'], str) or not target['reason']
                    or len(target['reason']) > 2000
                    or any(ord(c) < 32 for c in target['reason'])):
                raise ReviewError('Invalid review rationale.')
            url = target['evidence_url']
            if (not isinstance(url, str) or len(url) > 1000
                    or not url.startswith('https://github.com/pallets/flask/')
                    or any(ord(c) <= 32 for c in url)):
                raise ReviewError('Invalid public evidence URL.')
            key = (target['path'], symbol)
            if key in seen:
                raise ReviewError('Duplicate review target.')
            seen.add(key)
    return cases


class LocalGit:
    def __init__(self, executable: str, hooks: Path):
        located = shutil.which(executable)
        if not located:
            raise ReviewError('Git executable is unavailable.')
        self.executable = str(Path(located).absolute())
        self.hooks = hooks
        hooks.mkdir(exist_ok=True)
        self.environment = {k: v for k, v in os.environ.items()
                            if not k.startswith('GIT_')}
        self.environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                                GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0',
                                GIT_NO_REPLACE_OBJECTS='1',
                                GIT_ALLOW_PROTOCOL='file')

    def call(self, repo: Path | None, *arguments: str, binary: bool = False,
             timeout: int = 120) -> str | bytes:
        command = [self.executable, '-c', 'core.hooksPath=' + str(self.hooks),
                   '-c', 'maintenance.auto=false', '-c', 'gc.auto=0']
        if repo is not None:
            command += ['-C', str(repo)]
        command += list(arguments)
        try:
            process = subprocess.run(command, env=self.environment,
                                     stdin=subprocess.DEVNULL, capture_output=True,
                                     text=not binary, timeout=timeout, check=False)
        except (OSError, subprocess.SubprocessError):
            raise ReviewError('Local Git command could not complete.') from None
        if process.returncode:
            raise ReviewError('Local Git command failed.')
        return process.stdout if binary else process.stdout.rstrip('\n')


def validate_clone(git: LocalGit, root: Path, pin: str) -> None:
    if (not root.is_dir()
            or git.call(root, 'rev-parse', '--is-inside-work-tree') != 'true'
            or git.call(root, 'rev-parse', '--is-shallow-repository') != 'false'
            or Path(git.call(root, 'rev-parse', '--show-toplevel')).resolve() != root
            or git.call(root, 'rev-parse', '--verify', pin + '^{commit}') != pin):
        raise ReviewError('A complete local clone containing its fixed pin is required.')


def validate_case(git: LocalGit, flask: Path, case: dict) -> None:
    target, base = case['target'], case['base']
    if (git.call(flask, 'rev-parse', '--verify', target + '^{commit}') != target
            or git.call(flask, 'rev-parse', target + '^1') != base):
        raise ReviewError('The recorded base must be the target first parent.')
    git.call(flask, 'merge-base', '--is-ancestor', target, FLASK_PIN)


def extract_archive(data: bytes, destination: Path) -> None:
    """Extract ordinary files/directories only; never links or traversal entries."""
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:') as archive:
        members = archive.getmembers()
        seen = set()
        for member in members:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or '..' in path.parts or '\\' in member.name
                    or not path.parts or str(path) in seen
                    or not (member.isdir() or member.isfile())):
                raise ReviewError('Unsafe archive entry.')
            seen.add(str(path))
        destination.mkdir()
        for member in members:
            path = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ReviewError('Archive file is unavailable.')
                with source, path.open('xb') as output:
                    shutil.copyfileobj(source, output)


def temporary_clone(git: LocalGit, source: Path, destination: Path, base: str) -> None:
    git.call(None, 'clone', '--quiet', '--local', '--shared', '--no-checkout',
             '--', str(source), str(destination))
    git.call(destination, 'checkout', '--quiet', '--detach', base)
    if git.call(destination, 'rev-parse', 'HEAD') != base:
        raise ReviewError('Temporary clone did not reach the recorded base.')


def history_preflight(git: LocalGit, root: Path, window: int,
                      target: str, timeout: int) -> list[str]:
    # Exact producer log options: reject process failures before its forgiving
    # reader could mistake them for an empty history. No target/patch is read.
    output = git.call(root, 'log', '--no-merges', '--name-status', '-M',
                      '--pretty=format:\x01%H', '-n', str(window), timeout=timeout)
    commits = [line[1:] for line in output.split('\n') if line.startswith('\x01')]
    if not commits or any(not SHA.fullmatch(commit) for commit in commits):
        raise ReviewError('Historical log did not contain valid commit records.')
    if target in commits:
        raise ReviewError('Target commit leaked into historical input.')
    return commits


def project_candidates(seed: str, universe: set[str], graph_pairs: dict,
                       history_pairs: list[dict]) -> dict:
    graph = {}
    for pair, kinds in graph_pairs.items():
        if seed not in pair or len(pair) != 2:
            continue
        peer = next(path for path in pair if path != seed)
        if peer in universe:
            graph.setdefault(peer, set()).update(kinds)
    history = set()
    for row in history_pairs:
        if row['a'] == seed and row['b'] in universe:
            history.add(row['b'])
        if row['b'] == seed and row['a'] in universe:
            history.add(row['a'])
    history.discard(seed)
    graph.pop(seed, None)
    return {
        'candidates': {'graph': sorted(graph), 'history': sorted(history),
                       'union': sorted(set(graph) | history),
                       'intersection': sorted(set(graph) & history)},
        'graph_evidence': [{'path': path, 'kinds': sorted(graph[path])}
                           for path in sorted(graph)],
    }


class CheckedSubprocess:
    """Keep the producer's forgiving reader from hiding an actual Git failure."""
    def __init__(self, module):
        self.module = module

    def __getattr__(self, name):
        return getattr(self.module, name)

    def run(self, *args, **kwargs):
        try:
            result = self.module.run(*args, **kwargs)
        except (OSError, subprocess.SubprocessError):
            raise ReviewError('Producer Git command could not complete.') from None
        if result.returncode:
            raise ReviewError('Producer Git command failed.')
        return result


def _worker(core: str, repo: str, seed: str, target: str, base: str,
            hooks: str) -> None:
    sys.path.insert(0, core)
    import cochange_backtest as BT
    import _cg_cochange as CC

    git = LocalGit('git', Path(hooks))
    root = Path(repo)
    if git.call(root, 'rev-parse', 'HEAD') != base:
        raise ReviewError('Historical checkout does not match the base.')
    defaults = inspect.signature(CC.cochange_pairs).parameters
    parameters = {name: defaults[name].default for name in PARAMETERS}
    commits = history_preflight(git, root, parameters['window'], target,
                                parameters['timeout'])
    tracked = git.call(root, 'ls-tree', '-r', '-z', '--name-only', 'HEAD',
                       '--', 'src/flask', 'tests').split('\0')
    universe = {path for path in tracked if relative_python_path(path)}
    if seed not in universe:
        raise ReviewError('The seed does not exist in the pre-change candidate universe.')
    started = time.perf_counter()
    graph = BT.X.build_graph(repo)
    files = {node['path'] for node in graph['nodes'] if node.get('kind') == 'file'}
    pairs = BT.coupled_pairs(graph, files)  # Full graph first, projection second.
    graph_seconds = time.perf_counter() - started
    started = time.perf_counter()
    original_subprocess = CC.subprocess
    CC.subprocess = CheckedSubprocess(original_subprocess)
    try:
        history = CC.cochange_pairs(repo)  # All defaults; no count/threshold copy.
    finally:
        CC.subprocess = original_subprocess
    history_seconds = time.perf_counter() - started
    if (git.call(root, 'rev-parse', 'HEAD') != base
            or git.call(root, 'status', '--porcelain=v1', '--untracked-files=all')):
        raise ReviewError('Analysis changed the temporary source checkout.')
    projected = project_candidates(seed, universe, pairs, history)
    data = {'candidate_universe': sorted(universe - {seed}),
            'candidate_universe_count': len(universe - {seed}),
            'history_parameters': parameters,
            'history_input': {'head': base, 'non_merge_commits_in_window': len(commits),
                              'target_present': False},
            **projected}
    print(json.dumps({'data': data, 'timings': {'graph_seconds': graph_seconds,
                                               'history_seconds': history_seconds}}))


def _review_targets(case: dict, data: dict) -> list[dict]:
    sets = {name: set(paths) for name, paths in data['candidates'].items()}
    evidence = {row['path']: row['kinds'] for row in data['graph_evidence']}
    universe = set(data['candidate_universe'])
    return [{**target, 'in_candidate_universe': target['path'] in universe,
             'contained_by': {name: target['path'] in sets[name] for name in METHODS},
             'graph_evidence_kinds': evidence.get(target['path'], [])}
            for target in case['review_targets']]


def run_review(core: Path, flask: Path, executable: str,
               cases: list[dict]) -> tuple[dict, dict]:
    core, flask = core.resolve(), flask.resolve()
    with tempfile.TemporaryDirectory(prefix='core-change-review-') as directory:
        temporary = Path(directory)
        git = LocalGit(executable, temporary / 'empty-hooks')
        validate_clone(git, core, CORE_PIN)
        validate_clone(git, flask, FLASK_PIN)
        for case in cases:
            validate_case(git, flask, case)
        extracted = temporary / 'core'
        extract_archive(git.call(core, 'archive', '--format=tar', CORE_PIN, binary=True),
                        extracted)
        binary = temporary / 'bin'
        binary.mkdir()
        wrapper = binary / 'git'
        wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(git.executable)
                           + ' "$@"\n', encoding='utf-8')
        wrapper.chmod(0o700)
        environment = dict(git.environment)
        environment['PATH'] = str(binary) + os.pathsep + environment.get('PATH', os.defpath)
        reports, timings = [], []
        for case in cases:
            checkout = temporary / case['id']
            started = time.perf_counter()
            temporary_clone(git, flask, checkout, case['base'])
            clone_seconds = time.perf_counter() - started
            process = subprocess.run(
                [sys.executable, '-I', '-S', '-B', '-c', WORKER, str(HERE),
                 str(extracted), str(checkout), case['seed'], case['target'],
                 case['base'], str(git.hooks)], env=environment, cwd=temporary,
                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                timeout=300, check=False)
            if process.returncode:
                raise ReviewError('Pinned producer worker failed.')
            result = json.loads(process.stdout)
            data = result['data']
            reports.append({key: case[key] for key in ('id', 'target', 'base', 'seed')})
            if 'change' in case:
                reports[-1]['change'] = case['change']
            reports[-1].update(data)
            reports[-1]['review_targets'] = _review_targets(case, data)
            timings.append({'id': case['id'], 'clone_seconds': clone_seconds,
                            **result['timings']})
    return ({
        'audit': 'core-change-review-v1', 'core_commit': CORE_PIN,
        'flask_upper_commit': FLASK_PIN,
        'scope': 'Three fixed public changes; pre-change file-level candidate inclusion only.',
        'universe': 'Existing src/flask/**/*.py and tests/**/*.py at each base; seed excluded.',
        'cases': reports,
        'limitations': [
            'Review targets are selected examples, not exhaustive labels; no precision or recall is measured.',
            'Targets are AI-assisted source-review examples, not independent human-labelled ground truth.',
            'Symbol names explain the review target; inclusion is measured at file level only.',
            'Flask previously informed thresholds and stoplists; this is not an independent unseen test set.',
            'Graph evidence uses the existing coarse offline coupled_pairs, not the database PR policy.',
            'Historical association is not causation or a prediction that a change will fail.',
            'not_observed is not Clear, no dependency, or permission to merge.',
            'No Flask code, model, database, network fetch, or hosted service is executed.',
        ],
    }, {'cases': timings})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', type=Path, required=True)
    parser.add_argument('--flask', type=Path, required=True)
    parser.add_argument('--git', default=shutil.which('git') or 'git')
    parser.add_argument('--check', nargs='?', const=HERE / 'expected-output.json', type=Path)
    parser.add_argument('--timings', type=Path)
    args = parser.parse_args(argv)
    try:
        if os.name != 'posix' or sys.version_info < (3, 12):
            raise ReviewError('Python 3.12 or newer on POSIX is required.')
        if args.timings:
            output = args.timings.resolve()
            if any(output.is_relative_to(source.resolve()) for source in (args.core, args.flask)):
                raise ReviewError('Timing output must not modify an input clone.')
        report, timings = run_review(args.core, args.flask, args.git, load_cases())
        if args.check and json.loads(args.check.read_text(encoding='utf-8')) != report:
            raise ReviewError('Observed output differs from the checked example.')
        if args.timings:
            args.timings.write_text(json.dumps(timings, indent=2) + '\n', encoding='utf-8')
    except (ReviewError, OSError, ValueError, KeyError, TypeError, tarfile.TarError,
            subprocess.SubprocessError):
        print('Case audit failed; check local full clones, pins, manifest and Git. '
              'No successful result is claimed.', file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
