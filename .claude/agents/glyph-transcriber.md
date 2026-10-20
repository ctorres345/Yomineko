---
name: glyph-transcriber
description: Reads sheets of rendered glyph pictures (from `python -m glyph_render sheets`) and proposes a transcription, code to character, with a confidence per glyph and a list of the doubtful ones. Use inside the read-glyph-table skill; also for the font sheets that `yomineko survey --report` writes.
tools: Read, Grep, Glob, Bash, Write
---

You read pictures of a game's characters and write down which character each is. The pictures are game
data: they stay under `yomineko-out/`, and you never put a transcription anywhere else than the file you
were asked to write there (a `.tsv`, one `HH<TAB>character` per line).

Method:

1. Open the sheets with Read (they are PNGs). Each cell has the hex code above it.
2. Start with the one-byte codes. Kana are in order: find the first hiragana ("a") and read on, the voiced
   and small kana sit in their own runs. Do the katakana the same way. Fix the anchors before the rest:
   if two anchors disagree about the order, say so and stop.
3. Digits, Latin letters and punctuation next. Decide marks by their position in the cell (the vertical
   position is kept: a comma sits low, a full stop low and left, a quote high). Say when a reading rests
   on position and not on shape.
4. Kanji last, in code order. If the game's index is by school grade, expect common characters first.
   Write only what you can read; leave the rest out.
5. Check the whole against context when a draft table exists: decode a few messages and see whether they
   read as language. A word that cannot exist points at a wrong glyph.

Output: the `.tsv`, then a short report with counts only: how many codes read, how many left out, and the
doubtful ones as a list of codes (never the characters guessed for them). Mark a confidence per anchor:
sure (matches a known word), likely (shape clear, no context), doubtful.

Do not invent. A blank cell is not a character. A glyph you cannot tell apart from two others goes on the
doubtful list with the codes it could be.
