"""Compare complete CLI runs from two Aerleon source checkouts."""

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

WORKLOADS = {
    'all': None,
    'large': 'sample_stateful_multitarget_complex.pol',
    'small': 'sample_srx.pol',
    'msmpc': 'sample_msmpc.pol',
}


def hashes(root, folders, pattern='*'):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for folder in folders
        for path in sorted((root / folder).rglob(pattern))
        if path.is_file()
    }


def render(root, workload, optimize):
    with tempfile.TemporaryDirectory(prefix='aerleon-benchmark-') as directory:
        command = [
            sys.executable,
            '-m',
            'aerleon.aclgen',
            '--max_renderers=1',
            f'--base_directory={root / "policies"}',
            f'--definitions_directory={root / "def"}',
            f'--output_directory={directory}',
        ]
        if WORKLOADS[workload]:
            command.append(f'--policy_file={root / "policies/pol" / WORKLOADS[workload]}')
        if optimize:
            command.append('--optimize')
        started = time.perf_counter()
        subprocess.run(
            command,
            cwd=root,
            env=dict(os.environ, PYTHONHASHSEED='0'),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        seconds = time.perf_counter() - started
        files = hashes(Path(directory), ['.'])
        if not files:
            raise RuntimeError('no output files')
        return {'seconds': seconds, 'files': files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--base-revision', required=True)
    parser.add_argument('--candidate-revision', required=True)
    parser.add_argument('--rounds', type=int, default=6)
    parser.add_argument('--optimize', action='store_true')
    parser.add_argument('--workloads', nargs='+', choices=WORKLOADS, default=list(WORKLOADS))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error('--rounds must be positive')
    roots = {'baseline': args.baseline.resolve(), 'candidate': args.candidate.resolve()}
    inputs = {name: hashes(root, ['policies', 'def']) for name, root in roots.items()}
    if inputs['baseline'] != inputs['candidate']:
        raise RuntimeError('baseline and candidate inputs differ')
    data = {
        'revisions': {'baseline': args.base_revision, 'candidate': args.candidate_revision},
        'python': sys.version,
        'platform': platform.platform(),
        'workers': 1,
        'hash_seed': '0',
        'optimize': args.optimize,
        'timing': 'fresh python -m aerleon.aclgen; includes startup and output writes',
        'input_sha256': inputs['baseline'],
        'source_sha256': {name: hashes(root, ['aerleon'], '*.py') for name, root in roots.items()},
        'runs': [],
    }
    for workload in args.workloads:
        expected = None
        for round_number in range(-1, args.rounds):
            order = (
                ['baseline', 'candidate'] if round_number % 2 == 0 else ['candidate', 'baseline']
            )
            for name in order:
                result = render(roots[name], workload, args.optimize)
                if expected is None:
                    expected = result['files']
                elif result['files'] != expected:
                    raise RuntimeError(f'output mismatch for {name}/{workload}')
                result.update(backend=name, workload=workload, round=round_number)
                data['runs'].append(result)
                print(
                    json.dumps(
                        {
                            key: len(value) if key == 'files' else value
                            for key, value in result.items()
                        }
                    ),
                    flush=True,
                )
                args.output.write_text(json.dumps(data, indent=2) + '\n')
    data['medians'] = {
        workload: {
            name: statistics.median(
                row['seconds']
                for row in data['runs']
                if row['workload'] == workload and row['backend'] == name and row['round'] >= 0
            )
            for name in roots
        }
        for workload in args.workloads
    }
    args.output.write_text(json.dumps(data, indent=2) + '\n')


if __name__ == '__main__':
    main()
