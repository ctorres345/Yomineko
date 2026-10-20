# Architecture and Python conventions

How yomineko is organised and why. Written for someone new to Python projects: the
"why" notes explain the Python-specific choices so they are not just rituals.

## The one rule: dependencies point down

Code is arranged in layers. A module may import from layers **below** it, never above.

```
        cli                    command line (a thin layer: parse, call, print)
            |
        app                    the desktop window (pywebview around the web interface)
            |
        web                    the web interface (`yomineko serve`, FastAPI and htmx)
            |
        pipeline               what the CLI and the web app share (no printing, no UI)
            |
extract | export | script_io | analyze | survey    ROM -> Script; file writers; dictionary;
                                                     read-only ROM discovery (counts, no text)
            |
      profile.loader           finds and loads profiles, builds codecs
            |
          core                 pure logic: rom, encodings, discover, roundtrip
            |
  profile.schema | model       data definitions (what a profile / a script IS)
            |
          errors               the one exception base class
```

`core` knows how to read a ROM and find text. It does not know about YAML files, the
command line, or where profiles live. That keeps it easy to test (the tests build a fake
ROM in memory) and easy to reuse (the web interface and the desktop app call the same functions).

This is not a convention to remember: `lint-imports` (import-linter, configured in
`pyproject.toml`) fails CI if a lower layer imports a higher one, or if `core` imports
`typer` or `yaml`.

**Optional dependencies.** `[web]` adds the web interface (FastAPI, Jinja2; checked at run time by
`web/extra.py`), `[app]` adds the desktop window (pywebview) on top of it, and `[analyze]` adds the
tokenizer. A contributor installs `pip install -e ".[dev,analyze,web]"`, as CI does.
The tokenizer needs SudachiPy and
a 77 MB dictionary, so it is an extra. It is imported lazily, inside `SudachiTokenizer`, and a
missing install raises `MissingExtraError` with the exact command to run. Tests use a fake
tokenizer (`tests/support/tokens.py`) so the fast suite does not need it; the few tests of the
real one are marked `sudachi` and skip when it is absent.

**Reviews hold ids, never game text.** A review file (`analyze/review.py`) names JMdict entry
ids, ROM line ids and the reviewer's own English, so people can share corrections for a game
without sharing its script. The schema rejects a gloss that contains Japanese, and
`tools/repo_guard.py` rejects any file with a long run of Japanese. The worklist, which does
contain game text, is written under `yomineko-out/` and is never committed.

**The network rule.** Only `analyze/dictionary/source.py` may import a networking library,
and it runs only when the user types `yomineko dict download`. Extraction and export never
touch the network. `tests/test_network_boundary.py` reads every module's imports and fails if
another one appears.

*Why it matters in Python:* Python lets any module import any other, so without a rule a
project slowly becomes a tangle where everything depends on everything and one change breaks
five things. Writing the rule down as a checked contract stops that early.

**Compressed text.** A line inside a compressed block has no ROM offset, so its `address` and `id` are
a virtual address: `0xC0000000 + (block << 20) + offset in the decompressed block` (the top byte can
never be a real GBA bus address). Review files, sentence ranges, sorting and exports treat it like any
other address. `verify` checks such a line against the decompressed block (the text must re-encode to
the exact bytes it was read from) and says so; the compressed stream itself is not rebuilt.

**Text the profile may not hold.** Some games draw a common word for a single byte and keep the
word once in the ROM. That word is game text, so a profile names only its offset
(`encoding.rom_strings`) and `LoadedProfile.codec(rom)` reads it from the user's ROM when it builds
the codec. Such a codec cannot be built without the ROM; `check_table()` is what runs without one.

**Game Boy banks.** A Game Boy cartridge is a row of 16 KiB banks, and all but the first are seen at
the same addresses (0x4000-0x7FFF), so an address alone does not name a place in the ROM. Everything
inside yomineko therefore stays in file offsets: a profile's `{bank: n}` region is turned into offsets
when it is read, and a line's `address` and `id` are its offset (`text.pointer_base: 0`). The one place
that needs an address is the question "does this bank hold a pointer to this message?", answered by
`core/discover/pointers.py` with `core/rom/gb.py`.

## Layout

```
pyproject.toml          the single config file: metadata, dependencies, tool settings
src/yomineko/           the package (the "src layout")
  model.py              Script / Line / Word / Term: the JSON that extract and analyze write
                        (schema v4: analyze fills Line.word_ids, Term.jmdict_id and
                        Word.jmdict_rank)
  errors.py             YominekoError
  core/
    rom/                load a .gba, .gbc or one-ROM .zip; parse the GBA or Game Boy header and
                        tell the two apart; Game Boy bank addresses
    encodings/          Shift-JIS, .tbl tables, 16-bit glyph tables (table16), byte-stream tables with
                        commands (table8), readable-text conversion
    compression/        GBA BIOS LZ77 decoder (a pure function)
    containers.py       compressed blocks behind a pointer table, entry offsets, virtual addresses
    discover/           pointer scan, noise filter, string discovery, banks, text runs in compressed blocks
                        and in a byte stream inside regions (stream.py: any run, or only the lines of
                        whole messages when the profile describes their frame)
    roundtrip.py        rebuild a ROM from text and compare checksums (compressed text: against
                        the decompressed block)
  profile/
    schema.py           the profile format (pydantic models)
    loader.py           load profiles, look them up by ROM checksum
    template.py         the skeleton that `yomineko profile new` writes
  profiles/             packaged game profiles, data-only YAML
  schemas/              JSON Schemas: script.v4 and profile.v1 are generated (tools/gen_schemas.py);
                        script.v1 and v3 are frozen copies kept for older files (there was no v2 file)
  extract.py            the pipeline
  export/               writers and selection (CSV, JSON, Anki, XLSX, sentence picking, the
                        learner's level in level.py); they know only the data model
  script_io.py          read and write script.json (checks the schema version)
  analyze/              stage 2: words and meanings
    dictionary/         JMdict download, XML parser and the SQLite index
    tokenizer.py        the Tokenizer protocol; SudachiTokenizer (optional extra)
    matcher.py          pick the dictionary entry for a token (port of the prototype's find)
    vocabulary.py       script lines -> frequency-ordered Word list
    review.py           the review file: corrections to dictionary picks (ids only)
    worklist.py         ambiguous words and probable names with example lines, for writing review rules
  reviews/              packaged reviews, one YAML per game (JMdict ids and line ids only)
  pipeline/             steps shared by the CLI and the web app: reviews, sentence/deck choice,
                        analysis, export files, the workspace folders, the remembered word
                        choices (level and minimum count) and the words marked known (JMdict
                        ids only, shared by every game)
  web/                  the web interface (`yomineko serve`): pages, templates, static assets
  app/                  the desktop app (`yomineko app`, `yomineko-app`): the web interface in a window
  survey/               `yomineko survey`: detectors over raw bytes (extent and fill, BIOS streams,
                        plain Shift-JIS, pointer and offset tables, font candidates, token streams,
                        relative word search, save states, comparison with another version, the
                        control codes of a draft profile). Pure functions; reports hold counts and
                        offsets only, never ROM text. Imports `core`, `profile.loader` and `errors`
  cli/                  the command line (Typer)
tests/                  pytest tests; support/synthrom.py builds fake ROMs
tools/                  developer scripts, not in the wheel (the sdist has them): repo_guard, gen_schemas, sentence_excludes,
                        game_check (a scorecard for one game), glyph_render (read a character table
                        from an emulator: libretro host, sheets, table writer)
docs/                   plan and notes
```

*Why `src/`:* with the package in `src/yomineko/` (not at the repo root), `import yomineko`
only works once the package is installed. Tests therefore exercise the installed code the
way users get it, and you cannot accidentally pass tests because Python found a stray local
folder. `pip install -e ".[dev,analyze,web]"` installs it "editable": your edits take effect at once.

*Why `pyproject.toml`:* it is the standard single place for package metadata and tool
configuration (ruff, mypy, pytest, coverage, import-linter all read it). The older
`setup.py`/`setup.cfg`/`requirements.txt` split is not needed.

## Conventions

**Data at the edges is validated; logic in the middle is plain.** Profiles and the script
JSON are pydantic models: bad input is rejected with a clear message the moment it enters.
Inside `core`, small functions work on plain values (`bytes`, `str`, `int`) and dataclasses.

**Pure functions where possible.** `find_strings(data, codec, profile)` returns a result; it
does not read files or print. Anything that touches the disk (`load_rom`, `load_profile`) is
at the edge and small.

**Protocols over base classes.** `Codec` (in `core/encodings/base.py`) is a `Protocol`: any
object with `terminator`, `parse` and `encode` is a codec. No inheritance needed, and a new
encoding is one new file.

**Expected failures are `YominekoError`.** A bad ROM, a missing profile, a checksum mismatch:
raise a subclass of `YominekoError` with a message the user can act on. The CLI shows these
without a traceback. Any other exception is a bug and keeps its traceback.

**Type hints everywhere, checked.** `mypy --strict` runs in CI over `src/` and `tools/`. The
`py.typed` marker tells other projects the package ships its types.

**Config is data, not code.** Everything specific to one game (offsets, encoding, control
codes) lives in a profile YAML. Adding a game should not need a code change; if it does, the
profile format is missing something.

**No game content in the repo.** ROMs, extracted text and decks never get committed.
`tools/repo_guard.py` enforces it in the editor hook, pre-commit and CI.

## Tests

- Tests build fake ROMs in memory (`tests/support/synthrom.py`) with a *manifest* of what
  must be found, so a test asserts "extraction equals the manifest" rather than hard-coding
  numbers.
- A change to `core/` needs a test on a synthetic ROM.
- Tests that need a real dump are marked `realrom`, skip unless an environment variable
  points at the ROM, and compare counts and checksums only.
- Coverage is measured in CI (`pytest --cov`) and must stay at or above 95%.
- Names: `test_<what_it_does>`. One behaviour per test. Parametrize instead of copy-paste.

## Tooling: what runs where

| Tool | What it checks | Runs |
|---|---|---|
| ruff check / ruff format | style, import order, likely bugs, modern syntax | editor hook, pre-commit, CI |
| mypy (strict) | type hints agree with how values are used | pre-push, CI |
| import-linter | the layer rules above | pre-push, CI |
| pytest + coverage | behaviour, 95% floor | editor hook (fast), pre-push, CI |
| repo_guard | no ROMs, archives or game text | editor hook, pre-commit, CI |
| Dependabot | weekly PRs for outdated dependencies and actions | GitHub |

Run everything: see CONTRIBUTING.md.

## Where does new code go?

| I want to... | Put it in |
|---|---|
| support another text encoding | `core/encodings/<name>.py` (implement `Codec`), pick it in the profile |
| support another game | a YAML in `src/yomineko/profiles/`, no code if it fits the profile format ([guide](ADDING_A_GAME.md)) |
| support another compression scheme | `core/compression/<scheme>.py` (a pure decoder), then add it to `compressed.scheme` in `profile/schema.py` and call it from `core/containers.py` |
| support text stored as glyph ids | built (`table16` and `compressed`): see the profile fields in [ADDING_A_GAME.md](ADDING_A_GAME.md) |
| support another console | `core/rom/<platform>.py` plus a `platform` value in the profile schema (GBA and GBC exist) |
| add an export format | `export/<format>.py` reading `Script`, offered from `pipeline/exporting.py` |
| add a CLI command | `cli/`; keep the logic in `pipeline/` or lower |
| find out how an unknown game stores its text | `yomineko survey`; a new check is a pure function in `survey/`, a section in `survey/report.py` and a case in `tests/support/synthsurvey.py` |
| add a field to the script JSON | `model.py`, then `python tools/gen_schemas.py`, and bump `schema_version` if it breaks readers |

When a new top-level module appears (as `web` and `app` did, and `translate` will), add it to
the layers contract in `pyproject.toml` in the same PR.
