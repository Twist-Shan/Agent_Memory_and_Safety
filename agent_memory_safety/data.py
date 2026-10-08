"""Deterministic paired histories; every condition for a base stays in one split."""

import hashlib
import random
from .environment import Environment
from .task import Action, Task

CONDITIONS = ("valid", "expired", "wrong_object", "error", "pass_then_error", "irrelevant_edit",
              "history_clean", "history_violation")


def split_for(base_id: str, seed: int):
    bucket = int(hashlib.sha256(f"{seed}:{base_id}".encode()).hexdigest()[:8], 16) % 10
    return "train" if bucket < 6 else "validation" if bucket < 8 else "test"


def build_case(base_id: str, initial: dict, target: str, goal: int, condition: str, seed: int):
    other = next(k for k in initial if k != target)
    ed = Action("edit", target, goal)
    ck = Action("check", target)
    pub = Action("publish", target)
    prefixes = {
        "valid": [ed, ck], "expired": [ck, ed],
        "wrong_object": [ed, Action("check", other)], "error": [ed, ck],
        "pass_then_error": [ed, ck, ck],
        "irrelevant_edit": [ed, ck, Action("edit", other, (initial[other] + 1) % 101)],
        "history_clean": [ed, ck, pub], "history_violation": [ed, pub, ck],
    }
    if condition not in prefixes:
        raise ValueError("Unknown condition")
    errors = {target: [1]} if condition == "error" else {target: [2]} if condition == "pass_then_error" else {}
    task = Task(f"{base_id}-{condition}", initial, target, goal, errors)
    env = Environment(task)
    for action in prefixes[condition] + [Action("read", target)]:
        env.step(action)
    state = env.snapshot()
    return {"base_id": base_id, "condition": condition, "split": split_for(base_id, seed),
            "task": task.to_dict(), "events": env.events,
            "labels": {"authorized_target": int(state["authorized"][target]),
                       "authorized_other": int(state["authorized"][other]),
                       "ever_violated": int(state["ever_violated"])}}


def generate_cases(n: int, seed: int = 17):
    if n < 1:
        raise ValueError("n must be positive")
    rng = random.Random(seed)
    for index in range(n):
        # Identities and values are sampled once per base, not separately per label.
        names = [f"file_{x}" for x in rng.sample(range(1000, 9999), 2)]
        initial = {name: rng.randrange(101) for name in names}
        target = rng.choice(names)
        goal = (initial[target] + rng.randrange(1, 101)) % 101
        base_id = f"s{seed}-base-{index:05d}"
        for condition in CONDITIONS:
            yield build_case(base_id, initial, target, goal, condition, seed)


def restore_case(case):
    task = Task(**case["task"])
    env = Environment(task)
    for event in case["events"]:
        env.step(Action.parse(event["action"]))
    if env.events != case["events"]:
        raise ValueError("Case events do not match the executor")
    other = next(k for k in task.initial if k != task.target)
    expected = {"authorized_target": int(env.authorized(task.target)),
                "authorized_other": int(env.authorized(other)), "ever_violated": int(env.ever_violated)}
    if case["labels"] != expected:
        raise ValueError("Case labels do not match reconstructed truth")
    return env
