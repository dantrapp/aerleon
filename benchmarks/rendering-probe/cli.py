"""Start the real Aerleon CLI with one experimental backend installed."""

import sys

import candidates

from aerleon import aclgen

if __name__ == "__main__":
    if sys.argv[1] != "--backend":
        raise ValueError("expected --backend")
    backend = sys.argv[2]
    del sys.argv[1:3]
    if backend != "baseline":
        candidates.install(backend)
    aclgen.EntryPoint()
