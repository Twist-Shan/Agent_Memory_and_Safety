"""Optional HF adapter. Captures only final-prompt-token block residuals.

No model downloads or GPU allocation occur when importing the core package.
Hooks use raw decoder block outputs (before final model normalization).
"""

from pathlib import Path


class HFPolicy:
    def __init__(self, model_id, revision, device="cuda", precision="bfloat16", seed=17,
                 max_context=4096, max_new_tokens=128):
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer
        if not revision:
            raise ValueError("An explicit checkpoint revision is required")
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA unavailable; choose --device cpu for small-model tests")
        torch.manual_seed(seed)
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
        self.model = AutoModelForCausalLM.from_pretrained(model_id, revision=revision,
            torch_dtype=getattr(torch, precision), attn_implementation="eager").to(device).eval()
        for p in self.model.parameters():
            p.requires_grad_(False)
        self.layers = self.model.model.layers
        self.max_context, self.max_new_tokens = max_context, max_new_tokens
        self.metadata = {"model": model_id, "requested_revision": revision,
            "resolved_revision": getattr(self.model.config, "_commit_hash", None),
            "transformers": transformers.__version__, "torch": torch.__version__,
            "precision": precision, "device": device, "seed": seed,
            "enable_thinking": False, "use_cache": False, "do_sample": False,
            "max_context": max_context, "max_new_tokens": max_new_tokens,
            "activation_site": "decoder_block_output:last_prompt_token; zero-based layer index",
            "chat_template": self.tokenizer.chat_template}

    def _inputs(self, messages):
        text = self.tokenizer.apply_chat_template(messages, tokenize=False,
            add_generation_prompt=True, enable_thinking=False)
        inputs = self.tokenizer(text, return_tensors="pt", add_special_tokens=False).to(self.model.device)
        length = inputs["input_ids"].shape[1]
        if length + self.max_new_tokens > self.max_context:
            raise ValueError("Context budget exceeded; history is never silently truncated")
        return inputs

    def activations(self, messages):
        import numpy as np
        inputs = self._inputs(messages)
        saved, handles = {}, []
        for index, layer in enumerate(self.layers):
            def capture(module, args, output, index=index):
                hidden = output[0] if isinstance(output, tuple) else output
                saved[index] = hidden[0, -1].detach().float().cpu().numpy().copy()
            handles.append(layer.register_forward_hook(capture))
        try:
            with self.torch.inference_mode():
                self.model(**inputs, use_cache=False)
        finally:
            for handle in handles:
                handle.remove()
        return np.stack([saved[i] for i in range(len(self.layers))])

    def respond(self, messages, capture=None, patch=None):
        """patch=(layer, vector, mode, scale), at the fixed last prompt token.

        mode='replace' uses a matched donor residual; 'add' applies a direction.
        With use_cache=False, reapply at that site throughout THIS action decoding.
        The caller decides which actions to intervene on; other sites are untouched.
        """
        import numpy as np
        inputs = self._inputs(messages)
        if capture is not None:
            Path(capture).parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(capture, activations=self.activations(messages))
        handle = None
        if patch is not None:
            index, vector, mode, scale = patch
            if mode not in {"replace", "add"} or not 0 <= index < len(self.layers):
                raise ValueError("Invalid patch mode/layer")
            vector = self.torch.as_tensor(vector, device=self.model.device, dtype=self.model.dtype)
            if tuple(vector.shape) != (self.model.config.hidden_size,):
                raise ValueError("Patch vector dimension mismatch")
            position = inputs["input_ids"].shape[1] - 1
            def intervene(module, args, output):
                hidden = (output[0] if isinstance(output, tuple) else output).clone()
                if mode == "replace":
                    hidden[:, position, :] += scale * (vector - hidden[:, position, :])
                else:
                    hidden[:, position, :] += scale * vector
                return (hidden, *output[1:]) if isinstance(output, tuple) else hidden
            handle = self.layers[index].register_forward_hook(intervene)
        try:
            with self.torch.inference_mode():
                generated = self.model.generate(**inputs, do_sample=False, use_cache=False,
                    max_new_tokens=self.max_new_tokens, pad_token_id=self.tokenizer.eos_token_id)
            return self.tokenizer.decode(generated[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        finally:
            if handle is not None:
                handle.remove()
