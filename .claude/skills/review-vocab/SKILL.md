---
name: review-vocab
description: Correct the wrong dictionary picks in a game's word list: build a worklist, write review rules, apply and check them. Use when words or meanings look wrong, or for a newly supported game.
---

Review files are the fix for the homophone problem in kana-only text. They hold JMdict ids and
ROM line ids only, so they can be shared; the worklist holds game text and must not be.

1. **Prepare.** The dictionary and tokenizer must be installed:
   `yomineko dict download` once, and `pip install "yomineko[analyze]"`.
2. **Extract and analyze.** `yomineko extract GAME.gba`, then
   `yomineko analyze yomineko-out/<id>/script.json`. (The game's packaged review, if any, applies
   automatically; `--no-packaged-review` shows the raw picks.)
3. **Worklist.** `yomineko review worklist yomineko-out/<id>/script.json` writes `worklist.txt`
   next to the script, most frequent first, skipping words a review already covers. It lists
   ambiguous words and *probable names* (nouns often followed by a title, or two kanji that always
   go together). Raise `--min-freq` to start with the words that matter most.
4. **Decide per word** with the `vocab-reviewer` agent: right (no rule), remap to another entry
   (`to`), drop (not a real word, or a character's name), or re-gloss (JMdict lists a rare sense first). A correction that
   is only usually right gets `sentence_safe: false`. See the rule shapes in the agent.
5. **Write and validate.** Put the rules in your own file (outside the repo, or under
   `yomineko-out/`): `yomineko review validate my-review.yaml`.
6. **Apply and check.** `yomineko analyze SCRIPT --review my-review.yaml`, then
   `yomineko review check SCRIPT --review my-review.yaml`. Stale rules (matching nothing) and
   unknown ids are reported; fix them.
7. **Share or package.** To ship a review with the project, put it in
   `src/yomineko/reviews/<profile-id>.yaml` with `profile:` and `rom_sha1:` set, run
   `python tools/repo_guard.py --all`, and open a PR. Counts in the description, never words.

