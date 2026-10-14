"""Isolated rendering experiments, compiled from the pinned upstream functions."""

import ast
import inspect
import textwrap

from aerleon.lib import junipermsmpc, junipersrx, nacaddr

MSMPC_STR = junipermsmpc.Term.__str__
SRX_BOOK = junipersrx.JuniperSRX._GenerateAddressBook
SRX_ADDR = junipersrx.JuniperSRX._GenerateAddresses
SRX_SETS = junipersrx.JuniperSRX._GenerateAddressSets


def reset():
    junipermsmpc.Term.__str__ = MSMPC_STR
    junipersrx.JuniperSRX._GenerateAddressBook = SRX_BOOK
    junipersrx.JuniperSRX._GenerateAddresses = SRX_ADDR
    junipersrx.JuniperSRX._GenerateAddressSets = SRX_SETS


def prefix16_strings(address):
    if type(address) is not nacaddr.IPv6 or address.network_address.scope_id is not None:
        yield from (str(network) for network in address.subnets(new_prefix=16))
        return
    # The caller expands only IPv6 prefixes /1 through /15; all remaining bits are zero.
    first = int(address.network_address) >> 112
    for value in range(first, first + (1 << (16 - address.prefixlen))):
        yield f"{value:x}::/16" if value else "::/16"


def append_prefix16(config, address, exclude):
    suffix = " except;" if exclude else ";"
    if type(address) is not nacaddr.IPv6 or address.network_address.scope_id is not None:
        for network in address.subnets(new_prefix=16):
            config.Append(f"{network}{suffix}")
        return
    spaces = " " * config.indent
    config.lines.extend(f"{spaces}{network}{suffix}" for network in prefix16_strings(address))


class SubnetLines(ast.NodeTransformer):
    def __init__(self):
        self.replacements = 0

    def visit_For(self, node):
        call = node.iter
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "subnets"
            and len(call.keywords) == 1
            and call.keywords[0].arg == "new_prefix"
            and isinstance(call.keywords[0].value, ast.Constant)
            and call.keywords[0].value.value == 16
        ):
            assert len(node.body) == 1 and not node.orelse
            exclude = "except" in ast.unparse(node.body[0])
            self.replacements += 1
            return ast.copy_location(
                ast.Expr(
                    value=ast.Call(
                        func=ast.Name(id="_probe_append_prefix16", ctx=ast.Load()),
                        args=[
                            ast.Name(id="ret_str", ctx=ast.Load()),
                            call.func.value,
                            ast.Constant(value=exclude),
                        ],
                        keywords=[],
                    )
                ),
                node,
            )
        return self.generic_visit(node)


class SubnetStrings(ast.NodeTransformer):
    def __init__(self):
        self.replacements = 0

    def visit_Call(self, node):
        self.generic_visit(node)
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "subnets"
            and len(node.keywords) == 1
            and node.keywords[0].arg == "new_prefix"
            and isinstance(node.keywords[0].value, ast.Constant)
            and node.keywords[0].value.value == 16
        ):
            self.replacements += 1
            return ast.copy_location(
                ast.Call(
                    func=ast.Name(id="_probe_prefix16_strings", ctx=ast.Load()),
                    args=[node.func.value],
                    keywords=[],
                ),
                node,
            )
        return node


def install(name):
    if name in ("prefix16", "prefix16-batch"):
        source = ast.parse(textwrap.dedent(inspect.getsource(MSMPC_STR)))
        transform = SubnetStrings() if name == "prefix16" else SubnetLines()
        source = transform.visit(source)
        assert transform.replacements == 4
        namespace = dict(MSMPC_STR.__globals__)
        namespace["_probe_prefix16_strings"] = prefix16_strings
        namespace["_probe_append_prefix16"] = append_prefix16
        exec(compile(ast.fix_missing_locations(source), __file__, "exec"), namespace)
        junipermsmpc.Term.__str__ = namespace[MSMPC_STR.__name__]
    elif name == "collapse-once":
        source = textwrap.dedent(inspect.getsource(SRX_BOOK))
        old = "addrs.extend(self._GenerateAddresses(group, ips, fqdns))"
        source = source.replace(old, "ips = nacaddr.CollapseAddrList(ips)\n                " + old)
        old = "target.extend(self._GenerateAddresses(group, ips, fqdns))"
        source = source.replace(old, "ips = nacaddr.CollapseAddrList(ips)\n                " + old)
        namespace = dict(SRX_BOOK.__globals__)
        exec(compile(source, __file__, "exec"), namespace)
        junipersrx.JuniperSRX._GenerateAddressBook = namespace[SRX_BOOK.__name__]
        source = textwrap.dedent(inspect.getsource(SRX_ADDR))
        source = source.replace("    ips = nacaddr.SortAddrList(ips)\n", "")
        source = source.replace("    ips = nacaddr.CollapseAddrList(ips)\n", "")
        exec(compile(source, __file__, "exec"), namespace)
        junipersrx.JuniperSRX._GenerateAddresses = namespace[SRX_ADDR.__name__]
        source = textwrap.dedent(inspect.getsource(SRX_SETS))
        source = source.replace("for _ in nacaddr.CollapseAddrList(ips):", "for _ in ips:")
        exec(compile(source, __file__, "exec"), namespace)
        junipersrx.JuniperSRX._GenerateAddressSets = namespace[SRX_SETS.__name__]
    else:
        raise ValueError(name)
