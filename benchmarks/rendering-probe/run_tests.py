"""Run repository tests with the same backend in parent and spawned workers."""

import os

import candidates

candidates.install(os.environ.get("AERLEON_PROBE_BACKEND", "baseline"))


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main(["-q"]))
