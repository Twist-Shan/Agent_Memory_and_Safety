# Local API smoke test

The minimal API transport uses the same `LogicBridge`, system instruction,
`play(action)` tool, tool results and multi-turn runner as the native Muse harness.
It adds OpenRouter HTTP transport and matching `tool_call_id` values. There is no
planner, code executor, response repair, automatic retry, or model fallback.

Install the `agentic` extra, place `OPENROUTER_API_KEY=...` in the ignored
`.env.local`, then run with a **new** output directory:

```powershell
python -m agent_memory_safety.agentic.openrouter --out runs/openrouter_hanoi6_smoke_v1
```

This entry point runs one six-disk Hanoi episode with environment seed 224899942,
the `no-memory-claims` prompt, and the unchanged filesystem tools. The initial
scratchpad/past-games resource claims are removed; self-created notes remain
allowed. The limit is 220 model responses and the original environment's 126
configured game turns (127 at its boundary).

API settings: `meta/muse-glimmer-30b`, temperature 0.7, top_p 0.9, top_k 0,
reasoning effort low, seed 123 **on each request**, max_tokens 16384, no context
compression transform. The model catalog advertises 131072 context tokens.
Provider parameter support is required; provider fallback within a request is
disabled. Routing across requests is not pinned, and each returned provider is
recorded. Errors terminate the run and are retained rather than retried.

This is a separate integration trial, not a replication of the native study:
the API does not establish an identical weight revision, ATEM template/date, RNG
stream, or the native 65536-token remaining-budget policy. Context overflow is an
error, not permission to trim history. Native EOS/token IDs are not exposed;
the transport uses the API finish reason and does not execute truncated calls.
Reasoning fields returned by the provider are preserved in the conversation.

Intermediate state uses uniquely named snapshots, avoiding replacement of files
that Windows readers may hold open. Following an interrupted local save, an
explicit `--resume-from OLD_DIRECTORY` with a new `--out` replays saved API
responses and requires exact equality of every reconstructed request before
continuing. It does not regenerate those responses. Original failures remain
preserved; this is not an automatic retry policy.

The output contains a frozen source copy, manifest, every request and raw API
response, incremental/full episode, independent action/virtual-filesystem replay,
and provider-reported usage/cost. No activations are collected. The replay does
not re-tokenize or certify provider internals. Output and credentials stay outside
Git. A completed episode or passed replay does not imply a legal win; inspect
`exact_win`, `win_without_illegal`, and illegal-transition metrics separately.
