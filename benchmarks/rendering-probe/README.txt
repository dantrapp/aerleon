Aerleon rendering benchmark, 2026-10-14

Baseline: aerleon/aerleon d916a17052c7b3191019567c07ad9a0a40940b21
Environment: macOS 15.6.1, Apple M4, 10 CPU cores, 16 GiB RAM, Python 3.14.4.
Native prototype: Rust 1.94.1, PyO3 0.29.2, Maturin 1.15.0, release build.

Measured changes

* direct: group addresses by token; sort and compare integer network bounds.
  Retain the original Python address objects, stable duplicate ownership, and
  the existing implementation for scoped addresses and subclasses.
* rust: perform stable merge and containment filtering in Rust, returning
  indices into the original Python objects. Python conversion and dispatch
  costs are included in measurements.
* prefix16: generate IPv6 /16 text directly when the MS-MPC renderer expands
  a prefix between /1 and /15. Preserve the existing fallback for subclasses
  and scoped addresses.
* prefix16-batch: also append those subnet lines with one shared indentation
  value. The generated lines have no braces or comments that change indentation.
* collapse-once: reuse one collapsed SRX address list for address definitions
  and address-set members, instead of sorting and collapsing it repeatedly.

Primary results

Six measured fresh CLI processes per backend/workload, plus one discarded
warmup. Run order rotates each round. One renderer worker, PYTHONHASHSEED=0,
default --optimize setting (disabled). Timings include Python startup, imports,
experimental backend installation, definition and policy loading, parsing,
rendering, output writes, and subprocess completion. Input files are warm in
the operating-system cache. Output hashing is outside the timed region.

Median seconds                 Upstream    Python stack    Rust stack
All samples, 51 output files     1.764578       0.698392      0.656389
Large SRX/Palo Alto sample       0.589651       0.493790      0.440597
Small SRX sample                 0.144375       0.149915      0.148394
MS-MPC sample                    0.810075       0.199632      0.201329

Python stack = direct+prefix16-batch+collapse-once.
Rust stack = rust+prefix16-batch+collapse-once.

The combined sample workload is 2.53x faster in Python and 2.69x faster with
Rust. Rust reduces the Python stack's time by another 6.0% overall and 10.8%
on the large stateful sample. Small policies show no demonstrated benefit;
the primary comparison has a 4-6 ms increase. Dynamic source transformation
at startup is included, so these are prototype timings, not timings of a
production patch installed from a wheel.

The aggregate benefit is dominated by broad IPv6 expansion in two MS-MPC
outputs. It does not imply every Aerleon platform or production workload is
2.5x faster. These are the repository's sample policies, not customer traces.
The standalone MS-MPC sample is 4.06x faster with the Python stack.

comparison-final-cli.json retains all six timings, warmups, input hashes,
and SHA-256 hashes of every generated output for every run. All output
comparisons matched. comparison-collapse-cli.json isolates reuse of the SRX
collapse result: 2.8% less time across all samples and 2.2% on the large
stateful sample in that separate six-round comparison. Individual timings
overlap, so this is a modest secondary gain. comparison-optimized-cli.json checks --optimize with three
measured rounds; output comparisons also match, but timings have more noise.
Profiles are separate instrumented runs and are not used for speedup claims.

Correctness

* Unchanged upstream: 2,187 existing tests passed.
* Python stack: 2,187 existing tests passed.
* Rust stack: 2,187 existing tests passed.
* Address selection: 500 seeded cases, 6,000 batches, 100,791 input networks.
  Compare selected object identity, ordering, zones, tokens, and FQDN retention
  against the original implementation after every batch. Include duplicate,
  containment, mixed-family, scoped-address, and subclass boundary cases.
* IPv6 text: all 65,536 distinct /16 strings, 45 prefix ranges, subclass and
  scoped-address fallbacks, and batched indentation/exclusion output.
* Renderer: 32 comparisons with the original method, covering source and
  destination inclusions/exclusions, comments, mixed families, apply-groups,
  and noverbose settings.

The full suite was run outside the filesystem sandbox because three existing
multiprocessing tests need local IPC sockets. run_tests.py installs the selected
backend in both the parent and spawned workers. Other Python versions and
free-threaded builds have not been tested. The upstream application source is unchanged.

Reproduction

Use an Aerleon checkout at the baseline revision. From this directory:

    export AERLEON_REPO=/absolute/path/to/aerleon
    python3.14 -m venv .venv
    source .venv/bin/activate
    python -m pip install -e "$AERLEON_REPO" pytest==9.1.1 psutil==7.2.2 pyperf==2.10.0 maturin==1.15.0
    python -m pip install ./native
    python validate.py
    python validate_chained.py
    PYTHONHASHSEED=0 python probe.py --rounds 6 --cli --workloads all large small msmpc --backends baseline direct direct+collapse-once baseline+prefix16 direct+prefix16+collapse-once direct+prefix16-batch+collapse-once rust+prefix16-batch+collapse-once --output repeated.json

To run the full suite, set AERLEON_PROBE_BACKEND to baseline,
direct+prefix16-batch+collapse-once, or rust+prefix16-batch+collapse-once;
then run this directory's run_tests.py from the Aerleon repository root.

Native installation is needed only for Rust comparisons and validate.py.
Python-only benchmark commands can omit the native installation and Rust
backend. Do not run tests or other benchmarks concurrently with timed runs.
