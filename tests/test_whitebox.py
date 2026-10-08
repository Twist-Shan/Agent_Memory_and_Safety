"""Offline integration tests; opt in with AMS_TEST_WHITEBOX=1 and optional deps.

Uses random tiny Qwen3 weights; it is a software test, not a model experiment.
"""
import os
import unittest
from pathlib import Path
import tempfile
import json


@unittest.skipUnless(os.environ.get("AMS_TEST_WHITEBOX") == "1", "Optional offline white-box integration")
class WhiteboxTests(unittest.TestCase):
    def test_capture_patch_cleanup_and_context(self):
        import numpy as np
        import torch
        from transformers import Qwen3Config, Qwen3ForCausalLM
        from agent_memory_safety.whitebox import HFPolicy
        torch.set_num_threads(1)
        torch.manual_seed(17)
        config = Qwen3Config(vocab_size=32, hidden_size=16, intermediate_size=32,
                            num_hidden_layers=2, num_attention_heads=2, num_key_value_heads=2, head_dim=8)
        policy = HFPolicy.__new__(HFPolicy)
        policy.torch = torch
        policy.model = Qwen3ForCausalLM(config).eval()
        policy.layers = policy.model.model.layers
        policy.max_context, policy.max_new_tokens = 32, 3
        class Inputs(dict):
            def to(self, device):
                return Inputs({k: v.to(device) for k, v in self.items()})
        class Tokenizer:
            eos_token_id = 31
            def apply_chat_template(self, messages, **kwargs):
                return "test prompt"
            def __call__(self, text, **kwargs):
                return Inputs(input_ids=torch.tensor([[1, 2, 3]]), attention_mask=torch.ones(1, 3, dtype=torch.long))
            def decode(self, tokens, **kwargs):
                return str(tokens.tolist())
        policy.tokenizer = Tokenizer()
        messages = [{"role": "user", "content": "test"}]
        a = policy.activations(messages)
        self.assertEqual(a.shape, (2, 16))
        baseline = policy.respond(messages)
        self.assertEqual(baseline, policy.respond(messages, patch=(0, np.ones(16), "add", 0)))
        policy.respond(messages, patch=(0, a[0], "replace", 1))
        self.assertTrue(all(not layer._forward_hooks for layer in policy.layers))
        self.assertEqual(baseline, policy.respond(messages))
        policy.max_context = 3
        with self.assertRaises(ValueError):
            policy.activations(messages)
        self.assertTrue(all(not layer._forward_hooks for layer in policy.layers))

    def test_probe_grouping_and_training(self):
        import numpy as np
        from agent_memory_safety.analysis import fit_probe
        root = Path(__file__).resolve().parents[1] / "runs"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            path = Path(tmp)
            rows = []
            rng = np.random.default_rng(43)
            for split in ("train", "validation", "test"):
                for i in range(12):
                    label = i % 2
                    x = rng.normal(size=(2, 4)).astype("float32")
                    x[0, :] = 0  # Exact held-out signal; distractors live in the other layer.
                    x[0, 0] = 10 * (2 * label - 1)
                    name = f"{split}-{i}.npz"
                    np.savez(path / name, activations=x)
                    rows.append({"base_id": f"{split}-{i}", "split": split, "condition": "synthetic",
                                 "activation_file": name, "labels": {"authorized_target": label}})
            manifest = path / "manifest.jsonl"
            manifest.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            result = fit_probe(manifest, path / "fit")
            self.assertEqual(result["test_auroc"], 1.0)
            rows[-1]["base_id"] = rows[0]["base_id"]
            manifest.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            with self.assertRaises(ValueError):
                fit_probe(manifest, path / "bad")
