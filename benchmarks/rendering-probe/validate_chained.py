"""Check subnet text against the existing IP implementation."""

import ipaddress
import json

import chained

from aerleon.lib import juniper, junipermsmpc, nacaddr, policy


def main():
    checked = 0
    for start in (0, 1 << 127):
        network = nacaddr.IPv6((start, 1))
        actual = list(chained.prefix16_strings(network))
        expected = [str(ip) for ip in ipaddress.IPv6Network((start, 1)).subnets(new_prefix=16)]
        assert actual == expected
        for exclude in (False, True):
            original, batched = juniper.Config(indent=12), juniper.Config(indent=12)
            original.Append("source-address {")
            batched.Append("source-address {")
            suffix = " except;" if exclude else ";"
            for text in expected:
                original.Append(text + suffix)
            chained.append_prefix16(batched, network, exclude)
            original.Append("}")
            batched.Append("}")
            assert str(original) == str(batched)
        checked += len(actual)
    ranges = 0
    for prefix in range(1, 16):
        mask = ((1 << 128) - 1) ^ ((1 << (128 - prefix)) - 1)
        for start in (0, (0x5A3B << 112) & mask, mask):
            network = nacaddr.IPv6((start, prefix))
            assert list(chained.prefix16_strings(network)) == [
                str(ip) for ip in network.subnets(new_prefix=16)
            ]
            ranges += 1

    class CustomIPv6(nacaddr.IPv6):
        def subnets(self, **kwargs):
            return iter(["custom-subnet"])

    assert list(chained.prefix16_strings(CustomIPv6("2000::/15"))) == ["custom-subnet"]
    scoped = nacaddr.IPv6("fe00::%eth0/8")
    assert list(chained.prefix16_strings(scoped)) == [
        str(ip) for ip in scoped.subnets(new_prefix=16)
    ]

    contexts = 0
    for backend in ("prefix16", "prefix16-batch"):
        chained.install(backend)
        for apply_groups in (False, True):
            for noverbose in (False, True):
                for family in ("inet6", "mixed"):
                    for networks in (
                        ("::/13", "2::/15", "fff8::/13", "fffa::/15"),
                        ("2000::/13", "2002::/15", "4000::/13", "4002::/15"),
                    ):

                        def render(original):
                            term = policy.Term([])
                            term.name = "prefixes"
                            term.action = ["accept"]
                            for field, network in zip(
                                (
                                    "source_address",
                                    "source_address_exclude",
                                    "destination_address",
                                    "destination_address_exclude",
                                ),
                                networks,
                            ):
                                setattr(term, field, [nacaddr.IPv6(network, comment=field)])
                            if family == "mixed":
                                term.source_address.append(nacaddr.IPv4("10.0.0.0/8"))
                                term.destination_address.append(nacaddr.IPv4("172.16.0.0/12"))
                            renderer = junipermsmpc.Term(
                                term, family, noverbose, "test", apply_groups
                            )
                            return chained.MSMPC_STR(renderer) if original else str(renderer)

                        expected, actual = render(True), render(False)
                        assert expected and " except;" in expected and "::/16" in expected
                        assert actual == expected, (
                            backend,
                            apply_groups,
                            noverbose,
                            family,
                            networks,
                        )
                        contexts += 1
    chained.reset()
    print(
        json.dumps(
            {
                "unique_prefix16_strings": checked,
                "prefix_ranges": ranges,
                "renderer_cases": contexts,
                "fallbacks": ["subclass", "scoped IPv6"],
            }
        )
    )


if __name__ == "__main__":
    main()
