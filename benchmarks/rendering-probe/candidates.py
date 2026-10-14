"""Experimental address-book backends; the Aerleon checkout stays unchanged."""

import collections
import heapq
import itertools

from aerleon.lib import addressbook, nacaddr

ORIGINAL = addressbook.Addressbook.AddAddresses


def integer_indices(networks, existing):
    incoming = sorted(range(existing, len(networks)), key=networks.__getitem__)
    ordered = heapq.merge(range(existing), incoming, key=networks.__getitem__)
    selected = []
    last_version = None
    last_end = -1
    for index in ordered:
        version, start, prefix = networks[index]
        end = start | ((1 << ((32 if version == 4 else 128) - prefix)) - 1)
        if version != last_version or end > last_end:
            selected.append(index)
            last_version, last_end = version, end
    return selected


def sorted_integer_indices(networks, existing):
    ordered = sorted(range(len(networks)), key=networks.__getitem__)
    selected = []
    last_version = None
    last_end = -1
    for index in ordered:
        version, start, prefix = networks[index]
        end = start | ((1 << ((32 if version == 4 else 128) - prefix)) - 1)
        if version != last_version or end > last_end:
            selected.append(index)
            last_version, last_end = version, end
    return selected


def add_addresses(self, zone, addresses, select):
    groups = collections.defaultdict(list)
    for address in addresses:
        groups[address.parent_token].append(address)
    if zone not in self._ip_addressbook:
        self._ip_addressbook[zone] = collections.defaultdict(list)
        self._fqdn_addressbook[zone] = collections.defaultdict(list)
    for name in sorted(groups):
        current = self._ip_addressbook[zone][name]
        incoming = groups[name]
        candidates = current + incoming
        if any(
            type(ip) not in (nacaddr.IPv4, nacaddr.IPv6)
            or getattr(ip.network_address, "scope_id", None) is not None
            for ip in candidates
        ):
            ORIGINAL(self, zone, incoming)
            continue
        networks = [(ip.version, int(ip.network_address), ip.prefixlen) for ip in candidates]
        selected = select(networks, len(current))
        self._ip_addressbook[zone][name] = [candidates[index] for index in selected]


def direct_addresses(self, zone, addresses):
    groups = collections.defaultdict(list)
    for address in addresses:
        groups[address.parent_token].append(address)
    if zone not in self._ip_addressbook:
        self._ip_addressbook[zone] = collections.defaultdict(list)
        self._fqdn_addressbook[zone] = collections.defaultdict(list)
    for name in sorted(groups):
        combined = self._ip_addressbook[zone][name] + groups[name]
        if any(
            type(ip) not in (nacaddr.IPv4, nacaddr.IPv6)
            or getattr(ip.network_address, "scope_id", None) is not None
            for ip in combined
        ):
            ORIGINAL(self, zone, groups[name])
            continue
        combined.sort(key=lambda ip: (ip.version, int(ip.network_address), ip.prefixlen))
        selected = []
        for _, family in itertools.groupby(combined, key=lambda ip: ip.version):
            last_end = -1
            for ip in family:
                end = int(ip.broadcast_address)
                if end > last_end:
                    selected.append(ip)
                    last_end = end
        self._ip_addressbook[zone][name] = selected


def install(backend):
    import chained

    chained.reset()
    parts = backend.split("+")
    backend = parts[0]
    for part in parts[1:]:
        chained.install(part)
    if backend == "baseline":
        addressbook.Addressbook.AddAddresses = ORIGINAL
        return
    if backend == "direct":
        addressbook.Addressbook.AddAddresses = direct_addresses
        return
    if backend == "integers":
        select = integer_indices
    elif backend == "integer-sort":
        select = sorted_integer_indices
    elif backend == "rust":
        from _aerleon_probe import address_book_indices

        select = address_book_indices
    else:
        raise ValueError(backend)
    addressbook.Addressbook.AddAddresses = lambda self, zone, addresses: add_addresses(
        self, zone, addresses, select
    )
