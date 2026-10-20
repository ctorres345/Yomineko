# Security policy

## Supported versions

Security fixes go into the latest published version of yomineko only. Upgrade to it before
reporting a problem that may already be fixed.

## Reporting a vulnerability

Report privately with **Report a vulnerability** in the repository's **Security** tab. Do not
open a public issue, pull request or discussion about it, and do not open one to ask for a private
contact.

In the report, say which yomineko version you ran, how you installed it (pip, or the desktop app),
your operating system, what an attacker can do, the steps or input that show it, and a fix if you
have one.

Leave out of the report, its logs and its examples:

- ROMs, archives holding ROMs, save states, and anything extracted from a game: scripts, word
  lists, sentences, decks or worklists. If the problem needs a crafted file, describe it or give a
  small script that builds it from scratch, the way `tests/support/synthrom.py` does.
- Local paths that name you or your machine (your user folder, the workspace folder).
- The per-run token, cookies, and any key or password.

The maintainer will acknowledge the report, work out its scope, and agree with you on a fix and on
when to disclose it.

## Security boundary

**The local web interface** (`yomineko serve` and the desktop app) can read ROMs and write files,
so it keeps other computers and other web pages away from it:

- it listens on 127.0.0.1 only, and there is no option to change that;
- the `Host` header must be `localhost`, `127.0.0.1` or `[::1]`, which stops DNS rebinding;
- a request that changes anything must carry an `Origin` equal to the page's own and the per-run
  random token in a `SameSite=Strict` cookie, which another site cannot send;
- an upload larger than the largest ROM is refused before it is read;
- pages are served with a strict Content-Security-Policy and may not be framed.

These rules stop a web page or another computer from driving the server. They are not a sandbox:
they do not protect against a program already running as your user, which can read the token and
your files as you can.

**ROMs stay on your machine.** Extraction, word lists and exports make no network calls, and nothing
is sent anywhere: there is no telemetry and no account. The one download is the JMdict dictionary,
and only when you ask for it (`yomineko dict download`, or the download on the web interface's
start page): HTTPS only, from the EDRDG address by default, with a size limit. Anki cards hold links
to Jisho that open only when you click them.

**ROMs are untrusted input.** yomineko parses each ROM, and the one ROM inside a `.zip`, with your
user's permissions. It bounds how much it reads (a ROM is at most 32 MiB, also inside a zip), and
expected failures stop with an error message. A hostile file that makes the parser crash, hang or
use far too much memory or time is a bug worth reporting. yomineko does not run code from a ROM.

**What is out of scope:** no decryption and no circumvention, so a report asking yomineko to get
past a protection is not a vulnerability. Profiles and review files are data, read with a safe YAML
loader, but a profile from someone you do not trust can still make extraction slow or wrong, so
use the ones shipped with yomineko or ones you have read.
