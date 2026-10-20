---
name: add-game-profile
description: Add support for a new Japanese GBA or Game Boy Color game: investigate the user's own ROM, draft a profile, prove it with a round-trip, check it reads well, and prepare a pull request or a game-support request. Use when someone wants yomineko to support another game. Written for contributors, not only maintainers.
---

You help someone add a game to yomineko. They may not be a programmer: explain in plain
language, one step at a time, and say what you found and how sure you are. The full human guide is
`docs/ADDING_A_GAME.md`; keep both in step.

## Rules that never bend

- **The ROM stays on the user's computer.** Read it in memory (`yomineko.core.rom.base.load_rom`
  reads `.gba`, `.gbc` and one-ROM `.zip`). Never copy it into the repo, never upload it, never put it, or any
  text taken from it, in a commit, PR, issue, chat message or file under version control.
- **Findings contain offsets, counts, hex excerpts of a few bytes, encodings and control codes. Never
  game text.** The Windows console is cp1252: never print Japanese. If the user needs to see lines, write
  them to a UTF-8 file under `yomineko-out/` (git-ignored) and tell them to open it.
- **Japanese games only.** The header game code (`yomineko info`) ends in `J`. Otherwise stop and say
  yomineko reads Japanese games.
- **No circumvention.** If the game needs keys or decryption, stop; it is out of scope.
- Run nothing that sends data anywhere without asking. The only network use in the project is the
  dictionary download, and only on request.

## 0. Set up

Check the tool works: `yomineko --version`, and `yomineko profile list` (is the game already
supported? is its checksum in a profile?). If not installed: `pip install "yomineko[analyze]"`, or from
a checkout `pip install -e ".[dev,analyze,web]"`. Ask for the ROM path and the game's name.

## 1. Identify and classify

Run `yomineko info <rom>`: title, game code, revision, SHA-1, then `yomineko survey <rom> --report` (counts
and offsets only; see "Investigate" in `docs/ADDING_A_GAME.md`). If the user has another release of the same
game (the US version, say), add `--compare <other rom>`: it shows where the two differ, which is where a
Japan-only script usually is. Once a draft profile exists, `--commands <profile>` measures its control codes. Then investigate with the `rom-investigator`
agent. Output: `docs/games/<id>.md` (the id is lowercase letters, digits, dashes, like `my-game-jp`).
Classify what you find and tell the user:

| Finding | What to do |
|---|---|
| Standard Shift-JIS, uncompressed | Continue with step 2. |
| Custom character table, uncompressed | Continue; the profile uses `encoding.type: table` and a `.tbl`. Say how sure the table is. |
| BIOS LZ77 blocks behind a pointer table, text as 16-bit glyph ids | Continue; the profile uses `compressed` and `encoding.type: table16` with a `.tbl` read off the game's font. Follow "Glyph-id text" in `docs/ADDING_A_GAME.md` (find the font, map ids, find the commands' argument counts); expect a long session. `docs/games/gyakuten-saiban-jp.md` is the worked example. |
| A byte stream of one-byte codes (kanji as a lead byte plus an index) with prefixed commands, not compressed | Continue; the profile uses `encoding.type: table8` with `command_prefix`, `commands`, `line_breaks` and `text.regions`. Follow "Byte-stream text" in `docs/ADDING_A_GAME.md`; `docs/games/mario-luigi-rpg-jp.md` is the worked example. |
| A Game Boy Color game: one-byte codes where every byte value is a character, messages spread over 16 KiB banks | Continue; the profile uses `platform: gbc`, `encoding.type: table8`, `{bank: n}` regions and `discover.frame` (the command that starts text, breaks, end bytes, commands between texts). Follow "Game Boy Color: banks and framed messages" in `docs/ADDING_A_GAME.md`; `docs/games/pokemon-crystal-jp.md` is the worked example. Measure before choosing the limit for unpointed messages, and read what it loses. |
| Another compression scheme (or unknown) | **Stop.** Not supported yet. Finish the notes and go to "Not supported yet". |
| Other (needs keys, unknown scheme) | Stop and explain; write the notes. |

## 2. Draft the profile

Use the `profile-author` agent: `yomineko profile new <id>`, fill it in (rom, encoding, text regions,
`plain` rewrites for control codes and name placeholders, `tables` for names), then
`yomineko profile validate <file>`. The packaged profiles are the models, one per kind: `pmd-red-jp.yaml`
(Shift-JIS), `gyakuten-saiban-jp.yaml` (`table16`), `mario-luigi-rpg-jp.yaml` (`table8`) and
`pokemon-crystal-jp.yaml` (Game Boy Color, framed `table8`).

## 3. Round-trip

`yomineko verify <rom> --profile <file>` must say OK: the rebuilt ROM matches the original SHA-1. If not,
fix the encoding, terminator or control-code rules and repeat. Do not weaken the check.

## 4. Check that it reads well

`yomineko extract <rom> --profile <file>` then `yomineko export yomineko-out/<id>/script.json --format csv`.
Do not print the lines. Report counts (strings, unique lines, dialogue, terms), and ask the user to open
the CSV and read a few lines. Look together for: stray codes, name placeholders shown as raw bytes,
missing dialogue, quirks such as single-byte kana drawn as hiragana, glyph lead bytes. Fix with `plain`
rules or encoding settings and repeat steps 3 and 4. Never commit `yomineko-out/`.

## 5. Check the whole game

Run the `check-game` skill (`python tools/game_check.py <rom>`). It extracts, rebuilds, finds the words,
builds the deck, opens it and gives a verdict with named limits. Read its `samples.txt`. A game ships as
*works, with limits* at the least; *broken* does not ship.

## 6. Optional: word picks

If the analysis extra and dictionary are available, see `.claude/skills/review-vocab/SKILL.md` for a
review file (dictionary ids and the user's own English only).

## 7. Guard and submit

1. Run `python tools/repo_guard.py --all` and the `repo-guard` agent on the diff.
2. Files to include: `src/yomineko/profiles/<id>.yaml` (and its `.tbl`), `docs/games/<id>.md`, and a
   review in `src/yomineko/reviews/<id>.yaml` if you made one. Nothing else.
3. Run the checks from CONTRIBUTING.md (`ruff`, `mypy`, `lint-imports`, `pytest -m "not realrom"`).
4. Branch, commit by file name (`git add <file>`, never `git add -A`), push, and open a PR with
   `gh pr create --body-file <file>`. If the user has no write access, they fork first. The PR
   description has **counts and the verify result**, never text. Use the repo's PR template.
5. Maintainers merge. Do not merge for them.

## 8. What did this game teach the tool?

Every game should leave the tool a little better. Before you finish, ask: what did I do by hand that a
command could do, and what did the tool get wrong that it should get right for the next game? Examples
from the first four: a survey check that was missing (comparing two regions, measuring control codes), a
matcher bug that only a kana-heavy game showed, a quality measure the scorecard lacked. Write the answer
in one or two lines under "Lessons" in `docs/PLAN.md`, and when it is small, do it (a check in
`tools/game_check.py`, a survey detector with a synthetic test, a line in this skill or in
`docs/ADDING_A_GAME.md`). When it is large, add it to the plan as a task.

## Not supported yet

Still valuable. Finish `docs/games/<id>.md` (identity, layout, where the text is, the compression or
scheme, what is unknown). Then open a **game support request** (the issue form in the repo) with the
notes, or open a PR with only the notes file. Explain to the user that this tells the project which
features to build next; do not write a profile that cannot pass the round-trip.
