"""Compare candidate address selection and object ownership with current Aerleon."""

import argparse
import hashlib
import json
import random
from pathlib import Path

from aerleon.lib import addressbook
from aerleon.lib.addressbook import Addressbook
from aerleon.lib.fqdn import FQDN
from aerleon.lib.nacaddr import IPv4, IPv6


def snapshot(book):
    return (
        [
            (zone, [(name, [id(ip) for ip in ips]) for name, ips in groups.items()])
            for zone, groups in book._ip_addressbook.items()
        ],
        [
            (zone, [(name, [id(fqdn) for fqdn in fqdns]) for name, fqdns in groups.items()])
            for zone, groups in book._fqdn_addressbook.items()
        ],
    )


def check(batches):
    original, candidate = OriginalAddressbook(), Addressbook()
    fqdn = FQDN("example.test", "DNS")
    for book in (original, candidate):
        book.AddFQDNs("fqdn", [fqdn])
    for zone, incoming in batches:
        original.AddAddresses(zone, incoming)
        candidate.AddAddresses(zone, incoming)
        assert snapshot(candidate) == snapshot(original), (zone, incoming)


def main():
    boundary = []
    for cls, bits in [(IPv4, 32), (IPv6, 128)]:
        for prefix in [0, 1, bits - 1, bits]:
            mask = ((1 << bits) - 1) ^ ((1 << (bits - prefix)) - 1)
            for start in [0, mask]:
                boundary.append(
                    cls(
                        (start, prefix), comment=f"{cls.__name__}/{prefix}/{start}", token="bounds"
                    )
                )
    check([("z", []), ("z", boundary), ("z", list(reversed(boundary)))])
    check(
        [
            ("z", [IPv4("10.0.0.0/25", "first", "same"), IPv4("10.0.0.128/25", "second", "same")]),
            ("z", [IPv4("10.0.0.0/24", "wide", "same")]),
            ("z", [IPv4("10.0.0.0/24", "duplicate", "same")]),
        ]
    )

    class CustomIPv4(IPv4):
        pass

    check(
        [
            ("z", [CustomIPv4("10.0.0.0/24", "custom", "group")]),
            ("z", [IPv4("10.0.0.0/25", "normal", "group")]),
            ("scoped", [IPv6("fe80::%eth0/128", "scope", "group")]),
        ]
    )
    rng = random.Random(37421)
    incoming_count = 0
    batch_count = 0
    for case in range(500):
        pool = []
        batches = []
        for batch in range(12):
            incoming = []
            for item in range(rng.randrange(0, 35)):
                cls, bits = rng.choice([(IPv4, 32), (IPv6, 128)])
                prefix = rng.choice([0, 1, bits // 2, bits - 8, bits - 1, bits])
                start = rng.getrandbits(bits) >> (bits - prefix) << (bits - prefix)
                ip = cls(
                    (start, prefix),
                    comment=f"{case}/{batch}/{item}",
                    token=rng.choice(["a", "b", "c", "d"]),
                )
                if pool and rng.random() < 0.25:
                    old = rng.choice(pool)
                    ip = type(old)(old, comment=ip.text, token=old.parent_token)
                incoming.append(ip)
                pool.append(ip)
            incoming_count += len(incoming)
            batch_count += 1
            batches.append((rng.choice(["trust", "untrust", "fqdn"]), incoming))
        check(batches)
    print(
        json.dumps(
            {
                "source_sha256": {
                    name: hashlib.sha256(
                        (path / "aerleon/lib/addressbook.py").read_bytes()
                    ).hexdigest()
                    for name, path in [("baseline", args.baseline), ("candidate", args.candidate)]
                },
                "seed": 37421,
                "cases": 500,
                "batches": batch_count,
                "incoming_networks": incoming_count,
                "backends": ["baseline", "production"],
                "checks": "selected object identity, ordering, zones, tokens, FQDN retention after every batch",
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    assert (
        Path(addressbook.__file__).resolve()
        == (args.candidate / "aerleon/lib/addressbook.py").resolve()
    )
    namespace = {}
    exec((args.baseline / 'aerleon/lib/addressbook.py').read_text(), namespace)
    OriginalAddressbook = namespace['Addressbook']
    main()
