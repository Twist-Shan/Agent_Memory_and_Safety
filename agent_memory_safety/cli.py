import argparse
import hashlib
import json
import platform
import subprocess
from dataclasses import replace
from pathlib import Path

from .data import generate_cases, restore_case
from .environment import Environment
from .replay import replay
from .runner import ScriptPolicy, run_episode, summarize
from .task import Task


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def metadata(args):
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    return {"schema_version": 1, "python": platform.python_version(), "platform": platform.platform(),
            "git_commit": commit, "arguments": vars(args)}


def load_model(args):
    from .whitebox import HFPolicy
    return HFPolicy(args.model, args.revision, args.device, args.precision, args.seed,
                    args.max_context, args.max_new_tokens)


def main(argv=None):
    p = argparse.ArgumentParser(description="Agent Memory and Safety research harness")
    commands = p.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="Create six current-state and two history-state conditions")
    generate.add_argument("--bases", type=int, default=100)
    generate.add_argument("--seed", type=int, default=17)
    generate.add_argument("--output", required=True)
    pilot = commands.add_parser("pilot", help="Autonomous scripted or HF full rollouts")
    pilot.add_argument("--bases", type=int, default=100)
    pilot.add_argument("--policy", choices=["oracle", "always_check", "shortcut", "hf"], default="oracle")
    pilot.add_argument("--guard", action="store_true")
    pilot.add_argument("--explicit-state", action="store_true")
    pilot.add_argument("--max-steps", type=int, default=12)
    pilot.add_argument("--capture", action="store_true")
    pilot.add_argument("--output", required=True)
    collect = commands.add_parser("collect", help="Capture pre-action residuals for controlled checkpoints")
    collect.add_argument("--data", required=True)
    collect.add_argument("--output", required=True)
    intervene = commands.add_parser("intervene", help="One local intervention then a complete continuation")
    intervene.add_argument("--data", required=True)
    intervene.add_argument("--case-id", required=True)
    intervene.add_argument("--vector", required=True, help=".npy residual or direction; never a pickle")
    intervene.add_argument("--layer", type=int, required=True)
    intervene.add_argument("--mode", choices=["replace", "add"], default="add")
    intervene.add_argument("--scale", type=float, default=1.0)
    intervene.add_argument("--max-steps", type=int, default=12)
    intervene.add_argument("--output", required=True)
    for command in (pilot, collect, intervene):
        command.add_argument("--seed", type=int, default=17)
        command.add_argument("--model", default="Qwen/Qwen3-8B")
        command.add_argument("--revision", help="Required for HF; use an immutable commit SHA")
        command.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
        command.add_argument("--precision", choices=["bfloat16", "float32"], default="bfloat16")
        command.add_argument("--max-context", type=int, default=4096)
        command.add_argument("--max-new-tokens", type=int, default=128)
    verify = commands.add_parser("verify", help="Independently replay all episode files in a run")
    verify.add_argument("run")
    probe = commands.add_parser("probe", help="Fit a grouped, validation-selected linear probe")
    probe.add_argument("--manifest", required=True)
    probe.add_argument("--output", required=True)
    probe.add_argument("--label", choices=["authorized_target", "authorized_other", "ever_violated"], default="authorized_target")
    args = p.parse_args(argv)
    if hasattr(args, "bases") and args.bases < 1:
        p.error("--bases must be positive")
    if args.command == "verify":
        files = sorted(Path(args.run).glob("episodes/*.json"))
        if not files:
            p.error("No episodes found")
        for f in files:
            ep = json.loads(f.read_text(encoding="utf-8"))
            result = replay(Task(**ep["task"]), ep["events"])
            if any(ep["result"].get(k) != v for k, v in result.items()):
                raise ValueError(f"Result mismatch: {f.name}")
        print(json.dumps({"verified_episodes": len(files)}))
        return
    if args.command == "probe":
        from .analysis import fit_probe
        print(json.dumps(fit_probe(args.manifest, args.output, args.label), indent=2))
        return
    out = Path(args.output)
    if args.command == "generate":
        rows = list(generate_cases(args.bases, args.seed))
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        print(json.dumps({"bases": args.bases, "checkpoints": len(rows), "output": str(out)}))
        return
    if args.command in {"collect", "intervene"} or args.policy == "hf":
        if not args.revision:
            p.error("HF runs require --revision (prefer an immutable commit SHA)")
    out.mkdir(parents=True, exist_ok=False)
    meta = metadata(args)
    write_json(out / "metadata.json", meta)
    if args.command == "pilot":
        policy = load_model(args) if args.policy == "hf" else ScriptPolicy(args.policy)
        meta["policy_kind"] = "language_model" if args.policy == "hf" else "scripted_control"
        if args.policy == "hf":
            meta["model"] = policy.metadata
        write_json(out / "metadata.json", meta)
        (out / "episodes").mkdir()
        episodes = []
        for case in generate_cases(args.bases, args.seed):
            if case["condition"] != "valid":
                continue
            base = Task(**case["task"])
            for condition in ("normal", "first_error"):
                task = replace(base, task_id=f"{case['base_id']}-{condition}", guard=args.guard,
                    error_attempts={} if condition == "normal" else {base.target: [1]})
                capture = out / "activations" / task.task_id if args.capture and args.policy == "hf" else None
                ep = run_episode(Environment(task), policy, args.max_steps, args.explicit_state, capture)
                ep.update({"base_id": case["base_id"], "condition": condition, "split": case["split"], "source": "autonomous"})
                replay(task, ep["events"])
                write_json(out / "episodes" / f"{task.task_id}.json", ep)
                episodes.append(ep)
        report = summarize(episodes)
        report["by_condition"] = {c: summarize([e for e in episodes if e["condition"] == c]) for c in ("normal", "first_error")}
        write_json(out / "summary.json", report)
        print(json.dumps(report, indent=2))
    else:
        import numpy as np
        from .prompts import messages_for
        model = load_model(args)
        meta["model"] = model.metadata
        meta["data_sha256"] = hashlib.sha256(Path(args.data).read_bytes()).hexdigest()
        write_json(out / "metadata.json", meta)
        rows = read_rows(args.data)
        if args.command == "collect":
            with (out / "manifest.jsonl").open("x", encoding="utf-8") as manifest:
                for index, case in enumerate(rows):
                    env = restore_case(case)
                    replay(env.task, env.events)
                    name = f"activation-{index:06d}.npz"
                    np.savez_compressed(out / name, activations=model.activations(messages_for(env.task, env.events)))
                    record = {k: case[k] for k in ("base_id", "condition", "split", "labels")}
                    record["activation_file"] = name
                    manifest.write(json.dumps(record) + "\n")
                    manifest.flush()
            print(json.dumps({"captured_checkpoints": len(rows)}))
        else:
            matches = [c for c in rows if c["task"]["task_id"] == args.case_id]
            if len(matches) != 1:
                raise ValueError("case-id must uniquely identify one controlled checkpoint")
            vector = np.load(args.vector, allow_pickle=False)
            meta["vector_sha256"] = hashlib.sha256(Path(args.vector).read_bytes()).hexdigest()
            write_json(out / "metadata.json", meta)
            class OneShotPatch:
                def __init__(self):
                    self.used = False

                def respond(self, messages, capture=None):
                    patch = None if self.used else (args.layer, vector, args.mode, args.scale)
                    self.used = True
                    return model.respond(messages, capture, patch)
            (out / "episodes").mkdir()
            for name, policy in (("baseline", model), ("intervention", OneShotPatch())):
                ep = run_episode(restore_case(matches[0]), policy, args.max_steps)
                ep["source"] = "controlled_continuation"
                replay(Task(**ep["task"]), ep["events"])
                write_json(out / "episodes" / f"{name}.json", ep)
            print("Saved baseline and intervention continuations; assigned prefix violations are not autonomous errors.")


if __name__ == "__main__":
    main()
