"""Remaining-context boundary tests; mocked inference only, no GPU/model/network."""
from __future__ import annotations

import copy
from contextlib import nullcontext
from types import SimpleNamespace
import unittest

from agent_memory_safety.agentic import audit
from agent_memory_safety.agentic.muse import MuseAdapter, PREFIX
from agent_memory_safety.agentic.runner import SETTINGS, TOOLS


class Vector:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return list(self.values)


class Batch:
    def __init__(self, values):
        self.values = values

    def __getitem__(self, key):
        if isinstance(key, tuple):
            row, column = key
            assert row == 0
            return Vector(self.values[column])
        assert key == 0
        return Vector(self.values)

    def to(self, device):
        return self


class MockTokenizer:
    """An explicitly synthetic ID/text pair for generation-boundary tests."""
    def __init__(self, input_count, raw):
        self.input_ids = [101] * input_count
        self.raw = raw

    def __call__(self, text, **kwargs):
        return {"input_ids": Batch(self.input_ids)}

    def decode(self, ids, **kwargs):
        return self.raw


class MockCUDA:
    def __init__(self):
        self.calls = []

    def reset_peak_memory_stats(self, device):
        self.calls.append("reset")

    def synchronize(self, device):
        self.calls.append("synchronize")

    def max_memory_allocated(self, device):
        return 0

    def max_memory_reserved(self, device):
        return 0


class MockModel:
    def __init__(self, generated):
        self.generated = generated
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(sequences=Batch(kwargs["input_ids"].values + self.generated))


def make_adapter(input_count, generated, raw):
    # Exercise the production generate method without running __init__/loading.
    adapter = MuseAdapter.__new__(MuseAdapter)
    adapter.tokenizer = MockTokenizer(input_count, raw)
    adapter.model = MockModel(generated)
    adapter.torch = SimpleNamespace(cuda=MockCUDA(), inference_mode=nullcontext)
    adapter.max_new_tokens = None
    adapter.context_limit = 65536
    adapter.generation_budget_policy = "remaining_context"
    adapter.reasoning_strength = "low"
    adapter.current_date = "2026-10-15"
    adapter.device = "software-only"
    adapter.render_prompt = lambda messages, tools: "SOFTWARE_BOUNDARY_CHECK:" + PREFIX
    return adapter


class ContextBudgetTests(unittest.TestCase):
    def inspect(self, adapter):
        record = adapter.generate([], TOOLS)
        checked = audit.audit_response(record, [], TOOLS, audit.SETTINGS)
        return record, checked

    def test_runner_and_independent_auditor_have_same_frozen_policy(self):
        self.assertEqual(SETTINGS, audit.SETTINGS)
        self.assertIsNone(SETTINGS["max_new_tokens"])
        self.assertEqual(SETTINGS["context_limit"], 65536)

    def test_remaining_space_replaces_short_response_cap(self):
        adapter = make_adapter(1000, [110, 200008], " to=user<|message|>OK<|eot|>")
        record, checked = self.inspect(adapter)
        self.assertEqual(record["generation_budget"], 64536)
        self.assertEqual(adapter.model.calls[0]["max_new_tokens"], 64536)
        self.assertTrue(checked["eos"])
        self.assertFalse(checked["truncated"])

    def test_one_remaining_token_can_end_with_eos(self):
        adapter = make_adapter(65535, [200008], "<|eot|>")
        record, checked = self.inspect(adapter)
        self.assertEqual(record["generation_budget"], 1)
        self.assertEqual(adapter.model.calls[0]["max_new_tokens"], 1)
        self.assertTrue(checked["eos"])
        self.assertFalse(checked["truncated"])
        # An isolated EOS is not a complete ATEM message; no repair is allowed.
        self.assertTrue(checked["format_error"])
        self.assertEqual(checked["calls"], [])

    def test_exact_context_or_overflow_never_calls_model_or_cuda(self):
        for count in (65536, 65537):
            with self.subTest(count=count):
                adapter = make_adapter(count, [], "")
                record, checked = self.inspect(adapter)
                self.assertEqual(record["input_tokens"], count)
                self.assertEqual(len(record["input_ids"]), count)
                self.assertEqual(record["generation_budget"], 0)
                self.assertEqual(adapter.model.calls, [])
                self.assertEqual(adapter.torch.cuda.calls, [])
                self.assertTrue(checked["context_limit"])
                self.assertFalse(checked["truncated"])
                self.assertFalse(checked["eos"])
                self.assertIsNone(record["assistant_message"])

    def test_exact_budget_without_eos_is_truncation(self):
        adapter = make_adapter(65534, [110, 111], " to=self<|message|>unfinished")
        record, checked = self.inspect(adapter)
        self.assertEqual(record["generation_budget"], 2)
        self.assertTrue(checked["truncated"])
        self.assertFalse(checked["eos"])
        self.assertTrue(checked["format_error"])
        self.assertEqual(checked["calls"], [])

    def test_exact_budget_with_eos_is_not_truncation(self):
        adapter = make_adapter(65534, [110, 200008], " to=user<|message|>OK<|eot|>")
        record, checked = self.inspect(adapter)
        self.assertEqual(len(record["generated_ids"]), record["generation_budget"])
        self.assertTrue(checked["eos"])
        self.assertFalse(checked["truncated"])

    def test_auditor_rejects_output_beyond_remaining_space(self):
        adapter = make_adapter(65534, [110, 111, 200008], " to=user<|message|>OK<|eot|>")
        record = adapter.generate([], TOOLS)
        with self.assertRaisesRegex(AssertionError, "generation budget"):
            audit.audit_response(record, [], TOOLS, audit.SETTINGS)

    def test_auditor_rejects_old_budget_or_wrong_policy(self):
        adapter = make_adapter(1000, [110, 200008], " to=user<|message|>OK<|eot|>")
        record = adapter.generate([], TOOLS)
        for key, value in (("generation_budget", 2048), ("generation_budget_policy", "fixed_max_new_tokens")):
            with self.subTest(key=key):
                bad = copy.deepcopy(record)
                bad[key] = value
                with self.assertRaisesRegex(AssertionError, "generation budget"):
                    audit.audit_response(bad, [], TOOLS, audit.SETTINGS)

    def test_auditor_rejects_model_call_when_context_is_exhausted(self):
        record = make_adapter(65536, [], "").generate([], TOOLS)
        record["diagnostics"]["model_called"] = True
        with self.assertRaisesRegex(AssertionError, "context limit no model"):
            audit.audit_response(record, [], TOOLS, audit.SETTINGS)

    def test_auditor_rejects_fixed_setting(self):
        record = make_adapter(1000, [110, 200008], " to=user<|message|>OK<|eot|>").generate([], TOOLS)
        wrong = dict(audit.SETTINGS, max_new_tokens=2048)
        with self.assertRaisesRegex(AssertionError, "remaining-context setting"):
            audit.audit_response(record, [], TOOLS, wrong)

    def test_incomplete_tool_call_is_never_repaired(self):
        raw = ' to=play<|message|><atem:function_calls><atem:invoke name="play"><atem:parameter name="action">[1 r]'
        adapter = make_adapter(65534, [110, 111], raw)
        record, checked = self.inspect(adapter)
        self.assertTrue(checked["truncated"])
        self.assertTrue(checked["format_error"])
        self.assertEqual(record["tool_calls"], [])

    def test_invalid_config_rejected_before_heavy_imports(self):
        for kwargs in (dict(max_new_tokens=0), dict(max_new_tokens=-1), dict(max_new_tokens=True),
                       dict(context_limit=0), dict(context_limit=True)):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    MuseAdapter(**kwargs)


if __name__ == "__main__":
    unittest.main()
