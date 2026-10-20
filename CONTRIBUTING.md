# Contributing

## Never commit

ROMs or archives, extracted game text, prebuilt decks, encryption keys, or dictionary
data. A profile holds offsets, encodings and control codes only, never game text.
Do not use console or game trademarks as branding; a profile may name its game
factually. `python tools/repo_guard.py --all` checks the obvious cases and runs in CI.

What the project will not help with (circumvention, keys, sharing ROMs or game content, cheats or
ROM hacks for distribution) is in [DISCLAIMER.md](DISCLAIMER.md). Issues and pull requests that ask
for any of it are closed.

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate                  # Windows; on macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev,analyze,web]"   # analyze: the tokenizer, web: the web interface; their tests skip without them
pre-commit install                      # ruff + repo guard on commit; types, layers, tests on push
```

Run everything CI runs:

```bash
ruff check . && ruff format --check .   # style, import order, likely bugs
mypy                                    # types (strict)
lint-imports                            # architecture layers
pytest -m "not realrom" --cov           # tests, 95% coverage floor
python tools/repo_guard.py --all        # no ROMs, archives or game text
```

How the code is organised, and why, is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
Read it before adding a module: a lower layer must never import a higher one, and
`lint-imports` will fail if it does.

Tests use synthetic ROMs built in `tests/support/synthrom.py`, so they run anywhere.
A change to `src/yomineko/core/` needs a synthetic-ROM test. Tests that need a real
dump are marked `realrom`, read the path from an environment variable, and compare
counts and checksums only.

## Reviewing a game's words

Kana-only text makes the matcher pick the wrong homophone about 15% of the time. A *review file*
fixes it with JMdict ids and ROM line ids only, so it can be shared. The workflow is in
`.claude/skills/review-vocab/SKILL.md`: build a worklist (`yomineko review worklist`), write
rules, check them (`yomineko review check`), and put the file in `src/yomineko/reviews/` named
after the game's profile id. The worklist contains game text; never commit it.

## Adding a game profile

The full guide is [docs/ADDING_A_GAME.md](docs/ADDING_A_GAME.md), and the `add-game-profile` skill
(`.claude/skills/add-game-profile/SKILL.md`) lets Claude Code do the steps for you. Only Japanese games
for Game Boy Advance and Game Boy Color are in scope. Four kinds of text are supported (see the guide):
plain Shift-JIS or a `.tbl`, glyph ids in BIOS LZ77 blocks (`table16`), a byte stream with commands
(`table8`), and framed messages in Game Boy Color banks (`table8` with `discover.frame`). If you find
another kind of compression, record your notes in `docs/games/<id>.md` and open a *Game support
request* instead. Never include a ROM or any game text.
The short version:

1. `yomineko profile new my-game` writes a commented skeleton.
2. Fill in `rom` (SHA-1, game code, revision), the `encoding`, text `regions` and
   control-code `plain` rules. Check the encoding on a few strings first.
3. `yomineko verify my-game.gba --profile path/to/my-game.yaml` must report that
   the rebuilt ROM matches the original checksum.
4. Put the file in `src/yomineko/profiles/`, run `yomineko profile validate`, and open a PR.
   Include string counts in the PR description, not the strings.
