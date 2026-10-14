"""Compare address-book insertion shapes with cached network bounds."""

import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
from pathlib import Path

from aerleon.lib import addressbook
from aerleon.lib.addressbook import Addressbook
from aerleon.lib.nacaddr import IPv4, IPv6


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=6)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error('--rounds must be positive')
    source_path = Path('aerleon/lib/addressbook.py')
    assert Path(addressbook.__file__).resolve() == (args.candidate / source_path).resolve()
    namespace = {}
    exec((args.baseline / source_path).read_text(), namespace)
    original = namespace['Addressbook'].AddAddresses
    methods = {'baseline': original, 'candidate': Addressbook.AddAddresses}
    results = {
        'python': sys.version,
        'platform': platform.platform(),
        'source_sha256': {
            name: hashlib.sha256((root / source_path).read_bytes()).hexdigest()
            for name, root in [('baseline', args.baseline), ('candidate', args.candidate)]
        },
        'timing': 'AddAddresses only; seed insertion and identity validation excluded; cached network bounds',
        'existing_networks': 10000,
        'results': {},
    }
    for cls, base, shift, prefix in [
        (IPv4, 0x0A000000, 8, 24),
        (IPv6, 0x20010DB8000000000000000000000000, 64, 64),
    ]:
        existing = [cls((base + (i << shift), prefix), token='GROUP') for i in range(10000)]
        shapes = {
            'single_before': (existing, [cls((base - (1 << shift), prefix), token='GROUP')]),
            'single_after': (existing, [cls((base + (10001 << shift), prefix), token='GROUP')]),
            'single_duplicate': (existing, existing[5000:5001]),
            'many_duplicates': (existing, existing[::2]),
            'initial': ([], list(reversed(existing))),
        }
        for shape, (seed, incoming) in shapes.items():
            seconds = {name: [] for name in methods}
            expected = None
            for round_number in range(-1, args.rounds):
                order = list(methods) if round_number % 2 == 0 else list(reversed(methods))
                for name in order:
                    book = Addressbook()
                    original(book, 'zone', seed)
                    started = time.perf_counter()
                    methods[name](book, 'zone', incoming)
                    elapsed = time.perf_counter() - started
                    actual = [id(ip) for ip in book.GetAddress('zone', 'GROUP')]
                    if expected is None:
                        expected = actual
                    assert actual == expected, (cls.__name__, shape, name)
                    if round_number >= 0:
                        seconds[name].append(elapsed)
            medians = {name: statistics.median(values) for name, values in seconds.items()}
            results['results'][f'{cls.__name__}/{shape}'] = {
                'seconds': seconds,
                'medians': medians,
            }
            print(
                f'{cls.__name__}/{shape}: {medians["baseline"] * 1000:.3f} -> '
                f'{medians["candidate"] * 1000:.3f} ms',
                flush=True,
            )
    args.output.write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()
