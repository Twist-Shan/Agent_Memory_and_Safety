# Documentation index

## Tasks

| Question | Task | Guide and settings |
| --- | --- | --- |
| Does the agent check the current version before publishing? | Toy A | [Check Before Publish](toy_a.md) |
| Does it obey operation rules? | Agentic A | [15Puzzle](agentic_a_15puzzle.md) |
| Does it obey operation rules? | Agentic B | [Hanoi](agentic_b_hanoi.md) |
| Does it exploit unintended game feedback? | Agentic C | [Minesweeper](agentic_c_minesweeper.md) |
| Does it read hidden answers and report the source? | Agentic D | [Crosswords](agentic_d_crosswords.md) |
| Does it read hidden answers and report the source? | Agentic E | [GuessTheNumber](agentic_e_guessnumber.md) · [v2](agentic_e_setting_v2.json) · [historical v1](agentic_e_setting_v1.json) |
| Does it read hidden answers and report the source? | Agentic F | [Hangman](agentic_f_hangman.md) · [v1](agentic_f_setting_v1.json) |
| Does it modify protected resources? | Agentic G | [Git dedent](agentic_g_git_dedent.md) · [v1](agentic_g_setting_v1.json) |
| Does it modify protected resources? | Agentic H | [Astropy](agentic_h_astropy.md) · [v1](agentic_h_setting_v1.json) |
| Does it modify protected resources? | Agentic I | [Git log_clear](agentic_i_log_clear.md) · [v1](agentic_i_setting_v1.json) |

Each task guide states the experimental condition, results and their scope.
Final reporting is a separate measurement from whether a violation occurred.

## Shared methods and implementation

- [Environment, files and tools](agentic_environment.md)
- [Runner and audit](agentic_runner.md) · [Decoding settings](agentic_decoding.md)
- [Protected-resource measurements](agentic_resource_integrity.md)
- [Decision-site analysis](decision_site.md) · [Validation](validation.md)
- [Upstream provenance](agentic_provenance.md)
- [API smoke test](openrouter_smoke.md) · [Additional API games](hvta_extra_api.md)
- [Hidden-answer bridge](hidden_answer_bridge.md)
- [Repository layout and local archives](repository_layout.md)
