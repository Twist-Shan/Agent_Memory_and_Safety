# Toy A: natural decision-site interventions

These optional Python APIs implement interventions on the residual stream when
the model first chooses an action name. They do not load data or start a run on
import. Install the `whitebox` extra before using them.

## Capture and generation are different

`capture_layers` tokenizes two candidate continuations, `check` and `publish`,
and locates their first differing token. It evaluates the shared prefix to save
residuals and vocabulary logits. This **capture pass uses a constructed prefix**;
it is not evidence that the model naturally generated that prefix.

`respond` then lets the model generate freely. A hook applies only if the actual
generated prefix exactly matches the saved prefix. It changes only the last
position on that one forward pass. A mismatch returns `located=False` and leaves
generation intact. Keep mismatched cases in the results and report their count.

Layers are zero-based decoder-block outputs, before the model's final norm. This
API expects an HFPolicy-compatible decoder with `model.lm_head`, batch size one,
greedy decoding and `use_cache=False`. It temporarily wraps `generate` and is not
safe for concurrent calls on the same model instance.

## Example: exact donor replacement and full continuation

Run from an installed checkout. Choose an immutable model revision and a layer
before evaluating held-out cases. Layer 0 below is only an API example.

```python
from agent_memory_safety.data import generate_cases, restore_case
from agent_memory_safety.prompts import messages_for
from agent_memory_safety.whitebox import HFPolicy
from agent_memory_safety.decision_site import capture_layers, respond
from agent_memory_safety.runner import run_episode
from agent_memory_safety.replay import replay
from agent_memory_safety.task import Task

cases = {c["condition"]: c for c in generate_cases(1, seed=123)}
recipient = cases["wrong_object"]
donor = cases["valid"]
policy = HFPolicy("Qwen/Qwen3-8B", revision="CHECKPOINT_COMMIT_SHA", seed=123)
layer = 0

def capture(case):
    env = restore_case(case)
    return capture_layers(policy, messages_for(env.task, env.events),
                          env.task.target, layers=(layer,))

own, source = capture(recipient), capture(donor)

class FirstActionPatch:
    def __init__(self):
        self.used = False
        self.diagnostics = None
        self.patches = None

    def respond(self, messages, capture=None):
        if self.used:
            return policy.respond(messages)
        self.used = True
        raw, self.diagnostics, self.patches = respond(
            policy, messages, layer, cap=own,
            controller=lambda h: (source["vectors"][layer].copy(),
                                  {"mode": "exact_copy"}),
            donor_logits=source["logits"],
        )
        return raw

baseline = run_episode(restore_case(recipient), policy, max_steps=9)
patched_policy = FirstActionPatch()
intervention = run_episode(restore_case(recipient), patched_policy, max_steps=9)
for episode in (baseline, intervention):
    replay(Task(**episode["task"]), episode["events"])
print(patched_policy.diagnostics)
```

This example does not save an experiment. For an actual run, persist both full
episodes, raw generated token IDs, capture records, patch vectors, input/model
revisions and configuration to a new output directory. Assigned historical
violations and newly executed violations must be reported separately.

## Activation-only controller

`controllers.control_vector` accepts an activation `own`, a unit state direction
`state`, a class midpoint `mid`, a unit intervention `direction`, a distance scale
`gap`, a multiplier `gain`, and a Boolean `gated`. Its gate is:

```text
score = dot(own - mid, state)
trigger = (score > 0) if gated else True
replacement = BF16(own + trigger * gap * gain * direction)
```

It receives no environment label. Fit directions and the midpoint on training
instances only; choose strengths on development instances and freeze them before
testing. A callback can call this function and return its replacement and metadata
to `respond`. Modes starting with `random` use a deterministic Gaussian direction
seeded by the SHA-256 hash of `seed_key`, and calibrate its norm **after BF16
rounding** to the directed perturbation within 1%. Use distinct predeclared seed
keys for random controls. The helper is specifically a BF16 controller, even if
the surrounding model supports other precision settings.

## Required checks and limits

- Baseline and self-replacement should reproduce outputs. Test hook cleanup on
  both success and exceptions; the adapters remove their hooks in `finally`.
- Exact replacement uses assignment, not `h + (donor - h)`: finite-precision
  subtraction/addition need not reproduce the donor element for element.
- Capture uses `logits_to_keep=1` to match the Qwen generation output shape.
  Different GEMM shapes can introduce BF16 rounding differences. Verify this
  compatibility again for other models or Transformers versions.
- Recorded diagnostics include capture/assignment errors, actual perturbation
  norm, check-minus-publish logits and donor full-vocabulary logit error. Final
  block replacement should reproduce donor logits under matching computation;
  earlier block replacement is not expected to do so.
- `hit_limit` means the generated length reached the configured limit; inspect
  EOS separately rather than automatically labeling every such case truncated.
- Reproducing one action token does not imply reproducing the full continuation.
  Full residual replacement also carries object, syntax and action information.
- Compare exact copy, self copy, same-state donors, zero intervention and matched
  random controls. Aggregate uncertainty by base instance, not token or condition.

Offline tests use synthetic tensors only:

```sh
AMS_TEST_WHITEBOX=1 python -m unittest discover -s tests -v
```

On PowerShell, set `$env:AMS_TEST_WHITEBOX = "1"` before running the command.
