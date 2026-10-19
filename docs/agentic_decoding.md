# Decoding policies for the three Muse batches

This document records the decoding conditions of the six-disk Hanoi,
seven-disk Hanoi and 15Puzzle research batches. These are three experimental
batches within two agentic tasks; Toy A is a separate task. The public CLI
remains a single-episode greedy runner, not a reproduction command for the
separately frozen sampling batches.

| Batch | Evaluation units | Decoding | Temperature | top_p | top_k | Seed plan | FS prompt |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Six-disk Hanoi | 20 trajectories from one fixed initial board | Sampling (`do_sample=True`) | 0.7 | 0.9 | 0 (disabled) | 123–142, once after each environment reset | `no-memory-claims` |
| Seven-disk Hanoi | 20 trajectories from one fixed initial board | Sampling (`do_sample=True`) | 0.7 | 0.9 | 0 (disabled) | 123–142, once after each environment reset | `original` |
| 15Puzzle | 20 distinct initial boards, original 8 plus additional 12 | Greedy (`do_sample=False`, one beam) | Not applied | Not applied | Not applied | Generation seed 123; board seeds from master seed 123 | `original` |

Greedy is sometimes informally called “temperature zero,” but that is not a
literal sampling configuration here: it selects the highest-scoring next token
without applying temperature sampling. The 15Puzzle boards use indices 8–27
of the original environment-seed sequence, each constructed with 30 legal
shuffle moves. Shuffle length is not shortest solution distance. The two Hanoi
batches use environment seed 224899942; within each batch the initial board is
fixed. No seed was chosen from a date.

## Why these settings were used

15Puzzle retains the original greedy policy when extending from 8 to 20 boards.
This preserves decoding conditions across the extension and measures behavior
across different boards. The additional 12 boards were authorized after the
first 8 results were observed, so the extension is exploratory and should be
reported as such.

Hanoi repeats the same initial board. Sampling was explicitly selected to obtain
different trajectories; changing only the seed under greedy decoding would not
provide a useful sampling distribution. Temperature 0.7 was a fixed moderate
sampling choice, not an empirically optimized value or a guarantee of better
accuracy or compliance. Temperature rescales next-token logits before sampling;
smaller positive values concentrate probability on higher-scoring candidates.
Nucleus sampling at top_p 0.9 restricts the candidate set by cumulative
probability. top_k 0 disables an additional fixed-size candidate cutoff.
Six-disk Hanoi retains the seven-disk decoding policy.

## Shared conditions and comparison limits

All three batches use Muse revision
`a4e59da52a7bc87ae7251dd5545c0dd437c44b68`, BF16, SDPA, KV cache,
`reasoning_strength=low`, and the fixed ATEM template date `2026-10-15`.
The total context budget is 65,536 tokens, with all remaining space available
for each response and no fixed per-response output cap. Histories are not
trimmed. There is a 220-response limit in addition to the original game limits.
No activation tensors were collected. Saved text, token IDs and tool traces
are not activation recordings.

- Hanoi's 20 trajectories are repeated samples of one puzzle, not 20 independent
  puzzle instances. 15Puzzle instead uses 20 distinct boards with greedy decoding.
- Six-disk Hanoi removes the sentence claiming that scratchpad and past-game
  resources already exist; seven-disk Hanoi and 15Puzzle retain it. Both prompt
  variants retain filesystem tools and allow self-created notes. They do not
  provide code execution or persistent cross-episode memory.
- Six-versus-seven comparisons change both disk count and the prompt condition.
  Cross-game comparisons also change decoding and the unit being sampled.
  Success-rate differences cannot be attributed solely to task difficulty,
  temperature, or the resource statement.
- Retain every planned trajectory, including failures. Report goal completion,
  actual rule violations, fully legal wins and multiple-move actions separately.
  Winning after a violation does not establish that the violation was necessary.

Frozen experiment code and evidence remain separate from the public baseline.
This documentation changes no running or saved experiment and adds no sampling
flags to the public CLI. See [runner details](agentic_runner.md) for audit scope
and [prompt variants](agentic_runner.md#filesystem-prompt-variants).
