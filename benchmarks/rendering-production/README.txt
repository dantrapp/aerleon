Aerleon address-book and Juniper rendering benchmark

Baseline:  d916a17052c7b3191019567c07ad9a0a40940b21 (aerleon/aerleon main)
Candidate: 6530c7375e2dcebafd20d897c559a4c3c920a7a8 (dantrapp/aerleon perf/address-rendering)
Measured:  2026-10-14, Apple M4, 10 logical CPUs, 16 GiB, macOS 15.6.1 arm64,
           CPython 3.14.4, one renderer worker, PYTHONHASHSEED=0.

The candidate groups addresses before sorting, uses integer network keys and
bounds for ordinary IPv4/IPv6 objects, inserts single arrivals with bisect, and
retains the original comparison path for subclasses and scoped addresses.
Juniper MSMPC writes broad IPv6 networks as /16 strings directly. Juniper SRX
shares one collapsed list between address definitions and address-set members.

Complete CLI results

Each measurement starts a new `python -m aerleon.aclgen` process and includes
imports, definition loading, parsing, rendering, and output-file writes. Output
hashing runs after the timer. These runs execute the actual source checkouts,
without replacing methods at runtime. Inputs are the repository's sample
policies and definitions at the baseline revision.

One warmup pair is discarded, followed by six alternating baseline/candidate
pairs per workload. The filesystem cache is warm; it is not flushed. Medians
are reported below. Raw runs, source/input hashes, and every output-file hash
are in comparison-default.json and comparison-optimized.json.

Default rendering                 Baseline    Candidate   Reduction
All samples (39 policies, 51 files) 1.7351 s    0.6843 s      60.6%
Large stateful sample (2 files)     0.6028 s    0.4941 s      18.0%
Small SRX sample (1 file)           0.1385 s    0.1371 s       1.0%
MSMPC sample (1 file)               0.8024 s    0.1781 s      77.8%

With --optimize                   Baseline    Candidate   Reduction
All samples                        1.6592 s    0.6277 s      62.2%
Large stateful sample              0.5009 s    0.4204 s      16.1%
Small SRX sample                   0.1411 s    0.1403 s       0.6%
MSMPC sample                       0.8062 s    0.1828 s      77.3%

All output hashes match within every workload and rendering mode. The small
SRX sample shows no meaningful improvement. Broad IPv6 expansion in the MSMPC
samples accounts for most of the aggregate gain; these are sample-workload
results, not a general production speedup. The optimized runs include outliers
(for example, one baseline MSMPC run took 2.008 s); retain the raw distributions
when comparing machines. No competing test/build jobs ran during timing.

Workloads:
- all: all policies under policies/
- large: policies/pol/sample_stateful_multitarget_complex.pol
- small: policies/pol/sample_srx.pol
- msmpc: policies/pol/sample_msmpc.pol

Correctness and compatibility

- Full suite: 2,207 tests and 18 subtests pass on CPython 3.10.22, 3.14.4, 3.15.0.
- Address-book differential check: 6,000 seeded batches, 100,791 incoming
  networks, plus explicit boundary, subclass, scope, and metadata cases.
  Checks selected object identities, ordering, zones, tokens, and retained
  FQDNs after every batch against the baseline implementation.
- Committed tests compare expanded IPv6 output with Python's ipaddress module
  across every distinct /16, inclusion/exclusion clauses, indentation,
  comments, apply-groups, and noverbose settings. SRX tests cover adjacent
  subnet collapse, mixed families, FQDN numbering, and repeated rendering.
- Black, isort, pyupgrade, and source/wheel builds pass. Focused Pyright checks
  retain pre-existing errors (20 baseline, 15 candidate); no new diagnostics.
- Other operating systems, intermediate Python versions, free-threaded Python,
  and hosted CI were not verified. See checks.json and the test/build logs.

shape-comparison.json measures ten address insertion shapes with 10,000
existing networks (or an empty book for initial insertion). Construction,
seed insertion, and identity assertions are outside the timer. Both methods
reuse objects with cached network bounds after one discarded warmup. Six
alternating pairs are recorded. These are isolated AddAddresses timings,
separate from the complete CLI results. All ten medians improve; their output
object identities also match the baseline.

Reproduction

From a directory containing an Aerleon clone named `aerleon`:

  git -C aerleon remote add benchmark https://github.com/dantrapp/aerleon.git
  git -C aerleon fetch benchmark perf/address-rendering bench/rendering-pipeline
  git -C aerleon worktree add ../aerleon-base d916a17052c7b3191019567c07ad9a0a40940b21
  git -C aerleon worktree add ../aerleon-candidate 6530c7375e2dcebafd20d897c559a4c3c920a7a8
  git -C aerleon worktree add ../aerleon-bench benchmark/bench/rendering-pipeline
  python3.14 -m venv .venv-aerleon
  . .venv-aerleon/bin/activate
  python -m pip install -e ./aerleon-candidate 'PyYAML==6.0.3' 'absl-py==2.5.1' 'typing_extensions==4.16.0'
  python -m pip install 'pytest==9.1.1' 'psutil==7.2.2' 'pyperf==2.10.0'
  export PYTHONPATH="$PWD/aerleon-candidate"

Run the CLI comparisons (repeat with --optimize and a different output name):

  python aerleon-bench/benchmarks/rendering-production/compare.py \
    --baseline aerleon-base --candidate aerleon-candidate \
    --base-revision d916a17052c7b3191019567c07ad9a0a40940b21 \
    --candidate-revision 6530c7375e2dcebafd20d897c559a4c3c920a7a8 \
    --rounds 6 --output comparison-default.json

Run the differential and insertion checks:

  python aerleon-bench/benchmarks/rendering-production/validate.py \
    --baseline aerleon-base --candidate aerleon-candidate
  python aerleon-bench/benchmarks/rendering-production/shape_compare.py \
    --baseline aerleon-base --candidate aerleon-candidate \
    --rounds 6 --output shape-comparison.json

Run the test suite from the candidate checkout:

  cd aerleon-candidate
  python -m pytest -q

The source change adds no runtime dependency. Environment versions are recorded
in environment.json; production source hashes are retained with the results.
