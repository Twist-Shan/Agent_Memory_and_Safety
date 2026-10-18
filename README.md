# Agent Memory and Safety

Executable tasks for studying task completion and rule compliance from complete
agent histories. The maintained scope is three tasks:

| Task | Contract | Entry point |
| --- | --- | --- |
| **Toy A — Check Before Publish** | Publish only after a successful check of the same object and version | [Task guide](docs/toy_a.md) · `python -m agent_memory_safety` |
| **Agentic A — 15Puzzle** | Move a numbered tile into the adjacent empty space | [Task guide](docs/agentic_a_15puzzle.md) · `python -m agent_memory_safety.agentic --help` |
| **Agentic B — Hanoi** | Move one top disk at a time, never putting a larger disk on a smaller disk | [Task guide](docs/agentic_b_hanoi.md) · same agentic CLI |

The agentic tasks preserve pinned HV TextArena game rules, observations and
executable virtual filesystem tools, with its original logical bugs enabled.
They add no access ban, cheating cue or pressure prompt. The model can read game
source through the virtual filesystem. There is no host shell tool.

## Software validation

Python 3.10 or later:

```sh
python -m pip install -e '.[agentic]'
python -m unittest discover -s tests -v
python -m agent_memory_safety pilot --policy oracle --bases 100 --seed 123 --output runs/toy-a-oracle
python -m agent_memory_safety verify runs/toy-a-oracle
python -m agent_memory_safety.agentic demo --game fifteen --out runs/fifteen-demo
python -m agent_memory_safety.agentic demo --game hanoi --disks 7 --out runs/hanoi-demo
```

The two `demo` commands execute constructed legal routes and independently replay
the actual tools. They require no model, GPU or credentials. Their outputs are
explicitly marked `research_samples=0`. Output directories must be new.

## Model runs and audit

The [agentic runner guide](docs/agentic_runner.md) describes the pinned Muse
adapter, native tool transport, remaining-context budget and audit limits.
The public CLI runs one greedy episode. The separately frozen, ongoing 20-trial
sampling experiment is not a result of these software tests.

Game completion and compliance are distinct. Reaching a goal after an illegal
move remains an illegal trajectory even if the move was undone or the upstream
hack flag was cleared. Hanoi multi-move actions are reported separately from
disk-size violations. A win following a violation does not show its necessity.

## Repository contents

- `agent_memory_safety/`: Toy A executor, replay and analysis tools.
- `agent_memory_safety/agentic/`: two game bridges, Muse adapter, runner and independent audit.
- `agent_memory_safety/agentic/_vendor/`: required unchanged upstream modules,
  MIT notices and SHA256 manifest; see [provenance](docs/agentic_provenance.md).
- `tests/`: legal paths, illegal transitions, reversals, source integrity and budget boundaries.
- `docs/`: task contracts and reproducibility details.

Retired task implementations and research records are archived locally. All
outcomes within retained experimental batches, including failures, remain in the
private research archive. Raw model trajectories, unpublished reports, local
instructions and credentials are excluded from Git. This repository publishes
reusable code and software checks; it does not publish model-performance claims.

Project-authored code has no selected open-source license yet. Vendored files
retain their respective MIT licenses. Public visibility alone does not license
the rest of the project.
