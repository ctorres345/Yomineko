---
name: check-game
description: Check a supported game end to end the way a learner would use it (extract, rebuild, words, deck, sentences) and get a scorecard with a verdict. Use after adding or changing a game profile or review, before a release, and whenever someone asks "does this game work?".
---

This is the measurement behind every claim about a game ("ready", "works, with limits"). It runs on the
user's own ROM and prints counts only; the game text it needs you to read goes to a private file.

## Run it

Needs the analysis extra and the dictionary (`yomineko dict download`). With the project venv:

```
python tools/game_check.py "<path to the ROM or zip>" --out yomineko-out/<game id>
```

It writes `check.md` (counts only: safe to quote) and `samples.txt` (game text: the top 60 words, 100
sentences spread over the deck, the probable names; never commit or share it). The exit code is 1 only
when the verdict is *broken*.

## Read the verdict

- **ready**: the text rebuilds the ROM, no escape code reaches a card, almost every card ends like a
  sentence, no repeats, hardly any character names left in the word list, name or term cards exist, and
  every review rule still matches something.
- **works, with limits**: usable, and the limits are named. Say them to the user in plain words; they go in
  the README game table and in `docs/PLAN.md`.
- **broken**: do not release. Typical causes and where to look:
  - *the text does not rebuild the ROM*: the profile (encoding, regions, commands); `yomineko verify`.
  - *raw escape codes reach the cards*: a control code the profile keeps as `{XX}` inside a line; add a
    `plain` rule or mark it a line break (`yomineko survey --commands <profile>` shows what each code does).
  - *word cards without a meaning*, *dictionary credit missing*: a bug in the export, not in the profile.

## Then read `samples.txt` yourself

The numbers cannot tell a wrong dictionary pick from a right one. Read the top 60 words and the 100
sentences from the file (never print Japanese to the Windows console; open the file):

- A word that is a verb stem, a particle or a sound effect mapped to an unrelated noun: a review rule
  (`review-vocab` skill). If many verbs written with kanji are wrong, suspect the matcher, not the review.
- A character name listed as a word: `drop` it (the "probable names" section lists the likely ones).
- Sentences that stop mid-sentence, are menu text or debug strings: `sentences.exclude_ranges` or caps in
  the profile, or `sentences.exclude` ids in the review.

Fix, run the check again, and keep the numbers from the last run in `docs/PLAN.md`.

## Adding a new check

The thresholds are constants at the top of `tools/game_check.py` (`MAX_UNCLOSED`, `MAX_NAMES`,
`MIN_WORDS`). When a game shows a new kind of problem, add the measurement and a `judge()` rule with a test
in `tests/test_game_check.py`, so the next game is checked for it too.
