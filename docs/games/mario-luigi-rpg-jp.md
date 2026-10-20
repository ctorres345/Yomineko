# Mario & Luigi RPG (Japan) - investigation notes

Status: **supported** (profile `mario-luigi-rpg-jp`, 2026-10-05). Read "Result" and "Open work" first.
The "Investigation log" after them is kept in the order things happened: what was ruled out, how the script
was found, how the encoding was solved. Some early conclusions in it were wrong and are corrected further
down (the Huffman streams, the code at 0xF50000). No game text appears in this file.

## Identity (certain)

| Field | Value |
|---|---|
| Header title | `MARIO&LUIGIJ` |
| Game code | `A88J` |
| Revision | 0 |
| Size | 16,777,216 bytes; data ends about 0xC00000, the rest is 0xFF fill |
| SHA-1 | `edc538ac505bfcd337abdd03b3a6f2744d81eaab` |

## Result (2026-10-05)

- **Where:** two regions of one continuous byte stream, JP 0x3BE390-0x3DF0C0 (dialogue, menus,
  mini-game text) and 0x3EE2E0-0x3F0660 (tutorial and battle text). No pointer table is needed: a
  line is a run of text between line-ending commands. The regions before, between and after them are
  graphics and tables that decode into plausible-looking junk, which is why the profile bounds
  them tightly. (Before the stream was understood, the 1.5 MB high-entropy block at 0x480000 and the
  Huffman streams at 0xFA7640+ were suspected; they are graphics, and the Huffman ones belong to the
  embedded Mario Bros. image.)
- **Encoding:** `table8`: one-byte codes, kanji as a lead byte 0xFA-0xFE and an index, commands as
  `FF cmd params`. The table has 248 one-byte entries and 651 kanji (897 lines in the `.tbl`; two
  codes draw characters that another code already has and are handled by `plain` rules).
- **How the table was made:** every code was rendered in an emulator. A libretro mGBA core
  (`mgba_libretro.dll`, driven from Python with ctypes) loaded the ROM with the message bytes at the
  pointer found in a save state patched to `FF 03 FF 35 20 <code> FF 0C 30`, loaded that save state
  and ran 70 frames; the glyph was cropped at a fixed cursor position (1,530 codes in about two
  minutes, keeping each glyph's vertical position). Kana were read off labelled sheets: they are in
  gojuon order from 0x91 (hiragana) and 0xAB (katakana), with voiced and small kana elsewhere. The
  659 kanji that the script uses were transcribed by eye from 48-glyph sheets, ordered by code (the
  font order is by school grade, then by use). Anchors that confirmed the alignment: 17 codes read
  from the save states earlier, and the decoded text reading as ordinary game dialogue.
- **Counts:** 5,962 text runs, 5,152 unique readable lines (3,913 dialogue, 1,239 terms), `verify`
  rebuilds the ROM byte for byte, `analyze` finds 2,245 distinct words.

## Open work

- **Punctuation shapes** were decided by vertical position: 0x27 apostrophe (top), 0x2C comma and
  0x2E full stop (low), 0x3C the ideographic full stop, 0x3E the ideographic comma, 0x85 the
  ellipsis. The 0x3E and 0x3C readings rest on usage, not on a clear glyph.
- **Unsure kanji:** two codes (0xFB42, 0xFC27, one or two uses each) were left out of the table and
  show as nothing in the readable text; several rare ones may be misread. `review-vocab` on this game
  will show wrong words, which point back to the code.
- **Lines are runs, not messages.** The game's own message index (about 666 pointers from event
  data at 0x200000-0x24FFFF point into the stream, 4-aligned, into the `FF 0A` header of each
  message) is not used yet. Using it would give stable message ids and group the lines of one
  message into a scene.
- **Other text.** The `FF 00` terminators are also dense in 0x3A0000-0x3BE000, which decodes to
  nothing readable (tables); the US ROM keeps its menus separately (0x200000), so a Japanese menu bank
  elsewhere cannot be ruled out. Ruby, names inside commands (`FF 44`) and the speaker commands are
  kept as part of the lines.
- **A tool.** The emulator render is a reusable method for any game whose font is not stored as
  plain tiles (see `docs/ADDING_A_GAME.md`, "Byte-stream text"). The scripts that did it are local
  (`yomineko-out/scratch/`: `lr.py`, `gl2.py`, `bulk.py`, `sheets.py`, `mltable.py`, `gen_tbl.py`).
## Investigation log

In order. Later sections correct earlier ones.

### Layout (by entropy, hex peeks and pattern scans; medium confidence)

| Range | Content |
|---|---|
| 0x000000-0x190000 | ARM and Thumb code, small tables |
| 0x193000-0x1D1000 | music sequence data (note events such as `f1 3c 0c 37`) and instrument tables |
| 0x1E0000-0x430000 | mixed: more tables, event scripts, code |
| 0x430000-0x448000, 0x480000-0x600000 | 4bpp graphics (art), not compressed with a BIOS header |
| 0x680000-0x7FFFFF | low-entropy graphics |
| 0x8326F0 | 733 relative offsets into a block of 4bpp sprite frames (416 bytes each), not text |
| 0xA00000-0xBFFFFF | PCM audio samples |
| 0xC00000-0xF3FFFF | zero fill (so the 16 MiB size is mostly padding) |
| 0xF50000-0xF9FFFF | ARM/Thumb code that is probably Japan-specific (the first bytes are ARM; the US comparison below shows it is an embedded mini-game image); a data island at 0xF73000-0xF7DFFF (about 44 KB, entropy 4-5.4) is mixed data, not a 1bpp font in 8x8, 8x16 or 16x16 layouts |
| 0xFA0000-0xFDFFFF | animation/object bytecode (small tables of a shared pointer 0xFB4D5C plus blocks of 25-290 bytes starting `bc 00 ...`), 10 small LZ77 streams (graphics) | 
| 0xFE0000-0xFFFFFF | zero fill |

### Ruled out for the script

- **BIOS LZ77:** only 10 valid 0x10 streams in the whole ROM (sizes 8192, 2048, 344, 9728, 24576); none
  is large enough to be the script. Huffman (0x20/0x28) and RLE (0x30) header hits are noise (those
  bytes are common); nothing was decoded.
- **Plain Shift-JIS:** 14 hiragana runs of 4 or more characters, all in code or data. No kana text.
- **ASCII:** the printable runs are Thumb instruction patterns, so Latin letters are not stored as ASCII.
- **A one-colour 4bpp font** like Gyakuten Saiban's: no region of 1 KB windows with 8 or fewer byte
  values and a mixed zero share.
- **The big pointer tables** (0x3997B0 x529, 0x205130 x366, 0x3A2DDC x316, 0xE3158 x190, 0x49004 x172,
  0x14D670 x155) point at Thumb or ARM code, event bytecode and tables, not text.

### Also ruled out (second pass)

- Offset-table banks found by scanning for increasing u16/u32 runs (0x287CF2, 0x2B3650, 0x35E9E2,
  0x2057B6, 0x8326F0) hold fixed-size animation/object records and sprite frames, not messages.
- A scan of every 8 KB window for a 16-bit token-stream profile (many repeats of a few hundred small
  values) matches nothing, so the text is probably not 16-bit glyph ids like Gyakuten Saiban.
- Pointer targets with BIOS Huffman headers (0x24/0x28): **this was wrong.** The hand-made decoder had
  the tree base off by one and rejected everything; `yomineko survey` finds seven real streams
  (see "Survey" below).
- A relative search for a 3-kana name pattern assuming a gojuon-ordered one-byte table hits only
  graphics. Not conclusive either way.
- 4bpp tile-sheet overviews of 0x1E0000-0x440000 are noise at this scale.

### Third pass (disassembly)

- Scanning the Thumb code for the glyph-addressing idiom (a shift of 4-7 next to a halfword or byte
  load and a literal-pool pointer into the ROM) gives 367 sites and 151 targets, mostly record
  tables (shift 4 = 16-byte records); no target looks like a font. Strongest: 0x38A450 (38 sites),
  0x3A56B8 (32), 0x3B16F8 (20). Not followed up.
- 0x480000-0x5FFFFF (1.5 MB, about 7 bits per byte) shows no images as 4bpp tiles and is not a BIOS
  stream. Few pointers lead into it and they are misaligned, so it is not indexed by 0x08 pointer
  tables (offsets or banks computed in code?). Whether it is compressed graphics or compressed text is
  open; it is the biggest unexplained block and the best candidate for the script.

### Save-state pass (RetroArch/mGBA states, 2026-10-04)

Two states with a message on screen (a dialogue box, and a speech bubble) were decoded locally:
- The files are RetroArch `#RZIPv` (zlib chunks) around a `RASTATE` container whose `MEM ` block is
  an mGBA state of 405,568 bytes. The I/O registers are at 0x400, VRAM at 0x1000 (96 KB), then IWRAM
  and EWRAM. DISPCNT was 0x1F40 (mode 0, all layers); BG0CNT 0x1508 = char base 0x8000, screen
  base 0xA800, 4bpp. Reading BG0's tile map and tiles reproduced the bubble.
- **How the text is drawn:** the text is rendered at run time into a rectangle of consecutive BG0
  tiles (tile numbers 844 and up, one tile row after another), not copied from ROM tiles. Glyphs are
  proportional (narrow), about 8 pixels wide and 11 rows tall, one-pixel strokes with two ink shades
  (palette indices 1 and 2), and each row is drawn twice (doubled vertically).
- **Not found:** the glyph's row bytes as 1bpp bitmaps (any alignment or mirror, 1- or 2-byte rows) do
  not occur in the ROM or in RAM, and none of the VRAM glyph tiles occur in the ROM. The message
  source in RAM was not found either: pointers in RAM that differ between the two states lead to
  animation/event bytecode (around 0x22D4xx-0x22DBxx), not text.
- The routine at 0xF59258 (near the VRAM literals 0x0600EAD8...) writes tile numbers into the map
  (the bubble frame), not glyph pixels.

(Superseded by the emulator pass below.) The idea was: run the ROM code for a few thousand instructions from a state taken just before the
text starts (an ARM/Thumb emulator such as Unicorn), watch writes to the BG0 tiles and the reads from
the ROM that feed them. That gives the glyph source, its format and the message source directly.

### Emulator pass (mGBA 0.10.5 standalone, 2026-10-04)

- **Dialogue boxes are composed in RAM.** A text box is drawn into a 4bpp bitmap buffer in EWRAM (VRAM
  BG0 tile 900 is a copy of 0x0201AA80, tile n at 0x0201AA80 + (n - 900) * 32, 30 tiles per map row)
  and then copied to VRAM; the tile map has a shadow copy in EWRAM (0x0201B91C). Text ink is palette
  index 6 or 7 over background 0; the line is about 11 rows tall with 12-pixel full-width glyphs.
  A speech bubble (a different system) draws into BG0 tiles from 844 with 1-pixel strokes doubled
  vertically.
- **The font is not stored as plain bytes.** Rows of rendered glyphs do not occur in the ROM or in RAM as
  1bpp (1 or 2 bytes per row, any alignment or mirror), nor as 4bpp tiles in the ROM, even by shape
  (which nibbles are non-zero). The glyph source is probably compressed or built by code.
- **Tools used:** RetroArch `#RZIP` states decode to an mGBA state (I/O at 0x400, VRAM at 0x1000), but
  the standalone mGBA refuses them; states made in mGBA itself load (also `emu:loadStateSlot`). The
  Windows SDL build's GDB server fails to open its socket. Lua scripts in the Qt build can read
  memory, registers, press keys, save and load state buffers, single-step (`emu:step`) and run per-frame
  callbacks, but there is no watchpoint API and a script cannot be started from the command line.
- **Tracing result so far:** single-stepping from a state saved one frame earlier reproduces the draw,
  but picking the right byte to wait for is hard (the area also holds clears and fills, such as a
  zeroing loop in IWRAM at 0x03001F18 and a fill loop at 0x08018D1E). No glyph read was captured.

### What this game shows about the tool

None of the checks that work for a Shift-JIS or glyph-id game apply, so a developer-side `survey`
command would have saved most of this session: entropy map with fill detection, BIOS stream list,
Shift-JIS and one-byte-table text detectors, pointer-run and offset-table finders with a look at their
targets, a font-candidate finder (few-valued 4bpp, 1bpp/2bpp), and a token-stream (u16) detector. Also
missing for games like this: a way to say the script is headerless-compressed, and a way to reach data
by computed offsets rather than pointers.

### Survey (`yomineko survey`, 2026-10-04)

Counts and offsets from the survey command, checked against the hand work above (which it agrees with,
except for Huffman):

- Entropy: zero fill from 0xBDC5A0 to 0xF50000 (the table above says 0xFF; the dump has 0x00), then code
  and bytecode. Six fill runs of 4 KB or more; the image ends in fill from 0xFDF798.
- BIOS LZ77: 10 streams that decode cleanly, 6 of 8000 bytes or more, all in 0xFA3000-0xFB4000 (four of
  8192 bytes, then 9728 and 24576). None is large enough to be the script.
- **BIOS Huffman at pointer targets: 32 plausible headers, 7 decode** to their declared size with
  non-random output: 0x349694 (165,137 bytes, only two distinct values), 0xFA7640, 0xFA77FC, 0xFA79E4,
  0xFA7BF8 (2,048 bytes each, 15 distinct values: tile-like), 0xFA7E34 (24,064 bytes, 200 distinct
  values) and 0xFAC050 (32,768 bytes, 219 distinct values). Not yet looked at for content. Run-length at
  pointer targets: 8 headers, 8 decode (not examined; a decode gate on entropy does not rule out noise).
- Plain text: 14 hiragana runs of 4 or more (all in 0x5FB000-0x646000, so graphics or noise), 305
  katakana runs, none touching ASCII.
- Pointer runs of 32 or more: 62; their first targets are mostly code or records, not text. Increasing
  offset runs of 120 or more: 15 (5 open their own block, among them 0x287CF2, 0x2B3650, 0x31AD54 and
  0x35E9E2).
- Font candidates (8 or fewer byte values): none. Token streams: none, raw or decoded.
- **Save states** (both RetroArch states, and the owner's mGBA state): BG0 has char base 0x8000, screen
  base 0xA800, 4bpp. The dialogue box is a 30x5 rectangle of tiles from tile 834, none of its 34 inked
  tiles exact in the ROM (6 by shape), all in EWRAM as one buffer at 0x0201A240. The speech bubble is
  20x7 from tile 844 with 67 inked tiles: 8 exact and 51 same-shape matches in the ROM (frame and
  fill tiles), all 67 in EWRAM as one buffer at 0x02018C60. So the text is rendered into RAM at run time.

### US version and the decomp (2026-10-04)

The US release (A88E, SHA-1 `7c303cdde5061ee329296948060b875cb50ba410`) has a public decompilation,
`jellees/mlss` (mostly raw disassembly with `sub_`/`dword_` names so far; no text or font names). Reading
it and comparing the two ROMs changed several conclusions above:

- **0xF50000-0xFFFFFF is not Japan-specific code: it is an embedded copy of the Mario Bros. mini-game**
  (a second GBA image, header title `SUPER MARIOD`, code `AX4J`, at 0xF50000, with another header at
  0xF6F6C0). The two BIOS Huffman wrappers (0xF6F414 and 0xF72FA8) are inside it, and the Huffman streams
  at 0xFA7640-0xFAC050 are its graphics. The one other hit, 0x349694, has no caller and is probably a
  coincidence. The US decomp's main game has **no HuffUnComp call and one inline LZ77 call**, so the
  script is not BIOS-compressed.
- **The US script is plain ASCII**, found with a plain string search: menus (several languages) at
  0x200000-0x21FFFF and the dialogue in a block of about 1.2 MB from about 0x3B0000 to 0x520000.
- **Aligning the two ROMs** (matching 32-byte chunks, offsets only): code and tables are the same bytes
  shifted by a constant. The shift is -0x16xxx from 0x28xxxx to about JP 0x394C80 (US 0x3AA8F4), then
  -0x10E9xx from JP 0x411900 (US 0x520204) onwards, down to the Mario Bros. image. So the US has about
  0xF8774 bytes between US 0x3AA900-0x520200 that the JP ROM holds in at most **JP 0x394C80-0x411900
  (about 511 KB)**: the Japanese script and the data stored next to it are in that window, not in the
  1.5 MB block at 0x480000, which matches the US bytes (graphics). The window's profile is mixed
  (entropy 4-6.8 per 16 KB, a flat 6.3 stretch at 0x3B4000-0x3DC000).

### The script is found (2026-10-04, same session)

Using the US ROM as the answer key for structure only (no US or JP text is quoted here):

- **US message format.** The US text is plain ASCII in short strings, from about 0x3D0000 to 0x520000
  (a count of real English-looking runs per 64 KB makes it obvious; a naive letter-run count is fooled by
  4bpp graphics, whose bytes 0x55 and 0x33 are letters). Strings end with `FF 00`. `FF xx ...` is a
  command: seen `FF 11 00`, `FF 01 00`, `FF 0B 01`, `FF 0A 00 00 00 00 10 05`, `FF 03`, `FF 35` (the
  latter often right before text). A message is a chain of such commands and text spans.
- **The same command chains occur in the JP ROM**, and only in one place: `FF 0B 01 FF 35` 204 times and
  `FF 11 00 FF 01 00` 1,137 times, all between **0x3BE600 and 0x3F0700** (about 200 KB; one stray hit
  of the first marker elsewhere). So the Japanese script is stored in the same escape format,
  uncompressed, in that range. `FF 00` terminators are also dense in 0x3A0000-0x3BE600, which has no commands (other strings, not examined).
- **Command set (from the US ROM, confirmed in JP).** After `FF cmd`: `01`, `0B`, `0C` and `11` take one
  parameter byte; `0A` takes bytes up to the next `FF` (3 to 6 of them); `00`, `03`, `04`, `05`, `20`,
  `25`, `29`, `2B`, `2D`, `31`, `33`, `34`, `35`, `41` take none and the bytes that follow are text. JP
  also has `0D` (one parameter, then text), `6F` and `7F`. `FF 00` ends a page or line and text may follow
  it directly.
- **Encoding, solved in structure (2026-10-04, from the two save states).** Each state holds a pointer
  to the message being read (EWRAM 0x020167D0 and 0x020150BC point at JP 0x3C2E65 and 0x3C08AA, in
  the middle of a message). The bytes just before such a pointer are what the box shows, so each
  state gives a few code-to-glyph pairs read by eye from a PNG of the box. Result:
  - **Kana, punctuation and symbols are one byte** from the whole range 0x00-0xF9, NOT ASCII-compatible
    (0x20 is a space, 0x21 is the exclamation mark, but 0x22, 0x60 and 0x1B are the small yu, n and
    ji; a voiced kana has its own code).
  - **Kanji are two bytes: a prefix 0xFA, 0xFB, 0xFC, 0xFD or 0xFE, then an index** (up to about 1,280
    kanji in five banks of 256).
  - Verified codes so far: 0x97 ki, 0x92 i, 0x93 u, 0x8A de, 0x9D su, 0xDD ta, 0x60 n, 0x22 small yu,
    0x1B ji, 0x20 space, 0x21 exclamation mark, 0x5F wo, 0xE1 to, 0xE6 no; katakana 0xC9 ma, 0xCC me,
    0x40 the long-vowel mark, 0xD2 ri, 0xAB a; kanji FE14 and FE31 (the two of a country name), FD96
    and FA9F (a two-kanji word), FC02 (one more).
  - The glyph rendering: body pixels use palette index 6 and a shadow uses 7; the rendering code is
    not the one found by looking for compares with 0xFA-0xFF (those hits are stats code that uses 0xFF
    for "empty slot").
