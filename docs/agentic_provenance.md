# Agentic source provenance

The release vendors modules needed for Hanoi, FifteenPuzzle, Wordle, Sudoku,
Minesweeper, Crosswords, GuessTheNumber, Hangman, LogicPuzzle, Mastermind and
WordSearch:

| Project | Pinned commit | License |
| --- | --- | --- |
| HV TextArena | `318dc5644e4bd97796e6adf577909260fbfe5e6e` | MIT, original notice included |
| TextArena | `a2c896c5c84c8557d78d3d9182a066ff573daf44` | MIT, original notice included |

All 61 selected source/data/license files are unchanged and listed by byte count and
SHA256 in `agent_memory_safety/agentic/_vendor/source_manifest.json`, verified
before execution. Shared upstream files contain unused classes retained for
provenance; the original CLI exposes Hanoi/FifteenPuzzle, while the additional-game runner exposes Wordle, Sudoku and Minesweeper.

The hidden-answer bridge supports the six additional upstream games for software
checks and historical replay. This does not make all of them maintained research
tasks. The maintained D–F protocols, including task-specific changes, are linked
from the [documentation index](README.md).

The project-specific bridge, adapter and auditor are separate from these files.
They preserve original prompts, game dynamics, virtual files and tool outputs,
and add logging, native transport, stopping bounds and independent checks. The
audit's dependency on original game code is an explicit limit.

This extraction contains no model-run records, unpublished protocols, private
environment files, credentials or hardware endpoints. Historical research bundles
remain immutable locally; public-code edits do not alter a frozen running batch.
