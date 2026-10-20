# Gyakuten Saiban (Japan) (Rev 1) - investigation notes

Status: supported (profile `gyakuten-saiban-jp`). The script is 17 LZ77 blocks (GBA BIOS type 0x10)
and one uncompressed block of 16-bit glyph ids; the character table was read off the font. No game
text appears in this file.

## Identity (certain)

| Field | Value |
|---|---|
| Header title | `GYAKUTEN_SAI` (12 bytes, truncated) |
| Game code | `ASBJ` |
| Revision (header version byte) | 1 |
| Size | 8,388,608 bytes (8 MiB); data ends about 0x7C1000, 0x7C8000 to the end is 0xFF fill |
| SHA-1 | `ea7dabc4f5330c89a341ca38067fb025de73c835` |

## Layout (by entropy, pointer and LZ77 scan; confident)

| Range | Content |
|---|---|
| 0x000000-0x0FFFFF | ARM/Thumb code and tables (function-pointer tables at e.g. 0x361C, 0x4A80, 0x7934C, 0x11DBAC, 0x11DC08, all targeting Thumb prologues `b5 xx`) |
| 0x100000-0x11FFFF | data / sample-like bytes |
| 0x120000-0x17FFFF | 0xFF fill |
| 0x180000-0x1C0000 and 0x240000-0x4xxxxx | LZ77 graphics blocks (fixed sizes 1920, 3840, 5120, 7680, 10240, 38400 bytes: tiles, sprites, 240x160 backgrounds) |
| 0x1C0000-0x23FFFF, 0x440000-0x73FFFF | uncompressed 4bpp-like graphics and data (dominant bytes 0x00, 0x11, 0x22, 0xEE, 0xCC) |
| 0x749428-0x74A213 | one uncompressed script block (found in YOM-60, see "Reading the game's code with Ghidra") |
| 0x74A214-0x7C0FFF | 17 large LZ77 blocks: the script (see below) |

A naive Shift-JIS run scan finds about 1250 "kana-looking" runs; all checked ones are in
code or sample/graphics data, i.e. false positives. The game has no plain Shift-JIS text.

## Script location (high confidence it is the script, medium on exact semantics)

A pointer table of 17 words at 0x18738 to 0x18778 (stride 4, base 0x08000000) points to
17 LZ77 (header byte 0x10) blocks:

| # | ROM offset | decompressed size | old entry guess (wrong, see below) |
|---|---|---|---|
| 0 | 0x74A214 | 54032 | 28 |
| 1 | 0x74FC3C | 55674 | 37 |
| 2 | 0x7560F8 | 79298 | 39 |
| 3 | 0x75E1F4 | 59126 | 50 |
| 4 | 0x764A04 | 59246 | 27 |
| 5 | 0x76ADEC | 52778 | 35 |
| 6 | 0x770E54 | 51100 | 24 |
| 7 | 0x77659C | 73056 | 57 |
| 8 | 0x77E608 | 67872 | 32 |
| 9 | 0x785574 | 46130 | 36 |
| 10 | 0x78A6A0 | 59872 | 24 |
| 11 | 0x7907B4 | 74532 | 43 |
| 12 | 0x798A18 | 72052 | 33 |
| 13 | 0x79FFE0 | 85714 | 55 |
| 14 | 0x7A975C | 66428 | 25 |
| 15 | 0x7B0350 | 61604 | 26 |
| 16 | 0x7B7150 | 109494 | 30 |

## Decompressed layout (verified 2026-10-04 with `core/containers.py` on the owner's dump)

Each block opens with a little-endian u32 **entry count** `n`, then `n` u32 words; the first word
is `4 + 4n` (where the data starts) in all 17 blocks. The earlier note "first word is 4 x entry
count, 601 sub-entries" was wrong.

Counts `n` per block, 0 to 16: 115, 149, 158, 202, 109, 141, 97, 229, 128, 147, 98, 173, 132, 220,
103, 105, 121. Total 2,427 words. All offsets are even.

In 16 of 17 blocks (all but block 2) the last 1 to 35 words are **not offsets**: they are larger
than the block, their low 16 bits are small (often 0x0002) and their high 16 bits mostly
increase. What they are is unknown (a second table of u16 pairs?). The reader keeps the leading
run of increasing in-block offsets and ignores the rest, so the real entry count is 2,427 minus
those tails.

Entry data is 16-bit little-endian values. Block 0 has 742 distinct values; the commonest are
0x0C, 0x01, 0x02, 0x00, 0x178, 0x1E, 0x16E, 0x176, 0x0E, 0xC1, 0x1B, 0xD4, 0xCF. Values below
about 0x40 look like commands with arguments; 0x80-0x1FF look like glyph ids; a run such as
0x1D0, 0x1D1, 0x1D2 in order of first use suggests per-entry dynamic ids. **Unverified.**

## Font and character table (solved 2026-10-04)

Script values are glyph ids into the game's font; the table was read off the font itself.

- **Where:** 4bpp, two-colour (ink nibble 3), 16x16 glyphs of 128 bytes each, four 8x8 tiles in
  row-major order (top-left, top-right, bottom-left, bottom-right). Glyph for script id `v` is at
  `0x1D40AC + (v - 0x9F) * 128`, i.e. `0x1CF12C + v * 128`; the table runs to id 0x5CF (ends at
  0x1FD92C, a pointer the game's code also uses). Ids 0x5C8-0x5CF are blank.
- **Id layout:** 0x80-0x89 digits, 0x8A-0xA3 A-Z, 0xA4-0xBD a-z, 0xBE and 0xBF the ! and ? signs,
  0xC0-0xED hiragana in gojuon order (a, i, u, ... n), 0xEE-0x106 voiced hiragana, 0x107-0x10F small
  hiragana and the small tsu, 0x110-0x13D katakana, 0x13E-0x156 voiced katakana, 0x157-0x160 small
  katakana and vu, 0x161-0x180 punctuation and symbols (comma 0x16E, full stop 0x176, ellipsis
  0x178, ideographic space 0x17F), 0x181-0x5C7 kanji in order of first use by the game (1,103 glyphs,
  1,086 used). 1,352 glyphs in all, one character each, no gaps.
- **How it was found (reusable for other games):** a 4bpp region whose bytes are only 0x00, 0x03,
  0x30, 0x33 is a one-colour font. A per-position "ever inked" mask over 128-byte units showed the
  cell geometry (blank margins) and the half-glyph phase; the left/right 8-pixel windows shifted by
  a constant, which gave the unit start. The id offset came from comparing script id frequencies with
  hiragana frequencies in gojuon order (the first anchors: "n" very common, "nu" rare, "no" common).
  The kanji were then transcribed by eye from labelled sheets; template matching against a system
  font failed (too different in style). Checked by decoding real entries into readable sentences.
- **Script stream:** 16-bit values. Values 0x80-0x5C7 are glyphs; small values are opcodes with
  arguments, and an argument can itself be in the glyph range (a stray kana in the decode is an
  argument, not text), so the stream needs per-opcode argument counts. Seen so far: opcode 0x01
  separates lines, 0x0E is followed by a speaker word (0x0200, 0x0700, 0x0800, 0x0A00 ...),
  0x1B takes one argument, 0x08 two. Those were found by listing the glyphs that start a run far
  more often than chance and the word before them. Since YOM-36 the profile's `encoding.skip` holds
  the argument count of every command but 0x3F, read off the game's code (see "Reading the game's code with
  Ghidra" and "Command arguments in the profile" below); one-character runs are dropped.
- **Result (first version, five commands in `encoding.skip`):** 2,240 usable entries (the tail words
  of 16 blocks are not offsets), 36,273 text runs of two or more characters, 26,100 unique readable
  lines; the commonest glyph ids are the ellipsis, the full stop and the comma. The numbers today
  are in "Command arguments in the profile".

## Compression (certain)

Standard GBA BIOS LZ77: header byte 0x10, 24-bit size, flag bytes MSB-first, 4-bit length
(+3) and 12-bit displacement (+1). All 17 blocks decode cleanly to their declared size in
a throwaway decoder. The same scheme compresses most graphics in the ROM (about 1230
valid 0x10 streams in total).

## Profile feasibility

Not writable with today's features: the profile schema has `text.regions`, `tables` and
pointer scanning over raw ROM bytes, but no way to say "this pointer table targets
LZ77 blocks; decompress, then parse the offset table inside". Needed:
1. An LZ77 (0x10) decompressor hook plus a profile entry for compressed pointer tables
   (table base 0x18738, count 17, stride 4, nested u32 offset table in each block).
2. After decompression, a second investigation of the encoding (likely a custom 16-bit
   table via `.tbl`, or a Shift-JIS variant) and the command codes.
Addresses for `Line.address` would have to be (block offset, sub-entry, byte offset).

## Survey (`yomineko survey`, 2026-10-04)

The detectors were checked on this game first, because it is the known answer. Counts and offsets only.

- Entropy per 512 KB runs 2.4 to 7.3; fill runs of 4 KB or more: 3 (0x99686, 0x11E014-0x180000 and the
  last 245 KB of the 8 MiB image, all but the first 0xFF).
- BIOS LZ77: 1,228 streams decode cleanly, 20 of 8000 bytes or more. The largest are the 17 script
  blocks from 0x74A214 (decoded 51,100 to 79,298 bytes); the others are two 38,400-byte and one
  10,240-byte graphics block.
- **Token streams (the positive test):** none in the raw image, but 17 ranges inside decoded LZ77
  blocks, exactly the 17 script blocks. This is the check that finds a glyph-id script behind compression.
- Font candidates: 2 stretches with 8 or fewer byte values. 0x1DB400-0x1FD800 (values 00 03 30 33) is the
  glyph table; the geometry estimate gives a 128-byte cell with 0.29 of its positions never inked, as
  worked out by hand above. 0x1D3400-0x1DA800 is another one-colour graphic (cell estimate 512).
- Plain text: no hiragana runs, 10 katakana runs (chance). Pointer runs of 32 or more: 2; offset runs
  of 120 or more: 0 (the block tables are u32 offsets with a different step). Huffman at pointer
  targets: 2 headers, 1 decodes (225 bytes, noise); run-length: 7 headers, 7 decode (graphics).

## Reading the game's code with Ghidra (spike, YOM-60, 2026-10-12)

Question: does decompiling the game's own text routine give facts the survey can only infer, and
with which tool? Addresses, counts and tool facts only; the decompiled code stays on the owner's
machine under `yomineko-out/`.

**Recommendation: adopt. Add the method to the rom-investigator agent and `docs/ADDING_A_GAME.md` as
an optional step for GBA games, with plain Ghidra (headless), not rea.** The profile was not changed
here; the facts below are input for YOM-36.

### Tools

| Tool | Result |
|---|---|
| Ghidra 12.1.4, headless, JDK 21 | Works. Import as raw binary: `-loader BinaryLoader -loader-baseAddr 0x08000000 -processor ARM:LE:32:v4t -cspec default`. Import and auto-analysis take 28 to 58 seconds. No GBA loader extension was needed. |
| rea 6.4.0 (npm, the latest release) | Does not work for a ROM. The raw-binary route is not in the release (`Unknown flag: --architecture`; `--target-format` accepts only `dos-com`), and without it the ROM is refused as an unsupported binary format. The route exists on rea's `main` only, and its own doc says Ghidra on Windows admits PE files only, so it would be refused on this machine as well. |

### Does Thumb code decompile? Yes

- With no help, Ghidra follows the ARM entry stub into Thumb: 287 functions (285 Thumb, 2 ARM), all
  287 decompile, none with bad-instruction warnings.
- Seeding Thumb functions from odd pointers whose target is a `push {.., lr}` adds 43 functions
  (330, all decompile). Auto-analysis still missed 42 of the 96 handler-table entries (19 of them
  empty stubs), which are reached only through the table; creating a function at each entry fixed that.
- The ARM v7 language (the one rea uses) gives the same 287 functions on this game, so the language
  variant is not what stops rea.
- Missing with a raw import: names for I/O registers and BIOS calls (a GBA loader would add them),
  and literal-pool values are shown as data names, so they were read from the ROM by offset.

### What the code says (found in four steps from the script pointer table)

1. The literal `0x08018738` (the 17-pointer table) is read by one function, at 0x08005408. It
   decompresses the chosen block with BIOS call 0x11 (LZ77 to work RAM) to `0x02011FC0`.
2. The entry setup at 0x080054BC reads that address and one more: entry numbers below 0x80 come from
   an **uncompressed block in the ROM at 0x749428**, numbers from 0x80 up from the decompressed block.
3. The reader at 0x080055B0 takes a 16-bit token: below 0x80 it is a command, called through the
   handler table at **0x11DDA0**; from 0x80 up it is a glyph.
4. Each handler moves the script pointer (state + 4), which gives the argument count.

Facts the survey did not have:

- **An 18th script block.** 0x749428 to 0x74A214 (3,564 bytes, not compressed) has the same layout as
  the others: 31 entries, 1,718 words, 1,090 of them in the glyph range, and its entries walk cleanly
  with the argument table below. The profile did not read it then (it does since YOM-36).
- **Command set.** The handler table has 96 slots; 0x00 to 0x4C are real (77 commands, 0x02, 0x07,
  0x0A and 0x2D share a handler, as do 0x15 and 0x45), 0x4D to 0x5F are empty stubs. Other code
  (0x080084E4) loads 0x11DF20, so a different table starts right after slot 0x5F. The "about 115
  distinct small values" noted above were commands and their arguments counted together.
- **Argument counts** (16-bit words after the command):

  | Arguments | Commands |
  |---|---|
  | 0 | 00 01 02 07 0D 11 14 15 16 1F 21 24 2B 2D 2E 40 41 45 49 4C |
  | 1 | 03 04 06 0A 0B 0C 0E 10 13 17 18 1B 1C 1D 20 25 26 28 29 2C 30 34 36 38 39 3C 3D 3E 42 43 44 46 4A 4B |
  | 2 | 05 08 0F 19 22 23 27 2A 2F 31 32 35 37 3A 3B 47 48 |
  | 3 | 09 12 1E |
  | 4 | 1A |
  | 5 | 33 |
  | not worked out | 3F (7 uses in the whole script) |

  0x35 and 0x36 are jumps, 0x15 and 0x45 leave the pointer where it is (the script waits there).
  The handlers for 0x01, 0x08, 0x0E, 0x11, 0x12 and 0x1B were read in full; the rest are a first pass
  over the pointer arithmetic.
- **Against the profile's `encoding.skip`:** 0x0E, 0x0B and 0x1B (one argument) and 0x08 (two) are
  right. **0x12 takes three arguments, not one.**
- **Check on the data.** Walking all 2,240 entries of the 17 blocks with this table meets no undefined
  command (0x4D to 0x7F). With 0x12 set back to one argument it meets 3; with the profile's five-entry
  table and every other command taken as having no arguments it meets 1,166 (40 distinct values),
  which are arguments read as commands. 18,083 argument words have values in the glyph range; the
  profile's table covers 11,457 of them, and the other 6,626 are what can still be read as text.

### Cost and limits

- About 570 MB of Ghidra and three small headless scripts (seed functions, find who reads a literal,
  decompile chosen functions to a local file). By file times, the handler table was found 6 minutes
  after the first import and the argument table was checked against the script 4 minutes later.
- It needs one known anchor to start from. Here it was the script pointer table the survey had
  already found; a font address or a decompressed-buffer address would do as well.
- GBA only for now: this checks ARM and Thumb. Game Boy Color (SM83) was not tried.

## Command arguments in the profile (YOM-36, 2026-10-12)

The profile now holds what the spike found: `encoding.skip` lists the 56 commands that take
arguments with their counts (0x12 has three, not one), and `compressed.uncompressed` lists the 18th
block. That block is numbered 17, after the table blocks, so no existing line id moved; its lines
have ids from `C1100000`.

0x02, 0x07, 0x0A and 0x2D share one handler, and only 0x0A has an argument: the handler compares
the command with 0x0A and steps one word further for it. In the script all 248 uses of 0x0A are
followed by a word of 0x80 or more, which would otherwise start a text run.

0x3F is not in the table. Its count is 0 or 1: with either, a walk of all 18 blocks meets no
undefined command and no command whose arguments run past its entry, and with 2 or more all seven
uses run past the end of their entry. So the seven uses sit at the end of an entry and cannot touch
text.

**Noise before and after** (owner's dump, counts only; "argument words" are command arguments whose
value is a glyph id and that the profile does not step over, so they can be read as text):

| | before | after |
|---|---|---|
| Argument words that can be read as text, blocks 0 to 16 | 6,626 of 18,083 | 0 |
| The same, 18th block | not read (14 of 46 with the old table) | 0 |
| Undefined commands (0x4D to 0x7F) met by a walk with the profile's table | 1,166 | 0 |
| Blocks, entries | 17, 2,240 | 18, 2,271 |
| Text runs kept, blocks 0 to 16 | 36,273 | 35,756 |
| Text runs kept, 18th block | 0 | 103 |
| Text runs kept, total | 36,273 | 35,859 |
| Unique readable lines | 26,100 (22,598 dialogue, 3,502 terms) | 25,944 (22,469 dialogue, 3,475 terms), 65 of them from the 18th block |
| Unique lines of two or three characters | 1,317 | 1,150 |
| Distinct words (seen three or more times), with the packaged review | 4,144 (1,814) on 2026-10-11 | 4,098 (1,795) |

`verify` passes at the decompressed level on all 35,859 lines, and no run is unstable. The game
check (`tools/game_check.py`) still says *works, with limits* (no name or term cards): 1,455 word
cards and 1,000 sentences. One rule of the packaged word review was removed, because the word it
dropped came only from argument words and no longer appears (34 of 34 rules apply).

What is left: the argument counts of all but six commands are a first pass over the handlers'
pointer arithmetic. The walk above is the check on them, and it would not notice two wrong counts
that cancel out inside one entry.
