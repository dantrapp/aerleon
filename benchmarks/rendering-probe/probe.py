"""Measure Aerleon's complete sample-policy rendering and address-book costs."""

import argparse
import cProfile
import hashlib
import json
import logging
import multiprocessing
import os
import platform
import pstats
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from absl import logging as absl_logging

from aerleon import aclgen
from aerleon.lib import addressbook

ROOT = Path(os.environ.get("AERLEON_REPO", Path(__file__).resolve().parents[2]))
OUT = Path(__file__).resolve().parent
ORIGINAL = addressbook.Addressbook.AddAddresses
WORKLOADS = {
    "all": None,
    "large": "sample_stateful_multitarget_complex.pol",
    "small": "sample_srx.pol",
    "msmpc": "sample_msmpc.pol",
}


def render(workload, optimize):
    with tempfile.TemporaryDirectory(prefix="aerleon-render-") as directory:
        policy = WORKLOADS[workload]
        start = time.perf_counter()
        aclgen.Run(
            str(ROOT / "policies"),
            str(ROOT / "def"),
            str(ROOT / "policies/pol" / policy) if policy else None,
            directory,
            2,
            1,
            ["DEPRECATED", "def"],
            optimize,
            False,
            multiprocessing.get_context(),
        )
        elapsed = time.perf_counter() - start
        files = {}
        for path in sorted(Path(directory).rglob("*")):
            if path.is_file():
                files[str(path.relative_to(directory))] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        if not files:
            raise RuntimeError("render produced no files")
        return {"seconds": elapsed, "files": files}


def render_cli(workload, optimize, backend):
    with tempfile.TemporaryDirectory(prefix="aerleon-cli-") as directory:
        command = [
            sys.executable,
            str(OUT / "cli.py"),
            "--backend",
            backend,
            "--max_renderers=1",
            "--base_directory=" + str(ROOT / "policies"),
            "--definitions_directory=" + str(ROOT / "def"),
            "--output_directory=" + directory,
        ]
        if WORKLOADS[workload]:
            command.append("--policy_file=" + str(ROOT / "policies/pol" / WORKLOADS[workload]))
        if optimize:
            command.append("--optimize")
        start = time.perf_counter()
        subprocess.run(
            command, cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        elapsed = time.perf_counter() - start
        files = {
            str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path(directory).rglob("*"))
            if path.is_file()
        }
        if not files:
            raise RuntimeError("CLI produced no files")
        return {"seconds": elapsed, "files": files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--workloads", nargs="+", choices=WORKLOADS, default=list(WORKLOADS))
    parser.add_argument("--optimize", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--cli", action="store_true")
    parser.add_argument("--backends", nargs="+", default=["baseline"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    absl_logging.set_verbosity(absl_logging.ERROR)
    logging.disable(logging.WARNING)
    records = []
    result = {
        "revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "python": sys.version,
        "platform": platform.platform(),
        "hash_seed": os.environ.get("PYTHONHASHSEED"),
        "workers": 1,
        "optimize": args.optimize,
        "profiled": args.profile,
        "cli": args.cli,
        "runs": records,
        "input_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in [ROOT / "def", ROOT / "policies"]
            for path in sorted(folder.rglob("*"))
            if path.is_file()
        },
    }
    traces = []

    def traced(self, zone, addresses):
        before = {key: len(value) for key, value in self._ip_addressbook.get(zone, {}).items()}
        started = time.perf_counter()
        ORIGINAL(self, zone, addresses)
        traces.append(
            {
                "incoming": len(addresses),
                "existing": sum(before.values()),
                "groups": len({a.parent_token for a in addresses}),
                "seconds": time.perf_counter() - started,
            }
        )

    for workload in args.workloads:
        expected = None
        for round_number in range(-1, args.rounds):
            offset = max(round_number, 0) % len(args.backends)
            order = args.backends[offset:] + args.backends[:offset]
            for backend in order:
                addressbook.Addressbook.AddAddresses = ORIGINAL
                import candidates

                candidates.install(backend)
                if args.trace:
                    addressbook.Addressbook.AddAddresses = traced
                profiler = cProfile.Profile() if args.profile else None
                if profiler:
                    profiler.enable()
                measured = (
                    render_cli(workload, args.optimize, backend)
                    if args.cli
                    else render(workload, args.optimize)
                )
                if profiler:
                    profiler.disable()
                    if round_number >= 0:
                        profile_path = args.output.with_suffix(f".{workload}.{backend}.prof")
                        profiler.dump_stats(str(profile_path))
                        with profile_path.with_suffix(".txt").open("w") as stream:
                            pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats(
                                "cumulative"
                            ).print_stats(45)
                if expected is None:
                    expected = measured["files"]
                elif measured["files"] != expected:
                    raise RuntimeError(f"output differs for {workload}/{backend}")
                measured.update(workload=workload, backend=backend, round=round_number)
                records.append(measured)
                print(
                    json.dumps({k: len(v) if k == "files" else v for k, v in measured.items()}),
                    flush=True,
                )
                result["trace"] = traces
                args.output.write_text(json.dumps(result, indent=2) + "\n")
    result["medians"] = {
        workload: {
            backend: statistics.median(
                r["seconds"]
                for r in records
                if r["workload"] == workload and r["backend"] == backend and r["round"] >= 0
            )
            for backend in args.backends
        }
        for workload in args.workloads
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
