# Adding a game to yomineko

yomineko reads a game through a **profile**: a small YAML file that says where the game keeps its
text, how the characters are encoded and what its control codes mean. One profile per game. This
guide is for anyone who wants their game supported and is willing to do (or help an AI assistant
do) the detective work. You do not need to be a programmer, but you need patience.

## Before you start

- **You need your own dump** of the game (a `.gba` or `.gbc` file, or a `.zip` with one ROM). Game Boy
  Advance and Game Boy Color are the two consoles supported. Never send a ROM,
  or any text taken from one, to anyone, in an issue, in a PR or in a chat. Profiles and notes only ever
  contain **offsets, counts, encodings and control codes**.
- **Only Japanese games** are supported. The cartridge header has a four-letter game code; Japanese
  games end in `J` (`yomineko info game.gba` shows it). `extract`, `verify` and the web upload refuse any
  other code, and a profile's `rom.game_code` must end in `J`; `yomineko survey` still runs on any ROM.
  (An older Game Boy cartridge has no code; its header's destination byte must say Japan. A profile for
  one is not possible yet, since a profile needs a code.)
- **Install the tool** with the analysis extra: `pip install "yomineko[analyze]"` (see the
  [README](../README.md)), or from a checkout for development ([CONTRIBUTING](../CONTRIBUTING.md)).
- Check the list of supported games first: `yomineko profile list`.

## What is realistic

How hard a game is depends on how it stores its text:

| The game stores text as | Today |
|---|---|
| Standard Shift-JIS, not compressed (like Pokemon Mystery Dungeon) | A profile can be written in hours. |
| A custom character table (a `.tbl`), not compressed | Supported: the profile points to the table. You need to work the table out (often documented by fan translators). |
| BIOS LZ77 blocks behind a pointer table, text as 16-bit glyph ids (like Gyakuten Saiban) | Supported: the profile has a `compressed` block and `encoding.type: table16`. The hard part is the character table, which you read off the game's font (see "Glyph-id text" below). Allow a day or more. |
| A continuous byte stream of one-byte codes (kanji as a lead byte and an index) with `0xFF`-style commands, not compressed (like Mario & Luigi RPG) | Supported: `encoding.type: table8` and `text.regions` (see "Byte-stream text" below). The hard part is the character table. |
| One-byte codes where every byte value is a character, in messages spread over the banks of a Game Boy Color cartridge (like Pocket Monsters Crystal) | Supported: `platform: gbc`, `encoding.type: table8`, banked `text.regions` and `discover.frame` (see "Game Boy Color: banks and framed messages" below). The font is usually plain tiles, so the table is quick; the hard part is the frame. |
| Another compression scheme (RLE, Huffman, a custom one) | **Not supported yet.** Record what you found (step 1) and open a game request. |

Many Japanese games use a custom table, compression, or both. Plain Shift-JIS is the exception.
Finding out how a game stores its text is useful work even when you stop there.

## Step by step

### 1. Investigate

Find out, for your ROM: the header details and checksum, where the text is, how it is encoded and
whether it is compressed. `yomineko info game.gba` prints the header and SHA-1.

**Start with `yomineko survey game.gba`.** In a few seconds it prints counts and offsets (never text)
for the checks below: how much of the image is fill, the BIOS-compressed streams, plain Shift-JIS runs,
pointer and offset tables and what they lead to, font candidates, and 16-bit glyph-id streams (also
inside decoded LZ77 blocks). Its "Leads" list says which case your game looks like. Extra checks: `--word`
(a word you know is in the game, in kana: finds a table that keeps gojuon order; the word is not
printed), `--state FILE` (a RetroArch or mGBA save state taken while a message is on screen: shows
whether the text tiles come from the ROM or are drawn into RAM) and `--report` (writes
`yomineko-out/<id>/survey.md` and PNG sheets of the font candidates), `--compare OTHER.gba` (another
release of the same game, for instance the US one: shows the constant shifts between the two and the
ranges that exist in one only, which is where a Japan-only script usually is) and `--commands PROFILE`
(once a draft profile exists: how often each control code occurs, what surrounds it, how many parameters
it seems to take, which commands look like they end a line and, for glyph ids, which command arguments
read as text and need a `skip`).

- **Where is the text?** Text is usually reached through tables of 32-bit pointers
  (`0x08xxxxxx` on GBA; on Game Boy Color, 16-bit addresses inside a bank, see "Game Boy Color" below). `yomineko extract game.gba --profile my-game.yaml` (with the skeleton from
  step 2) reports how many strings it found and in how many groups.
- **Is it Shift-JIS?** Set `encoding.type: shift_jis`, extract, and look at the exported lines
  (`yomineko export ... --format csv`). Real lines read as sentences. A scan can show hundreds of
  "kana-looking" runs that are really code or graphics; trust only lines that make sense and rebuild.
- **Is it a custom table?** Strings look like noise but use a small repeated alphabet. You need a
  `.tbl` file, the usual ROM-hacking format: one `HEX=text` pair per line, `*HEX` for the line break,
  `#` for comments.
- **Is it compressed?** BIOS LZ77 streams start with the byte `0x10` followed by a 24-bit size.
  Graphics use the same scheme, so a ROM holds a thousand of them; the script is the few large ones
  (tens of kilobytes) reached through a pointer table. Go to "Glyph-id text" below.

Write what you learn in `docs/games/<game>.md`: counts, offsets and short hex excerpts. **No text.**

### 2. Draft the profile

```bash
yomineko profile new my-game          # writes my-game.yaml, a commented skeleton
yomineko profile validate my-game.yaml
```

Fill in:
- `rom`: SHA-1, game code, revision (from `yomineko info`).
- `encoding`: `shift_jis` or `table` (with `table: my-game.tbl` next to the profile), the terminator
  byte, and quirks such as `single_byte_kana: hiragana` or `custom_leads` for icon glyphs. For
  glyph ids: `table16`, the table (`HHHH=character`, the 16-bit id in hex), and `skip` (see below).
- `text.regions` and the pointer settings: where to look for strings.
- `plain`: rewrites that turn control codes into readable text (new lines, colour codes, name
  placeholders such as the player's name).
- `tables`: lists of names (items, moves, places) that become term cards. A table is `count` entries
  from `base`: text pointers `stride` bytes apart (the default), or the names themselves, as
  `kind: records` (`stride` bytes each, padded with the terminator) or `kind: strings` (one after
  another, each ended by the terminator).
- Optional `sentences`: address ranges to keep out of sentence decks and caps for repetitive lines.

The packaged `src/yomineko/profiles/pmd-red-jp.yaml` is a complete example.

### 3. Prove it with a round trip

```bash
yomineko verify my-game.gba --profile my-game.yaml
```

It rebuilds the ROM from the extracted text and compares checksums. It must say **OK**: the rebuilt
ROM matches the original byte for byte. If not, some strings do not re-encode exactly; fix the
encoding, terminator or control-code rules.

### 4. Check it reads well

```bash
yomineko extract my-game.gba --profile my-game.yaml
yomineko export yomineko-out/<id>/script.json --format csv
```

Open the CSV and read some lines. Check that:
- sentences read naturally, with no stray codes or boxes;
- the player's name and other placeholders show as a placeholder, not as raw bytes;
- most dialogue is found (compare the count with what you expect from the game's size);
- names and terms are in their own list.

Do **not** commit the output: it contains the game's text.

### 5. Optional: improve the word picks

The game is written in kana, so the dictionary sometimes picks the wrong word. With the analysis
extra and the dictionary (`yomineko dict download`), `yomineko analyze` finds the words, and the
review screen in the app (or `yomineko review worklist`) shows the ambiguous ones. A review file holds
dictionary ids and your own English only, so it can be shared. See `.claude/skills/review-vocab/SKILL.md`.

### 6. Submit it

1. Put the profile in `src/yomineko/profiles/<id>.yaml` (and the `.tbl` next to it if there is one).
   The `id` is lowercase letters, digits and dashes, for example `gyakuten-saiban-jp`.
2. Add your notes as `docs/games/<id>.md`.
3. Run the checks: `yomineko profile validate` and `python tools/repo_guard.py --all` (it refuses ROMs,
   archives and long runs of Japanese text).
4. Open a pull request. Give the **counts** (strings found, lines, dialogue, terms) and the
   `yomineko verify` result in the description. Never paste text.

A maintainer will review it. Profiles are accepted when they validate, verify and read well.

## Glyph-id text (compressed or not)

Some games store each character as the index of its glyph in the game's font, in 16-bit words mixed
with command words. `docs/games/gyakuten-saiban-jp.md` is a worked example; the steps:

1. **Find the blocks.** A pointer table whose targets are LZ77 streams; each block starts with an
   entry count and that many entry offsets. `yomineko` reads them with the profile block
   `compressed: {scheme: lz77, tables: [{base: 0x..., count: N, stride: 4}], min_chars: 2}`. Lines in
   a block get virtual ids starting with `C`. A block of the same layout that the game keeps without
   compression is listed by its file offsets: `uncompressed: [{start: 0x..., end: 0x...}]`.
2. **Find the font.** It is graphics, usually uncompressed 4bpp with one ink colour (bytes made of
   only a few values such as `00 03 30 33`). Mark which positions inside a 128-byte unit are ever
   inked: the empty margins show the glyph size and where a glyph starts. Render glyph sheets to PNG
   (under `yomineko-out/`) and read them.
3. **Map ids to characters.** Hiragana in gojuon order is the easy anchor: match the id frequencies
   of the script against kana frequencies (a very common id is the particle no, a rare one is nu).
   The rest follows the font order; kanji you transcribe from the sheets. Write the `.tbl` (one
   character per id, all different) and check by decoding a few lines into a UTF-8 file.
4. **Skip the arguments.** Commands are small words followed by arguments, and an argument can have
   the value of a glyph id. `encoding.skip: {0x0E: 1, ...}` lists the commands and how many words
   follow; those words are never text. The statistics that find them: a glyph that starts a run far
   more often than chance, and the word that comes before it. One-character runs are dropped.
5. `yomineko verify` checks every line against the decompressed block.

Not every game is like this; if yours is not, the next section applies.

## Byte-stream text

Some games keep the script as a continuous stream of one-byte codes (a kana is one byte, a kanji is a
lead byte and an index byte) with commands in the middle, and no pointer to each line.
`docs/games/mario-luigi-rpg-jp.md` is a worked example. The profile uses `encoding.type: table8`:

- `table`: a `.tbl` with `HH=char` for one-byte codes and `HHHH=char` for two-byte codes. Every code
  maps to a different character. A code you did not solve stays in the line as a `{XXXX}` escape.
- `command_prefix` (for example `0xFF`) and `commands`: each command byte and how many parameter
  bytes follow it (`-1`: up to the next prefix byte). Parameters are never text, even if they look
  like kana.
- `line_breaks`: the commands that end a line (end of page, new box, event record). The other
  commands sit inside a sentence and are kept in the line as `{FF}{0B}{01}` escapes, which the
  readable text drops.
- `text.regions`: the byte ranges that hold the stream. Keep them tight: graphics data next to the
  script decodes into plausible-looking junk. `discover.stream_min_chars` and `stream_min_jp_ratio`
  drop runs that are too short or full of Latin letters.

How the table is found when the font is not in the ROM as plain tiles (the method is reusable):

1. `yomineko survey` finds the script's command bytes (a repeated `FF xx` chain) and where they end.
2. A **save state** taken while a message is on screen holds a pointer into the message being read;
   the bytes right before it are what the box shows. That gives a few code-to-glyph pairs and the
   structure (one-byte kana, prefixed kanji).
3. To get every glyph, **render the codes in an emulator and read the pixels** (the tool is
   `python -m glyph_render`, the method is the `read-glyph-table` skill): load the ROM into a
   libretro core with Python (ctypes), patch the message bytes in the ROM image *before* loading it
   (the core copies the ROM), load the state, and run about 70 frames per code; the glyph lands at a
   fixed cursor position in the box and can be cropped from a screenshot or the tile buffer. Keep the
   vertical position of each glyph (a comma and an apostrophe differ only in height). Draw the glyphs
   on labelled sheets and read the kana (they come in gojuon order) and the kanji that the script uses.
4. If another region's version of the game has the same engine and a readable script (here the US ROM),
   it is the answer key for the command set and parameter sizes.
5. `yomineko verify` rebuilds the script bytes from the lines; the readable text is checked by
   running `analyze` and looking at words. The last step of any new game is
   `python tools/game_check.py <rom>`: it reads the whole game the way a learner would and gives a
   verdict (ready, works with named limits, broken).

## Game Boy Color: banks and framed messages

`docs/games/pokemon-crystal-jp.md` is a worked example. A Game Boy cartridge is a row of 16 KiB
*banks*. Bank 0 is always visible at addresses 0x0000-0x3FFF; one other bank at a time is switched in
at 0x4000-0x7FFF. So an address does not say which bank it is in, and
**file offset = bank x 0x4000 + (address - 0x4000)** for bank 1 and up. In a profile:

- `platform: gbc`, and `text.pointer_base: 0`, so a line's id is its file offset.
- `text.regions` lists the banks that hold text, each as `{bank: 0x15}` (the whole bank). A plain
  `{start, end}` in file offsets still works, for a bank that is text only in part.
- `tables` take file offsets.

Text on these consoles is often one byte per character with no prefix, and **every byte from 0x80 up
is a character**. A plain run scan then reads code and data as kana (in this game, about as many junk
runs as real ones inside the text banks), and there are no Latin letters to tell them apart. Describe
the frame of a message instead, and text is read from whole messages only:

```yaml
discover:
  frame:
    start: 0x00                  # the command that text follows
    breaks: [0x4F, 0x51, 0x55]   # in text: next line, paragraph, scroll (each ends a line)
    ends: [0x57, 0x58]           # in text: the message is over
    resume: 0x50                 # in text: commands follow; as a command: the message is over
    commands: {0x01: 2, 0x02: 3} # commands between two texts: parameter bytes to step over
  unreferenced: {min_japanese: 6}
  ignore: ['<[^>]*>']
```

A candidate is a message only if every byte fits: a table code or a break inside text, a known command
between texts, and a real end. (The start command, a break, an end or the `resume` byte cannot also be a table code; a
command between texts can share its value with a character, since it is not read as text. A frame
cannot be combined with `encoding.command_prefix`.) It is kept when a pointer in its own bank leads to it (the address of its
`start` byte, as a 16-bit word somewhere in that bank), or when its text has at least
`unreferenced.min_japanese` kana and kanji of its own; what the `ignore` patterns remove does not
count. Lines of a pointed-at message are marked `referenced`. To find the frame, read the game's
character routine: the bytes it compares before drawing are the control characters, and the jump
table of the routine that reads a message gives the commands and their sizes. A disassembly of
another region's release of the same engine is an answer key for what to look for; copy nothing
from it, and confirm every value in your own ROM.

Things this kind of game does, and how the table and `plain` rules handle them:

- **A byte that draws a fixed string** (a common word the text engine keeps once and draws for one
  byte). The string is game text, so it does not go into the table file or the profile. List where it
  is instead: `encoding.rom_strings: {0x54: 0x1294}` (byte, then the file offset of the string, which
  is table codes up to `encoding.terminator`). yomineko reads it from the user's ROM and gives the
  byte the table text `<string>`. The marks matter: without them the same word spelled out in ordinary
  characters would re-encode to the one byte and `verify` would fail.
- **A byte that draws a name from memory** (the player's name and the like). Give it a marked, unique
  table text of your own, such as `52=<name52>`.
- Remove the marks with `plain` rules: `{pattern: '<name[0-9A-F]{2}>', replace: 〇〇}` (the name
  placeholder), then `{pattern: '[<>]', replace: ''}`. A replacement is inserted as written; there are
  no `\1` groups. List the marked entries in `discover.ignore` (`'<[^>]*>'`) so they do not count as
  a message's own text (script bytes often read as those).
- **Two characters, one glyph.** A font can leave out a katakana that looks like its hiragana and use
  the hiragana code inside katakana words. The table gives the code one text; `plain` rules with a
  look-behind or look-ahead show it as katakana next to a katakana character. Read the contexts in
  your own output before writing them: a particle after a katakana noun must stay hiragana.
- **Every byte the text uses needs a table entry**, or the frame rejects the whole message. Leave out
  the codes that are graphics (meter pieces, box corners): data that happens to hold them is then not
  a message either.
- **Name tables** hold the names themselves (`kind: records` or `kind: strings`), and
  `encoding.terminator` is the byte that pads or ends them.
- **Short rows.** A line is one row of the text box. Set `kinds.dialogue_min_length` low enough that
  rows count as dialogue, or their words never reach the word list.

## If something else is going on (or you got stuck)

Please attach the output of `yomineko survey --report` (numbers only) and open a **game support request** (the issue form in this repo) with your notes: game
title, code, checksum, what you found (for example "script in LZ77 blocks behind a pointer table at
0x...") and how sure you are. That tells the project which features to build next, and
[docs/games/gyakuten-saiban-jp.md](games/gyakuten-saiban-jp.md) shows what good notes look like.

## Doing it with an AI assistant

The repository includes a skill for Claude Code (`.claude/skills/add-game-profile/SKILL.md`) and
agents (`rom-investigator`, `profile-author`, `repo-guard`) that do the steps above for you. Open
the project in Claude Code and say, for example: *"Add support for my game using the add-game-profile
skill. My ROM is at <path>."* The assistant reads your ROM on your computer and does not need to
upload it, but check what any tool you use sends to its provider, and keep to the rules above:
**no ROM and no game text in anything you share**. Using an assistant costs whatever your own account
costs; the project provides no credits.

## Rules, once more

- No ROMs, archives, extracted text, decks or encryption keys, ever.
- No trademarks or game art in the project's branding; a profile may name its game factually.
- No circumvention: yomineko does not break encryption. Games that need keys are out of scope.
- Profiles are data (offsets, encodings, control codes), under the project's licence.
