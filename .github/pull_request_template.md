## What this changes

<!-- A few sentences. For a new game: its title and game code. -->

## Checks

- [ ] `ruff check .`, `ruff format --check .`, `mypy`, `lint-imports`, `pytest -m "not realrom" --cov`
- [ ] `python tools/repo_guard.py --all`
- [ ] A change to `src/yomineko/core/` has a synthetic-ROM test
- [ ] The diff was code-reviewed (with Claude Code: `/code-review high`) and each finding is fixed or answered here

## Adding a game? (counts only)

<!-- Never paste ROM data or game text here. -->

- Game and code:
- `yomineko verify` result (must be OK, rebuilt SHA-1 matches):
- Strings found / unique lines / dialogue / terms:
- Encoding (Shift-JIS or table) and anything unusual:

## Rules

- [ ] No ROM, archive, extracted text, deck, key or dictionary data is included
