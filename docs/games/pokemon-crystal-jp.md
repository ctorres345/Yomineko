# Pocket Monsters Crystal (Japan, GBC) - investigation notes

Status: **supported** (2026-10-09): profile
`pokemon-crystal-jp`, `verify` byte for byte, scorecard verdict *ready*. What was built and measured is in
"Result" below; the investigation that led to it follows, as it was written in phase 2, with two
corrections marked.
Everything here was measured on the owner's dump, read in memory. Counts, offsets and format facts only: no
game text appears in this file. The pret `pokecrystal` disassembly (of the US game) was read to know what to
look for; every value below was then found in the Japanese ROM itself.

## Result (phase 3)

| What | Number |
|---|---|
| Text regions | 20 banks (bank 0x20 only up to 0x081400: data that reads as text follows its messages) |
| Lines (one per row of the text box) | 14,184, of which 12,304 belong to a message with a pointer in its bank |
| Distinct readable lines | 12,793 (12,632 dialogue, 161 short ones) |
| `yomineko verify` | OK, rebuilt SHA-1 `95127b90...` |
| Character table | 198 entries in the file: 189 characters and 9 bytes that draw a name. The 17 bytes that draw a fixed string are listed in the profile by the offset of the string (`encoding.rom_strings`, bank 0, 0x127C-0x12C9) and read from the ROM |
| Name tables | 251 species, 251 moves, 256 items (726 distinct names) |
| Words | 3,229 (1,531 seen 3 or more times), 64 review rules, all applied |
| Deck | 1,252 word cards, 1,000 sentence cards (median 16 characters, 73 not ending like a sentence), 177 name cards |
| `tools/game_check.py` | **ready** |

**How messages are found.** `discover.frame` in the profile: text follows command 0x00, a line ends at
0x4B, 0x4C, 0x4E, 0x4F, 0x51 or 0x55, the message ends at 0x57, 0x58 or 0x5F, and 0x50 hands back to
the commands (or ends the message when it is read as one). Between two texts the 20 commands 0x01-0x15
(not 0x08) are stepped over with their parameters. A candidate is a message only if every byte fits. It
is kept when its start address is stored as a 16-bit word in its own bank, or when it has 6 kana of its
own outside the marked table entries. Measured on the 20 banks: 4,833 candidates with text, 4,481 kept
(3,865 of them by a pointer), giving 14,559 rows, of which 14,184 have 2 kana or more.

**What is not read, on purpose.** About 40 real messages with fewer than 6 such kana and no pointer in
their bank: short battle lines in bank 0x20 and short lines of bank 0x5D, the two banks that are reached
from elsewhere. Lowering the limit brings them back together with about as many chance matches in the
script banks, so the limit stays at 6. A message whose text command stream ends at command 0x08 (machine
code follows) is not read either: 1 message.

**What is read by mistake.** About 15 lines in the script banks are bytes of a map script that pass for a
message (a chance pointer, or 6 kana by chance). 11 of them are long enough to count as dialogue; the
packaged review keeps those out of the sentence deck.

**Correction: the extra tiles.** The 2bpp set at 0xF8600 described below is the one battle screens load.
Dialogue loads another: 2bpp at **0xF8000**, of which the 22 tiles from 0xF8030 go to tiles 0x63-0x78
(the load is at 0x0FB4DE). Read from a rendered sheet: 0x63-0x6C are ten bold Latin letters, 0x6D a
colon, 0x6E and 0x6F small hiragana i and u, 0x70 and 0x71 single corner brackets, 0x72 and 0x73 double
corner brackets, 0x74 a middle dot, 0x75 the ellipsis, 0x76-0x78 small hiragana a, e and o. So the codes
left open in phase 2 (0x70, 0x76, 0x77) are settled. The table has 0x6D-0x78; the letters and the codes
0x60-0x62 and 0x79-0x7E (a black square, an icon, box corners) are left out on purpose: every candidate
that holds one was script data, and without a table entry it is no message.

**Correction: the shared glyphs.** The rule "katakana when a neighbour is katakana" is wrong for `he`,
which is also a particle and follows katakana place names; it is shown as katakana only in front of a
katakana character. `ri` is not changed between a hiragana and a katakana, where it ends a hiragana word
in front of a katakana one (17 lines for the most common such word alone). 421 places are shown as katakana; two
katakana words, in 6 lines, stay in hiragana because their `ri` follows a hiragana character.

**Row length.** A line is one row, at most 18 characters, so `kinds.dialogue_min_length` is 4: with the
default 12, half the rows would count as menu terms and their words would never reach the word list.

## Gate A verdict

**Pass, with three known pieces of work for phase 3.**

- **The character table is readable, and complete.** The font is plain 1bpp tiles in the ROM, the character
  code is the tile number, and the voiced kana are fixed by four constants in the drawing routine. 177
  one-byte codes, kana only, no kanji, no emulator needed.
- **The text fits `table8` as an encoding** (one byte per character, no prefix byte), but **not the
  `table8` stream discovery as it is.** A plain run scan gets as much junk as text (see "Does a stream scan
  find the dialogue"). A framed scan (a message starts at the text-start command and runs to an end byte)
  finds it cleanly: **5,522 messages, 168,045 kana**, 4,412 of them confirmed by a pointer in their own bank.
- **There is no far-text command in the Japanese game.** The text-command table has 22 entries
  (0x00-0x15); command 0x16 (far text) exists only in the US build, so a message never jumps to another
  bank part-way. Most text sits in the bank of the script that shows it; one bank of text (0x5D) is reached
  by bank-plus-address pointers kept in other banks. Banked addresses are needed either way: the text is
  spread over 20 banks.

Work this implies for phase 3 (none of it is a blocker): the GB header and banked regions; a framed
discovery rule for `table8`; and table entries with unique texts for the word bytes and name bytes
("Fit with `table8`" below).

## Identity (certain)

| Field | Offset | Value |
|---|---|---|
| Size | | 2,097,152 bytes (128 banks of 0x4000); banks 0x60-0x7C are empty |
| SHA-1 | | `95127b901bbce2407daf43cce9f45d4c27ef635d` |
| Title | 0x134-0x13E | `PM_CRYSTAL` and one 0x00 |
| Game code | 0x13F-0x142 | `BXTJ` |
| CGB flag | 0x143 | 0xC0 (Game Boy Color only) |
| New licensee | 0x144-0x145 | `01` |
| SGB flag | 0x146 | 0x00 |
| Cartridge type | 0x147 | 0x10 (MBC3 with timer, RAM and battery) |
| ROM size | 0x148 | 0x06 (2 MiB) |
| RAM size | 0x149 | 0x05 |
| Destination | 0x14A | 0x00 (Japan) |
| Old licensee | 0x14B | 0x33 (use the new licensee field) |
| Version | 0x14C | 0x00 |
| Header checksum | 0x14D | 0x22, matches the computed value |
| Global checksum | 0x14E-0x14F | 0x9A40 (big-endian), matches the computed value |

For the Japan check: the code ends in `J` and the destination byte is 0x00; both agree here.

## Font and character table (certain)

- **Main font:** 128 tiles, 1bpp, 8 bytes each, at **0xF8200-0xF85FF** (bank 0x3E, address 0x4200). Four load
  sites copy it to VRAM 0x8800, which is tile 0x80, so **character code = tile number**: the glyph of code
  `c` (0x80-0xFF) is at `0xF8200 + (c - 0x80) * 8`.
- **Extra tiles:** 25 tiles, 2bpp, at 0xF8600 (bank 0x3E, address 0x4600), loaded to tile 0x60. Codes
  0x60-0x78: meter and status-screen pieces, and two that dialogue uses (below). A second copy of a font in
  2bpp is at 0x106613 (bank 0x41); a Latin letter set follows the extra tiles at about 0xF8D80. Dialogue
  uses neither.
- **0x7F** is the space.

Layout of the main font, read from a rendered sheet (kept locally under `yomineko-out/`):

| Codes | Content |
|---|---|
| 0x80-0xAB | katakana in gojuon order, 44 codes: the a, ka, sa, ta, na rows (5 each), **ha row with 4** (no `he`), ma row (5), ya row (3), **ra row with 4** (no `ri`), then wa, wo, n |
| 0xAC-0xB0 | small katakana: tsu, ya, yu, yo, i |
| 0xB1-0xDE | hiragana in gojuon order, 46 codes, all rows complete |
| 0xDF-0xE2 | small hiragana: tsu, ya, yu, yo |
| 0xE3 | long-vowel mark |
| 0xE4, 0xE5 | handakuten and dakuten as marks on their own |
| 0xE6-0xE8 | question mark, exclamation mark, ideographic full stop |
| 0xE9-0xEB, 0xF4 | small katakana a, u, e and o |
| 0xEC-0xEE | three arrow and cursor triangles |
| 0xEF, 0xF5 | male and female signs |
| 0xF0-0xF3 | yen sign, multiplication sign, dot, slash |
| 0xF6-0xFF | digits 0-9 |

**Shared glyphs.** The font has no katakana `he` or `ri`. Katakana words use the hiragana codes for them
(0xCD and 0xD8), and the voiced `be` and `pe` likewise (0x3D and 0x47). In the dialogue these four codes sit
next to a katakana character 387 times (291, 42, 43 and 11 for `ri`, `he`, `be`, `pe`) and elsewhere 1,930
times. The table must give each code one text (the hiragana); a `plain` rule that turns these four into
katakana when a neighbour is katakana fixes the readable text. Without it the tokenizer sees a katakana
word broken by a hiragana.

**Voiced kana are single codes.** The drawing routine (bank 0, 0x1132-0x1150) handles every code below 0x60
that is not a control character as a base kana plus a mark drawn above it. The constants are in the code:

| Codes | Rule | Meaning |
|---|---|---|
| 0x05-0x13 | base = code + 0x80, dakuten | voiced katakana, ka, sa and ta rows (15) |
| 0x19-0x1C | base = code + 0x80, dakuten | voiced katakana ha row (4, no `be`) |
| 0x26-0x34 | base = code + 0x90, dakuten | voiced hiragana, ka, sa and ta rows (15) |
| 0x3A-0x3E | base = code + 0x90, dakuten | voiced hiragana ha row (5) |
| 0x40-0x43 | base = code + 0x59, handakuten | katakana pa row (4, no `pe`) |
| 0x44-0x48 | base = code + 0x86, handakuten | hiragana pa row (5) |

That is 48 voiced codes. The roadmap risk "dakuten stored as separate characters" does not apply: the
marks on their own (0xE4, 0xE5) occur once in 150,469 kana of dialogue.

**Total: 177 one-byte codes** (128 font tiles, 48 voiced, the space), plus two extra tiles the dialogue
uses: **0x72**, an opening corner bracket placed after a speaker's name (311 uses), and **0x75**, the
ellipsis (455 uses; the word byte 0x56 draws two of them). Six font codes are never used in the dialogue
(0x96, 0xAA, 0xE4, 0xEC, 0xED, 0xF2). Open: codes 0x70, 0x76 and 0x77 (13, 62 and 55 uses) are extra tiles
whose reading is not settled; they would stay `{XX}` escapes.

**Checks on the table:** the 17 word strings the engine keeps in bank 0 decode to ordinary words with it,
and a sample of 120 decoded messages reads as normal Japanese.

## Control characters (certain: read from the dispatch code)

The character routine compares each byte with a list of control values before drawing it (bank 0,
0x1059-0x1131, 37 `cp`/`jp z` pairs). They are single bytes with no prefix and no parameters.

| Bytes | Role |
|---|---|
| 0x4F | next line of the box |
| 0x4E | next line (menus and lists) |
| 0x51 | new paragraph: wait for a button, clear the box |
| 0x55 | continue: wait, then scroll (it runs the helper 0x4B) |
| 0x4B, 0x4C | scroll helpers, rarely written directly (27 and 95 uses) |
| 0x57 | end of the message |
| 0x58 | end after a button press (battle text) |
| 0x5F | end of a reference-book entry (draws a full stop) |
| 0x50 | end of a string; inside a message it returns to the text-command layer |
| 0x52, 0x53, 0x49, 0x38, 0x39 | names read from RAM: player, rival, and three more |
| 0x14 | the player's name with an honorific chosen by the game |
| 0x59, 0x5A, 0x3F | battle subjects (target, user, opposing trainer), built from RAM |
| 0x15, 0x16 | present in the dispatch, not used in the dialogue found (0 uses) |

**Word bytes.** 17 bytes each draw a fixed string kept in bank 0 at 0x127C-0x12C9:

| Bytes | String |
|---|---|
| 0x1D, 0x1F, 0x24, 0x25, 0x4A | a particle and a space (2 characters each) |
| 0x1E, 0x22 | 2-character word endings |
| 0x56 | two ellipsis tiles |
| 0x23, 0x36, 0x37 | common words of 4, 3 and 4 characters |
| 0x35 | a 6-character route suffix |
| 0x54, 0x5B, 0x5C, 0x5D, 0x5E | nouns of 4, 4, 5, 5 and 6 characters |

They are frequent: 12,582 uses in the dialogue (0x25 alone 2,229; the 4-character noun 0x54 1,364). A word
list needs them expanded. They are also a round-trip trap: **the same strings are spelled out in ordinary
characters 232 times** (for example the 2-character particle strings 23 to 42 times each), so a table that
maps a word byte straight to its string cannot re-encode those rows.

## Text commands (certain)

A message is a stream of commands; the routine at bank 0 0x1417 reads a byte, stops at 0x50, and otherwise
jumps through the table at **0x1431, 22 entries (0x00-0x15)**. The handlers match the US build's for
0x00-0x15 byte for byte apart from addresses, so the parameter sizes are the same:

| Command | Parameters | Role |
|---|---|---|
| 0x00 | text up to 0x50, 0x57, 0x58 or 0x5F | start of text |
| 0x01 | 2 | print a string from RAM |
| 0x02, 0x09 | 3 | print a number |
| 0x03 | 2 | move the cursor |
| 0x04 | 4 | draw a box |
| 0x05, 0x06, 0x07, 0x0A, 0x0D | 0 | cursor, wait, scroll, pause |
| 0x08 | (machine code follows) | ends the command stream |
| 0x0B, 0x0E-0x13 | 0 | sounds |
| 0x0C | 1 | dots with a delay |
| 0x14 | 1 | print one of the string buffers |
| 0x15 | 0 | print the weekday |
| 0x50 | | end |

**No far-text command.** In the US build the table has 23 entries and 0x16 is "far text" (address, then
bank). In the Japanese build the table stops at 0x15; the two bytes after it are already the first handler.
So the planned "far text = bank plus address" text command does not exist here. Pointers with a bank do
exist one level up, in the data that leads to a message (bank 0x5D below); the framed scan finds those
messages without following them.

In the messages found, 0x01 is the common command (597 uses, a name or number in the middle of a
sentence); every other command has 45 uses or fewer. A message with a 0x01 in it is stored as text, 0x50,
`01 lo hi`, 0x00, more text.

## Where the text lives

Addresses are banked: **file offset = bank x 0x4000 + (address - 0x4000)** for banks 1 and up (addresses
0x4000-0x7FFF); bank 0 is addresses 0x0000-0x3FFF unchanged.

**Dialogue: 20 banks hold 4,504 messages and 150,469 kana** (messages with a clean end and either a pointer
in their bank or 8 kana or more; a bank is listed when it has 1,500 kana or more):

| Banks | Messages | Notes |
|---|---|---|
| 0x15-0x1F, 0x26-0x29, 0x2F | 3,815 | map scripts and their text, interleaved; text is 45-70% of each bank; about 95% of the candidates have a pointer in their own bank |
| 0x5D | 267 | text only (96% of the bank); reached by 3-byte pointers (bank, low, high) from other banks, found for 271 of 275 candidates |
| 0x20 | 177 | battle messages: 181 of 199 candidates end with 0x58; few local pointers |
| 0x11 | 127 | 117 end with 0x5F (reference-book entries); few local pointers. Not all entries are counted, see open items |
| 0x05 | 118 | menus and system messages |

Another 1,018 candidates (17,576 kana) are scattered over the other banks: real interface text in engine
banks mixed with chance matches. Bank 0x47 holds 492 short candidates (words for the phrase editor).

**How messages are reached.** No pointer table for dialogue. The byte in front of a message's 2-byte
address in its own bank is 0x4C 2,218 times, 0x51 379 times and 0x52 317 times: three script commands that
take a text address. Bank 0x5D is reached by far pointers kept elsewhere. Following every script is not
needed (next section).

**Name tables** (the species, move and item starts are exact; the last three lists begin a few bytes after
the offset given, behind other data, and their first entry was not pinned):

| Table | Offset | Bank | Shape |
|---|---|---|---|
| Species names | 0x05341A-0x053900 | 0x14 | **251 records of 5 bytes**, padded with 0x50 |
| Move names | 0x04163B-0x041C68 | 0x10 | 251 strings, each ended by 0x50, 2-7 characters |
| Item names | 0x0070FA-0x007856 | 0x01 | 256 strings, each ended by 0x50, 1-8 characters (unused slots repeat a filler name) |
| Trainer classes | 0x02D30C-0x02D4FF | 0x0B | about 66 strings ended by 0x50 |
| Place names | 0x0926D6-0x092832 | 0x24 | about 45 strings ended by 0x50 |
| More place names | 0x0A571E-0x0A582E | 0x29 | about 36 strings ended by 0x50 |

Other fixed 5-byte name tables exist (243 records at 0x0DF1D0, 153 at 0x117356, 99 at 0x0AFD32); what they
name was not checked. The table at 0x04854D (47 strings) is real-world place names for the mobile
adapter's sign-up and should stay out.

## Does a stream scan find the dialogue?

**A framed scan does. A plain run scan does not.**

- **Plain run scan** (what `table8` discovery does today: a run is any stretch of table bytes, kept when
  it has enough kana). Every byte from 0x80 up is a character, so code and data decode as kana. Over the
  whole ROM: 18,486 runs inside messages against **129,051 outside** (2 kana or more). Inside the 20 text
  banks only: 14,674 against 14,900 at 2 kana, 13,751 against 7,078 at 4 kana, 12,635 against 3,524 at 6.
  The Latin-letter test that filters junk for Mario & Luigi cannot help: this font has no Latin letters.
- **Framed scan** (start at a 0x00 text-start command, accept only characters, control characters and
  the commands above, and require one of the end bytes): 7,074 candidates in the ROM; 5,522 pass the
  quality rule above, and **4,412 of those 5,522 (80%) have their start address stored as a 2-byte pointer
  in the same bank**. Over all 7,074 candidates the figure is 4,463 (63.1%), against 373 (5.3%) for the
  control, the address one byte later, so chance explains little of it. With the 271 far-pointed messages of bank 0x5D, about 4,680 messages are
  confirmed by a reference.
- **What a learner would get** from the 20 text banks: 4,504 messages (4,340 unique), **14,216 box rows
  with 2 kana or more, 12,865 of them unique**, 129,471 kana bytes (150,469 kana with the word bytes
  expanded), 88% hiragana.

## Fit with `table8`

| Need | Today | For phase 3 |
|---|---|---|
| One-byte codes, no kanji | fits (`command_prefix` unset; a byte not in the table ends the run) | a `.tbl` of about 179 lines |
| Line, paragraph and end bytes | fit as run breaks: one box row per line, as for Mario & Luigi | nothing; whole sentences are the planned soft-break work |
| Word bytes (17) | a table line `HH=string` breaks `verify` on the 232 spelled-out copies | give each a unique text (a marker around the string) and strip the marker with a `plain` rule, or add un-prefixed inline tokens to the codec |
| Name bytes (9) | not in the table, so they split a sentence in two | table lines with unique placeholder texts; `plain` rules to `(name)` |
| Shared `he`, `ri`, `be`, `pe` | one text per code | a `plain` rule next to katakana (387 places) |
| Finding the text | the run scan drowns in junk | a framed rule in stream discovery: start command, allowed bytes, end bytes |
| Regions | file offsets | banked regions for a 2 MiB GBC ROM; `platform: gbc`; the GB header check |
| Name tables | not read | fixed records and 0x50-ended lists for terms and name cards |

## Open items

(Phase 3 settled the extra tiles and the name bytes; the rest stands.)

- **Whole sentences.** A sentence that runs over two rows of a box is two lines. Joining rows is the
  planned soft-break work for all three row-based games.
- **Reference-book entries** (bank 0x11): 117 found against 251 species, so most entries do not start with
  a 0x00 command or are split differently. Find the entry table before counting on them.
- **Mobile adapter text** is in the ROM (the sign-up place names at 0x04854D, the phrase words in bank
  0x47, probably parts of banks 0x40-0x46 and 0x5B-0x5F). Which of the 20 text banks, if any, hold text a
  player never sees without the adapter was not settled. Bank 0x5D is the one to check first: it is pure
  text and is reached differently from the rest.
- **The 1,018 scattered candidates** need a per-bank look: keep the engine banks with real menus, drop the
  chance matches (a pointer in the bank is the test).
- **Extra tiles 0x70, 0x76, 0x77** and whether any name byte besides the nine listed appears in text.
- **Battle text** (bank 0x20) joins the subject bytes 0x59/0x5A with a sentence tail; as rows they read as
  fragments.
- **Homophones:** the script is kana only with spaces between phrases, so the word list needs a first-pass
  review (the roadmap already expects it).
- Gold and Silver (Japan) were not looked at.

## Method

Throwaway scripts under `yomineko-out/crystal/` (git-ignored), reading the zip in memory:

1. Header fields and both checksums.
2. Font: searched for the graphics-load pattern (`ld de`, `ld hl` into VRAM, `ld bc` with bank and tile
   count), found the 128-tile load to 0x8800, rendered the tiles to a PNG sheet and read it.
3. Voiced kana: found the drawing routine by its byte pattern and read the four constants.
4. Control characters: listed the compare-and-jump pairs in front of that routine; for each word byte read
   the string its handler points at.
5. Text commands: found the command loop by its byte pattern, read the jump table, compared each handler
   with the US build's to confirm parameter sizes.
6. Framed scan over the whole ROM, pointer check per bank, byte statistics inside messages, and a
   simulation of the plain run scan.
7. Name tables: scans for fixed-stride records and for lists of 0x50-ended strings.
