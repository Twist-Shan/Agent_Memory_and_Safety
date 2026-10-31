# Hidden-answer software support

`agent_memory_safety.agentic.hidden_games` provides deterministic case creation,
virtual-filesystem actions and replay for six pinned upstream environments:
Crosswords, GuessTheNumber, Hangman, LogicPuzzle, Mastermind and WordSearch.
Logical bugs and opponent channels are disabled. The filesystem prompt does not
claim that scratchpad or past-game files already exist.

The bridge records whether answer content actually appeared in a file-read
response, including after a file was renamed. Directory listing alone does not
count as reading the answer. Reading, using the answer and admitting its source
are distinct observations; replay checks state transitions, not intent.

## Scope of defaults

These are shared software fixtures and historical replay support, not a new
batch runner. In particular, `guessnumber` retains the exploratory 1–20 setting;
`guessnumber1000` enforces ten distinct valid guesses within 1–1000 but retains
the upstream hidden-file label. The final Agentic E v2 condition additionally
changes that label and asks for a source report. See the [E guide](agentic_e_guessnumber.md)
and [versioned protocol](agentic_e_setting_v2.json) for that complete condition.
Likewise, the postgame reporting prompts and sampling settings for D and F are
defined in their task guides rather than in this environment bridge.

## Software validation

Install `.[api-games]` and the NLTK resources listed in the root README. Then run:

```sh
python -m unittest discover -s tests -p 'test_hidden_games.py' -v
```

Tests construct cases with seed 123, exercise answer reads and legal winning
routes, reject altered replay events, check renamed-file reads and verify the
ten-valid-guess stopping boundary. They make no API calls and require no private
research manifest. These checks generate zero model research samples.
