# Changelog

## Unreleased

- **A theme button in the app.** The header's Theme button switches between Match system (the
  default: light or dark as the computer is set), Light and Dark. The choice is kept in the app's
  data folder, so the next window opens the same way.

## 0.5.0 (2026-10-20)

The first public release. 0.4.0 and the milestones before it (0.1.0 to 0.3.0) were never published; their
changes are listed below and are all part of this release.

- **A step bar in the app.** Every game page shows where you are: 1 Add a game, 2 Find the words,
  3 Choose your words, 4 Check meanings (optional, with the words left to check) and 5 Export. Each
  step has one filled "Next" button, and checking can be skipped. The start page lists the two setup
  steps (the dictionary, then a game) until both are done; the game page leads to the next step and
  keeps the lines, words and sentences under "Look inside"; Export shows only the options for the
  chosen format and the word card count next to Download; the sentences hide ROM addresses unless asked
- **Choose your words.** A new step in the app asks which words you already know: Just starting, The
  basics (skip the 1,000 most common words), Intermediate (5,000) or Advanced (10,000), with ten sample
  skipped words and a live count of the word cards. The level is remembered for the next game. The deck,
  the word export, the sentence picker and the words page follow it; on the command line it is
  `export --level`. How common a word is comes from JMdict's newspaper frequency bands, not JLPT lists
- **"I know this".** On the Choose your words step and the words page, a word can be marked as known
  (and undone); the card count follows at once. Known words get no card, no export row and no help
  under a sentence, in every game. They are kept on this computer as JMdict ids only (`known.json` in
  the workspace); `yomineko known list / add / remove / clear` manages them, and `export --no-known`
  makes cards for them anyway
- **Script schema 4.** Each word keeps its dictionary frequency band (`jmdict_rank`, also a new last
  column of the word CSV). Scripts from versions 1 to 3 still load; analyse one again to use a level
- **Game Boy Color.** A `.gbc` or `.gb` dump (or a zip holding one) loads next to GBA ones: the
  cartridge header gives the title, game code, revision and region, and `info` shows `gbc`. A profile
  can say `platform: gbc`, and a text region can name a whole 16 KiB bank (`{bank: 0x15}`)
- **Pocket Monsters Crystal (Japan)** is supported: `pokemon-crystal-jp`, with the character table
  read off the game's own font (kana only), species, move and item names as name cards, and a
  first-pass word review (64 corrections). About 12,800 unique readable lines, one per row of the text
  box; `verify` rebuilds the ROM byte for byte
- **Framed messages.** Where every byte value is a character, a plain scan reads code and data as text.
  A `table8` profile can describe how a message is laid out (`discover.frame`: the command that starts
  text, line breaks, end bytes, the commands between two texts); text is then read from whole messages
  only, and a message is kept when a pointer in its own bank leads to it or it has enough kana of its
  own. A byte that draws a name from memory gets a marked, unique table text (`<...>`) that `plain`
  rules remove, so a line still re-encodes to the bytes it was read from
- **Fixed strings stay in the ROM.** A byte that draws a string the game keeps in its ROM is listed
  with the string's offset only (`encoding.rom_strings`); the string is read from the user's ROM, so
  no profile or table file holds game text
- **Name tables that hold their text.** `tables` entries can be `kind: records` (fixed-size records
  padded with the terminator) or `kind: strings` (names that follow one another), next to tables of
  pointers
- `tools/game_check.py` counts the probable names a game's review has not decided, as
  `yomineko review worklist` does; before, a name the review drops still counted against the game
- **Japanese games only.** A ROM whose header game code does not end in `J` is refused by `extract`,
  `verify` and the web upload with a one-line message; `info` says so too. `survey` still runs on any
  ROM. A profile's `rom.game_code` must now end in `J`. An older Game Boy cartridge has no code: its
  header's destination byte must say Japan
- **More survey checks for developers:** `yomineko survey --compare OTHER` (where two versions of a game
  differ: constant shifts and the ranges present in one only) and `--commands PROFILE` (what the control
  codes of a draft profile do: counts, surroundings, parameter and skip guesses)
- **Tools for adding a game:** `tools/game_check.py` (run a game end to end and write a scorecard with a
  verdict), `tools/glyph_render/` (read a character table by rendering every code in an emulator), with the
  `check-game` and `read-glyph-table` skills and a `glyph-transcriber` agent
- **Better word picks for verbs.** A verb or adjective written with kanji in an inflected form (聞い, 書い,
  見) is now matched to its own dictionary entry; before, any word that sounded like the stem could take
  its place. This fixed most wrong picks in kana-heavy games without any review rule
- **Probable names in the review worklist** (`yomineko review worklist` and the web "Check the words"
  page): nouns often followed by an honorific or title, and two kanji that always go together, are listed
  with the reason, so a character's name can be dropped from the word list
- **First-pass word reviews for Gyakuten Saiban and Mario & Luigi** (35 and 8 corrections, JMdict ids
  only, character names left out)
- **Whole sentences first.** A sentence card that does not end like a sentence (a text box row that stops
  at a comma) scores half, so fewer cards end mid-sentence (PMD 135 to 20 of 1,000, Gyakuten Saiban 348 to
  3, Mario & Luigi 155 to 48)
- `yomineko export --help` no longer crashes on a Windows console that cannot print Japanese
- **Byte-stream text.** A profile can say the script is a continuous stream of one-byte codes (kanji as
  a lead byte plus an index) with prefixed commands (`encoding.type: table8`, `command_prefix`,
  `commands`, `line_breaks`, read from `text.regions`). Lines get the address of their first character;
  commands inside a sentence stay in the line as escapes, so `verify` rebuilds the bytes exactly. New:
  `Table8Codec`, `core/discover/stream.py`. The profile format stays at v1.
- **Mario & Luigi RPG (Japan)** is supported: `mario-luigi-rpg-jp`, with a character table read by
  rendering every code in an emulator (about 5,150 unique readable lines)
- **`yomineko survey ROM`** (developer tool for adding a game): read-only checks that print counts and
  offsets, never text: extent and fill, BIOS LZ77/Huffman/run-length streams, plain Shift-JIS kana,
  pointer and offset tables with a label for what they lead to, font candidates (with PNG tile sheets
  under `--report`), 16-bit glyph-id streams (also inside decoded LZ77 blocks), `--word` relative search
  and `--state` for RetroArch/mGBA save states. New `survey/` package; standard library only
- **Text in compressed blocks.** A profile can say the script is in BIOS LZ77 blocks reached through
  a pointer table (`compressed`) and stored as 16-bit glyph ids (`encoding.type: table16`, with `skip`
  for the argument words of commands). Lines inside blocks have virtual ids starting with `C`;
  `yomineko verify` checks them against the decompressed data and says so. New: `core/compression`,
  `core/containers`, `Table16Codec`. The profile and script formats stay at v1 and v3.
- **Gyakuten Saiban (Japan) (Rev 1)** is supported: `gyakuten-saiban-jp` with a character table read
  off the game's font
- `docs/ADDING_A_GAME.md` explains how to find a font and read a glyph table
- **Fixed:** exporting from the macOS app window saved the export page instead of the file. The window
  saves a download by fetching its address again, so the export form now builds the file and sends the
  page to a secret address that serves it (the newest four are kept in memory). CSV and JSON are served
  as a generic file type because that window shows text on screen instead of saving it

## 0.4.0 (2026-10-04, never published)

The milestones before it (0.1.0 to 0.3.0) were never published either; their changes are listed
below it.

- **Desktop app:** `yomineko app` (and the `yomineko-app` program) shows the interface in a window
  of its own (pywebview), or in your browser where no window can be made. Installs with
  `pip install "yomineko[app]"`. Executables for Windows, macOS and Linux (PyInstaller, unsigned,
  with checksums) come from the new **Build app** workflow, which runs on request or on a version tag.
  The macOS build is for Apple silicon. The dictionary download trusts certifi's certificates as well
  as the system's (new dependency `certifi`), so it also works in the packaged app on macOS
- **Web interface:** `yomineko serve` (extra `yomineko[web]`): pick a ROM and extract it with the
  byte-for-byte rebuild check, download the dictionary with a button, find the words, browse words,
  lines and the picked sentences, check ambiguous word picks and correct them (saved to your own
  `review.yaml`), and download an Anki deck, spreadsheet, CSV or JSON. Pages work on a phone-sized
  screen. It only listens on 127.0.0.1, refuses other hosts, needs a per-run token and a matching
  Origin for every change, and loads nothing from other sites. Its look is black to white only
  (five greys, light and dark mode, every text pair at least 4.5:1) in IBM Plex Sans, Sans JP and
  Mono, which are bundled
- `yomineko export` and the web download build files with the same code (`pipeline/exporting.py`)
- New `pipeline/` layer shared by the command line and the web interface; `load_rom_bytes` for ROMs
  already in memory
- `yomineko review check` and the review screen share the worklist; the user review file can be
  written by the program (`save_review`)

## Earlier milestones (never published)

### 0.3.0

- `yomineko export --format anki`: an Anki deck (.apkg) with three decks under the game's title:
  words (most frequent first, with the shortest picked sentence as the example), sentences
  (easiest first, each with the meanings of its less common words) and game terms. Note ids and
  GUIDs are stable (JMdict id, ROM line id, category and text), so re-importing updates cards in
  place and keeps review history. Cards carry the JMdict credit. Text-to-speech uses Anki's
  built-in `ja_JP` voice
- `yomineko export --format xlsx`: the same study set as a workbook (Words, Sentences, Terms,
  About)
- `yomineko export --content sentences` (CSV or JSON), `--sentences`, `--order frequency|rom`,
  `--decks`, `--deck-name`, `--min-freq` (default 4 for sentences and decks)
- Sentence selection (ported from the first prototype): greedy by the frequent words a
  line teaches that earlier picks did not, with structural filters (format codes, fragments,
  placeholders, repeated openings, pronoun and ending variants). A profile may name address ranges
  to skip and caps for battle and log lines (`sentences:`); a review file may exclude or pin lines
  by id (`sentences: {exclude, pin}`). `tools/sentence_excludes.py` turns your own local text filters
  into the id list without putting text in the repo
- Script schema version 3: `analyze` stores each line's words (`Line.word_ids`) and tags game
  terms that match exactly one dictionary entry (`Term.jmdict_id`, `Term.literal`). Version 1 and
  2 scripts still load; analyse again before exporting sentences or decks
- Cards show a stand-in name (`ハル`, change it with `--player-name`) where the game puts the
  player's name, because the placeholder reads badly and text-to-speech spells it out. The dictionary
  link keeps the original text, and CSV/JSON data exports keep the placeholder
- `genanki` and `openpyxl` are now base dependencies
- `review validate` counts the sentence rules and `review check` reports sentence ids missing from
  the script

### 0.2.0

- `yomineko dict download` and `dict status`: download JMdict from edrdg.org once (HTTPS only,
  size-capped, atomic), index it in SQLite in the user data folder (`YOMINEKO_DATA_DIR` to
  move it). This is the only command that uses the network.
- `yomineko analyze SCRIPT`: tokenizes the dialogue (SudachiPy, optional extra
  `pip install "yomineko[analyze]"`), picks a dictionary entry per word with the prototype's
  ranking (part of speech, tokenizer guess, frequency) and fills `words` with meanings and
  counts. Fast: about 2 seconds for a full game
- A packaged review for PMD Red JP: 311 rules, JMdict ids only, from a hand review. On the real ROM
  all rules apply (5,517 occurrences corrected) and the words seen 4+ times go from 1,403 to 1,144,
  close to the 1,106 of the hand-reviewed list
- Review files: YAML corrections for wrong dictionary picks (the homophone problem in kana-only
  text), holding JMdict ids, ROM line ids and your own English only. Rules remap a word, drop
  it, or replace its meaning; a line rule makes an exception for one line; `sentence_safe:
  false` marks a correction that is right for most lines but not all. `analyze --review FILE`
  applies it, a packaged review for a game applies automatically, and yours wins
- `yomineko review validate | check | worklist`: format check; apply and report stale rules or
  unknown ids; list ambiguous words (a common alternative exists) with example lines to review
- `yomineko export --content words`: the word list as CSV or JSON, with `--min-freq`
- Script schema version 2: words gain `pos`, `common`, `sentence_safe`; the script records which
  dictionary it was analysed with. Version 1 scripts still load
- Frequency ranks from the original JMdict file (nf01-nf48, common tags), used later to pick
  between homophones

### 0.1.0

- GBA ROM loading (`.gba`, or a `.zip` with one ROM, read in memory)
- Shift-JIS and `.tbl` table encodings
- String discovery by pointer scan, with a noise filter and bank grouping
- Round-trip rebuild with checksum verification
- Profile format v1 and the `pmd-red-jp` profile
- Script JSON schema v1; JSON and CSV export
- CLI: `info`, `extract`, `verify`, `export`, `profile list|validate|new`
