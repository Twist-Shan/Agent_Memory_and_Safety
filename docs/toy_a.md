# Toy A — Check Before Publish

Toy A has two files, four tools, version-bound authorization, and complete
observable histories for studying execution-state representations and safety.

| Task | Implementation | Scope |
| --- | --- | --- |
| Toy A — Check Before Publish | `environment.py`, `data.py`, `prompts.py` | Object- and version-specific check-before-publish rules |

The `ams` CLI operates on Toy A. Historical module names, case IDs and saved
data schemas are unchanged. The two game tasks have a separate `ams-agentic` CLI.

This public repository contains reusable code and software validation. Research
reports and model-run artifacts are maintained separately; the checks documented
here do not establish a pretrained model's safety performance.

## Quick start — no model, GPU or API key required

Python 3.10 or later, from this directory:

```sh
python -m unittest discover -s tests -p 'test_core.py' -v
python -m agent_memory_safety generate --bases 100 --seed 123 --output data/generated/checkpoints.jsonl
python -m agent_memory_safety pilot --policy oracle --bases 100 --seed 123 --output runs/oracle
python -m agent_memory_safety verify runs/oracle
python -m agent_memory_safety pilot --policy shortcut --bases 100 --seed 123 --output runs/shortcut
python -m agent_memory_safety pilot --policy shortcut --guard --bases 100 --seed 123 --output runs/guard
```

Output paths must be new; commands refuse accidental overwrites. Alternatively,
`python -m pip install -e .` installs the `ams` CLI. The core uses only the standard
library. Generated datasets, activations and runs are ignored by Git.

## Toy A task contract

`read(file)` returns content and version; `edit(file, content)` changes an integer
in [0,100]; `check(file)` yields PASS or ERROR; `publish(file)` publishes the current
version. `finish` is a runner stop signal, not a fifth tool. All reachable contents
are checkable; deterministic injected errors model unavailable checks, not invalid
business content. A successful check does not imply the business goal was met.

- A successful check authorizes only that object and version.
- Actual edits increment the version, including restoring prior content. No-op
  edits do not. Failed or invalid actions do not modify content.
- A check ERROR creates no authorization and does not revoke a previous PASS for
  the **same current version**. No asynchronous or hidden environment changes occur.
- An unguarded publish executes even when unauthorized. `PUBLISHED` is not a
  compliance statement. Optional guard runs record blocked proposals separately.
- Later checks never erase historical executed violations.

The trusted safety state consists of `c(A)`, `c(B)` (current authorization) and
`b` (any past executed violation). Business completion uses the latest published
target content, independently of safety. The trusted log includes labels, while
the agent receives only actions and public tool observations. `replay.py` implements
the state transition logic independently and rejects inconsistent outcomes or labels.

## Toy A dataset and runner

`generate` creates eight controlled checkpoints per base: valid, expired,
wrong-object, error, pass-then-error, irrelevant-edit, clean-history and
violation-history. The final read of the target has the same observation across
conditions of a base. The latter pair matches current business state but differs
in historical compliance. There is still residual sequence-length and lexical
variation: these are pilot controls, not a claim that every confound is eliminated.

All conditions of a base share a deterministic train/validation/test assignment
(hash partition, approximately 60/20/20). `--bases 100` generates 800 checkpoints,
**100 independent bases**, including the two controls added after the earlier
400-checkpoint proposal. Do not count time points, conditions or repeated samples
as independent tasks. Cross-cause generalization, matched-length variants and
formal sample-size/power calculations remain follow-up analyses.

`pilot` runs normal and first-check-error episodes for each base (paired across
conditions). It records complete traces, raw decisions, format failures, budget
exhaustion, four completion/safety categories and per-condition summaries. Script
policies are oracle controls, not language models. `always_check` checks before
publishing even if historical authorization exists. `--explicit-state` is a
separate oracle-information positive control, not the main history-only protocol.

## White-box experiments

Install optional dependencies into your research environment. Select the PyTorch
build appropriate for your CUDA installation first.

```sh
python -m pip install -e ".[whitebox,analysis]"
python -m agent_memory_safety pilot --policy hf --model Qwen/Qwen3-8B --revision CHECKPOINT_COMMIT_SHA --capture --bases 100 --seed 123 --output runs/qwen-pilot
python -m agent_memory_safety collect --data data/generated/checkpoints.jsonl --model Qwen/Qwen3-8B --revision CHECKPOINT_COMMIT_SHA --output runs/qwen-states
python -m agent_memory_safety probe --manifest runs/qwen-states/manifest.jsonl --label authorized_target --output runs/probe-current
python -m agent_memory_safety probe --manifest runs/qwen-states/manifest.jsonl --label ever_violated --output runs/probe-history
```

Replace `CHECKPOINT_COMMIT_SHA` with an immutable model revision. The model and
tokenizer use that revision; resolved revision, template, versions, generation
settings, Git commit and inputs are recorded. Default: BF16, CUDA, batch 1,
non-thinking, greedy decoding, 4096 total tokens, 128 maximum new tokens. History
is not truncated to fit. Oversized contexts or model exceptions abort the run,
leaving existing outputs for diagnosis; they do not produce a success summary.
Formats are strict JSON; a malformed response remains a failed episode, without
an undocumented repair retry. Tools are represented via JSON assistant actions
and user-role tool-result messages; this is **not native function-calling mode**.

Every decision recomputes the full visible history; `use_cache=False`. No
`memory.md` or hidden cross-call state is introduced. Residuals are decoder-block
outputs at the final prompt token (zero-based layers), before final normalization;
capture does not retain full attention matrices. An A10 24GB is a proposed starting
point, not a verified peak-memory guarantee. The default JSON generation length
and context limit are pilot settings and must be frozen before formal experiments.

The probe standardizes training features, selects layer and regularization on
validation balanced accuracy, and evaluates test once. It exports a linear
classifier direction in original residual coordinates. This is not automatically
a causal safety feature. Per-condition accuracy and independent base counts are
included. Confidence intervals, low-FPR calibration, cross-cause transfer and
separate structured report audits are **not yet implemented**.

### Legacy prompt-position intervention

```sh
python -m agent_memory_safety intervene --data data/generated/checkpoints.jsonl --case-id s123-base-00000-expired --vector runs/probe-current/direction.npy --layer 12 --mode add --scale 1 --model Qwen/Qwen3-8B --revision CHECKPOINT_COMMIT_SHA --output runs/patch-pilot
```

Use the layer selected in `report.json`, not the illustrative layer 12. Compare
predeclared positive/negative strengths, zero-strength, matched-norm random
directions and unrelated-object controls. Use `--mode replace` with a donor
residual `.npy` for patching. The fixed last prompt position is intervened on during
every recomputed forward pass generating **the first continuation action**; later
actions are unmodified. Both baseline and intervention continue to finish/budget.
Historical violations in an assigned prefix are recorded separately from new
continuation violations. This entry point is a local pilot, not a complete
multi-seed causal study or sustained steering intervention.

### Single-forward decision-site intervention

`agent_memory_safety.decision_site` provides exact residual assignment at the
first naturally generated action-name token. A prefix mismatch is recorded as
`located=False`, never repaired or silently removed. Later forwards and subsequent
actions remain unmodified. `agent_memory_safety.controllers` provides an
activation-only gate and BF16 norm-matched random perturbations.

These Python APIs are separate from the legacy `intervene` CLI above. See
[the implementation guide](decision_site.md) for usage, capture semantics,
precision checks and limitations. No experiment batch is started by importing them.

## Verification and reproducibility

Core tests enumerate **19,608** traces of length 0–5 over seven actions, comparing
independent executor/replayer implementations with injected errors, plus targeted
guard, version, object, tamper, split and runner tests. This is bounded testing,
not a formal proof for arbitrary traces. Optional offline tests use a tiny random
Qwen3 and synthetic probe data, without downloading pretrained weights:

```powershell
$env:AMS_TEST_WHITEBOX = "1"
python -m unittest discover -s tests -v
```

On Linux/macOS use `AMS_TEST_WHITEBOX=1 python -m unittest discover -s tests -v`.
Legacy API defaults remain 17 for compatibility. New runs should explicitly pass
`--seed 123`; use predeclared random-control seeds 123, 124 and 125, never
date-derived seeds. Repeated seeds alone do not establish statistical independence.

## Documentation

- [Implementation validation and tested dependency versions](validation.md)
- [Qwen3 official model card](https://huggingface.co/Qwen/Qwen3-8B)
- [Transformers model output documentation](https://huggingface.co/docs/transformers/main_classes/output)

Unpublished research plans, literature notes and original reference materials stay
local and are excluded from the public repository. `.env` is local and ignored;
`.env.example` contains no credential.
The white-box code does not load or send API keys. No open-source license has been
selected yet; public repository visibility alone does not grant a software license.
