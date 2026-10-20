# yomineko (読み猫): plan and status

Last updated 2026-10-09, on the branch that adds Game Boy Color and a fourth game to 0.5.0 (the first
release). This file is
the starting point for whoever picks the project up next: what exists, what was decided and why, what is
left, and where the next session starts (see "Next session" near the end). Architecture and Python conventions are in
[ARCHITECTURE.md](ARCHITECTURE.md); rules for working in the repo are in [CLAUDE.md](../CLAUDE.md).

## Goal

A free tool that extracts the full Japanese script from a game ROM the user owns and turns it
into study material: a frequency-ordered word list, curated sentences with translations, and
exports to **Anki (.apkg)**, **spreadsheet (CSV/XLSX)** and **JSON**.

The niche: learners usually mine words *while* playing (text hooker + pop-up dictionary).
This tool works *before* playing: study the words that cover most of the game, with real lines
from it as examples. jpdb does this for VNs/anime; nothing good exists for ROMs.

## Status at a glance

| Stage | State |
|---|---|
| 1. Core + PMD profile (extract, verify, JSON/CSV) | **Done** |
| 2. Analysis + review (dictionary, words, review file, worklist) | **Done** |
| 3. Exporters: Anki, XLSX, sentence selection | **Done** (imported into Anki by the owner; see "Stage 3 follow-ups"); decisions in "Stage 3 decisions" |
| 4. Local web UI, desktop app and executables (one PR) | **Done.** Build app run #1 (2026-10-11) green on Windows, macOS and Linux with the smoke steps; the owner opened the macOS app and exported decks from the app window (YOM-11, YOM-12). See "Stage 4 decisions" |
| 5. Translation providers | Not started |
| 6. Second game: Gyakuten Saiban (GBA, Japan, Rev 1) | **Done and merged** (PR #19). LZ77 blocks, a 16-bit glyph table read off the font, a profile, `verify` at the decompressed level. Line quality work is open: see "After that" |
| Before the first release | **Done** (2026-10-05, `release/0.5.0-prep`): the three games checked as a user would use them, Japan-only check, first-pass reviews for two games, 0.5.0 prepared. Several checksums per profile is deferred: see "Before the first release". **Release PR 2026-10-11** (YOM-14): changelog dated, wheel and sdist rebuilt with Crystal and checked (see "Release roadmap") |
| 7. Profile discovery helpers | **Done and merged** (PR #20): `yomineko survey`, eight detectors. Play-along ordering is not started |
| 8. Third game: Mario & Luigi RPG (Japan) | **Done and merged** (PR #20): `encoding.type: table8`, byte-stream regions, a character table made by rendering every code in an emulator. Open work is in `docs/games/mario-luigi-rpg-jp.md` |
| Clean-up and verification | **Done 2026-10-05** (PR #22): see "Clean-up session" |
| 9. Pocket Monsters Crystal (Japan, GBC) | **Done 2026-10-09** (phase 3 of the release roadmap): Game Boy Color loading, banked regions, framed `table8` messages, name tables that hold their text, the profile and a first-pass review. Verdict *ready*. See "Release roadmap" |
| Gate B | **Passed 2026-10-12** (YOM-15): every item in "Before the first release" is done or deferred with a reason |
| **Next** | Release day: see "Next session" |

- **Not released yet; 0.5.0 is prepared** (decided 2026-10-05: the first upload is 0.5.0; 0.4.0 and 0.1.0
  to 0.3.0 were never published). README, changelog (dated 2026-10-20, release day; move the date if the
  upload slips), NOTICE and the wheel and sdist (rebuilt 2026-10-11 with Crystal) are ready; the owner does the
  upload (steps in `.claude/skills/release/SKILL.md`, release-day list under "Next session"). The name
  `yomineko` was free on 2026-10-04 and is not reserved until the first upload; nobody but the owner handles
  the PyPI token.
- **Repositories (decided 2026-10-04).** All work happens in **`yomineko-private`** (private; git remote
  `origin`): branches, PRs, the owner merges. **`yomineko`** (git remote `public`) is also private for
  now and is where the first public release lives. It holds `main` as pushed once on 2026-10-04 plus 8
  commits that private `main` does not have (3 merged Dependabot "bump actions" PRs). **At release:**
  the owner either deletes and recreates `yomineko` and pushes private `main` into it (hides those 3
  PRs; needs the branch ruleset, Dependabot and secret-scanning settings set again), or merges
  `public/main` into private `main` and pushes. Either way the history of private `main` goes public
  with it, and one commit in it (77c94fc, 2026-10-09) has a character table that holds 17 short strings
  of a game's text engine; they were moved out the next day. If that history should not be public,
  push a single squashed commit of `main` instead. Only `main` is ever pushed to `public`, never other
  branches or PR refs, so the 17 development PRs stay private. The README logo and project links work
  only once the public repo is public. Making it public is the owner's step.
- **Quality gate** (also CI): ruff lint and format, mypy strict, import-linter (layers), pytest
  with a 95% coverage floor (98.6% now), `tools/repo_guard.py --all`, `yomineko profile validate`.
  1,162 fast tests plus 39 opt-in real-ROM tests on four dumps (2026-10-11).

## What exists now

```
ROM --extract--> script.json (schema v2) --analyze [+ review]--> words --export--> CSV / JSON
```

| Command | What it does |
|---|---|
| `yomineko info / extract / verify ROM` | header and matching profile; extract to `script.json`; rebuild the ROM from the text and compare checksums |
| `yomineko export SCRIPT -f csv\|json [--all] [--kind] [--content lines\|words\|sentences] [--min-freq] [--sentences N] [--order]` | write lines, the word list or the picked sentences |
| `yomineko export SCRIPT -f anki\|xlsx [--decks] [--deck-name] [--min-freq] [--sentences N] [--order]` | a study deck (words, sentences, game terms) as .apkg or .xlsx; needs `analyze` |
| `yomineko dict download / status` | fetch JMdict once (the only command that uses the network), show where it is |
| `yomineko analyze SCRIPT [--review FILE] [--download]` | tokenize the dialogue, pick a dictionary entry per word, count; applies the game's packaged review |
| `yomineko review validate / check / worklist` | check review files; apply and report stale rules or unknown ids; list ambiguous words with example lines |
| `yomineko known list / add / remove / clear [--workspace] [--app]` | the words marked "I know this" (JMdict ids, every game); `export` leaves them out unless `--no-known` |
| `yomineko profile list / validate / new` | game profiles |
| `yomineko survey ROM [--state FILE] [--word KANA] [--report]` | developer tool: how does this game store its text? Counts and offsets only (see ARCHITECTURE.md, `survey/`) |

Packaged for PMD Red JP: the profile (`src/yomineko/profiles/pmd-red-jp.yaml`, including the
sentence address range and caps) and a review of 311 rules (`src/yomineko/reviews/pmd-red-jp.yaml`,
ids only).

**Measured on the owner's real PMD Red JP dump (2026-10-04):**
- extract: 12,817 strings in 826 banks; 12,128 unique readable lines (9,549 dialogue, 2,579 terms);
  rebuild byte-identical (sha1 `4bc9370e...`); about 2.5 s. The pointer tables in the profile
  yield 2,843 term entries.
- analyze, no review: 3,214 distinct words, 1,403 seen 4+ times, about 2.4 s, deterministic.
- analyze with the packaged review: all 311 rules apply, 5,517 occurrences corrected; 2,952
  words, 1,144 seen 4+ times (the prototype's hand-reviewed list had 1,106); 14 words are not
  sentence safe; 297 ambiguous words (seen 4+ times) remain on the worklist.
- dictionary: 218,856 entries indexed in about 8 s (72 MB), lookups about 1 ms.

## Decisions

| Topic | Decision |
|---|---|
| Platforms | GBA and GBC (GBC added 2026-10-09 for Pocket Monsters Crystal (Japan), before the first release); then NDS, PSP and others |
| Interfaces | CLI, plus a desktop app for the first release: the local web UI in a native window (pywebview), falling back to the browser. `yomineko serve` gives the browser version. Executables for Windows, macOS and Linux (PyInstaller), unsigned |
| Cost | Zero for the project: nothing hosted, nothing paid. Anything that costs money uses the user's own account |
| Translation | Free/offline by default; AI only with the user's own key or agent (see below) |
| License | Apache-2.0 for code |
| Name | **yomineko** (読み猫, "reading cat") |
| Web UI stack | FastAPI + Jinja templates + HTMX + Pico CSS: no JS build step, mobile-friendly layout, assets vendored. Binds to 127.0.0.1 only. `--lan` (phones on the same Wi-Fi) is postponed |
| Profiles | In-repo data-only YAML keyed by ROM checksum (`src/yomineko/profiles/`), PR + CI schema check |
| Ordering | User preference: ROM order, frequency, script order (when the profile knows scene tables), play-along |
| Dictionary | The original EDRDG `JMdict_e.gz`, downloaded at runtime and never bundled. Chosen over the jmdict-simplified JSON because the JSON dropped the frequency ranks (nf01 to nf48) that pick between homophones |
| Tokenizer | SudachiPy split mode C, an **optional extra**: `pip install "yomineko[analyze]"` (the dictionary package is 77 MB). Imported lazily; a missing install raises `MissingExtraError` with the exact command |
| Review file | YAML of JMdict ids, ROM line ids and the reviewer's own English, never game text. Word rules (remap, drop, gloss, `sentence_safe`), line exceptions that beat word rules; a packaged review per game applies automatically and the user's wins |
| Network | Only `analyze/dictionary/source.py` may touch the network, only on `dict download`; a test enforces it |
| Architecture | Layers are enforced by import-linter: dependencies point down (see ARCHITECTURE.md) |
| Git workflow | Branch per PR, commits authored with the personal address, PR bodies passed with `--body-file`, the owner merges, never `main` directly |

## Legal guardrails (not legal advice)

The public statement of these rules, for users and contributors, is `DISCLAIMER.md` (YOM-62).

- Ship code and profiles only: **no ROMs, no extracted scripts, no prebuilt decks**, no game
  assets. Users run the tool on their own dumps (verified by checksum).
- **No circumvention**: never ship keys or decryption. Stick to platforms whose dumps need none
  (GBA/GBC/NDS/PSP). The Nintendo v. Yuzu settlement (2024) centred on keys and piracy-facing messaging.
- Profiles and reviews hold offsets, encodings, ids and control codes only, **never game text**.
  `tools/repo_guard.py` blocks ROM/archive/deck files and any file with a long run of Japanese
  outside `tests/`; the review schema rejects a gloss containing Japanese.
- The worklist and any export contain game text: they live under the git-ignored `yomineko-out/`
  and are never committed or shared.
- Dictionary data (JMdict, CC BY-SA, (c) EDRDG) is **downloaded at runtime**, not bundled; it is
  credited in `dict` output, in scripts (`dictionary.credit`) and in word exports. Anki cards must
  carry the credit too.
- No Nintendo/Pokemon names or art in the project name, logo or marketing. A profile or doc may
  name a game factually.
- Everything runs locally; ROMs never leave the user's machine. No telemetry, no accounts.

## Translation strategy (free by default)

Each translation records its source: `official`, `dictionary`, `machine`, `reviewed`.

1. **Dictionary glosses (default, free, offline)**: every sentence card lists its words with JMdict
   meanings. Enough to read most lines without a full translation.
2. **Official English from the user's own English ROM**: if a Western release exists, the user
   supplies that dump too and the tool aligns text through matching tables (as the prototype did
   via the US decomp). Real localization, free; looser than literal.
3. **Bring your own provider**: pluggable interface (Gemini, Claude, OpenAI, DeepL Free); the user
   pastes their own API key, costs go to their account. Batching + caching so lines are never
   translated twice.
4. **Local model**: optional offline machine translation through a model the user runs (e.g. Ollama).
5. **Export, translate anywhere, import**: CSV out with untranslated lines, CSV back in.
6. **Agent integration**: an MCP server (`list_untranslated`, `submit_translation`, `lookup_word`)
   plus a skill, so users with an agent subscription can translate in batches with their own plan.

## Architecture

Current layout (see ARCHITECTURE.md for the rules and the reasons):

```
src/yomineko/
  model.py  errors.py  script_io.py  extract.py
  core/        rom, encodings (Shift-JIS, .tbl, readable text), discover, roundtrip
  profile/     schema.py (the format), loader.py, template.py
  profiles/    packaged game profiles (YAML)        reviews/   packaged reviews (YAML)
  analyze/     dictionary/ (download, XML parser, SQLite index), tokenizer, matcher,
               vocabulary, review, worklist
  export/      select, csv_export, json_export, words_export, sentences, sentences_export,
               study (the card-ready set), anki, xlsx_export
  cli/         app, dict_cmd, analyze_cmd, review_cmd, study_cmd, common
tools/         repo_guard, gen_schemas, sentence_excludes
               (developer scripts)
```

Still to come, from the original design: `translate/` (providers), `order/` (rom, frequency,
script, play-along), `web/` (stage 4), `mcp/` (stage 5).

Data model (JSON is canonical, schema version 4; versions 1 to 3 still load). `Script` holds
`game`, `lines`, `words`, `terms` and `dictionary` (the credit). A `Line` has `id` (the ROM address
as 8 hex digits), `address`, `bank`, `raw`, `text`, `kind`, `referenced`, `duplicate_of`,
`translation {text, source}`, `word_ids` (JMdict ids of the line's reviewed, sentence-safe words,
filled by `analyze`) and unused `scene`/`seen`. A `Word` has `jmdict_id`, `written`, `kana`,
`kanji`, `pos`, `common`, `jmdict_rank` (JMdict's frequency band: 1 to 48 in bands of 500, 60 other
common, 100 the rest; empty when analysed before schema 4), `sentence_safe`, `meanings`, `freq` and
`examples` (line ids, capped at 20). The learner's level (`export/level.py`, YOM-68) skips the words
whose `jmdict_rank` is in the commonest 1,000, 5,000 or 10,000; export, the CLI (`--level`), the
sentence picker and the web pages share that one selection. Words marked "I know this" (YOM-69,
`pipeline/known.py`: `<workspace>/known.json`, JMdict ids only, shared by every game) are left out
by the same selection, whatever the level; `yomineko known` lists and clears them. Schema 4 is not released yet, so YOM-25's
`Line` field can join version 4 if it lands before the release; after the release it needs version 5. A `Term` has `jp`, `category`, `index`, `line_id`, `jmdict_id` and `literal` (set when the text
matches exactly one dictionary entry) and an unused `official_en`.

## Stages still to do

3. **Exporters** (built; see "Stage 3 follow-ups" for what is left to confirm on real data).
4. **Local web UI, desktop app and executables.** See "Stage 4 decisions".
5. **Translation providers.** Official alignment from an English ROM; CSV round-trip; BYO API key
   interface; local model; MCP server + skill.
6. **Second game: Gyakuten Saiban (GBA, Japan, Rev 1).** Tests whether the profile system
   generalizes beyond PMD. The owner has a dump (kept outside the repo).
   To verify on first look: its text encoding (possibly a custom table rather than Shift-JIS) and
   whether the script is compressed. There was no English GBA release (the English version came
   out on DS), so official-English alignment would be a cross-platform stretch goal. Use the
   `rom-investigator` agent and the `add-game-profile` skill. Then compression hooks, then NDS.
   **Investigated and built 2026-10-04** (`docs/games/gyakuten-saiban-jp.md`): the script is 17 standard
   GBA BIOS LZ77 blocks behind a pointer table; each block starts with a count and entry offsets; the
   text is 16-bit glyph ids into the game's own font (the table was read off the font). Built: the
   decoder, `compressed` profile block, `table16` encoding, virtual line addresses, decompressed-level
   `verify`, the profile. Open: line quality, joins, word review (see "Next session").
7. **Play-along ordering** from text-hooker logs; discovery helpers to draft profiles.

## Stage 3 decisions (settled 2026-10-04)

Stage 3 shipped as two PRs: **A** schema v3 (merged) and **B** sentence selection, Anki, XLSX, docs and
0.3.0 (one PR, at the owner's request).

1. **Sentence filters.** Generic structural heuristics in code; address ranges and caps become
   optional profile data; the review file gains `sentences: {exclude, pin}` holding ROM line ids
   only. The PMD exclude list is generated locally from the prototype's regexes by a dev tool and
   committed as ids. The regexes themselves (game text) never enter the repo.
2. **Words per line.** `Line.word_ids` (reviewed, sentence-safe JMdict ids, first-seen order, no
   repeats), filled by `analyze`; schema version 3. Older files read with it empty; sentence export
   asks for a re-run of `analyze`.
3. **Dependencies.** `genanki` and `openpyxl` are base dependencies.
4. **Term cards.** A term gets a card only when its text matches exactly one JMdict entry;
   `analyze` stores the match (`Term.jmdict_id`, `Term.literal`). Official names wait for stage 5.
5. **Translations.** Sentence cards carry the dictionary-gloss word list; the English field comes
   from `Line.translation` when set (nothing writes it before stage 5).
6. **Ordering.** `--order frequency` (default) or `rom`; script order and play-along wait.
7. **Card design.** The prototype's Word, Sentence and Term note types, `ja_JP` TTS, a Jisho link,
   the JMdict credit footer. Ids come from SHA-1 of stable parts: note types versioned and shared,
   decks per game, GUIDs from the JMdict id (words), ROM line id (sentences) and category plus text
   (terms), so re-import updates cards in place. Deck tree `<game>::1 Words / 2 Sentences / 3 Terms`.
8. **Verification.** Tests read the `.apkg` (a zip with SQLite); the owner imports one deck into Anki.
9. **Reuse.** `export/select.py`, `export/words_export.py`, `Word.sentence_safe`, `Script.dictionary`,
   `tests/support/`.

## Stage 4 decisions (settled 2026-10-04)

One PR (`feat/stage4-app`), one commit per step, each green on its own:
0. Packaging check, throwaway: PyInstaller bundled today's CLI with SudachiPy and its dictionary on
   Windows (226 MB, onedir) and reproduced the native numbers (1,144 words, 1,000 sentences, 464 terms).
1. `pipeline/` layer shared by `cli` and `web` (reviews, study, analysis, workspace). Done.
2. `web/` skeleton: `serve`, safety middleware, vendored HTMX and Pico CSS, first-run notice, ROM
   upload and extract. Done. (A real browser caught that `Referrer-Policy: no-referrer` makes Chromium
   send `Origin: null` on form posts, which the Origin check refuses; the policy is `same-origin`.)
3. Dictionary download button, analyze with progress (background job, polled), and browsing of words,
   lines and the picked sentences. Done; on the PMD dump the UI gives the CLI numbers.
4. Review screen: word corrections saved to the user's own `review.yaml`. Sentence exclude/pin stays
   in the YAML for now. Done: ambiguous words with alternatives and example lines (297 on the PMD dump),
   choose another entry (optionally "right for most lines, not all"), drop, replace the meaning, or confirm
   the pick (remembered in `review-state.json`, since a review file cannot say "this is fine"); undo; an
   "apply" button re-analyses.
5. Export form: Anki, XLSX, CSV, JSON as downloads. Done. The CLI and the web page both build files with
   `pipeline/exporting.py`; on the PMD dump the web deck is byte-identical in size to the CLI deck (2,608 cards).
6. `app/` (pywebview window, browser fallback with a Quit button), PyInstaller builds for three systems in
   a manual GitHub Actions workflow with a smoke test and checksums, README, CHANGELOG, version 0.4.0.
   Done and checked on Windows: the 239 MB folder passes `yomineko app --smoke` (pages, packaged data,
   tokenizer), analyses the PMD script and exports the same 2,608 cards, and the windowed app opened a
   window serving on 127.0.0.1 only. **Not run here:** the macOS and Linux builds and the workflow itself
   (its YAML parses); the first run of "Build app" on GitHub is the real test, and the owner opening the
   macOS and Linux apps once. Open: signing (decided against for now), file downloads inside the
   pywebview window (the setting is on; not yet tried by hand: export a deck from the app once), the 239 MB size.
   Found in pywebview's source (YOM-12): on macOS the window saves a download by fetching its address again
   with a GET, so a file sent as the answer to the export form's POST came out as the export page. The
   form now builds the file and redirects to `/downloads/<secret>`, which serves it (the newest four kept).
   Windows (WebView2) and Linux (GTK, Qt) save the response they got and were not affected.
   Checked by hand in the Windows window (Anki and XLSX saved, Save dialog each time) and, through the real
   WebKit path with a scripted Save panel, on a Mac. The Mac window shows text/csv and application/json on
   screen instead of saving, so downloads are served as application/octet-stream.

Rules for the local server: 127.0.0.1 only, `Host` check against DNS rebinding, a per-run token and
same-origin check on every state-changing request, ROM uploads size-capped and kept in memory, nothing
loaded from a CDN, and `test_network_boundary` keeps one extra allow-list entry for the listener. The
dictionary is not bundled: a button downloads it on first use, which is the only network use.

Follow-ups after the first release:
- **In-browser version (static site, free hosting).** Considered and postponed. The ROM would never
  leave the device, like Rom Patcher JS (marcrobledo.com/RomPatcher.js), but yomineko needs a Python
  runtime and two dictionaries. First look: Pyodide ships pydantic, PyYAML and sqlite3; SudachiPy has
  no browser build, but two community WebAssembly builds of the same engine exist (sudachi.rs based);
  about 150 MB on first visit; open questions are phones (iOS memory limits) and whether edrdg.org
  allows a browser fetch (CORS). Static hosting is free; a domain is the only cost. Needs a spike:
  tokens must match SudachiPy so the packaged review still applies.
- **`--lan`:** phones on the same Wi-Fi, with a QR code and an access token.
- **Release:** the repo must be made public first (the checklist under Backlog), then the PyPI upload
  and attaching the executables to a GitHub Release; both are the owner's steps.

## Before the first release (decided 2026-10-04)

**Why profiles matter.** yomineko works best with a curated *profile* per game: where the text is, how
it is encoded, what the control codes mean, plus a packaged review of the word picks. Making one takes
real investigation (hours for a plain Shift-JIS game, much more for a custom table or compressed text),
so the project cannot do it for every game itself. The plan is to **let users contribute profiles**
and to give them the tools to do it alone: the `add-game-profile` skill, the guide
[ADDING_A_GAME.md](ADDING_A_GAME.md), and issue and PR templates. All of that exists now; the work
left is making the underlying features good enough that contributors succeed (below).

**What a scan of ten other Japanese games showed (2026-10-04, from the owner's collection).** A
profile-less Shift-JIS scan, the way a "generic mode" would work, read 0 to 141 kana lines per game,
against about 9,500 dialogue lines for PMD. All ten had a `J` game code. Most Japanese GBA games use a
custom character table, compression, or both, so "any Japanese game works with no profile" is not
realistic. A best-effort generic mode is postponed until a second and third game show what is common.

**Pre-release goals.**
1. **Fine-tune with a couple of real ROMs before releasing.** PMD Red JP is the reference. Gyakuten
   Saiban (compressed, probably a custom 16-bit table) is the hard case that drives the next features.
   Pick one plain Shift-JIS game as an easy case (none of the ten scanned looked like one; choose by
   trying). Record counts for each in this file. (Done 2026-10-11: four games checked on real dumps, counts
   under "Release roadmap". PMD Red is itself plain Shift-JIS, so it is also the easy case; no other plain
   Shift-JIS game was found.)
2. **LZ77 decompression and the Gyakuten Saiban profile** (done, PR #19; line quality work is open, see
   "After that").
3. **Japan-only check.** (Done 2026-10-05.) `extract`, `verify` and the web upload refuse a ROM whose game
   code does not end in `J` ("yomineko reads Japanese games"); a profile's `game_code` must end in `J`.
4. **Several checksums per profile**, for revisions and other dumps of the same game. (Deferred: a revision
   usually moves the offsets, so a second checksum alone would not make a profile work, and there is no
   second dump of a supported game to test with.)
5. **Contributor kit** (done): `docs/ADDING_A_GAME.md`, the reworked skill, `.github` templates, the README
   section "Games and profiles". Keep it true as the features above land.
6. **Real-world checks still owed:** export a deck from inside the app window, open the macOS build (the
   owner does it), `pytest -m realrom` bands (done 2026-10-11: 39 passed on four dumps, see phase 4). The owner cannot open a Linux build, so the **Build app**
   workflow's smoke step on its Linux runner (`--version` and `app --smoke`) is the Linux check (decided
   2026-10-09). (Done 2026-10-11: Build app run #1 green on all three systems with the smoke steps (YOM-11);
   the owner opened the macOS app, which needs the quarantine flag cleared as the README says; decks exported
   from the app window on Windows and through the WebKit path on a Mac (YOM-12). Moved to release day: a CSV
   export and a human click on the Save panel in the Mac window.)
7. Then release: the steps in "Repositories" above and `.claude/skills/release/SKILL.md` (YOM-16).

**Gate B (YOM-15, 2026-10-12): passed.** Items 1 to 3, 5 and 6 are done, 4 is deferred with its reason, and
7 is release day. The release-candidate tickets YOM-9 to YOM-14 and YOM-59 are done.
The owner's merge of this change is the go.

## Clean-up session (done 2026-10-05)

Nothing was added; `main` was checked and a few things fixed (PR #22, one commit per finding).

- **Gate:** green on `main` (972 tests before the fixes, 982 after; 98.69% coverage, 4 import contracts kept, three profiles valid).
  `pytest -m realrom`: 27 passed on the owner's three dumps.
- **Real runs (counts only):**

  | Game | strings | unique lines | words | deck | verify |
  |---|---|---|---|---|---|
  | PMD Red JP | 12,817 | 12,128 (9,549 dialogue, 2,579 terms) | 2,952 | 2,608 cards | rebuilt, sha1 `4bc9370e...` |
  | Gyakuten Saiban JP | 36,273 | 26,100 (22,598 dialogue, 3,502 terms) | 4,207 | 2,467 cards (1,467 words, 1,000 sentences) | decompressed level, 36,273 lines |
  | Mario & Luigi RPG JP | 5,962 | 5,152 (3,913 dialogue, 1,239 terms) | 2,245 | 1,534 cards (534 words, 1,000 sentences) | rebuilt, sha1 `edc538ac...` |

- **Mario & Luigi sentence deck:** all 1,000 sentences read as dialogue; no debug strings, menu fragments or
  escapes. No `sentences.exclude_ranges` or caps are needed. The button glyphs (circled letters) occur in real
  tutorial lines and stay. Bank names are `bank_<offset>` (31 banks).
- **Web interface on the Mario & Luigi script:** the game is listed, the game page shows the CLI counts,
  and the lines, words, sentences, review and export pages all answer 200 with rows.
- **Fixed:** `yomineko export --help` crashed on a cp1252 Windows console (the `--player-name` default is
  Japanese); the help of the main commands is now tested. From the code review: one shared `RUN_LIMIT`
  for table8, each LZ77 candidate decoded once in the survey, no block copy per compressed entry, and tiles
  cut short by the end of VRAM are ignored in the save-state check.
- **Documentation:** `.claude/agents/rom-investigator.md`, `profile-author.md` and the `add-game-profile`
  skill now mention `yomineko survey` and the three profile kinds; the Mario & Luigi notes put the result and
  open work first, with the investigation log after them. README, CHANGELOG, ARCHITECTURE and ADDING_A_GAME
  were read against the code and were already true.
- **Review findings left open (not bugs that bite today):**
  - `core/discover/stream.py`: a run that crosses the end of a region is dropped without a message. Report
    it (as `unstable` or a count) the next time that file is touched. (Touched on 2026-10-09 for framed
    messages and left as it was: reporting it needs a count carried up to the CLI and the web page.)
  - `core/encodings/table8.py`: a command whose parameters run to the next prefix byte (`UNTIL_PREFIX`)
    uses `data.find` on every call; harmless in the three profiles, quadratic in a sparse region.
  - `survey/state.py`: `_match_tiles` searches the ROM once or twice per distinct tile (up to 512); an index of
    the ROM's tiles would make the state check fast. Only matters with `--state`.
  - `profile/schema.py`: `Encoding._table_required` holds about ten rules (2026-10-18); split it by encoding type if another kind
    is added.
  - `extract.py` picks the discovery route with `isinstance(codec, Table8Codec)`; a codec-level `discover`
    would keep it closed to new kinds.
  - (Closed 2026-10-18: `synthsurvey.py` imports its shared encoders from `synthrom.py` and repeats none.)
  - `core/encodings/base.py`: `escape_literal` is used nowhere; delete it the next time the file is touched.
  - (Re-checked 2026-10-18 for YOM-16, before the release: the others above are still open and none blocks it.)
- **Machine clean-up:** the owner approved deleting the spike output in `yomineko-out/` (all but `patterns.txt`,
  `review.bak`, the six table-making scripts with their `glyphs_jp.json` and `kanji_used.json`, `save/` and the
  new `verify/`) and the merged branches. The first delete was refused by the tool's safety check, so it is
  still to do (local folder only; nothing is tracked).

## Release check (2026-10-05): can the tool be used on the three games?

Done through the web interface as a user would (upload, extract, analyse, browse, export Anki, XLSX, CSV and
JSON), through the CLI, and from the built wheel in a clean virtual environment. Every page answered, every
export opened, the same numbers came out of all three routes, and no raw escape (`{FF}`, `{8540}`) reached a
card or a sentence.

| Game | Verdict | What the user gets | Limits |
|---|---|---|---|
| PMD Red JP | **ready** | 1,144 words, 1,000 sentences, 464 name cards (2,608 cards) | the remaining ambiguous words are unreviewed |
| Gyakuten Saiban JP | **works, with limits** | 1,469 words, 1,000 sentences (2,469 cards) | sentences are one text-box row (median 14 characters), but whole sentences are preferred (3 of 1,000 do not end like a sentence); 35-rule first-pass review with the main names left out; no name cards |
| Mario & Luigi RPG JP | **works, with limits** | 545 words, 1,000 sentences (1,545 cards) | one box line per sentence (median 14); 48 of 1,000 do not end like a sentence; 8-rule first-pass review; no name cards; two rare kanji (0xFB42, 0xFC27) are not in the table |

**Second round (2026-10-05, `fix/word-quality`).** The wrong verb picks had one cause in the matcher: an
inflected verb written with kanji has the reading of its inflected form (聞い is きい), and the entry was only
accepted when its reading matched, so a word that sounded like the stem took its place. Fixed in
`analyze/matcher.py`; 15 of the review rules written an hour earlier stopped matching anything and were
removed (PMD's 311 all still apply). Character names (surnames split into single kanji, nicknames spelled
like a noun) are now listed in the worklist as "probable names" with the reason (honorific after the noun, or
a single kanji always followed by another); 14 were dropped with review rules. The sentence selector scores a
card that does not end like a sentence at half, which cut unclosed cards from 348 to 3, 155 to 48 and 135
to 20.

Why the first-pass reviews were needed: the top of both word lists held wrong dictionary picks (こと as 琴,
verb stems such as 聞い, 書い, 言い, 見 matched to unrelated words, character names split in two). One rule
fixes hundreds of cards (3,361 and 500 occurrences). `tests/test_real_reviews.py` checks that every rule still
applies on the real dumps.

Not done on purpose: joining Gyakuten Saiban's rows into sentences (needs the meaning of its commands), the
Mario & Luigi message index, the long tail of word review, name cards for the two new games (needs profile
`tables`).

Also found and fixed: `yomineko export --help` crashed on a cp1252 console; NOTICE said "later releases" for
JMdict and did not mention Sudachi, which the desktop builds ship.

Release hygiene checked: the wheel and sdist hold the three profiles, the two character tables, the three
reviews, schemas and web assets, and no ROM, archive, deck, game text or local path; `twine check` passes;
git history (96 commits) has no blob over 500 KB, no ROM-like file, no token pattern, no local path. Commits
carry the owner's personal e-mail address; it becomes public with the repository unless the public
history is a new squashed commit authored with a GitHub noreply address (see "Repositories" above).

## Release roadmap (2026-10-09)

The owner wants **Pocket Monsters Crystal (Japan, GBC)** in the first release. The release stays 0.5.0
(nothing was ever published); its changelog gains a Crystal entry and the date moves to release day.

**MVP for 0.5.0:** a learner points yomineko at their own Japanese ROM and gets a word list, sentence cards
and an Anki deck. Games: PMD Red (ready), Crystal (target: ready), Gyakuten Saiban and Mario & Luigi RPG
(shipped as "works, with limits", the limits stated in the README). Platforms: GBA and GBC. Everything in
"What exists now", the web UI, the desktop app and the executables. Not in 0.5.0: translation (stage 5),
whole sentences from text-box rows, Fire Emblem, NDS/PSP, play-along ordering, several checksums per
profile, LAN mode, name cards for the two "with limits" games.

| Phase | Where | Done when |
|---|---|---|
| 1. Release health check | cloud | **Done 2026-10-09** (below) |
| 2. Investigate Crystal | owner's machine (the dump stays there) | **Done 2026-10-09**: `docs/games/pokemon-crystal-jp.md` |
| Gate A | | **Passed 2026-10-09**: the encoding fits `table8` and the 177-code kana table was read off the font tiles. Had it failed, three games would ship and Crystal would move to 0.6.0 |
| 3. GBC support and the Crystal profile (one PR) | cloud + owner's machine | **Done 2026-10-09** (results below): GB header and Japan check, `platform: gbc`, banked regions, a framed `table8` discovery rule, unique table texts for the word and name bytes, a rule for the katakana that use hiragana glyphs, name tables, synthetic GBC ROM tests, the profile, byte-identical `verify`, a first-pass review |
| 4. Release candidate | owner's machine | `tools/game_check.py` on four games (**done 2026-10-11**, below), `pytest -m realrom` (**done 2026-10-11**: 39 passed, 0 skipped, on `164bea8` with all four dumps; `tests/test_real_reviews.py` 3/3, so every packaged review rule still applies), docs say GBA and GBC (**done 2026-10-11**, below), Build app run (**done 2026-10-11**: run #1 green on all three systems with the smoke steps, macOS opened by the owner), deck exported from the app window (**done 2026-10-11**: Anki and XLSX on Windows, and through the WebKit path on a Mac) |
| Release PR | cloud | **Done 2026-10-11** (YOM-14): changelog dated 2026-10-11; full gate green (1,162 passed, 98.6% coverage); a fresh wheel and sdist pass `twine check` and hold the four profiles, the three character tables, the four reviews, the schemas and the web assets, and no ROM, archive, deck, game text or local path (the tables hold only marked `<...>` entries); the wheel installs in a clean venv, `yomineko --version` says 0.5.0 and `profile validate` passes all four. `dist/` is not committed: rebuild it on release day with `python -m build` |
| Gate B | | **Passed 2026-10-12** (YOM-15): every item in "Before the first release" is done or deferred with a reason |
| 5. Release day | owner | the steps in "Next session" below |

**Crystal, expected before phase 2 (confirmed or corrected in `docs/games/pokemon-crystal-jp.md`):** one-byte
characters, kana only, with control bytes for line, paragraph and end of text (fits `table8`; confirmed);
text in many 16 KiB banks (20 text banks; needs banked addresses: bank x 0x4000 + offset). Corrected: the
Japanese game has no far-text command (it exists only in the US build), so text sits inline with its
scripts; fixed-length name
tables for species, moves and items (term and name cards); header title `PM_CRYSTAL` with a 4-character
code ending in `J`, and the destination byte 0x14A (0x00 = Japan) as the fallback for carts without one.
The pret `pokecrystal` disassembly is of the US game. It documents the shared engine (text commands, far
text, scripts) and lists the Japanese kana in its character map; read it to understand the format only,
copy nothing, and check the table against the Japanese ROM's font. Risks: text reached only through
scripts (fall back to a stream scan of the text banks, as Mario & Luigi does), dakuten stored as separate
characters, kana-only homophones (needs a first-pass word review), Mobile System GB text in the sentences.
Gold and Silver (Japan) share the engine and are natural follow-ons.

**Phase 1 results (2026-10-09, `main` at 1abbd8b):** the full gate is green (ruff, format, mypy strict, 4
import contracts, 3 profiles valid, repo guard; 1,057 tests passed, 2 skipped without Pillow, 98.58%
coverage). A fresh wheel and sdist (133 and 237 files) pass `twine check` and hold the three profiles, two
character tables, three reviews, schemas and web assets, and no ROM, archive, deck or local path. `yomineko`
is still free on PyPI. The public repository is 8 commits ahead of and 56 behind private `main`.
`SECURITY.md` did not exist yet (added 2026-10-12, YOM-18).

**Phase 3 results (2026-10-09, counts only; `docs/games/pokemon-crystal-jp.md` has the detail):**

| Game | strings | unique lines | words | deck | verify | verdict |
|---|---|---|---|---|---|---|
| Pocket Monsters Crystal JP | 14,184 | 12,793 (12,632 dialogue, 161 short) | 3,229 | 2,429 cards (1,252 words, 1,000 sentences, 177 names) | rebuilt, sha1 `95127b90...` | **ready** |

- **What was built:** `core/rom` tells GBA from Game Boy by each header's own checksum and carries the
  region on `Rom`; `platform: gbc`; `{bank: n}` regions (read as file offsets); `discover.frame` and the
  message scan in `core/discover/stream.py` with the in-bank pointer test; `tables[].kind` `records` and
  `strings`; a synthetic four-bank GBC ROM with every shape of message and of non-message.
- **Decisions taken on the data** (each one measured, see the notes): text is read from whole messages,
  not from every stretch after a 0x00; an unpointed message needs 6 kana outside the marked entries
  (about 40 short real ones are lost, about 15 junk lines remain; at 8 the battle bank loses 40 more, at
  5 the junk comes back); the graphic tiles 0x60-0x6C and 0x79-0x7E are left out of the table; bank 0x20
  is read to 0x081400 only; `dialogue_min_length` is 4 because a line is one short row.
- **Kept:** all 20 text banks, bank 0x5D (calls on the phone) and the mobile-adapter lines inside the
  script banks included. Not separable by address, and a player sees most of them.
- **A scorecard fix came with it:** `tools/game_check.py` counted probable names in the unreviewed picks,
  so dropping a name in a review could never clear the limit. It now applies the game's review, as
  `yomineko review worklist` does. The other three verdicts are unchanged (PMD ready; the other two
  limited by having no name cards).
- **Detection checked on the owner's collection:** 97 GBA and 51 GBC archives all load with the right
  platform; the region agrees with the file name for all but one world release without a game code.
- **After the merge (2026-10-10), on the owner's decision:** the 17 fixed strings of the text engine
  left the character table. The profile lists their ROM offsets (`encoding.rom_strings`) and they are
  read from the user's ROM, so no file in the repository holds them. The limit of 6 kana for a message
  with no pointer stays: it keeps junk out of the cards. The earlier table is still in the history of
  the private repository (commit 77c94fc); see "Repositories" before making anything public.
- **Still open for Crystal:** the list at the end of its notes (reference-book entries, whole
  sentences, the long tail of the word review, Gold and Silver).

**Phase 4 scorecards (2026-10-11, `main` at 164bea8, counts only):** `tools/game_check.py` on the owner's
four dumps. Every verdict matches the README's game table, and every game rebuilds byte for byte with no raw
escape in a card and every review rule applied. Crystal is still *ready* after PR #32 moved its 17 fixed
strings to `encoding.rom_strings`.

| Game | strings | distinct lines | words (3+) | deck | sentences: median, unclosed | review | verdict |
|---|---|---|---|---|---|---|---|
| PMD Red JP | 12,817 | 12,128 (9,549 dialogue, 2,579 terms) | 2,948 (1,418) | 2,608 cards (1,144 words, 1,000 sentences, 464 terms) | 31, 20 | 311 of 311 | **ready** |
| Gyakuten Saiban JP | 36,273 | 26,100 (22,598 dialogue, 3,502 terms) | 4,144 (1,814) | 2,469 cards (1,469 words, 1,000 sentences) | 14, 3 | 35 of 35 | **works, with limits** (no name or term cards) |
| Mario & Luigi RPG JP | 5,962 | 5,152 (3,913 dialogue, 1,239 terms) | 2,227 (758) | 1,545 cards (545 words, 1,000 sentences) | 14, 48 | 8 of 8 | **works, with limits** (no name or term cards) |
| Pocket Monsters Crystal JP | 14,184 | 12,793 (12,632 dialogue, 161 terms) | 3,229 (1,531) | 2,429 cards (1,252 words, 1,000 sentences, 177 terms) | 16, 73 | 64 of 64 | **ready** |

The manual read of each game's `samples.txt` (the skill's judgement step) was not part of this run.

**Phase 4 docs check (2026-10-11):** README, CHANGELOG, CONTRIBUTING, ARCHITECTURE, ADDING_A_GAME and every
agent and skill read against the code. Fixed: the README game table gained the scorecard verdicts and `.gb`
files; the phone line no longer promises a phone version; CONTRIBUTING names all four text kinds; the
ARCHITECTURE layer diagram and layout gained `web` and `app`; the profile-author and rom-investigator agents,
the add-game-profile skill and ADDING_A_GAME cover Game Boy Color pointers and the Crystal profile; the
read-glyph-table skill says it has been used on GBA only. CHANGELOG was already true. No user-facing doc
promises translation, NDS or LAN mode (the translator agent and translate-lines skill say they are
placeholders).
The rest of phase 4 (`pytest -m realrom`, the Build app run, a deck exported from the app window) was done on
2026-10-11; see the phase 4 row above.

## Next session: release day, then the next game

**Owner's steps on release day** (nobody else can or should do them):
1. Run the **Build app** workflow on the release commit (run #1 on 2026-10-11 was green on all three
   systems). In the macOS window, export a CSV and click Save by hand (the one export not yet tried there).
2. Make the public repository public and push `main` to it (the two options are in "Repositories").
   Then turn on private vulnerability reporting (Settings, Code security) so the Security tab
   link in `SECURITY.md` works; GitHub offers it on public repositories.
3. On merged `main`, `python -m build` (the `dist/` built before Crystal is stale), then
   `python -m twine upload dist/*` with their own token, tag `v0.5.0`, attach the executables to a GitHub
   Release (`.claude/skills/release/SKILL.md`).

**After the release, in this order:**
0. **Whole sentences from text-box rows** (planned, not built). Three games give one box row per
   sentence card (Gyakuten Saiban, Mario & Luigi, Crystal; for Crystal the break bytes are in
   `discover.frame.breaks`, and 0x4F is the one inside a box). Build it from `yomineko survey --commands`: a profile field `encoding.soft_breaks` (the
   commands that are only a line feed inside one box), discovery marks a line that follows the previous one
   across soft breaks (a `Line` field: in schema v4 if that is still unreleased, else v5), and the sentence export joins
   such chains (the id of the first row, the words of all). `verify`, lines and the word list stay as they are.
1. **A fourth game: Fire Emblem: Fuuin no Tsurugi (Japan)**, which the owner wants to try. First look
   (2026-10-05, counts only; `AFEJ`, 8 MiB, sha1 `a57095da...`): the script is **Huffman-coded with the game's
   own tree**, not the BIOS format, so none of the three profile kinds can read it. The tree is 3,283 nodes of
   4 bytes at 0xF300C-0xF6358 (a node is two 16-bit child indexes; a leaf has 0xFFFF in the high half and the
   symbol in the low half; the root is the last node). 3,342 ascending pointers at 0xF635C-0xF9794 lead to
   the messages (0x9FAC0-0xF2FFF). Bits are read from the low bit of each byte up and a message ends at symbol
   0; with that, 3,341 of 3,342 messages end exactly where the next begins. Symbols are Shift-JIS two-byte
   values (low byte first, about 64% kana and 14% kanji by use) and one-byte control codes 0x01-0x1C and 0x80.
   Huffman coding is compression, not encryption: no keys are involved. To build: a tree decoder and encoder
   in `core/compression/`, a `huffman` block in the profile schema, discovery that gives each message a
   virtual address (as the compressed blocks do), `verify` by re-packing every message, the control-code
   table, tests on a synthetic ROM, and a survey check for "a table of leaf-style words next to a pointer
   table". Add its dump path to `reference_local_environment` and a `YOMINEKO_ROM_FIRE_EMBLEM_6_JP` variable.
   **Checked against the game's decoder (YOM-61, 2026-10-12): read `docs/games/fire-emblem-6-jp.md` before
   building.** The tree, the bit order and the end of a message are confirmed. Corrected: a symbol is one
   or two output bytes, not a character (156 two-byte symbols are the argument of code 0x10); 0x10 takes
   two argument bytes and 0x80 one; the root is the node whose address is stored after the tree; a leaf is
   a node with bit 31 set; the "one message that does not end at the next" is only the last one. A scratch
   encoder re-packs all 3,342 messages to the ROM's bytes with the split rule in the notes.
2. Several checksums per profile (needs a second dump of a supported game to test with).
3. Gyakuten Saiban dialogue joins and line quality; the rest of the word reviews; stage 5 (translation).
4. The open review findings listed under "Clean-up session".

## After that: check and use Gyakuten Saiban, then the other two games

**Done 2026-10-04 (merged as PR #19):** the LZ77 decoder
(`core/compression/lz77.py`), the block reader and virtual line addresses (`core/containers.py`: ids
0xC0000000 and up, script schema stays v3), the 16-bit glyph codec (`core/encodings/table16.py`), the
`compressed` profile block and `encoding.skip`, text-run discovery (`core/discover/compressed.py`),
`verify` at the decompressed level, and the packaged profile `gyakuten-saiban-jp` with its character
table. The table was read off the game's font; `docs/games/gyakuten-saiban-jp.md` has the layout and
the method, which is the reusable part (other games will need it).

**Real run on the owner's dump** (counts only; a real-ROM test pins them): 18 blocks (17 LZ77 and one
uncompressed), 2,271 entries, 35,859 text runs, 25,944 unique readable lines (22,469 dialogue, 3,475
terms), 4,098 distinct words (1,795 seen three or more times). `yomineko verify` passes at the
decompressed level. Before YOM-36: 17 blocks, 36,273 runs, 26,100 lines.

**Open work, in order:**
1. (Done: PR #19 is merged.)
2. (Done: YOM-36.) **Line quality.** `encoding.skip` holds the argument count of every command but
   0x3F, read off the game's code in the Ghidra spike (YOM-60), and the profile reads the uncompressed
   18th block; 6,626 argument words that could be read as text are down to 0. One-character runs are
   still dropped (`min_chars: 2`). The numbers are in "Command arguments in the profile" in
   `docs/games/gyakuten-saiban-jp.md`.
3. **Dialogue joins.** A box of text is split into one line per row of the text box (command 0x01 and
   others). Joining them gives whole sentences but needs the meaning of the commands in between.
4. **Word picks and sentence rules** for this game: `yomineko review worklist` and the `review-vocab`
   skill (the top word is a kana-only mis-pick, as in PMD), sentence caps and exclusions.
5. **The other two Gyakuten Saiban games** in the owner's collection probably use the same engine:
   try the notes' method (font first) and see how much of the profile carries over.
6. Pre-release items 3 and 4 above (Japan-only check; several checksums per profile).

**Constraints that always apply.** No ROM, extracted text or decks in the repo; profiles hold offsets,
encodings and control codes only; tables are character mappings (data), not game text, but check each
one with `repo_guard`; no circumvention; ROMs stay on the owner's machine and are read in memory only;
never print Japanese to the Windows console (write it to a UTF-8 file and read that). Real-ROM checks
are opt-in (`-m realrom`), compare counts and checksums only, and the ROM path comes from an environment
variable (`YOMINEKO_ROM_GYAKUTEN_SAIBAN_JP`).

## Stage 3 follow-ups

Done 2026-10-04 on the owner's dump (synthetic data in the tests, real data here):
- Real run: 9,349 lines have words; 636 of 2,843 terms match one dictionary entry (464 distinct
  term cards). Export gives **1,144 words, 1,000 sentences and 464 terms** (the prototype had 1,106
  words, about 1,000 sentences and 287 hand-written terms). The new real-ROM test bands use these.
- The packaged PMD review now lists 681 `sentences.exclude` line ids, generated by
  `tools/sentence_excludes.py` from the prototype's `DEBUG` and `LOW_VALUE` patterns (kept in a local,
  git-ignored file; only ids are committed).

The owner imported the generated PMD deck into Anki on 2026-10-04 and it looked right. A rebuilt deck
(900 sentences instead of 1,000) was then imported over it: all 2,508 notes updated existing ones and none
were new, so re-import updates cards in place.
Also the owner's: skim the 464 term cards for names that are real words but poor study material.

## Lessons (carry these over)

From the PMD Red JP prototype:
- Text was Shift-JIS, but the **half-width katakana range is drawn as hiragana**, and lead bytes
  0x84-0x87/0xEB+ were **custom glyphs**. Expect per-game quirks.
- Pointer scanning (32-bit `0x08xxxxxx` on GBA) found 12.8k real strings; random Shift-JIS matches in
  graphics needed a filter (require a full-width kana).
- Kana-only text makes the tokenizer pick wrong homophones about 15% of the time.
- JMdict's first sense is often not the common one (すごい "terrible"); allow gloss overrides.
- Sentence selection needs filters: system/menu text, sleep-talk, fragments, partner-pronoun
  variants, templated battle logs.
- Game names: keep only real words, drop proper nouns; pair a literal meaning with the official name.
- Official English can be aligned **by table index** when US data exists.

Learned building stage 2 on real data:
- Frequency rank alone reproduces the prototype's mistakes (こと as 琴 with 543 occurrences, いらい as
  以来, じしん as 自身, かえる as 代える). That is why the review file exists: one rule fixes hundreds
  of occurrences. Start a game's review with the most frequent items.
- JMdict marks 事 as "usually written in kana", so a worklist must show the kanji next to the reading
  or the right alternative is unrecognisable.
- A newer dictionary and tokenizer fix some old mistakes by themselves: 21 of the prototype's 337
  review rows were for words the current analysis no longer produces, and several others were already
  the matcher's pick. Expect a review to age.
- A short line containing a custom-glyph escape (`{8540}`) can score below the 0.7 text threshold and
  be dropped. This matches the prototype and was kept on purpose.
- YAML reads an unquoted `01001000` as an octal number; line ids in review files must be quoted (the
  loader catches it).
- The tokenizer is quick (about 2 s for a whole game) once per-token results are remembered.

Learned on the second game and the ten-game scan (2026-10-04):
- Plain Shift-JIS text, as in PMD, is the exception. Custom tables and BIOS LZ77 compression are common;
  `docs/games/gyakuten-saiban-jp.md` shows the pattern (pointer table to compressed blocks, an offset
  table inside each block). Graphics use the same LZ77, so 0x10 streams are everywhere in a ROM: a
  decompressor alone does not tell you where the script is.
- A naive Shift-JIS run scan reports about a thousand "kana-looking" runs even in a game with no Shift-JIS
  text: code and sample data decode as kana. Judge a scan by lines that rebuild, not by run counts.
- The header's game code ends in `J` for Japan: a cheap, reliable region check.

Learned from the first three games, and what became a tool (2026-10-05):
- A bug can hide behind the first game. The matcher threw away the right entry for an inflected verb written
  with kanji; PMD, written mostly in kana, hardly showed it, and Gyakuten Saiban filled its top words with it.
  Check a new game's top 60 words from a file before trusting the matcher: `tools/game_check.py` writes them.
- Measure before saying "good enough". The scorecard (`tools/game_check.py`, skill `check-game`) holds the
  numbers behind every verdict: rebuild, escapes in cards, cards that stop mid-sentence, repeated sentences,
  probable names, stale review rules, empty fields. A new kind of problem becomes a new measure and a test.
- Investigation by hand is slow once and cheap after it is a tool. The Mario & Luigi work left four methods:
  compare two regions (`yomineko survey --compare`: 8 s, finds the Japan-only ranges that hold the script),
  measure the control codes of a draft profile (`--commands`: finds which command arguments read as text),
  render every code in an emulator (`tools/glyph_render`, skill `read-glyph-table`, agent
  `glyph-transcriber`) and the scorecard above. `add-game-profile` ends by asking what the game taught the
  tool; write the answer here.
- Names are the main noise left in a kana-heavy word list. The worklist now lists probable names (honorific
  after the noun, or two single kanji that always go together); a person confirms and drops them.

Learned on the fourth game, the first on another console (2026-10-09):
- When every byte value is a character, no test on the characters separates text from data. What does
  is structure: where a message may start, what may be inside it, and that it must end. Find the frame
  in the game's own text routine before trying filters.
- Count before choosing a threshold, and read what each choice loses. "A pointer or 8 kana" from the
  investigation notes looked right until the list showed 40 real battle lines under it and script bytes
  passing over it because one byte can stand for a six-kana word. Counting only the kana outside the
  marked entries, with a limit of 6, kept the lines and dropped the bytes.
- A font is not one picture. The tiles a dialogue box loads at a code can differ from the ones a battle
  screen loads at the same code; find the load that the text you are reading uses.
- One glyph for two characters needs its contexts read, not guessed: the same code is a katakana in one
  word and a particle after another.
- A table entry for a byte that draws several characters must not be the plain string, or the same
  string spelled out re-encodes to the wrong bytes. A marked text keeps `verify` exact and costs two
  `plain` rules.
- A measure that ignores the fix it recommends cannot improve (the scorecard's name count). When a
  number does not move after the remedy, read how it is computed.
- A second worktree shares the first one's virtual environment, which imports the first one's source.
  Set `PYTHONPATH` to the worktree's `src` for every check, and print `yomineko.__file__` once.

Environment notes (Windows):
- The Windows console is cp1252: never print Japanese from a command; write it to a UTF-8 file.
- Windows cannot delete a file a SQLite connection still has open; always close connections.
- Python 3.10 is supported: no `datetime.UTC`, no `StrEnum`.
- PowerShell 5.1 splits arguments at embedded quotes: pass PR bodies with `gh pr create --body-file`.
- `gh` is installed (winget) and logged in as `ctorres345`; a shell opened before the install needs a
  refreshed PATH.

## Working with Claude: agents, skills, hooks

**CLAUDE.md** has the project rules. **Subagents** (`.claude/agents/`): `rom-investigator`,
`profile-author`, `vocab-reviewer` (real since stage 2), `translator` (placeholder until stage 5),
`test-writer`, `repo-guard`. **Skills** (`.claude/skills/`): `add-game-profile`, `review-vocab` (real
since stage 2), `translate-lines` (placeholder until stage 5), `release`. **Hooks**
(`.claude/settings.json`): `tools/repo_guard.py` before every write and commit, and ruff plus the
fast tests after Python edits. A pre-commit config (`.pre-commit-config.yaml`) offers the same
checks locally; `pre-commit install` is optional and not done for anyone.

**Later:** the stage-5 MCP server doubles as a development tool, so Claude can call
`list_untranslated` / `submit_translation` while working on decks.

## Backlog (non-blocking)

- Review the 297 remaining ambiguous PMD words with the `review-vocab` workflow, and decide the 2
  drop rules (あり, わし) that were left unconverted because two words share the text.
- `pip-audit` in CI (could be noisy for tools outside our control) and PyPI Trusted Publishing
  (tokenless publish on a tag push) once the first upload is done.
- Before making the repo public: re-read the legal guardrails and README; a history scan on 2026-10-04
  found no ROMs, archives, decks, large files or secrets. Public repos get branch protection, Dependabot
  alerts and secret scanning; claim the PyPI name with the first upload.
- Optional: a docs site; script-order data in profiles (scene tables).
