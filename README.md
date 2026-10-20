<p align="center">
  <img src="https://raw.githubusercontent.com/ctorres345/yomineko/main/docs/assets/logo.png" width="220" alt="yomineko logo: a black cat with big yellow eyes wearing a red polka-dot party hat">
  <br>
  <sub>Logo by @loritoart</sub>
</p>

# yomineko 読み猫

Extract the Japanese script from games you own and turn it into study material:
a frequency-ordered word list, sentences that teach the most words, each with the meanings of
its words, and exports to Anki, spreadsheets and JSON.

Learners usually mine words *while* playing. yomineko works *before* you play: study
the words that cover most of the game, with real lines from it as examples.

> **For games you own.** yomineko does not include or distribute ROMs, game scripts or
> prebuilt decks. You run it on your own dump, and nothing leaves your machine. See
> [DISCLAIMER.md](https://github.com/ctorres345/yomineko/blob/main/DISCLAIMER.md) for responsible use and what the project will not help with.
> Files you export contain the game's text and are for your personal study only.

**Status:** early but usable, version 0.5.0. It extracts the
script from a Game Boy Advance or Game Boy Color ROM and checks that it rebuilds byte for byte,
finds the words with
dictionary meanings and frequency counts, lets you correct the wrong picks that kana-heavy
text causes, picks the sentences that teach the most words, and exports Anki decks,
spreadsheets, CSV and JSON. You can use it in a desktop app, in your browser, or from a
terminal. Four games are supported so far (see [Games and profiles](#games-and-profiles) for
what each gives you).
See the [changelog](https://github.com/ctorres345/yomineko/blob/main/CHANGELOG.md) for what each version added.

**Contents:** [Install](#install) · [How to use it](#how-to-use-it) ·
[Troubleshooting](#troubleshooting) · [Command line](#command-line) ·
[Games and profiles](#games-and-profiles) · [Credits](#credits) · [License](#license)

## Install

### Desktop app (no Python needed)

A download for Windows, macOS and Linux holds the app (`yomineko-app`) and the command-line
program (`yomineko`). Unzip it, open `yomineko-app`, pick your game file and follow the steps: add the game,
find the words, choose them, check them, export. Builds come from the **Build app** workflow (Actions tab) and
are attached to releases once there is one.

The downloads are not code-signed, so your system warns once:
- **Windows:** SmartScreen says "Windows protected your PC": choose *More info*, then *Run anyway*.
- **macOS:** the build is for Apple silicon (M1 and later). Recent macOS versions no longer let
  *Open* from the right-click menu past the warning, so clear the download's quarantine flag once in
  Terminal, in the folder you unpacked it to: `xattr -dr com.apple.quarantine yomineko`, then
  `./yomineko/yomineko-app`.
- **Linux:** unpack the archive, then `chmod +x yomineko yomineko-app` if needed. The window needs
  GTK or Qt web libraries; without them the app opens in your browser instead.

Check a download against its `.sha256` file (`shasum -a 256 -c yomineko-<system>.<ext>.sha256`, or
`Get-FileHash` on Windows).

### With Python

Python 3.10 or newer. Use a virtual environment if you can (`python -m venv .venv`, then activate it).

```bash
pip install yomineko                    # extract, verify and export
pip install "yomineko[analyze]"         # also the word list (adds the tokenizer, about 80 MB)
pip install "yomineko[web]"             # the web interface: yomineko serve
pip install "yomineko[app,analyze]"     # the desktop app: yomineko app
```

To work on yomineko itself, install from a checkout instead: see [CONTRIBUTING.md](https://github.com/ctorres345/yomineko/blob/main/CONTRIBUTING.md).

## How to use it

The whole job takes a few minutes. You need:

- **The game file**, a dump of a game you own: a `.gba`, `.gbc` or `.gb` file, or a `.zip` holding
  exactly one. It must be an unmodified dump, because yomineko recognises the game by its checksum.
  Today that means *Pokemon Mystery Dungeon: Red Rescue Team (Japan)*, *Gyakuten Saiban (Japan)*,
  *Mario & Luigi RPG (Japan)* (Game Boy Advance) or *Pocket Monsters Crystal (Japan)* (Game Boy
  Color).
- **An internet connection once**, to download the dictionary (about 10 MB). Nothing else is ever
  downloaded, and your game file never leaves your computer.
- **Anki**, if you want flashcards ([apps.ankiweb.net](https://apps.ankiweb.net)). A spreadsheet
  program is enough for the other exports.

### Step by step

Open the **desktop app** (`yomineko-app`). If you installed with Python, run `yomineko app` for the
same window, or `yomineko serve` to use your browser at <http://localhost:8765>. The pages are
identical.

A bar at the top of each game's pages shows the five steps (1 Add a game, 2 Find the words, 3 Choose
your words, 4 Check meanings, 5 Export) and each page has one **Next** button to the following step.

1. **Read the short notice** the first time and press **Got it**.

2. **Download the dictionary.** On the start page, press **Download the dictionary**. It takes about
   a minute. The word meanings come from it. You only do this once.
3. **Add a game.** Under *Add a game*, press **Choose file**, select your game file (`.gba`,
   `.gbc`, `.gb` or `.zip`), and press **Read the game's text**. After a few seconds you see how many
   lines were found. Look for
   **Rebuild check: OK**: it means the text was read completely and correctly.
4. **Find the words.** On the game page, press **Find the words**. It takes a few seconds and then
   shows how many different words the game uses. Under **Look inside**, **Browse the words** lists
   them (most frequent first), **Browse the lines** shows the game's text, and **See the sentences it
   would pick** previews your example sentences.
5. **Choose your words.** Press **Next: Choose your words** and pick a level: *Just starting* (every
   word), *The basics*, *Intermediate* or *Advanced* (these skip the 1,000, 5,000 or 10,000 most
   common words in the dictionary). Ten sample skipped words help you choose, and the number of word
   cards updates as you go. The level is remembered for your next game. Below, set how often a word
   must appear in the game to get a card (default 4) and press **Save**. In the word list, **I know
   this** leaves a word out of every game's cards (and **Undo** brings it back).
6. **Check meanings (optional).** The game is written almost entirely in hiragana, so a
   word can be matched to the wrong dictionary entry with the same sound (for example こと as 琴, a
   koto, instead of 事, a thing). Press **Next: Check the meanings** and then **Prepare the words to
   check**. For each word you see the lines it appears in and what it could mean instead. Choose:
   - one of the **alternatives**, if the pick was wrong (tick *right for most lines, not all* when
     the alternative is right most of the time but not in every line: it then stays off the sentence
     cards);
   - **The pick is right**, so it leaves the list;
   - **Not a real word here**, to drop it;
   - or type your own **meaning** in English and press **Use it**.

   Your answers are saved on your computer. When you are done, press **Apply them (find the words
   again)**. The game already comes with a review of the most common mistakes, so you can press
   **Skip this step**. Anything you undo can be removed under **Your corrections**.
7. **Export.** Press **Next: Export** and choose what you want:
   - **An Anki deck** (`.apkg`): words, sentences and game names, ready to import;
   - **A spreadsheet** (`.xlsx`), with the same cards as rows;
   - **A CSV or JSON file**, for your own tools (the word list, the picked sentences or every line).

   Only the options for the format you chose are shown. *More options* lets you change how often a
   word must appear (it starts from your choice in step 5), how many sentences to pick (default
   1,000), easiest first or in game order, and the name shown where the game uses *your* name. Press
   **Download**.
8. **Import into Anki.** In Anki on your computer, choose **File, Import** and select the `.apkg`.
   You get three decks named after the game: **1 Words** (most frequent first), **2 Sentences**
   (easiest first, each with the meanings of its less common words) and **3 Terms** (game names
   that are real words). To study on a phone, import on your computer, sync, then open Anki
   (AnkiMobile or AnkiDroid) on the phone.

When you are finished, close the window (or press **Quit yomineko** if the app opened in your
browser).

### Good to know

- **Where things are saved.** The start page shows the folder. Each game has its own folder holding
  the extracted text and your corrections. They contain the game's text: keep them private.
- **Doing it again is safe.** Export a new deck after changing your corrections and import it over
  the old one: Anki updates the cards in place and keeps your review history.
- **What to study first.** Start with *1 Words*. Add a few new cards a day (10 to 20 is plenty).
  The sentence deck starts with lines made of the most common words, so it gets harder as you go.
- **The sound on cards** is Anki's built-in Japanese text-to-speech. If you hear nothing, install a
  Japanese voice in your system settings.
- **Meanings** come from the JMdict dictionary (EDRDG, CC BY-SA 4.0), credited on every card.
  They are dictionary glosses, not a translation of each line.
- **Phones.** The app runs on a computer only; to study on a phone, use Anki there (step 8).

## Troubleshooting

<details>
<summary><strong>"no profile for this ROM"</strong></summary>

yomineko does not know this game, or the file is not an unmodified dump (patched, trimmed or
translated versions have a different checksum). `yomineko profile list` shows the supported games.
Adding a game is described in [CONTRIBUTING.md](https://github.com/ctorres345/yomineko/blob/main/CONTRIBUTING.md).
</details>

<details>
<summary><strong>Rebuild check says "Mismatch"</strong></summary>

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

You installed with Python and without the tokenizer. Run `pip install "yomineko[analyze]"` (the downloaded
desktop app already includes it).
</details>

<details>
<summary><strong>Windows or macOS warns that the app is from an unknown developer</strong></summary>

The app is not code-signed (that costs money each year), so the first start shows a warning. See
[Install](#desktop-app-no-python-needed) for the steps that get past it, and compare the
download with its `.sha256` file if you want to be sure it is the file the project built.
</details>

<details>
<summary><strong>The app opens in my browser instead of a window</strong></summary>

That happens when the system has no web view available (mostly on Linux). It works the same.
Use the **Quit yomineko** button at the bottom of the page when you are done.
</details>

<details>
<summary><strong>Port 8765 is already in use (yomineko serve)</strong></summary>

Run `yomineko serve --port 9000` (or any free port) and open that address instead. The desktop app
picks a free port by itself.
</details>

<details>
<summary><strong>Some meanings look wrong</strong></summary>

The game is written in kana, so the dictionary can pick the wrong word. Use **Check meanings**
(step 6). Your corrections are only ever ids and your own English, so they are safe to share
without sharing any game text.
</details>

## Command line

Everything the app does is also available in a terminal. Files are written under `yomineko-out/`.

```bash
yomineko info   game.gba                 # header, checksum, matching profile
yomineko survey game.gba                 # developer: how does this game store its text? (counts only)
yomineko extract game.gba                # writes yomineko-out/<game>/script.json
yomineko verify game.gba                 # rebuild from the extracted text, compare checksum
yomineko dict download                   # once: fetch JMdict (CC BY-SA, EDRDG) for word lookups
yomineko analyze yomineko-out/<game>/script.json            # find the words (needs the extra)
yomineko review worklist yomineko-out/<game>/script.json    # ambiguous words and probable names to double-check
yomineko analyze yomineko-out/<game>/script.json --review my-review.yaml
yomineko export yomineko-out/<game>/script.json --format anki     # words, sentences and terms deck
yomineko export yomineko-out/<game>/script.json --format anki --level basics   # no cards for the 1,000 commonest words
yomineko export yomineko-out/<game>/script.json --format xlsx     # the same as a spreadsheet
yomineko export yomineko-out/<game>/script.json --content words --format csv --min-freq 3
yomineko export yomineko-out/<game>/script.json --content sentences --format csv
yomineko dict status                     # where the dictionary is stored and how recent it is
yomineko serve                           # the web interface at http://localhost:8765
yomineko app                             # the desktop app
```

The deck needs `analyze` first (run it again if the script was analysed with an older yomineko).
Words need `--min-freq` occurrences (default 4), about 1,000 sentences are picked (`--sentences`),
easiest first or in ROM order (`--order`), and `--decks words,sentences,terms` chooses the parts.
`--level` skips the words you already know: `basics`, `intermediate` and `advanced` leave out the
1,000, 5,000 and 10,000 most common words in the dictionary (`starting`, the default, keeps them all).
Those counts come from JMdict's newspaper word frequencies, not JLPT lists, so a few everyday words rank
lower than you might expect. Skipped words still appear in the sentences.
Words you marked "I know this" in the app (or with `yomineko known add`) are left out too, in every
game; `yomineko known list` shows them and `--no-known` makes cards for them anyway.
Where the game uses the player's name, cards show a stand-in (`--player-name`). Game names become
cards only when they match exactly one dictionary entry.

`game.gba` may also be a `.gbc` or `.gb` file, or a `.zip` holding one ROM. A game is supported when a
[profile](https://github.com/ctorres345/yomineko/blob/main/CONTRIBUTING.md) matches the ROM's SHA-1 (`yomineko profile list`). `yomineko serve` and
`yomineko app` only listen on your own computer (127.0.0.1).

## Games and profiles

yomineko reads each game through a **profile**: a small file that says where the game keeps its text,
how its characters are encoded and what its control codes mean. A profile is what makes the text come
out clean, and a packaged *review* of the word picks makes the meanings right. Because every game
stores its text differently, **support is per game**, and only Japanese games are in scope. Today four
games are supported, on Game Boy Advance and Game Boy Color (`yomineko profile list` shows the list). A
file that is not an unmodified dump of a supported game is refused, with a message that says so, and so
is a game that is not a Japanese release (the header's game code must end in `J`; an older Game Boy
cartridge has no code, and its header must name Japan).

| Game | Verdict | Words | Sentences | Name cards | Notes |
|---|---|---|---|---|---|
| Pokemon Mystery Dungeon: Red Rescue Team (Japan) | ready | reviewed (311 corrections) | whole lines, filtered | yes | the reference game |
| Gyakuten Saiban (Japan) (Rev 1) | works, with limits | first-pass review (35 corrections, main character names left out), the rest of the long tail unreviewed | one text-box row each (about 14 characters); whole sentences are preferred | no | a few less frequent names may still show up as words |
| Mario & Luigi RPG (Japan) | works, with limits | first-pass review (8 corrections), the rest unreviewed | one box line each (about 14 characters); whole sentences are preferred | no | two rare kanji are not in the character table |
| Pocket Monsters Crystal (Japan) | ready | first-pass review (64 corrections), the rest of the long tail unreviewed | one text-box row each (about 16 characters); whole sentences are preferred | yes | Game Boy Color; the game is written in kana only; a few very short messages are not read (see below) |

In Pocket Monsters Crystal every byte value is a character, so text is read from whole messages only,
and a message that nothing in its part of the ROM points to is kept when it has at least six kana. About
40 short real messages (a few battle lines and goodbyes on the phone, out of some 4,500) are left out
that way; in return, almost no stray data is read as text.

The verdict comes from the project's own check of each game, run the way a learner uses it
(`tools/game_check.py`): *ready* means the text rebuilds the ROM, no raw code reaches a card and almost
every card ends like a sentence; *works, with limits* means usable, with the limits named in the row.
"Reviewed" means the most frequent wrong dictionary picks were corrected by hand. Even then, check the
words you study: kana-heavy text makes a dictionary program guess, and the `Check meanings` page
(or `yomineko review`) lets you fix more.

Making a profile takes detective work: finding the text, working out the encoding, and proving that
it all rebuilds the original file byte for byte. A plain Shift-JIS game takes hours. Many Japanese
games use their own character table or compress their text. Text in BIOS LZ77 blocks stored as
glyph ids is supported (that is how Gyakuten Saiban works), and so is text stored as one-byte codes
with commands (Mario & Luigi RPG) or as framed messages spread over the banks of a Game Boy Color
cartridge (Pocket Monsters Crystal); other compression is not yet. So support
grows one game at a time, and it grows faster with your help.

### Add your game

If you have a Japanese game you own and want to study, you can write its profile yourself, or let an AI
assistant do the work on your computer:

- **Guide for everyone:** [docs/ADDING_A_GAME.md](https://github.com/ctorres345/yomineko/blob/main/docs/ADDING_A_GAME.md) walks through it step by step:
  investigate, draft, prove it with a round trip, check it reads well, submit.
- **With Claude Code:** the repository includes a skill and agents. Open the project, say *"add support
  for my game using the add-game-profile skill"* and give it the path of your game file.
- **Stuck, or the text is stored some other way?** Open a *Game support request* (an issue form) with what you
  found: counts and offsets only. That tells the project which features to build next.

Your game file never leaves your computer, and **nothing taken from a game belongs in an issue, a pull
request or a chat**: no ROMs, no extracted text. Profiles and notes hold offsets, counts, encodings
and control codes only. Accepted profiles are added to the repository and shipped to everyone.
Issues that ask for ROMs, keys or circumvention are closed: see [DISCLAIMER.md](https://github.com/ctorres345/yomineko/blob/main/DISCLAIMER.md).

Found a security problem? Report it privately, as [SECURITY.md](https://github.com/ctorres345/yomineko/blob/main/SECURITY.md) describes, not in an issue.

## Credits

- **Logo:** illustration by @loritoart.
- **Word meanings:** [JMdict](https://www.edrdg.org/jmdict/j_jmdict.html), © the Electronic Dictionary
  Research and Development Group, CC BY-SA 4.0. Downloaded when you ask for it, never bundled.
- **Tokenizer:** [Sudachi](https://github.com/WorksApplications/SudachiPy) (Works Applications,
  Apache-2.0).
- **Web interface:** [htmx](https://htmx.org) and [Pico CSS](https://picocss.com), see [NOTICE](https://github.com/ctorres345/yomineko/blob/main/NOTICE).

## License

Apache-2.0. See [LICENSE](https://github.com/ctorres345/yomineko/blob/main/LICENSE) and [NOTICE](https://github.com/ctorres345/yomineko/blob/main/NOTICE). yomineko is not affiliated
with any game publisher or console maker. The logo is by @loritoart and is not covered by this
licence.
