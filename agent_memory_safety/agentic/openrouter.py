"""Minimal OpenRouter transport; no retries, prompt repair, or model fallback."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import shutil
import time
import urllib.error
import urllib.request

from .runner import MAX_RESPONSES, run_episode, save, utc

MODEL = "meta/muse-glimmer-30b"
URL = "https://openrouter.ai/api/v1/chat/completions"


def parse_response(raw):
    choice = raw["choices"][0]
    message = choice["message"]
    # Retain reasoning details verbatim for providers requiring round-trip state.
    assistant = {k: copy.deepcopy(v) for k, v in message.items()
                 if k in {"role", "content", "tool_calls", "reasoning", "reasoning_details"}
                 and v is not None}
    calls = copy.deepcopy(message.get("tool_calls") or [])
    invalid = assistant.get("role") != "assistant"
    ids = set()
    for call in calls:
        call_id = call.get("id")
        if not isinstance(call_id, str) or not call_id or call_id in ids:
            invalid = True
        ids.add(call_id)
        try:
            call["function"]["arguments"] = json.loads(call["function"]["arguments"])
        except (ValueError, TypeError, KeyError):
            invalid = True
    finish = choice.get("finish_reason")
    return dict(assistant_message=assistant, tool_calls=calls,
                truncated=finish == "length", format_error=invalid,
                eos=finish in ("stop", "tool_calls"), finish_reason=finish,
                raw_api_response=raw)


class OpenRouterAdapter:
    def __init__(self, key, out, resume_from=None):
        self.key, self.out, self.index = key, Path(out), 0
        self.resume_from = resume_from
        self.replay_count = 0
        if resume_from:
            while (resume_from / f"response_{self.replay_count:03d}.json").exists():
                self.replay_count += 1

    @staticmethod
    def make_tool_message(call, result):
        return dict(role="tool", tool_call_id=call["id"],
                    content=json.dumps(result, ensure_ascii=False, separators=(",", ":")))

    def build_payload(self, messages, tools):
        return dict(model=MODEL, messages=messages, tools=tools,
                       temperature=0.7, top_p=0.9, top_k=0, seed=123,
                       reasoning={"effort": "low", "exclude": False},
                       max_tokens=16384, stream=False, transforms=[],
                       provider={"require_parameters": True, "allow_fallbacks": False})

    def generate(self, messages, tools):
        payload = self.build_payload(messages, tools)
        if payload is None:
            return dict(assistant_message=None, tool_calls=[], truncated=False,
                        format_error=False, eos=False, finish_reason='local_context_guard')
        index = self.index
        self.index += 1
        save(self.out / f"request_{index:03d}.json", payload)
        if index < self.replay_count:
            old_request = json.loads((self.resume_from / f"request_{index:03d}.json").read_text(encoding="utf-8"))
            if old_request != payload:
                raise ValueError("Saved request/history mismatch; refusing continuation")
            body = (self.resume_from / f"response_{index:03d}.json").read_bytes()
            (self.out / f"response_{index:03d}.json").write_bytes(body)
            parsed = parse_response(json.loads(body))
            parsed["replayed_saved_response"] = True
            return parsed
        request = urllib.request.Request(URL, json.dumps(payload).encode(),
                    headers={"Authorization": "Bearer " + self.key,
                             "Content-Type": "application/json"})
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            body = error.read()
            (self.out / f"response_{index:03d}.json").write_bytes(body)
            raise RuntimeError(f"HTTP {error.code}; response saved; no retry") from None
        (self.out / f"response_{index:03d}.json").write_bytes(body)
        raw = json.loads(body)
        if "error" in raw:
            raise RuntimeError("API error; response saved; no retry")
        parsed = parse_response(raw)
        parsed["elapsed_seconds"] = time.monotonic() - started
        print(json.dumps({"response": index, "finish": parsed["finish_reason"],
                          "usage": raw.get("usage"), "provider": raw.get("provider")}), flush=True)
        return parsed


def main():
    from .cli import CODE_ROOT, file_hashes, verify_sources, replay_actions
    from .environment import build_case
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=Path(".env.local"))
    parser.add_argument("--resume-from", type=Path,
                        help="Replay saved responses with exact request comparison, then continue; new output required")
    args = parser.parse_args()
    out = args.out.resolve()
    if out == CODE_ROOT or CODE_ROOT in out.parents:
        parser.error("Output must be outside source")
    verify_sources()
    key = next(line.split("=", 1)[1].strip().strip('\"').strip("'")
               for line in args.env_file.read_text(encoding="utf-8-sig").splitlines()
               if line.startswith("OPENROUTER_API_KEY="))
    if not key:
        raise ValueError("Empty credential")
    out.mkdir(parents=True, exist_ok=False)
    case = build_case("hanoi", 224899942, disks=6, fs_prompt_variant="no-memory-claims")
    shutil.copytree(CODE_ROOT, out / "frozen_source", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    save(out / "manifest.json", dict(schema="openrouter_smoke_v1", created_utc=utc(),
         model=MODEL, case=case, max_responses=MAX_RESPONSES, code_hashes=file_hashes(CODE_ROOT),
         resumed_from=str(args.resume_from.resolve()) if args.resume_from else None,
         limitations=["API weight revision/template unverified; separate integration trial.",
          "Provider context 131072; per-response max_tokens 16384; not native 65536 remaining-budget policy.",
          "API seed 123 per request; not one persistent native RNG stream.",
          "Provider-reported usage; no local retokenization or activation collection."] ))
    try:
        snapshot_index = 0
        (out / "snapshots").mkdir()
        def snapshot(value):
            nonlocal snapshot_index
            # Unique immutable names avoid replacing a file held by a Windows reader.
            path = out / "snapshots" / f"snapshot_{snapshot_index:04d}.json"
            with path.open("x", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            snapshot_index += 1
        episode = run_episode(case, OpenRouterAdapter(key, out, args.resume_from), partial=snapshot)
        save(out / "episode.json", episode)
        events = [e["audit_event"] for step in episode["steps"] for e in step["events"] if e["audit_event"] is not None]
        record = dict(case=case, initial=episode["initial_audit"], events=events, final=episode["final"])
        result = replay_actions(record)
        result.pop("research_samples", None)
        result.update(api_smoke_episodes=1, tokenizer_checked=False, termination=episode["termination"])
        save(out / "action_audit.json", result)
        usages = [s["response"]["raw_api_response"].get("usage", {}) for s in episode["steps"]]
        costs = [u.get("cost") for u in usages]
        save(out / "usage_summary.json", dict(responses=len(usages), usages=usages,
             total_cost_usd=sum(costs) if all(isinstance(c, (int, float)) for c in costs) else None))
        print(json.dumps(result), flush=True)
    except BaseException:
        import traceback
        (out / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
