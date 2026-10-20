# yomineko

Extracts the Japanese script from game ROMs the user owns and turns it into study
material (word list, sentences, Anki/CSV/JSON). Scope, decisions and task order are in
`docs/PLAN.md`: tick a stage off there when it lands.

## Data model

JSON is canonical; every export derives from it and checks `schema_version`.
`Script { schema_version, game, lines, words, terms }`. A `Line` carries `id`, `address`,
`raw` (exact, round-trippable), `text` (readable), `kind` and an optional translation
with a source (`official`, `dictionary`, `machine`, `reviewed`). Games are described by
data-only YAML profiles in `src/yomineko/profiles/`, keyed by ROM SHA-1.

## Guardrails (never break these)

- Never commit ROMs, archives, extracted game text, prebuilt decks, encryption keys,
  or dictionary data. Tests use synthetic ROMs built in `tests/support/synthrom.py`
  with sentences written for the tests.
- Profiles hold offsets, encodings and control codes only, never game text.
- No circumvention: no keys, no decryption. GBA/GBC/NDS/PSP dumps that need none only.
- No Nintendo or Pokemon names or art in project branding. A profile or doc may name a
  game factually.
- No telemetry, no accounts, no network calls in the extraction path. Secrets (PyPI or
  API tokens) never go in the repo, in docs, or in chat.
- Review files hold JMdict ids, ROM line ids and your own English only; a worklist contains game
  text and stays under `yomineko-out/`.
- `tools/repo_guard.py` and the hooks in `.claude/settings.json` enforce the file rules.
  Run `git status` and stage files by name before committing.

## Working

- Setup and checks: see CONTRIBUTING.md. Where the work stands and what the next session does: `docs/PLAN.md`. Use the project venv: `.venv/Scripts/python`
  (Windows) or `.venv/bin/python`.
- Install for development with `pip install -e ".[dev,analyze,web]"` (the same as CI; `analyze` is
  the tokenizer, `web` the web interface, and their tests and type checks need them).
- Check before committing (the same as CI): `python -m ruff check .`,
  `python -m ruff format --check .`, `python -m mypy`, `lint-imports`,
  `python -m pytest -m "not realrom" --cov`, `python tools/repo_guard.py --all`.
- Architecture and Python conventions: `docs/ARCHITECTURE.md`. Dependencies point down
  (cli > app > web > pipeline > extract|export|script_io|analyze|survey > profile.loader > core >
  profile.schema|profile.template|model > errors); a new
  top-level module goes into the layers contract in `pyproject.toml` in the same PR.
  Expected failures raise a `YominekoError` subclass. Type hints are required (mypy strict).
- A change to `src/yomineko/core/` needs a synthetic-ROM test.
- Real-ROM tests are opt-in (`-m realrom`, ROM path in an env variable) and compare
  counts and checksums only.
- Commits: one per plan task, authored with the repo-local git email. Work on a feature
  branch and open a PR; the owner merges. Releases and PyPI uploads are the owner's
  steps; never run `twine upload`.
- Before opening a PR, review the diff against the guardrails above and consult the advisor.

## Translation style (for the translator agent and skill)

Faithful but natural English. Keep `(name)` placeholders for the player/partner names.
Mark low-confidence lines instead of guessing. Never invent context.

## Finding out how a game stores its text

`yomineko survey ROM` (see `docs/ADDING_A_GAME.md`) prints counts and offsets only. Games are supported
through profiles of three kinds: plain Shift-JIS, compressed 16-bit glyph ids (`table16`), and byte-stream
text with commands (`table8`; with `discover.frame` when every byte value is a character, as on Game Boy
Color). Platforms: GBA and GBC. Real-ROM tests read their paths from `YOMINEKO_ROM_PMD_RED_JP`,
`YOMINEKO_ROM_GYAKUTEN_SAIBAN_JP`, `YOMINEKO_ROM_MARIO_LUIGI_RPG_JP` and `YOMINEKO_ROM_POKEMON_CRYSTAL_JP`.

## Lessons from code reviews

- A scan that starts again inside what it has just walked must remember what it found at each
  place, or hostile and merely odd input makes it quadratic. Test the amount of work (count the
  steps), not the time, and keep the plain version in a test to compare against on random input.
- Check a byte's role where the byte is read. In a layered format the same value can be a command
  in one layer and a character in another; a check that forbids every overlap breaks a real game.
  Run a new check on the real profiles before trusting it.
- When two file formats can each match the other's file by chance, let the stronger checksum
  decide, and test both directions, including the damaged-header case.
- A test must fail when the thing in its name breaks: change the input the name talks about and
  see. A name that promises more than the body shows gets renamed.
- CI runs `pytest`, not `python -m pytest`. The second puts the repository root on the import
  path, so `from tests.support...` works locally and fails in CI. Tests import `support...`;
  before a PR, run the suite once with the `pytest` program.
- Edit existing files with small replacements. Rewriting a whole file can drop characters that
  are invisible in a listing (a control character inside a string literal did go missing once).

## Agents and skills

`.claude/agents/`: rom-investigator, profile-author, vocab-reviewer, glyph-transcriber, translator,
test-writer, repo-guard. `.claude/skills/`: add-game-profile, check-game, read-glyph-table, review-vocab,
translate-lines, release. Tools behind them: `tools/game_check.py` (scorecard and verdict for a game),
`tools/glyph_render/` (character table from an emulator), `yomineko survey` with `--compare` and
`--commands`. The translator agent and translate-lines skill are placeholders until
stage 5 defines their file formats; vocab-reviewer and review-vocab are real (stage 2).

## graphify

Optional and local only: `graphify-out/` is gitignored, so a graph exists only on a machine
where someone has run `/graphify`. If `graphify-out/graph.json` is missing, ignore this section.
When it exists it holds god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
