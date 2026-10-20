---
name: read-glyph-table
description: Work out a game's character table when its font is not stored as plain tiles, by rendering every text code in an emulator and reading the pictures. Use when `yomineko survey` finds no font and no plain text, a save state shows the text is drawn at run time, and a profile needs a `.tbl` (table8 or table16). Slow and partly manual: expect an hour or two.
---

This is the method that produced the Mario & Luigi (Japan) table: 897 entries in about two minutes of
rendering, then reading the pictures. The other method (the font is plain tiles in the ROM, as in Gyakuten
Saiban and Pocket Monsters Crystal) is in `docs/ADDING_A_GAME.md`, "Glyph-id text"; try that first, it is
cheaper. The renderer has only been used on Game Boy Advance (the mGBA core and its 240x160 screen); Game Boy
Color fonts are usually plain tiles, so a GBC game rarely needs this skill.

Rules: the ROM stays on the user's machine, nothing printed or written to the repo contains game text.
The glyph pictures and sheets are game data: keep them under `yomineko-out/`. The finished `.tbl` is a
character mapping (data), checked with `repo_guard`.

## What you need

1. The user's ROM and a **save state with a message on screen** (RetroArch or mGBA; the tool unwraps
   RetroArch and PNG states). Ask for it once; do not ask them to drive the emulator.
2. A **libretro mGBA core** (`mgba_libretro.dll` / `.so`; RetroArch ships one in its `cores` folder).
3. `pip install Pillow` for the sheets (a tool dependency, not a project one).

## 1. Find where the message is read from

`yomineko survey ROM --state STATE` reports, from the state, which background layer shows the text, that the
tiles are not in the ROM, and that they are mirrored in RAM at one buffer. That is the proof the text is
drawn at run time. Now find the **ROM offset of the message the game is reading**: the state holds a
pointer to it in RAM (for the first game it sat at one EWRAM address, found by looking for words that point
into the script region). Check it: the bytes just before that pointer are the characters the box shows.
If the script format is unknown, `yomineko survey ROM --compare OTHER` against another region's release
shows where the script is, and `--commands` measures the control codes once a draft profile exists.

## 2. Make a template

A short message that prints one character, with `{code}` where the character goes: for the first game
`FF03 FF35 20 {code} FF0C 30` (new text box, a style command, a space, the code, a wait, a terminator).
Copy the command bytes from the game's own messages. The glyph appears at a fixed place in the box.

## 3. Find the window

Render one code and look at the frame (the tool crops a window `x0,x1,y0,y1` of the 240x160 screen).
Start with the area right of the previous character; adjust until a code such as the letter for "a" lands
fully inside and nothing else does.

## 4. Render every code

```
python -m glyph_render render --core <core> --rom <rom> --state <state> --pointer 0x<offset> \
    --template "<hex with {code}>" --window x0,x1,y0,y1 --codes "00-F9,FA00-FEFF" \
    --out yomineko-out/<game>/glyphs.json
```

The code ranges are the one-byte codes and the lead-plus-index pairs of the game's scheme (change them for
another scheme). About 1,500 codes take two minutes. The output reports how many are blank (codes with no
glyph: they stay `{XX}` escapes). Then `python -m glyph_render sheets glyphs.json --out yomineko-out/<game>/sheets`
writes labelled PNGs, 128 glyphs each.

## 5. Read the sheets

Use the `glyph-transcriber` agent: it reads the sheets and proposes a transcription with a confidence per
glyph. Kana come in order (gojuon), so the first few anchors fix the rest; kanji and punctuation need care.
Check the doubtful ones against context: decode a few real lines with the draft table
(`yomineko extract` with the draft profile) and see whether they read as dialogue.

## 6. Write the table

A transcription is a text file, one `HH<TAB>character` (or `HHHH<TAB>character`) per line:

```
python -m glyph_render table transcription.tsv --out src/yomineko/profiles/<id>.tbl --header "<Game>: table8"
```

Two codes that draw the same character cannot both be in a table (it must map back uniquely): the later
one is reported as an alias, to handle with a `plain` rule in the profile. Then finish the profile and
prove it: `yomineko verify <rom>` must say OK, then the `check-game` skill.

## What to tell the user

How many codes were rendered, how many are blank, how many glyphs were doubtful and which, and what still
needs their eyes (a code you could not read goes into the notes as an open item, not into the table).
