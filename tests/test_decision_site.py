"""Optional offline tests; synthetic tensors, no pretrained weights or downloads."""
import os
import unittest

@unittest.skipUnless(os.environ.get('AMS_TEST_WHITEBOX') == '1', 'Optional offline white-box integration')
class DecisionSiteTests(unittest.TestCase):

    def test_exact_copy_locality_identity_and_cleanup(self):
        import numpy as np
        import torch
        from agent_memory_safety.decision_site import respond
        torch.manual_seed(123)

        class Block(torch.nn.Module):

            def forward(self, h):
                return h + 1

        class Toy(torch.nn.Module):

            def __init__(self):
                super().__init__()
                self.block = Block()
                self.lm_head = torch.nn.Identity()
                self.outputs = []

            def forward(self, input_ids):
                return self.lm_head(self.block(input_ids[:, :, None].float().repeat(1, 1, 8)))

            def generate(self, input_ids, **kwargs):
                seq = input_ids.clone()
                self.outputs = []
                for nxt in (4, 5, 7, 8):
                    self.outputs.append(self(input_ids=seq).detach().clone())
                    seq = torch.cat([seq, torch.tensor([[nxt]])], 1)
                return seq

        class Tokenizer:
            eos_token_id = 8

        class Policy:
            max_new_tokens = 4
            tokenizer = Tokenizer()

            def __init__(self):
                self.model = Toy()
                self.layers = [self.model.block]

            def _inputs(self, messages):
                return {'input_ids': torch.tensor([[1, 2, 3]])}

            def respond(self, messages):
                return str(self.model.generate(**self._inputs(messages)).tolist())
        Policy.torch = torch
        p = Policy()
        own = np.full(8, 6.0, dtype='float32')
        cap = dict(prefix_ids=[4, 5], vectors={0: own}, logits=own, check_token=0, publish_token=1)
        _, g, _ = respond(p, [], 0, cap)
        clean = p.model.outputs
        assert g['decision_logits']['baseline_full_max_error'] == 0 and g['interventions'][0]['capture_max_error'] == 0
        donor = np.arange(8, dtype='float32')
        _, g, patches = respond(p, [], 0, cap, lambda h: (donor.copy(), dict(exact=True)), donor)
        assert len(patches) == len(g['interventions']) == 1 and g['decision_logits']['donor_full_max_error'] == 0
        assert g['interventions'][0]['assignment_max_error'] == 0
        assert all((torch.equal(p.model.outputs[k], clean[k]) for k in [0, 1, 3]))
        assert torch.equal(p.model.outputs[2][:, :-1], clean[2][:, :-1])
        _, g, _ = respond(p, [], 0, cap, lambda h: (h.copy(), {}))
        assert g['decision_logits']['baseline_full_max_error'] == 0
        wrong = dict(cap, prefix_ids=[4, 6])
        _, g, ps = respond(p, [], 0, wrong, lambda h: (donor.copy(), {}))
        assert not g['located'] and (not ps)
        assert not p.model._forward_pre_hooks and (not p.layers[0]._forward_hooks) and (not p.model.lm_head._forward_hooks)

        def fail(own):
            raise RuntimeError('controller failed')
        try:
            respond(p, [], 0, cap, fail)
        except RuntimeError:
            pass
        else:
            raise AssertionError('expected controller failure')
        assert not p.model._forward_pre_hooks and (not p.layers[0]._forward_hooks) and (not p.model.lm_head._forward_hooks)
        assert p.model.generate.__func__ is Toy.generate

    def test_gate_and_bfloat16_random_norm(self):
        import numpy as np
        import torch
        from agent_memory_safety.controllers import control_vector
        rng = np.random.default_rng(123)
        own = rng.normal(size=4096).astype('float32')
        state = rng.normal(size=4096)
        state /= np.linalg.norm(state)
        mid = np.zeros(4096)
        direction = state
        for gate in [True, False]:
            for mode in ['state_gated', 'random123', 'random124', 'random125']:
                vector, meta = control_vector(torch, own, state, mid, direction, 40.0, 0.5, gate, mode, mode + ':toy')
                actual = np.linalg.norm(vector - torch.tensor(own, dtype=torch.bfloat16).float().numpy())
                assert abs(actual - meta['planned_norm']) < 0.0001
                assert meta['relative_norm_error'] <= 0.01
                if gate and (not meta['trigger']):
                    assert actual == 0
        vector, m = control_vector(torch, -state.astype('float32'), state, mid, direction, 40.0, 1.0, True, 'state_gated', 'x')
        assert not m['trigger'] and m['planned_norm'] == 0
