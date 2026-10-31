# Repository layout

## Public code and documentation

| Location | Contents |
| --- | --- |
| `README.md` | Project entry point and maintained tasks |
| `docs/` | Task guides, versioned settings, derived results and shared methods |
| `agent_memory_safety/` | Toy A environment, replay, analysis and CLI |
| `agent_memory_safety/agentic/` | Shared game bridges, model adapters, runner and replay |
| `agent_memory_safety/agentic/_vendor/` | Pinned upstream files, licenses and source hashes |
| `tests/` | Software checks; these are not model experiment samples |
| `scripts/` | Maintained utilities, including staged-secret checks |
| `.github/workflows/` | CI software validation |

Shared implementations stay together so fixes to transport or replay do not
require duplicate task copies. Task guides and settings retain their stable paths;
the [documentation index](README.md) groups them by research question.

## Local research workspace (excluded from Git)

| Location | Contents and handling |
| --- | --- |
| `Reference/Toy_A/`, `Reference/Agentic_*/` | Reports and notes grouped by selected task |
| `Reference/rubbish_bin/` | Unselected candidate tasks, retained for traceability |
| `Reference/others/` | Shared literature, papers, presentations and organization history |
| `runs/` | Frozen experiments, raw responses, evidence, captures and analysis outputs |
| `_local_archive/` | Retired implementations, historical drivers and early research notes |
| `data/generated/`, `models/` | Generated datasets and local model artifacts |
| `.env*` except `.env.example` | Private configuration and credentials |

Frozen run directories keep their original layout: source hashes, replay and
provenance may refer to those paths. File organization must not rewrite their
evidence or turn an earlier failed audit into a successful one. Historical driver
copies have an archive manifest recording original paths, byte counts and hashes.

Before publishing, stage only intended public files and run
`python scripts/check_staged_secrets.py`. Raw reports and experiment archives are
not automatically published with the code.
