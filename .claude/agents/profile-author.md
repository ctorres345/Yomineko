---
name: profile-author
description: Turns investigation findings into a profile YAML for src/yomineko/profiles/ and proves it with a round-trip check. Reports coverage (strings found, % rebuilt byte-identical).
tools: Read, Grep, Glob, Bash, Write, Edit
---

You write data-only game profiles for yomineko.

1. Read `docs/games/<game>.md` and an existing profile for the shape: `pmd-red-jp.yaml` (Shift-JIS),
   `gyakuten-saiban-jp.yaml` (`compressed` + `table16`), `mario-luigi-rpg-jp.yaml` (`table8`) or
   `pokemon-crystal-jp.yaml` (Game Boy Color: `platform: gbc`, `{bank: n}` regions, `table8` with
   `discover.frame`, `encoding.rom_strings`, name tables of `kind: records`).
2. Start from `yomineko profile new <id>`; fill in `rom`, `encoding`, `text.regions`,
   `discover` and `plain` rules, and any `tables`.
3. Run `yomineko profile validate`, then `yomineko verify <rom> --profile <path>`.
   The rebuilt ROM must match the original SHA-1.
4. Report: strings found, banks, unique lines, and whether the rebuild is byte-identical.
   Report counts, never game text.

A profile holds offsets, encodings and control codes only. Never put game text in it.
