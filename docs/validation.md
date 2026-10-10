# Implementation validation

Validated locally on 2026-10-08. These are software checks and scripted controls,
not pretrained-model safety experiments.

## Environment

- Python 3.12.7 on Windows.
- PyTorch 2.5.1+cu121, Transformers 4.57.6.
- NumPy 1.26.4, scikit-learn 1.8.0, SciPy 1.13.1.
- Project-local `.venv` reused installed packages; NumPy was installed locally to
  avoid an incompatible NumPy 2 / older scientific-library combination. Global
  packages were not replaced. A clean virtual environment is recommended elsewhere.

## Completed checks

- All **17 tests passed**, including both optional offline integration tests.
- Exhaustive bounded comparison of **19,608** length-0-to-5 tool traces with
  independent executor and replay implementations.
- Targeted version rollback, no-op edit, object binding, failure preservation,
  blocked proposal versus executed violation, log-tampering and grouped data tests.
- Tiny randomly initialized Qwen3: residual shape, zero-strength patch identity,
  replacement-patch execution, hook removal and context-budget rejection.
- Synthetic held-out probe training and deliberate cross-split leakage rejection.
- Editable package installation and installed `ams --help` entry point.
- 100 base instances, seed 17: **800 controlled checkpoints** generated.
- Three scripted runs of 200 episodes each, all independently replayed:

| Script control | Safe completion | Executed violation | Interpretation |
| --- | ---: | ---: | --- |
| Oracle | 200/200 | 0/200 | Uses trusted state to check/retry before publishing |
| Shortcut | 0/200 | 200/200 | Publishes target content without checking |
| Shortcut with guard | 0/200 | 0/200 | All 200 episodes exhaust budget; blocked proposals persist |

Each run pairs normal and first-check-error conditions over 100 bases. The guard
result demonstrates why zero executed violations does not establish successful
agent behavior. Raw outputs remain in ignored local `runs/`; they are reproducible
using the README commands. Dates are record metadata, not random seeds.

## Scope of the original validation record

The original software-validation run did not measure pretrained Qwen3-8B
behavior, A10 peak memory, learned safety representations or causal improvement.
Separate research runs and their results are outside this public validation record. Native function calling,
report-audit experiments, low-FPR calibration and group-bootstrap confidence
intervals remain follow-up work. CI runs core tests; the optional integrations
above were run locally with installed research dependencies.


## Toy A repository update

The public task name is **Toy A — Check Before Publish**. Existing case IDs,
environment transitions and archived experiment files are unchanged.

The decision-site and controller modules are extracted from the local experiment
adapters, with formatting and argument checks for public use. Software checks cover
exact donor assignment and full-logit identity in a synthetic decoder,
self-replacement identity, one-forward/one-position locality, retained prefix
mismatches, cleanup after controller exceptions, activation-only gating and random
perturbation norms after BF16 rounding. These synthetic checks do not establish a
learned authorization mechanism or safety improvement.

Validated on 2026-10-10 with the environment listed above: **19/19 tests passed**
with `AMS_TEST_WHITEBOX=1`, including the two new adapter/controller tests and
both existing offline integrations. No pretrained weights were downloaded and no
GPU experiment was launched. The environment emitted optional pandas accelerator
version warnings for numexpr/bottleneck; they did not fail these checks.
