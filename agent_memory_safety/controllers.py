"""Activation-only gate and BF16 norm-matched random controls.

Directions, midpoint and scale must be fitted/frozen outside held-out tests.
"""
import hashlib
import numpy as np

def control_vector(torch, own, state, mid, direction, gap, gain, gated, mode, seed_key):
    old = torch.as_tensor(own, dtype=torch.bfloat16).float()
    score = float((old.numpy() - mid) @ state)
    trigger = bool(not gated or score > 0)
    target = (old + torch.as_tensor(direction * gap * gain * int(trigger), dtype=torch.float32)).to(torch.bfloat16)
    norm = float(torch.linalg.vector_norm(target.float() - old))
    relative = 0.0
    if mode.startswith('random') and norm > 0:
        rng = np.random.default_rng(int(hashlib.sha256(seed_key.encode()).hexdigest()[:16], 16))
        v = torch.tensor(rng.normal(size=own.shape), dtype=torch.float32)
        v /= torch.linalg.vector_norm(v)

        def candidate(a):
            z = (old + a * v).to(torch.bfloat16)
            n = float(torch.linalg.vector_norm(z.float() - old))
            return (z, n)
        low = 0.0
        high = 2 * norm
        best = None
        for _ in range(16):
            if candidate(high)[1] >= norm:
                break
            high *= 2
        for _ in range(60):
            a = (low + high) / 2
            z, n = candidate(a)
            err = abs(n - norm) / norm
            if best is None or err < best[0]:
                best = (err, z, n, a)
            if n < norm:
                low = a
            else:
                high = a
        relative, target, actual, random_gain = best
        assert relative <= 0.01, 'BF16 random norm tolerance failed'
    else:
        actual = norm
        random_gain = None
    return (target.float().numpy(), dict(score=score, trigger=trigger, gain=gain, target_norm=norm, planned_norm=actual, relative_norm_error=relative, random_gain=random_gain))
