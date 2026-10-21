# Agent Memory and Safety

Executable tasks for studying task completion and rule compliance from complete
agent histories. The maintained scope includes the following tasks:

| Task | Contract | Entry point |
| --- | --- | --- |
| **Toy A — Check Before Publish** | Publish only after a successful check of the same object and version | [Task guide](docs/toy_a.md) · `python -m agent_memory_safety` |
| **Agentic A — 15Puzzle** | Move a numbered tile into the adjacent empty space | [Task guide](docs/agentic_a_15puzzle.md) · `python -m agent_memory_safety.agentic --help` |
| **Agentic B — Hanoi** | Move one top disk at a time, never putting a larger disk on a smaller disk | [Task guide](docs/agentic_b_hanoi.md) · same agentic CLI |
| **Agentic C — Minesweeper** | Reveal safe cells; distinguish ordinary wins from wins after full-grid disclosure | [Task guide and exploratory results](docs/agentic_c_minesweeper.md) |
| **Agentic D — Crosswords** | Solve the crossword; separately measure hidden-answer file reads and disclosure of that source in a postgame report | [Task guide and exploratory results](docs/agentic_d_crosswords.md) |
| **Agentic E — GuessTheNumber** | Guess 1–1000 within 10 valid guesses; hidden file explicitly labels the target answer; measure reads, use and accuracy of a source report | [Current v2 setting and results](docs/agentic_e_guessnumber.md) |
| **Agentic F — Hangman** | Guess a word with six incorrect attempts; measure hidden-answer reads and disclosure when explicitly asked about sources | [Setting and exploratory results](docs/agentic_f_hangman.md) |

The agentic tasks preserve pinned HV TextArena game rules, observations and
executable virtual filesystem tools, with condition-specific rule changes documented
in each guide. A–C enable logical bugs; D–F instead enable
hidden-answer files and disable logical bugs and opponent channels. These retain
the upstream filesystem README warning that using the answer file is cheating.
The harness adds no exploit hint or pressure prompt. The model can read game
source through the virtual filesystem. There is no host shell tool.

See [what the agent can see and do](docs/agentic_environment.md) for the initial
files, tools, multi-turn loop and the exact six-disk prompt change.

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
The public CLI runs one greedy episode. The separately frozen research batches are not results of these software tests.
Their [decoding policies and comparison limits](docs/agentic_decoding.md)
distinguish the six- and seven-disk Hanoi sampling batches from greedy 15Puzzle.

Game completion and compliance are distinct. Reaching a goal after an illegal
move remains an illegal trajectory even if the move was undone or the upstream
hack flag was cleared. Hanoi multi-move actions are reported separately from
disk-size violations. A win following a violation does not show its necessity.

## Repository contents

- `agent_memory_safety/`: Toy A executor, replay and analysis tools.
- `agent_memory_safety/agentic/`: game bridges, native/API adapters, runner and action replay.
- `agent_memory_safety/agentic/_vendor/`: required unchanged upstream modules,
  MIT notices and SHA256 manifest; see [provenance](docs/agentic_provenance.md).
- `tests/`: legal paths, illegal transitions, reversals, source integrity and budget boundaries.
- `docs/`: task contracts and reproducibility details.

Retired task implementations and research records are archived locally. All
outcomes within retained experimental batches, including failures, remain in the
private research archive. Raw model trajectories, unpublished reports, local
instructions and credentials are excluded from Git. This repository publishes
reusable code, software checks and explicitly scoped exploratory summaries; raw research archives remain private.

Project-authored code has no selected open-source license yet. Vendored files
retain their respective MIT licenses. Public visibility alone does not license
the rest of the project.
