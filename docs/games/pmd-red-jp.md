# Pokemon Fushigi no Dungeon - Aka no Kyuujotai (Japan): survey notes

The game is supported (profile `pmd-red-jp`, plain Shift-JIS). These are only the numbers `yomineko
survey` gives for it, kept as the reference for what a Shift-JIS game looks like. No game text.

| Field | Value |
|---|---|
| Game code | `B24J` |
| SHA-1 | `4bc9370edebb3da5bdf768eeced689fda3f8b77b` |
| Size | 33,554,432 bytes (32 MiB) |

- Plain text: **23,007 runs** of 4 or more Shift-JIS hiragana, 3,115 katakana runs, 947 hiragana runs
  with ASCII right next to them. This is what "try a Shift-JIS profile" means; the other two games
  have 0 to 14 runs.
- BIOS LZ77: 17 streams, none of 8000 bytes or more (small graphics). Huffman at pointer targets: 1,065
  plausible headers, 2 decode; run-length: 14 headers, 14 decode.
- Pointer runs of 32 or more: 1,177 (text is reached by pointer tables here). Increasing offset runs of
  120 or more: 442, only 1 opens its own block.
- Fill: 0x27518C-0x300000, 0x36FEB4-0x390000 and 0x3B2E74-0x3D0000 of 0xFF, plus two small runs.
- Font candidates: 4 stretches of 8 KB or more with few byte values (0x30F400, 0x508000, 0x50AC00,
  0x50EC00); the last three are 4bpp graphics with a 256-byte cell. Token-stream windows: one range at
  0x4CA000-0x4D2000 in the raw image, probably a coincidence (no LZ77 script here).
- The survey takes 11 seconds on this 32 MiB image.
