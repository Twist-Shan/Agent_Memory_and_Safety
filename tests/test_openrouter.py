import copy
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from agent_memory_safety.agentic.openrouter import parse_response, OpenRouterAdapter


def response(action, call_id="x", finish="tool_calls"):
    return {"choices": [{"finish_reason": finish, "message": {
        "role": "assistant", "tool_calls": [{"id": call_id, "type": "function",
        "function": {"name": "play", "arguments": json.dumps({"action": action})}}]}}]}


class TransportTests(unittest.TestCase):
    def test_saved_response_resume_never_reissues_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old, new = root / "old", root / "new"
            old.mkdir(); new.mkdir()
            transport = OpenRouterAdapter("unused", old)
            class Reply:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def read(self): return json.dumps(response("[A C]")).encode()
            with patch("urllib.request.urlopen", return_value=Reply()) as network:
                transport.generate([], [])
                self.assertEqual(network.call_count, 1)
            with patch("urllib.request.urlopen", side_effect=AssertionError("Network forbidden")):
                resumed = OpenRouterAdapter("unused", new, old)
                self.assertTrue(resumed.generate([], [])["replayed_saved_response"])
                mismatch = OpenRouterAdapter("unused", new, old)
                with self.assertRaisesRegex(ValueError, "mismatch"):
                    mismatch.generate([{"role": "user", "content": "changed"}], [])

    def test_raw_arguments_and_terminal_safety(self):
        raw = response("[A C]")
        original = copy.deepcopy(raw)
        parsed = parse_response(raw)
        self.assertEqual(raw, original)
        self.assertEqual(parsed["tool_calls"][0]["function"]["arguments"], {"action": "[A C]"})
        self.assertIsInstance(parsed["assistant_message"]["tool_calls"][0]["function"]["arguments"], str)
        self.assertTrue(parse_response(response("[A C]", finish="length"))["truncated"])
        raw["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = "{"
        self.assertTrue(parse_response(raw)["format_error"])

    def test_full_legal_route_with_call_id_history(self):
        from agent_memory_safety.agentic.environment import build_case, legal_hanoi_route
        from agent_memory_safety.agentic.runner import run_episode
        from agent_memory_safety.agentic.cli import replay_actions
        owner = self
        class Fake:
            make_tool_message = staticmethod(OpenRouterAdapter.make_tool_message)
            def __init__(self):
                self.route = iter(legal_hanoi_route(6))
                self.index = 0
            def generate(self, messages, tools):
                if self.index:
                    owner.assertEqual(messages[-1]["tool_call_id"], str(self.index - 1))
                raw = response(next(self.route), str(self.index))
                self.index += 1
                return parse_response(raw)
        case = build_case("hanoi", 224899942, disks=6, fs_prompt_variant="no-memory-claims")
        episode = run_episode(case, Fake())
        result = replay_actions(dict(case=case, initial=episode["initial_audit"],
            events=[e["audit_event"] for s in episode["steps"] for e in s["events"]], final=episode["final"]))
        self.assertTrue(result["win_without_illegal"])
        self.assertEqual(len(episode["steps"]), 63)
