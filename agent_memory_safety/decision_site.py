"""Single-forward natural decision-site capture and intervention for Toy A.

Optional NumPy/PyTorch support; no model is loaded on import.
Use with batch-one, greedy HFPolicy and use_cache=False. Not thread-safe.
Capture uses a constructed shared action prefix; respond never forces that prefix.
"""
import numpy as np

def capture_layers(policy, messages, target, layers=(15, 23, 35)):
    import json
    layers = tuple(layers)
    if not layers or any(not 0 <= layer < len(policy.layers) for layer in layers):
        raise ValueError('Capture layers must be valid decoder-block indices')
    torch = policy.torch
    tok = policy.tokenizer
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    prompt = tok(text, add_special_tokens=False)['input_ids']
    alts = [tok(text + json.dumps({'tool': tool, 'file': target}), add_special_tokens=False)['input_ids'] for tool in ('check', 'publish')]
    assert all((a[:len(prompt)] == prompt for a in alts))
    k = next((i for i, (a, b) in enumerate(zip(*alts)) if a != b))
    assert k >= len(prompt)
    if k >= policy.max_context:
        raise ValueError('Decision capture exceeds the context budget')
    inputs = torch.tensor([alts[0][:k]], device=policy.model.device)
    saved = {}
    handles = []
    for l in layers:

        def hook(module, args, out, l=l):
            h = out[0] if isinstance(out, tuple) else out
            saved[l] = h[0, -1].detach().float().cpu().numpy().copy()
        handles.append(policy.layers[l].register_forward_hook(hook))
    try:
        with torch.inference_mode():
            out = policy.model(input_ids=inputs, use_cache=False, logits_to_keep=1)
    finally:
        for h in handles:
            h.remove()
    logits = out.logits[0, -1].float().cpu().numpy()
    return dict(vectors=saved, logits=logits, prefix_ids=alts[0][len(prompt):k], input_ids=alts[0][:k], prompt_tokens=len(prompt), check_token=alts[0][k], publish_token=alts[1][k], log_odds=float(logits[alts[0][k]] - logits[alts[1][k]]))

def respond(policy, messages, layer, cap=None, controller=None, donor_logits=None):
    """Full donor copy uses direct assignment, never BF16 interpolation."""
    if controller is not None and cap is None:
        raise ValueError('A capture record is required for intervention')
    if cap is not None and (not 0 <= layer < len(policy.layers) or layer not in cap['vectors']):
        raise ValueError('Intervention layer must exist in model and capture')
    torch = policy.torch
    n = int(policy._inputs(messages)['input_ids'].shape[1])
    seen = {}
    applied = []
    patches = []
    gen = {}
    handles = []
    original = policy.model.generate

    def record(module, args, kw):
        seen['ids'] = kw.get('input_ids', args[0] if args else None)

    def hook(module, args, out):
        h = out[0] if isinstance(out, tuple) else out
        ids = seen.get('ids')
        if applied or ids is None or ids.shape[1] - n != len(cap['prefix_ids']) or (ids[0, n:].tolist() != cap['prefix_ids']):
            return out
        old = h[0, -1].detach().clone()
        r = dict(position=int(ids.shape[1] - 1), actual_norm=0.0, capture_max_error=float((old.float() - torch.as_tensor(cap['vectors'][layer], device=old.device)).abs().max()))
        if controller is not None:
            vector, meta = controller(old.float().cpu().numpy())
            patches.append(vector.copy())
            r['controller'] = meta
            h = h.clone()
            h[0, -1] = torch.as_tensor(vector, device=h.device, dtype=h.dtype)
            r['actual_norm'] = float(torch.linalg.vector_norm(h[0, -1].float() - old.float()))
            r['assignment_max_error'] = float((h[0, -1].float() - torch.as_tensor(vector, device=h.device)).abs().max())
        applied.append(r)
        seen['measure'] = True
        return (h, *out[1:]) if isinstance(out, tuple) else h

    def head(module, args, out):
        if not seen.pop('measure', False):
            return
        z = out[0, -1].detach().float().cpu().numpy()
        gen['decision_logits'] = dict(check=float(z[cap['check_token']]), publish=float(z[cap['publish_token']]), log_odds=float(z[cap['check_token']] - z[cap['publish_token']]), top_id=int(z.argmax()), baseline_full_max_error=float(np.max(np.abs(z - cap['logits']))))
        if donor_logits is not None:
            gen['decision_logits']['donor_full_max_error'] = float(np.max(np.abs(z - donor_logits)))

    def generate(*args, **kw):
        out = original(*args, **kw)
        ids = out[0, n:].detach().cpu().tolist()
        gen.update(prompt_tokens=n, ids=ids, eos=bool(ids and ids[-1] == policy.tokenizer.eos_token_id), hit_limit=len(ids) >= policy.max_new_tokens)
        return out
    if cap is not None:
        handles = [policy.model.register_forward_pre_hook(record, with_kwargs=True), policy.layers[layer].register_forward_hook(hook), policy.model.lm_head.register_forward_hook(head)]
    policy.model.generate = generate
    try:
        raw = policy.respond(messages)
    finally:
        policy.model.generate = original
        for h in handles:
            h.remove()
    gen.update(located=bool(applied), interventions=applied, patch_requested=controller is not None)
    return (raw, gen, patches)
