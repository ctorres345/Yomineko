# Fire Emblem: Fuuin no Tsurugi (Japan) - investigation notes

Status: **not supported yet** (no profile). The text format is known and was checked against the game's
own decoder (YOM-61, 2026-10-12); the decoder, the profile block and the profile are YOM-28, YOM-29 and
the tickets after them. Everything here was measured on the owner's dump, read in memory. Counts, offsets
and format facts only: no game text and no decompiled code appear in this file. The scratch scripts and
the decompiled functions stay on the owner's machine under `yomineko-out/yom61/`.

## Identity (certain)

| Field | Value |
|---|---|
| Header title | `FIREEMBLEM6` |
| Game code | `AFEJ` |
| Revision | 0 |
| Size | 8,388,608 bytes |
| SHA-1 | `a57095da867de4d585c33d4394712986245fe6ca` |

## The format, checked against the decoder (YOM-61)

The first look (2026-10-05) inferred the format from statistics. Each fact below was then
read off the game's code with Ghidra and tried on the data.

| Inferred fact | Verdict | What the code and the data say |
|---|---|---|
| The game's own Huffman tree, not the BIOS format | **Confirmed** | The decoder is the game's own bit loop (140 bytes of ARM code at 0x0006E4), with no BIOS call. |
| Tree of 3,283 four-byte nodes at 0xF300C-0xF6358 | **Confirmed** | The decoder loads the base 0x080F300C from its literal pool. 1,642 leaves and 1,641 inner nodes. |
| A node is two 16-bit child indexes | **Confirmed, with the order** | Bit 0 takes the low half (bytes 0-1), bit 1 the high half (bytes 2-3). The index is multiplied by 4 and added to the base. |
| A leaf has 0xFFFF in the high half | **Corrected (same result here)** | The decoder tests only bit 31 of the 32-bit node. In this ROM every leaf has 0xFFFF there and no inner node has bit 31 set, so both readings agree. |
| The root is the last node | **Corrected (same result here)** | The root is not found by position. The word at 0xF6358, right after the tree, holds the address of the root (0x080F6354, node 3,282, which is the last one), and the decoder reads it through the literal 0x080F6358. |
| Bits are read from the low bit of each byte up | **Confirmed** | Each message starts on a byte boundary with an empty bit buffer. Unused bits of the last byte are 0 in all 3,342 messages. |
| A message ends at symbol 0 | **Confirmed, more exactly** | The decoder stops after writing a single byte 0x00. No leaf has a zero low byte with a non-zero high byte. |
| Symbols are Shift-JIS two-byte values, low byte first, plus one-byte codes | **Corrected** | A symbol is one or two **output bytes**, not a character: if bits 8-15 of the leaf are 0 it writes one byte, otherwise the low byte and then the high byte. 1,457 two-byte symbols are Shift-JIS characters; **156 are not**: they are the 16-bit argument of code 0x10 (see below). The output is a plain byte stream with a 0x00 at the end. |
| 3,342 pointers at 0xF635C-0xF9794 | **Confirmed in the data, no count in the code** | One function (0x013AD0, 163 callers) reads `table[index]` at 0x080F635C with no bounds check and passes the pointer to the decoder as it is: no flag bits, no other storage form. The table ends where other data begins (0xF9794, loaded by different code at 0x000B16). All 3,342 pointers are ROM addresses, strictly ascending. |
| 3,341 of 3,342 messages end where the next begins; one does not | **Resolved: there is no odd message** | The one that "does not" is the last (index 3,341): it has no next pointer to compare with. It starts at 0xF2FFF, uses 11 bytes and ends at 0xF300A; two zero bytes align the tree to 0xF300C. Message data is 0x9FAC0-0xF300A (341,322 bytes), not up to 0xF2FFF. |
| One-byte control codes 0x01-0x1C and 0x80 | **Corrected** | Two codes take arguments, and 0x15 has a case in the code but is never used. See "Control codes". |

### How a message is read (addresses in the ROM)

1. `0x013AD0` (Thumb) takes a message number. If it is the number decoded last (kept at 0x0202A404) it
   returns the buffer at once; otherwise it reads the pointer from the table at 0xF635C and calls
   `0x00384C`, which calls the decoder through a pointer in RAM (0x03003780).
2. The decoder is ARM code in the ROM at `0x0006E4`. At start-up `0x003764` copies the block
   0x000228-0x000A20 to RAM at 0x03002D80 and stores the new address of six routines; the decoder is one.
3. It writes to a 4,096-byte buffer at 0x02029404. The longest message decodes to 3,379 bytes.

### Control codes (lengths from the text-width routine at 0x00C584)

The width routine and the interpreter at 0x009970 both switch on the byte through a 130-entry table
(values 0x00-0x81). The width routine steps over each code, which gives its length; the interpreter's
own steps were not read. The length of 0x10 is also shown by the tree (its 156 arguments are leaves of
their own); the length of 0x80 rests on the width routine and on the re-packing check below.

| Bytes | Codes |
|---|---|
| 1 (no argument) | 0x01-0x0F, 0x11-0x1C |
| 3 (two argument bytes) | **0x10** |
| 2 (one argument byte) | **0x80** (the second byte selects among 0x00-0x11) |
| end of message | 0x00 |
| a character | everything else; 0x81 0x40 is treated apart (a fixed width) |

In the data: 0x10 is used 2,284 times with 156 distinct 16-bit arguments (third byte 0x01 2,185 times,
0xFF 99 times). 0x80 is used 401 times with 9 second bytes (0x04, 0x05, 0x0A-0x0F, 0x11). 0x15 is never
used, and neither are 0x1D-0x1F. The other 27 one-byte codes are all used (0x01: 27,065 times, 0x03:
15,841, 0x0C: 5,149, 0x09: 4,951, 0x17: 3,293).

### Checked on the data

- A scratch decoder written from the facts above (not from the game's code) reads all 3,342 messages:
  383,266 symbols, 699,361 bytes, 313,811 characters (1,457 distinct, every one a valid Shift-JIS pair).
  228 messages are empty (a single 0x00).
- **The split into symbols can be rebuilt from the bytes**, which `verify` by re-packing needs: a
  Shift-JIS lead byte takes two bytes as one symbol; 0x10 is one symbol and its two argument bytes are
  the next; every other byte is a symbol of its own (0x80 and its second byte are two symbols). With that
  rule all 3,342 messages re-pack to the ROM's bytes exactly. Two simpler rules fail: "take any pair that
  is a leaf" rebuilds 2,201 messages, "pairs only at a lead byte" 2,180.
- Code lengths run from 4 to 19 bits. Every leaf is used at least once.

### What this changes for YOM-28 and YOM-29

- **YOM-28 (decoder and encoder).** Take the root from the profile (here: the node whose address is stored
  after the tree), not "the last node". Treat a node as a leaf when bit 31 is set. A symbol is 16 bits and
  stands for one or two bytes; the output is bytes. The encoder needs the symbol split as input (it does
  not follow from the tree alone) and pads the last byte with zero bits.
- **YOM-29 (profile block, discovery, verify).** The encoding layer reads a byte stream: Shift-JIS pairs
  and one-byte codes, with argument counts per code (0x10: two bytes, 0x80: one), the same idea as
  `encoding.skip`. `verify` re-packs with the split rule above. The message count comes from the pointer
  table's range in the profile; the last message ends at its 0x00, not at a next pointer.

Still unknown: what each control code does (only lengths were read; 0x08-0x0F and the 0x80 codes 0x0A-0x11
set a value the width routine compares, which looks like the speaker's position), and what the 156
arguments of 0x10 refer to.

### Tool notes (they differ from the Gyakuten Saiban spike)

- Ghidra's auto-analysis did not finish on this ROM in 10 minutes: with the code area not bounded it
  disassembles data. Importing with `-noanalysis` and decompiling chosen addresses took under a minute
  per run and was enough.
- Ghidra refuses a project folder whose path has a part starting with a dot.
- The decoder is ARM, not Thumb, and no Thumb instruction loads its literals, so a search for Thumb
  readers of the tree address finds nothing. What found it: listing every word in the ROM that holds
  the tree base, the address of the root word or the table address (0x0006DC, 0x0006E0, 0x013B10, and
  0x100430 in a data record whose reader was not looked for), then the ARM `ldr` that reads the first two.
- The control-code routines were found by scanning the code for jump tables and taking the two whose
  guard is 0x81.
