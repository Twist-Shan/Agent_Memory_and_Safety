"""Muse ATEM adapter for a text-only, auditable Transformers experiment.

Protocol source: meta-models/Muse-Glimmer-30B at MODEL_REVISION, especially
chat_template.jinja and generation_config.json. No generation prefix, tool
call, argument, or malformed response is repaired. ``_native_text`` preserves
generated ATEM/reasoning exactly when building the next model input.

Heavy dependencies are imported only by MuseAdapter.__init__, so parser tests
run without PyTorch, Transformers, or downloaded weights.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODEL_ID = "meta-models/Muse-Glimmer-30B"
MODEL_REVISION = "a4e59da52a7bc87ae7251dd5545c0dd437c44b68"
OFFICIAL_EOS_IDS = [200001, 200008]
PREFIX = "<|start|>assistant"
_HEADER = re.compile(r"<\|start\|>assistant to=([^\s<>]+)<\|message\|>")
_ENDING = re.compile(r"<\|eom\|>|<\|eot\|>|<\|end_of_text\|>")
_INVOKE = re.compile(r'<atem:invoke name="([^"<>]+)">(.*?)</atem:invoke>', re.S)
_PARAM = re.compile(r'<atem:parameter name="([^"<>]+)">(.*?)</atem:parameter>', re.S)


class NativeFormatError(ValueError):
    pass


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise NativeFormatError("duplicate JSON object key: " + key)
        result[key] = value
    return result


def _json(value: str):
    def bad_constant(token):
        raise NativeFormatError("non-finite JSON value: " + token)
    return json.loads(value, object_pairs_hook=_unique_json, parse_constant=bad_constant)


def tool_message(name: str, result: Any) -> dict[str, Any]:
    """Official template uses role=tool and an explicit tool name."""
    return {"role": "tool", "name": name,
            "content": json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True)}


def _atem_calls(body: str, recipient: str, tools: list[dict]) -> list[dict]:
    # Official documentation explicitly says ATEM is not necessarily valid XML.
    # Do not use an XML parser: string values may contain raw &, <, or quotes.
    wrapped = re.fullmatch(r"\s*<atem:function_calls>(.*?)</atem:function_calls>\s*", body, re.S)
    if wrapped is None:
        raise NativeFormatError("tool channel is not one complete ATEM function_calls block")
    inner = wrapped.group(1)
    schema = {t.get("function", t)["name"]: t.get("function", t) for t in tools}
    calls, offset = [], 0
    for invoke in _INVOKE.finditer(inner):
        if inner[offset:invoke.start()].strip():
            raise NativeFormatError("unparsed text between ATEM invocations")
        name, params = invoke.groups()
        if name != recipient:
            raise NativeFormatError("channel recipient and ATEM function name differ")
        arguments, pos = {}, 0
        properties = schema.get(name, {}).get("parameters", {}).get("properties", {})
        for parameter in _PARAM.finditer(params):
            if params[pos:parameter.start()].strip():
                raise NativeFormatError("unparsed text between ATEM parameters")
            key, value = parameter.groups()
            if key in arguments:
                raise NativeFormatError("duplicate ATEM parameter: " + key)
            kind = properties.get(key, {}).get("type")
            if kind == "string":
                # String spaces and quote characters are significant (official template).
                parsed = value
            elif kind in ("array", "object", "integer", "number", "boolean", "null"):
                try:
                    parsed = _json(value)
                except (ValueError, TypeError) as exc:
                    raise NativeFormatError("invalid JSON parameter: " + key) from exc
            else:
                # Unknown fields/functions still reach the environment for rejection.
                # The official response parser allows non-JSON scalar strings.
                try:
                    parsed = _json(value)
                except (ValueError, TypeError):
                    parsed = value
            arguments[key] = parsed
            pos = parameter.end()
        if params[pos:].strip():
            raise NativeFormatError("unclosed or unparsed ATEM parameter")
        calls.append({"type": "function", "function": {"name": name, "arguments": arguments}})
        offset = invoke.end()
    if inner[offset:].strip() or not calls:
        raise NativeFormatError("unclosed or missing ATEM invocation")
    return calls


def parse_native_output(raw_text: str, tools: list[dict]) -> dict[str, Any]:
    """Parse only text actually generated after the official assistant prefix.

    On any format error, return no executable calls; retain all raw text and
    parsed segments for diagnosis. Truncated outputs must also not be executed.
    """
    native = PREFIX + raw_text
    segments, calls, reasons, content = [], [], [], []
    offset = 0
    try:
        while offset < len(native):
            header = _HEADER.match(native, offset)
            if header is None:
                raise NativeFormatError("missing or invalid native assistant channel header")
            ending = _ENDING.search(native, header.end())
            if ending is None:
                raise NativeFormatError("missing native message ending")
            recipient = header.group(1)
            body = native[header.end():ending.start()]
            if "<|start|>" in body or "<|message|>" in body:
                raise NativeFormatError("nested native message boundary")
            end = ending.group(0)
            segments.append({"recipient": recipient, "content": body, "ending": end})
            if recipient == "self":
                reasons.append(body)
            elif recipient == "user":
                content.append(body)
            else:
                calls.extend(_atem_calls(body, recipient, tools))
            offset = ending.end()
            if end != "<|eom|>" and offset != len(native):
                raise NativeFormatError("content after native end-of-turn")
        if not segments or segments[-1]["ending"] == "<|eom|>":
            raise NativeFormatError("response ended before end-of-turn")
        message = {"role": "assistant", "content": "".join(content),
                   "reasoning_content": "".join(reasons), "tool_calls": calls,
                   "_native_text": native}
        return {"assistant_message": message, "tool_calls": calls,
                "format_error": None, "native_segments": segments}
    except NativeFormatError as exc:
        # Failure history is preserved verbatim; the runner must not execute
        # partial calls or invent a closing token, even in the next phase.
        message = {"role": "assistant", "content": "", "reasoning_content": "".join(reasons),
                   "tool_calls": [], "_native_text": native}
        return {"assistant_message": message, "tool_calls": [],
                "format_error": str(exc), "native_segments": segments}


def render_native_prompt(processor, messages: list[dict], tools: list[dict],
                         reasoning_strength: str = "low", current_date: str | None = None) -> str:
    """Use the official template for external messages and exact generated text.

    Re-serializing tool arguments or collapsing multiple reasoning messages
    would change the original trajectory. A unique sentinel occupies each
    recorded assistant turn during official rendering, then is replaced by its
    original native bytes. No generated content is normalized.
    """
    safe, replacements = [], []
    corpus = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    for i, original in enumerate(messages):
        m = copy.deepcopy(original)
        native = m.pop("_native_text", None)
        if native is not None:
            if m.get("role") != "assistant" or not native.startswith(PREFIX):
                raise ValueError("native text must be a complete assistant transcript")
            marker = "MUSE_RAW_TURN_" + hashlib.sha256((str(i) + corpus).encode()).hexdigest()
            if marker in corpus:
                raise ValueError("native rendering marker collision")
            m = {"role": "assistant", "recipient": "user", "end_turn": True, "content": marker}
            replacements.append((PREFIX + " to=user<|message|>" + marker + "<|eot|>", native))
        safe.append(m)
    prompt = processor.apply_chat_template(safe, tools=tools,
                                          reasoning_strength=reasoning_strength,
                                          current_date=current_date,
                                          add_generation_prompt=True, tokenize=False)
    for marker, native in replacements:
        if prompt.count(marker) != 1:
            raise ValueError("official template did not render the expected native placeholder")
        prompt = prompt.replace(marker, native, 1)
    if not prompt.endswith(PREFIX):
        raise ValueError("official generation prompt differs from verified Muse prefix")
    return prompt


class MuseAdapter:
    def __init__(self, model_id: str = MODEL_ID, revision: str = MODEL_REVISION,
                 *, seed: int = 123, max_new_tokens: int | None = None,
                 context_limit: int = 65536, reasoning_strength: str = "low",
                 attn_implementation: str = "sdpa", device: str = "cuda:0",
                 current_date: str | None = None):
        if max_new_tokens is not None and (type(max_new_tokens) is not int or max_new_tokens <= 0):
            raise ValueError("max_new_tokens must be a positive integer or None for remaining context")
        if type(context_limit) is not int or context_limit <= 0:
            raise ValueError("context_limit must be a positive integer")
        import torch
        import transformers
        from transformers import AutoModelForMultimodalLM, AutoProcessor, set_seed
        from transformers.utils.hub import cached_file

        if revision != MODEL_REVISION or model_id != MODEL_ID:
            raise ValueError("this audited adapter is pinned to its documented model revision")
        if reasoning_strength not in {"low", "medium", "high", "xhigh"}:
            raise ValueError("invalid Muse reasoning strength")
        self.torch = torch
        self.seed = seed
        self.max_new_tokens = max_new_tokens
        self.context_limit = context_limit
        self.generation_budget_policy = "remaining_context" if max_new_tokens is None else "fixed_max_new_tokens"
        self.reasoning_strength = reasoning_strength
        self.current_date = current_date or datetime.now(timezone.utc).date().isoformat()
        self.device = device
        set_seed(seed)
        self.processor = AutoProcessor.from_pretrained(model_id, revision=revision, trust_remote_code=False)
        self.tokenizer = self.processor.tokenizer
        config_path = Path(cached_file(model_id, "config.json", revision=revision))
        if config_path.parent.name != revision:
            raise RuntimeError("downloaded config snapshot does not match pinned revision")
        template_path = Path(cached_file(model_id, "chat_template.jinja", revision=revision))
        generation_path = Path(cached_file(model_id, "generation_config.json", revision=revision))
        generation = json.loads(generation_path.read_text(encoding="utf-8"))
        if generation["eos_token_id"] != OFFICIAL_EOS_IDS:
            raise RuntimeError("unexpected official generation EOS configuration")
        expected_tokens = {"<|begin_of_text|>": 200000, "<|end_of_text|>": 200001,
                           "<|eom|>": 200007, "<|eot|>": 200008,
                           "<|finetune_right_pad|>": 200018,
                           "<|start|>": 200022, "<|message|>": 200023}
        for token, token_id in expected_tokens.items():
            if self.tokenizer.convert_tokens_to_ids(token) != token_id:
                raise RuntimeError("unexpected native special token mapping: " + token)
        self.model = AutoModelForMultimodalLM.from_pretrained(
            model_id, revision=revision, trust_remote_code=False,
            dtype=torch.bfloat16, device_map={"": device},
            attn_implementation=attn_implementation,
        ).eval()
        self._metadata = {
            "model_id": model_id, "model_revision": revision,
            "resolved_config_snapshot": config_path.parent.name,
            "transformers_version": transformers.__version__, "torch_version": torch.__version__,
            "cuda_version": torch.version.cuda, "device": device,
            "gpu_name": torch.cuda.get_device_name(device), "dtype": "bfloat16",
            "attention_implementation": attn_implementation, "use_cache": True,
            "reasoning_strength": reasoning_strength, "seed": seed,
            "template_current_date": self.current_date,
            "max_new_tokens": max_new_tokens, "context_limit": context_limit,
            "generation_budget_policy": self.generation_budget_policy,
            "do_sample": False, "num_beams": 1, "logits_to_keep": 1,
            "eos_token_ids": OFFICIAL_EOS_IDS, "pad_token_id": 200018,
            "official_sampling_defaults": generation,
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "chat_template_sha256": hashlib.sha256(template_path.read_bytes()).hexdigest(),
            "generation_config_sha256": hashlib.sha256(generation_path.read_bytes()).hexdigest(),
            "native_history_policy": "exact recorded assistant native text; official external-message template",
        }

    @staticmethod
    def tool_message(name: str, result: Any) -> dict:
        return tool_message(name, result)

    def metadata(self) -> dict:
        return copy.deepcopy(self._metadata)

    def render_prompt(self, messages: list[dict], tools: list[dict]) -> str:
        return render_native_prompt(self.processor, messages, tools, self.reasoning_strength, self.current_date)

    def count_tokens(self, messages: list[dict], tools: list[dict]) -> int:
        return len(self.tokenizer.encode(self.render_prompt(messages, tools), add_special_tokens=False))

    def generate(self, messages: list[dict], tools: list[dict]) -> dict:
        torch = self.torch
        prompt = self.render_prompt(messages, tools)
        inputs = self.tokenizer(prompt, add_special_tokens=False, return_tensors="pt")
        input_ids = inputs["input_ids"][0].tolist()
        # No separate response cap in this batch: use only the remaining space
        # after the exact, unabridged input. An exhausted input never calls the model.
        budget = max(0, self.context_limit - len(input_ids)) if self.max_new_tokens is None else self.max_new_tokens
        common = {"input_ids": input_ids, "prompt_text": prompt,
                  "rendered_prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                  "template_kwargs": {"reasoning_strength": self.reasoning_strength,
                                      "current_date": self.current_date,
                                      "add_generation_prompt": True, "tokenize": False},
                  "input_tokens": len(input_ids), "generation_budget": budget,
                  "generation_budget_policy": self.generation_budget_policy}
        if budget == 0 or len(input_ids) + budget > self.context_limit:
            return {**common, "generated_ids": [], "raw_text": "", "assistant_message": None,
                    "tool_calls": [], "format_error": None, "truncated": False,
                    "eos": False, "stop_reason": "context_limit", "native_segments": [],
                    "diagnostics": {"model_called": False, "input_not_truncated": True}}
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        torch.cuda.reset_peak_memory_stats(self.device)
        torch.cuda.synchronize(self.device)
        started = time.monotonic()
        with torch.inference_mode():
            output = self.model.generate(
                **inputs, max_new_tokens=budget, do_sample=False,
                num_beams=1, use_cache=True, logits_to_keep=1,
                eos_token_id=OFFICIAL_EOS_IDS, pad_token_id=200018,
                return_dict_in_generate=True, output_scores=False,
            )
        torch.cuda.synchronize(self.device)
        ids = output.sequences[0, len(input_ids):].tolist()
        raw_text = self.tokenizer.decode(ids, skip_special_tokens=False,
                                         clean_up_tokenization_spaces=False)
        eos = bool(ids and ids[-1] in OFFICIAL_EOS_IDS)
        truncated = not eos and len(ids) >= budget
        parsed = parse_native_output(raw_text, tools)
        return {**common, "generated_ids": ids, "raw_text": raw_text, **parsed,
                "eos": eos, "truncated": truncated,
                "stop_reason": "eos" if eos else "max_new_tokens" if truncated else "other",
                "diagnostics": {"model_called": True, "input_not_truncated": True,
                                "elapsed_seconds": time.monotonic() - started,
                                "generated_tokens": len(ids),
                                "peak_allocated_bytes": torch.cuda.max_memory_allocated(self.device),
                                "peak_reserved_bytes": torch.cuda.max_memory_reserved(self.device),
                                "end_token_id": ids[-1] if ids else None}}
