<p align="center">
  <img src="https://raw.githubusercontent.com/ctorres345/yomineko/main/docs/assets/logo.png" width="200" alt="yomineko logo: a black cat with big yellow eyes wearing a red polka-dot party hat">
</p>

<h1 align="center">yomineko 読み猫</h1>

<p align="center">
  <strong>Turn the Japanese script of a game you own into flashcards.</strong><br>
  A word list, example sentences and Anki decks, made from the game's own text.
</p>

<p align="center">
  <a href="https://pypi.org/project/yomineko/"><img src="https://img.shields.io/pypi/v/yomineko?color=black" alt="PyPI version"></a>
  <a href="https://pypi.org/project/yomineko/"><img src="https://img.shields.io/pypi/pyversions/yomineko?color=black" alt="Python 3.10 and newer"></a>
  <a href="https://github.com/ctorres345/yomineko/actions/workflows/ci.yml"><img src="https://github.com/ctorres345/yomineko/actions/workflows/ci.yml/badge.svg" alt="CI status"></a>
  <a href="https://github.com/ctorres345/yomineko/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-black" alt="Apache-2.0 licence"></a>
  <a href="https://ko-fi.com/pandaveloper"><img src="https://img.shields.io/badge/Ko--fi-support%20the%20project-FF5E5B?logo=ko-fi&logoColor=white" alt="Support the project on Ko-fi"></a>
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#how-to-use-it">How to use it</a> ·
  <a href="#supported-games">Supported games</a> ·
  <a href="#add-your-game">Add your game</a> ·
  <a href="#troubleshooting">Troubleshooting</a> ·
  <a href="#command-line">Command line</a> ·
  <a href="#support-the-project">Support</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/ctorres345/yomineko/main/docs/assets/screenshots/words-dark.png" width="760" alt="The word list in the yomineko app: each word with its reading, meaning, how often the game uses it, and an I know this button">
</p>

## What it does

yomineko reads the text stored inside a Game Boy Advance or Game Boy Color game, finds every
word in it, and turns them into study material:

- 📖 **A word list**, most frequent first, with readings and dictionary meanings.
- 💬 **Example sentences** taken from the game, picked so that each one teaches you new words.
- 🃏 **Anki decks**, spreadsheets, CSV and JSON, ready to import.
- 🎯 **Only what you need**: tell it your level and the words you already know, and it leaves them out.
- 🔒 **Everything stays on your computer.** Nothing is uploaded, and there are no accounts.

Most learners look words up *while* they play. yomineko helps you *before* you play: study the words
that cover most of the game, with real lines from it as examples, and then enjoy the game with far
fewer trips to the dictionary.

> **For games you own.** yomineko does not include or share ROMs, game scripts or ready-made decks.
> You run it on your own copy of the game, and nothing leaves your machine. Files you export contain
> the game's text and are for your personal study only. See [DISCLAIMER.md](https://github.com/ctorres345/yomineko/blob/main/DISCLAIMER.md)
> for responsible use and what the project will not help with.

## Why I made this

While practising my Japanese, I wanted to bring video games into the media I study with. My
vocabulary and grammar are still growing, so I was looking for a tool to help me look up words and
sentences while playing. There are tools that read the text on the screen, like the ones people use
for visual novels, but I play on handheld consoles most of the time, so running one next to the game
isn't really possible.

Then I came across a few game decompilation projects, and they gave me an idea: use the same
approach to find the game's actual script and turn it into study material. It may be a niche use
case, but if it helps someone else study the way it has helped me, it's worth sharing.

— Cesar

## Install

**Status:** version 0.5.0, early but usable. See the [changelog](https://github.com/ctorres345/yomineko/blob/main/CHANGELOG.md) for what each version added.

### Desktop app (recommended, no Python needed)

1. Download the file for your system from the [latest release](https://github.com/ctorres345/yomineko/releases/latest):
   Windows (`.zip`), macOS on Apple silicon or Linux (`.tar.gz`).
2. Unpack it and open **`yomineko-app`**.
3. The first time, your system warns you because the app is not code-signed (signing costs money every
   year). Here is how to get past the warning once:

| System | What to do |
|---|---|
| **Windows** | SmartScreen says "Windows protected your PC": choose *More info*, then *Run anyway*. |
| **macOS** | In Terminal, in the folder you unpacked it to, run `xattr -dr com.apple.quarantine yomineko`, then `./yomineko/yomineko-app`. (Recent macOS no longer lets you get past the warning with right-click, *Open*.) The build is for Apple silicon (M1 and later). |
| **Linux** | Run `chmod +x yomineko yomineko-app` if needed. The window needs GTK or Qt web libraries; without them the app opens in your browser instead, and works the same. |

The download also holds the command-line program, `yomineko`. To check a download, compare it with its
`.sha256` file (`shasum -a 256 -c yomineko-<system>.<ext>.sha256`, or `Get-FileHash` on Windows).

### With Python

You need Python 3.10 or newer. A virtual environment is a good idea (`python -m venv .venv`, then activate it).

```bash
pip install "yomineko[app,analyze]"     # the desktop app and the word list: run "yomineko app"
pip install "yomineko[web,analyze]"     # the same pages in your browser: run "yomineko serve"
pip install "yomineko[analyze]"         # command line only, with the word list (adds a ~80 MB tokenizer)
pip install yomineko                    # command line only: extract, verify and export the text
```

To work on yomineko itself, install from a checkout instead: see [CONTRIBUTING.md](https://github.com/ctorres345/yomineko/blob/main/CONTRIBUTING.md).

## How to use it

The whole job takes a few minutes. You need:

- **Your game file**: an unmodified dump of a game you own, as a `.gba`, `.gbc` or `.gb` file, or a
  `.zip` holding exactly one. yomineko recognises the game by its checksum, so patched or translated
  versions are not accepted. See [Supported games](#supported-games) for the list.
- **An internet connection, once**, to download the dictionary (about 10 MB). Nothing else is ever
  downloaded, and your game file never leaves your computer.
- **[Anki](https://apps.ankiweb.net)**, if you want flashcards. A spreadsheet program is enough for
  the other exports.

Open the **desktop app** (`yomineko-app`, or `yomineko app` if you installed with Python). You can
also run `yomineko serve` and use your browser at <http://localhost:8765>: the pages are the same.

<p align="center">
  <img src="https://raw.githubusercontent.com/ctorres345/yomineko/main/docs/assets/screenshots/start.png" width="640" alt="The start page: a box to add a game file and the list of your games">
</p>

A bar at the top shows the five steps, and each page has one **Next** button that takes you to the
following one.

1. **Get started.** Read the short notice and press **Got it**. Then press **Download the dictionary**
   (about a minute, and only once). The word meanings come from it.
2. **Add a game.** Press **Choose file**, pick your game file and press **Read the game's text**.
   After a few seconds you see how many lines were found. **Rebuild check passed** means the text was
   read completely and correctly.
3. **Find the words.** Press **Find the words**. A few seconds later you see how many different words
   the game uses. Under **Look inside** you can browse the words (most frequent first), the game's
   lines, and the sentences yomineko would pick for you.
4. **Choose your words.** Pick your level: *Just starting* (every word), *The basics*, *Intermediate*
   or *Advanced* (these skip the 1,000, 5,000 or 10,000 most common words). Ten sample words help you
   choose, and the number of cards updates as you go. You can also set how often a word must appear in
   the game to get a card (4 times by default). In the word list, **I know this** leaves a word out
   of every game's cards, and **Undo** brings it back.
5. **Check the meanings (optional).** Older games are written mostly in kana, so a word can be matched
   to the wrong dictionary entry with the same sound (for example こと as 琴, a koto, instead of 事, a
   thing). Each supported game already comes with fixes for the most common mistakes, so you can press
   **Skip this step**. To check more, press **Prepare the words to check**. For each word you see the
   lines it appears in and pick the right meaning, mark the pick as right, drop it, or type your own
   meaning. Then press **Apply them**.
6. **Export.** Choose an **Anki deck** (`.apkg`), a **spreadsheet** (`.xlsx`), or a **CSV or JSON
   file**, and press **Download**. *More options* lets you change how many sentences to pick (1,000 by
   default), their order, and the name shown where the game uses *your* name.
7. **Import into Anki.** In Anki on your computer, choose **File › Import** and select the `.apkg`.
   You get three decks named after the game: **1 Words** (most frequent first), **2 Sentences**
   (easiest first, each with the meanings of its harder words) and **3 Terms** (game names that are
   real words). To study on your phone, sync and open AnkiMobile or AnkiDroid.

When you are done, close the window (or press **Quit yomineko** if the app opened in your browser).

<table>
  <tr>
    <td width="50%"><img src="https://raw.githubusercontent.com/ctorres345/yomineko/main/docs/assets/screenshots/sentences.png" alt="The sentences page: lines from the game that teach the most words, with how many new words each one has"></td>
    <td width="50%"><img src="https://raw.githubusercontent.com/ctorres345/yomineko/main/docs/assets/screenshots/export.png" alt="The export page: choose an Anki deck, a spreadsheet, a CSV file or a JSON file"></td>
  </tr>
  <tr>
    <td align="center"><sub>The sentences that teach the most words</sub></td>
    <td align="center"><sub>Export to Anki, a spreadsheet, CSV or JSON</sub></td>
  </tr>
</table>

<sub>The screenshots use a small demo ROM and sentences written for these pictures, not text from a real game.</sub>

### Good to know

- 📁 **Where things are saved.** The start page shows the folder. Each game has its own folder with the
  extracted text and your corrections. They contain the game's text, so keep them private.
- 🔁 **Doing it again is safe.** Export a new deck after changing your corrections and import it over
  the old one: Anki updates the cards in place and keeps your review history.
- 🌱 **What to study first.** Start with *1 Words* and add a few new cards a day (10 to 20 is plenty).
  The sentence deck starts with lines made of the most common words, so it gets harder as you go.
- 🔊 **Sound on the cards** comes from Anki's built-in Japanese text-to-speech. If you hear nothing,
  install a Japanese voice in your system settings.
- 📚 **Meanings** come from the JMdict dictionary (EDRDG, CC BY-SA 4.0) and are credited on every card.
  They are dictionary glosses, not a translation of each line.
- 📱 **Phones.** The app runs on a computer only. To study on a phone, use Anki there (step 7).

## Supported games

yomineko reads each game through a **profile**: a small file that says where the game keeps its text,
how its characters are encoded and what its control codes mean. Every game stores its text
differently, so **support is per game**, and only Japanese releases are in scope.

| Game | Platform | Verdict | Word meanings | Sentence cards | Name cards |
|---|---|---|---|---|---|
| Pokemon Mystery Dungeon: Red Rescue Team (Japan) | GBA | ✅ ready | reviewed (311 corrections) | whole lines | yes |
| Pocket Monsters Crystal (Japan) | GBC | ✅ ready | first-pass review (64 corrections) | one text-box row each | yes |
| Gyakuten Saiban (Japan) (Rev 1) | GBA | ⚠️ works, with limits | first-pass review (35 corrections) | one text-box row each | no |
| Mario & Luigi RPG (Japan) | GBA | ⚠️ works, with limits | first-pass review (8 corrections) | one text-box row each | no |

`yomineko profile list` shows the same list. A file that is not an unmodified dump of one of these
games is refused with a message that says so.

<details>
<summary><strong>What the verdicts and notes mean</strong></summary>

- **ready** means the text rebuilds the ROM exactly, no raw code reaches a card, and almost every card
  ends like a sentence. **works, with limits** means usable, with the limits below.
- **Reviewed** means the most frequent wrong dictionary picks were corrected by hand. Even then, check
  the words you study: kana-heavy text makes any dictionary program guess, and **Check the meanings**
  (or `yomineko review`) lets you fix more.
- **One text-box row each**: these games store a sentence across several short rows (14 to 16
  characters), so the sentence deck prefers rows that hold a whole sentence.
- **Pokemon Mystery Dungeon** is the reference game: its sentences are whole lines, filtered.
- **Gyakuten Saiban**: the main characters' names are left out of the word list, but a few less
  frequent names may still show up as words.
- **Mario & Luigi RPG**: two rare kanji are not in the character table yet.
- **Pocket Monsters Crystal** is written in kana only. Every byte value is a character, so text is
  read from whole messages, and a message that nothing points to is kept only when it has at least six
  kana. About 40 short real messages (out of some 4,500) are left out that way; in return, almost no
  stray data is read as text.

The verdicts come from the project's own check of each game, run the way a learner uses it
(`tools/game_check.py`).
</details>

## Add your game

**yomineko grows one game at a time, and every new game is a team effort.** Each profile that someone
contributes is shipped to everyone, so the next learner who owns that game can start studying right
away. If you have a Japanese GBA or GBC game you would like to study, adding it is the best way to
make yomineko better for all of us.

Making a profile takes some detective work: finding the text, working out how it is encoded, and
proving that it all rebuilds the original file byte for byte. A plain Shift-JIS game can take a few
hours. Many games use their own character table or compress their text; yomineko already handles
text in BIOS LZ77 blocks stored as glyph ids (Gyakuten Saiban), one-byte codes with commands
(Mario & Luigi RPG) and framed messages spread across a Game Boy Color cartridge (Pocket Monsters
Crystal). You don't need to do it all alone:

- 🧭 **Step-by-step guide:** [docs/ADDING_A_GAME.md](https://github.com/ctorres345/yomineko/blob/main/docs/ADDING_A_GAME.md) walks you
  through it: investigate, draft, prove it with a round trip, check that it reads well, and submit.
- 🤖 **With Claude Code:** the repository includes a skill and agents for this. Open the project, say
  *"add support for my game using the add-game-profile skill"* and give it the path of your game file.
- 🙋 **Stuck, or the text is stored some other way?** Open a *Game support request* (an issue form) with
  what you found, counts and offsets only. Even an unfinished investigation tells the project which
  features to build next, and someone else may pick it up from there.

> **Your game file never leaves your computer**, and **nothing taken from a game belongs in an issue, a
> pull request or a chat**: no ROMs and no extracted text. Profiles and notes hold offsets, counts,
> encodings and control codes only. Issues that ask for ROMs, keys or circumvention are closed (see
> [DISCLAIMER.md](https://github.com/ctorres345/yomineko/blob/main/DISCLAIMER.md)).

Found a security problem? Please report it privately, as [SECURITY.md](https://github.com/ctorres345/yomineko/blob/main/SECURITY.md) describes, not in an issue.

## Troubleshooting

<details>
<summary><strong>"no profile for this ROM"</strong></summary>

yomineko does not know this game, or the file is not an unmodified dump (patched, trimmed or
translated versions have a different checksum). `yomineko profile list` shows the supported games,
and [Add your game](#add-your-game) explains how to add one.
</details>

<details>
<summary><strong>The rebuild check says "Mismatch"</strong></summary>

The text read from your file does not rebuild the original exactly, so some of it may be missing or
wrong. Check that the dump is complete and not damaged. If it keeps happening with a good dump,
please open an issue and say which game it is.
</details>

<details>
<summary><strong>"Download the dictionary first"</strong></summary>

The word list needs the dictionary. Press **Download the dictionary** on the start page. It needs an
internet connection once. If the download fails, try again later, or check that nothing blocks
`edrdg.org`.
</details>

<details>
<summary><strong>The word list fails, saying an extra is missing</strong></summary>

You installed with Python and without the tokenizer. Run `pip install "yomineko[analyze]"` (the
desktop app download already includes it).
</details>

<details>
<summary><strong>Windows or macOS warns that the app is from an unknown developer</strong></summary>

The app is not code-signed, so the first start shows a warning. See [Install](#desktop-app-recommended-no-python-needed)
for the steps that get past it, and compare the download with its `.sha256` file if you want to be
sure it is the file the project built.
</details>

<details>
<summary><strong>The app opens in my browser instead of a window</strong></summary>

That happens when the system has no web view available (mostly on Linux). It works the same. Use the
**Quit yomineko** button at the top of the page when you are done.
</details>

<details>
<summary><strong>Port 8765 is already in use (<code>yomineko serve</code>)</strong></summary>

Run `yomineko serve --port 9000` (or any free port) and open that address instead. The desktop app
picks a free port by itself.
</details>

<details>
<summary><strong>Some meanings look wrong</strong></summary>

The game is written in kana, so the dictionary can pick the wrong word. Use **Check the meanings**
(step 5). Your corrections are only ever ids and your own English, so you can share them without
sharing any game text.
</details>

## Command line

Everything the app does is also available in a terminal. Files are written under `yomineko-out/`.

```bash
yomineko info   game.gba                 # header, checksum, matching profile
yomineko extract game.gba                # writes yomineko-out/<game>/script.json
yomineko verify game.gba                 # rebuild from the extracted text, compare checksum
yomineko dict download                   # once: fetch JMdict (CC BY-SA, EDRDG) for word lookups
yomineko analyze yomineko-out/<game>/script.json            # find the words (needs the analyze extra)
yomineko export yomineko-out/<game>/script.json --format anki     # words, sentences and terms deck
yomineko serve                           # the web interface at http://localhost:8765
yomineko app                             # the desktop app
```

<details>
<summary><strong>More commands and export options</strong></summary>

```bash
yomineko survey game.gba                 # developer: how does this game store its text? (counts only)
yomineko review worklist yomineko-out/<game>/script.json    # ambiguous words and probable names to double-check
yomineko analyze yomineko-out/<game>/script.json --review my-review.yaml
yomineko export yomineko-out/<game>/script.json --format anki --level basics   # no cards for the 1,000 commonest words
yomineko export yomineko-out/<game>/script.json --format xlsx     # the same as a spreadsheet
yomineko export yomineko-out/<game>/script.json --content words --format csv --min-freq 3
yomineko export yomineko-out/<game>/script.json --content sentences --format csv
yomineko dict status                     # where the dictionary is stored and how recent it is
yomineko known list                      # the words you marked "I know this"
```

- The deck needs `analyze` first (run it again if the script was analysed with an older yomineko).
- Words need `--min-freq` occurrences (default 4). About 1,000 sentences are picked (`--sentences`),
  easiest first or in ROM order (`--order`), and `--decks words,sentences,terms` chooses the parts.
- `--level` skips the words you already know: `basics`, `intermediate` and `advanced` leave out the
  1,000, 5,000 and 10,000 most common words in the dictionary (`starting`, the default, keeps them all).
  Those counts come from JMdict's newspaper word frequencies, not JLPT lists, so a few everyday words
  rank lower than you might expect. Skipped words still appear in the sentences.
- Words you marked "I know this" in the app (or with `yomineko known add`) are left out too, in every
  game; `--no-known` makes cards for them anyway.
- Where the game uses the player's name, cards show a stand-in (`--player-name`). Game names become
  cards only when they match exactly one dictionary entry.
- `game.gba` may also be a `.gbc` or `.gb` file, or a `.zip` holding one ROM. `yomineko serve` and
  `yomineko app` only listen on your own computer (127.0.0.1).
</details>

## Support the project

yomineko is free and open source, and it will stay that way. If it helps your Japanese and you'd like
to say thanks, you can buy me a coffee on Ko-fi. It's completely optional and very much appreciated.

<p>
  <a href="https://ko-fi.com/pandaveloper"><img src="https://img.shields.io/badge/Ko--fi-buy%20me%20a%20coffee-FF5E5B?logo=ko-fi&logoColor=white&style=for-the-badge" alt="Buy me a coffee on Ko-fi"></a>
</p>

Contributing a game profile, reporting a problem, or telling a friend who is learning Japanese helps
just as much.

## Credits

- **Logo:** illustration by @loritoart.
- **Word meanings:** [JMdict](https://www.edrdg.org/jmdict/j_jmdict.html), © the Electronic Dictionary
  Research and Development Group, CC BY-SA 4.0. Downloaded when you ask for it, never bundled.
- **Tokenizer:** [Sudachi](https://github.com/WorksApplications/SudachiPy) (Works Applications,
  Apache-2.0).
- **Web interface:** [htmx](https://htmx.org) and [Pico CSS](https://picocss.com), see [NOTICE](https://github.com/ctorres345/yomineko/blob/main/NOTICE).

## License

Apache-2.0. See [LICENSE](https://github.com/ctorres345/yomineko/blob/main/LICENSE) and [NOTICE](https://github.com/ctorres345/yomineko/blob/main/NOTICE). yomineko is not
affiliated with any game publisher or console maker. The logo is by @loritoart and is not covered by
this licence.
