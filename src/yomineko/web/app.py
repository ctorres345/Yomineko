"""The web application: choose a ROM, extract it, analyse it and look through what was found."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.datastructures import QueryParams
from starlette.middleware.trustedhost import TrustedHostMiddleware

from yomineko import __version__
from yomineko.analyze.dictionary.install import DictionaryInfo, dictionary_info, install_dictionary
from yomineko.analyze.dictionary.xml_parser import DictionaryError
from yomineko.analyze.review import WordRule
from yomineko.analyze.tokenizer import SudachiTokenizer, Tokenizer
from yomineko.analyze.worklist import WorkItem, describe_entry
from yomineko.core.rom.base import MAX_ROM_SIZE, RomError, load_rom_bytes
from yomineko.errors import YominekoError
from yomineko.export.level import (
    LEVELS,
    Choice,
    Level,
    choose_words,
    parse_level,
    word_status,
)
from yomineko.export.select import select_lines
from yomineko.export.sentences import Sentence
from yomineko.export.study import DEFAULT_PLAYER_NAME
from yomineko.model import LineKind, Script, Word
from yomineko.pipeline.analysis import open_dictionary, run_analysis
from yomineko.pipeline.choices import MAX_MIN_FREQ, Choices, load_choices, save_choices
from yomineko.pipeline.exporting import STUDY_FORMATS, ExportRequest, build_export
from yomineko.pipeline.extraction import extract_rom, read_status, save_extraction
from yomineko.pipeline.known import load_known, mark_known, unmark_known
from yomineko.pipeline.reviewing import (
    RuleError,
    confirm,
    prepare_worklist,
    remove_word_rule,
    set_word_rule,
    user_review,
)
from yomineko.pipeline.reviews import describe_report
from yomineko.pipeline.study import choose_sentences, parse_decks
from yomineko.pipeline.workspace import Workspace
from yomineko.profile.loader import packaged_profiles
from yomineko.script_io import read_script, write_script
from yomineko.web import security
from yomineko.web.jobs import Busy, Job, Jobs, Outcome, Work
from yomineko.web.paging import paginate

HERE = Path(__file__).parent
NOTICE_FILE = ".notice-accepted"
SENTENCE_COUNT = 1000
REVIEW_PAGE_SIZE = 10
FORMATS = ("anki", "xlsx", "csv", "json")
CONTENTS = ("words", "sentences", "lines")
KEPT_DOWNLOADS = 4
# A type no web view can show, so every export is saved. The macOS window (WebKit) shows text/csv
# and application/json on screen even with a Content-Disposition of attachment.
SAVED_AS_FILE = "application/octet-stream"
# The step bar on a game's pages: number, name and address ({id} is the game's id).
STEPS = (
    (1, "Add a game", "/"),
    (2, "Find the words", "/games/{id}"),
    (3, "Choose your words", "/games/{id}/choose"),
    (4, "Check meanings", "/games/{id}/review"),
    (5, "Export", "/games/{id}/export"),
)


def _number(text: str, default: int | None, low: int, high: int) -> int | None:
    """A whole number from a form field, kept within limits; blank means ``default``."""
    text = text.strip()
    if not text:
        return default
    if not (text.isascii() and text.isdigit()):
        raise YominekoError(f"{text!r} is not a whole number.")
    return min(max(int(text), low), high)


def _ranked(script: Script) -> bool:
    """True when every word knows how common it is (analysed with schema 4 or later)."""
    return all(w.jmdict_rank is not None for w in script.words)


def _level(script: Script, choices: Choices) -> Level:
    """The saved level, or "starting" for a script analysed before words had ranks: the level is
    shared by every game, and an older script cannot skip by rank."""
    return choices.level if _ranked(script) else "starting"


def _summary(choice: Choice, min_freq: int) -> str:
    parts = []
    if choice.skipped:
        parts.append(f"{choice.skipped:,} skipped for your level")
    if choice.known:
        parts.append(f"{choice.known:,} you know")
    if choice.rare:
        parts.append(
            f"{choice.rare:,} seen fewer than {min_freq} time{'' if min_freq == 1 else 's'}"
        )
    return ", ".join(parts) + "." if parts else "Every word gets a card."


def _how_common(word: Word) -> str:
    """The dictionary's rank of ``word`` in words, for the table on the Choose page."""
    rank = word.jmdict_rank
    if rank is None:
        return ""
    for top in (1000, 5000, 10000, 24000):
        if rank <= top // 500:
            return f"Top {top:,}"
    return "Less common"


@dataclass(frozen=True)
class Download:
    """An export built by a form post, kept so its address can be fetched more than once."""

    filename: str
    media_type: str
    data: bytes


@dataclass(frozen=True)
class Step:
    """One step in the bar: ``state`` is "done", "current" or "later"."""

    number: int
    name: str
    href: str
    state: str
    note: str = ""


@dataclass(frozen=True)
class GameSummary:
    id: str
    title: str


def _start(jobs: Jobs, label: str, work: Work) -> Job:
    """Start a job; if another one is running, show that one instead."""
    try:
        return jobs.start(label, work)
    except Busy as busy:
        return busy.running


def create_app(
    workspace: Workspace,
    *,
    token: str | None = None,
    make_tokenizer: Callable[[], Tokenizer] = SudachiTokenizer,
    install: Callable[[], DictionaryInfo] = install_dictionary,
    on_quit: Callable[[], None] | None = None,
) -> FastAPI:
    """The application for ``workspace``. ``token`` is the per-run secret (random by default).
    ``make_tokenizer`` and ``install`` can be replaced (the tests do). With ``on_quit`` the pages
    show a Quit button (the desktop app, when it has no window of its own to close)."""
    token = token or security.new_token()
    app = FastAPI(
        title="yomineko", version=__version__, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.middleware("http")(security.guard(token))
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=security.ALLOWED_HOSTS)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.globals["version"] = __version__
    templates.env.globals["can_quit"] = on_quit is not None
    jobs = Jobs()
    scripts: dict[str, tuple[int, Script]] = {}  # game id -> (file mtime, parsed script)
    worklists: dict[str, list[WorkItem]] = {}  # game id -> the words still to look at
    downloads: dict[str, Download] = {}  # secret id -> a built export, the newest few
    downloads_lock = threading.Lock()
    picks: dict[str, tuple[object, list[Sentence]]] = {}  # game id -> (inputs, last selection)

    def page(request: Request, name: str, code: int = 200, **context: object) -> HTMLResponse:
        return templates.TemplateResponse(request, name, context, status_code=code)

    def notice_accepted() -> bool:
        return (workspace.root / NOTICE_FILE).is_file()

    def titles() -> dict[str, str]:
        return {p.profile.id: p.profile.title for p in packaged_profiles()}

    def load(game_id: str) -> Script:
        """The game's script, parsed again only when the file changed."""
        path = workspace.script_path(game_id)
        if not path.is_file():
            raise YominekoError("That game has not been extracted.")
        stamp = path.stat().st_mtime_ns
        cached = scripts.get(game_id)
        if cached is None or cached[0] != stamp:
            cached = scripts[game_id] = (stamp, read_script(path))
        return cached[1]

    def review_files(game_id: str) -> list[Path] | None:
        path = workspace.review_path(game_id)
        return [path] if path.is_file() else None

    def steps(game_id: str, script: Script, current: int) -> list[Step]:
        """The step bar for a game's page. A step before the current one is done once it can
        be: adding the game always, the later ones only after the words were found."""
        left = worklists.get(game_id)
        bar = []
        for number, name, href in STEPS:
            if number == current:
                state = "current"
            elif number < current and (number == 1 or script.words):
                state = "done"
            else:
                state = "later"
            note = ""
            if number == 4:
                note = "optional" if left is None else f"optional, {len(left):,} left"
            bar.append(Step(number, name, href.format(id=game_id), state, note))
        return bar

    def to_job(job: Job) -> RedirectResponse:
        return RedirectResponse(f"/jobs/{job.id}", status_code=303)

    @app.exception_handler(YominekoError)
    def known_error(request: Request, exc: YominekoError) -> HTMLResponse:
        return page(request, "error.html", 400, message=str(exc))

    # ------------------------------------------------------------------- home

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        known = titles()
        games = [GameSummary(g, known.get(g, g)) for g in workspace.games()]
        return page(
            request,
            "home.html",
            games=games,
            notice=not notice_accepted(),
            max_mb=MAX_ROM_SIZE >> 20,
            dictionary=dictionary_info(),
            folder=str(workspace.root.resolve()),
        )

    @app.post("/quit")
    def quit_app(request: Request) -> HTMLResponse:
        if on_quit is None:
            return page(request, "error.html", 404, message="There is nothing to quit here.")
        threading.Timer(0.3, on_quit).start()  # after this response has been sent
        return page(request, "stopped.html")

    @app.post("/notice")
    def accept_notice() -> RedirectResponse:
        workspace.root.mkdir(parents=True, exist_ok=True)
        (workspace.root / NOTICE_FILE).write_text("accepted\n", encoding="utf-8")
        return RedirectResponse("/", status_code=303)

    @app.post("/extract")
    def extract(file: Annotated[UploadFile, File()]) -> Response:
        name = file.filename or ""
        if not name:
            raise RomError("choose a ROM file first")
        data = file.file.read(MAX_ROM_SIZE + 1)
        rom = load_rom_bytes(data, name)
        extraction = extract_rom(rom)
        save_extraction(workspace, extraction)
        worklists.pop(extraction.script.game.profile_id, None)
        return RedirectResponse(f"/games/{extraction.script.game.profile_id}", status_code=303)

    # ------------------------------------------------------------------- jobs

    @app.post("/dictionary/download")
    def download_dictionary() -> RedirectResponse:
        def work(say: Callable[[str], None]) -> Outcome:
            say("Downloading the dictionary from edrdg.org and indexing it (about a minute)")
            info = install()
            return Outcome("/", [f"{info.entries:,} entries, dated {info.date}.", info.credit])

        return to_job(_start(jobs, "Downloading the dictionary", work))

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_page(request: Request, job_id: str) -> HTMLResponse:
        job = jobs.get(job_id)
        if job is None:
            return page(request, "error.html", 404, message="That task is not running.")
        return page(request, "job.html", job=job)

    @app.get("/jobs/{job_id}/status", response_class=HTMLResponse)
    def job_status(request: Request, job_id: str) -> HTMLResponse:
        job = jobs.get(job_id)
        if job is None:
            return page(request, "error.html", 404, message="That task is not running.")
        return page(request, "_job_status.html", job=job)

    @app.post("/games/{game_id}/analyze")
    def analyze(game_id: str) -> RedirectResponse:
        path = workspace.script_path(game_id)
        if not path.is_file():
            raise YominekoError("That game has not been extracted.")
        if dictionary_info() is None:
            raise DictionaryError("Download the dictionary first (on the start page).")

        def work(say: Callable[[str], None]) -> Outcome:
            say("Reading the script")
            script = read_script(path)
            say("Finding the words and their meanings (a few seconds)")
            done = run_analysis(
                script, make_tokenizer, review_files=review_files(game_id), download=False
            )
            write_script(done.script, path)
            found = len(done.script.words)
            notes = [f"{found:,} distinct word{'' if found == 1 else 's'} found."]
            if done.report is not None:
                notes.extend(describe_report(done.report))
            return Outcome(f"/games/{game_id}", notes)

        return to_job(_start(jobs, "Analysing the game", work))

    # ------------------------------------------------------------------- game

    @app.get("/games/{game_id}", response_class=HTMLResponse)
    def game(request: Request, game_id: str) -> HTMLResponse:
        if not workspace.script_path(game_id).is_file():
            return page(request, "error.html", 404, message="That game has not been extracted.")
        script = load(game_id)
        unique = select_lines(script)
        dialogue = sum(1 for x in unique if x.kind == "dialogue")
        return page(
            request,
            "game.html",
            script=script,
            game_id=game_id,
            status=read_status(workspace, game_id),
            lines=len(unique),
            dialogue=dialogue,
            terms=len(unique) - dialogue,
            words=len(script.words),
            dictionary=dictionary_info(),
            steps=steps(game_id, script, 2),
        )

    def words_page(
        request: Request, game_id: str, q: str = "", min_freq: int = 1, p: int = 1
    ) -> HTMLResponse:
        script = load(game_id)
        choices = load_choices(workspace, game_id)
        known = load_known(workspace)
        level = _level(script, choices)
        needle = q.strip().lower()
        ranked = [
            (rank, w)
            for rank, w in enumerate(script.words, start=1)
            if w.freq >= min_freq
            and (
                not needle
                or any(needle in t.lower() for t in (w.written, w.kana, w.kanji, *w.meanings))
            )
        ]
        return page(
            request,
            "words.html",
            game_id=game_id,
            title=script.game.title,
            rows=paginate(ranked, p),
            q=q,
            min_freq=max(min_freq, 1),
            analysed=bool(script.words),
            choices=choices,
            level=LEVELS[choices.level],
            status=lambda w: word_status(w, level=level, min_freq=choices.min_freq, known=known),
            ranked=_ranked(script),
            steps=steps(game_id, script, 3),
        )

    @app.get("/games/{game_id}/words", response_class=HTMLResponse)
    def words(
        request: Request, game_id: str, q: str = "", min_freq: int = 1, p: int = 1
    ) -> HTMLResponse:
        return words_page(request, game_id, q, min_freq, p)

    @app.get("/games/{game_id}/lines", response_class=HTMLResponse)
    def lines(
        request: Request, game_id: str, q: str = "", kind: str = "", p: int = 1
    ) -> HTMLResponse:
        script = load(game_id)
        wanted: LineKind | None = None
        if kind == "dialogue":
            wanted = "dialogue"
        elif kind == "term":
            wanted = "term"
        found = [x for x in select_lines(script, kind=wanted) if q.strip() in x.text]
        return page(
            request,
            "lines.html",
            game_id=game_id,
            title=script.game.title,
            rows=paginate(found, p),
            q=q,
            kind=kind,
            steps=steps(game_id, script, 2),
        )

    @app.get("/games/{game_id}/sentences", response_class=HTMLResponse)
    def sentences(
        request: Request,
        game_id: str,
        count: int = SENTENCE_COUNT,
        p: int = 1,
        addresses: bool = False,
    ) -> HTMLResponse:
        script = load(game_id)
        choices = load_choices(workspace, game_id)
        count = min(max(count, 1), 5000)
        files = review_files(game_id)
        level = _level(script, choices)
        known = load_known(workspace)
        # the selection takes most of a second on a long script, so paging reuses the last one
        inputs = (
            scripts[game_id][0],
            files[0].stat().st_mtime_ns if files else None,
            count,
            choices.min_freq,
            level,
            known,
        )
        cached = picks.get(game_id)
        if cached is None or cached[0] != inputs:
            picked = choose_sentences(
                script,
                count=count,
                min_freq=choices.min_freq,
                review_files=files,
                level=level,
                known=known,
            )
            cached = picks[game_id] = (inputs, picked)
        picked = cached[1]
        return page(
            request,
            "sentences.html",
            game_id=game_id,
            title=script.game.title,
            rows=paginate(picked, p),
            count=count,
            addresses=addresses,
            steps=steps(game_id, script, 2),
        )

    # ----------------------------------------------------------------- choose

    def choose_page(request: Request, game_id: str, choices: Choices, p: int = 1) -> HTMLResponse:
        script = load(game_id)
        ranked = _ranked(script)
        level = _level(script, choices)
        known = load_known(workspace)
        choice = choose_words(script, level=level, min_freq=choices.min_freq, known=known)
        return page(
            request,
            "choose.html",
            game_id=game_id,
            title=script.game.title,
            analysed=bool(script.words),
            ranked=ranked,
            levels=list(LEVELS.items()),
            level=level,
            min_freq=choices.min_freq,
            max_min_freq=MAX_MIN_FREQ,
            choice=choice,
            summary=_summary(choice, choices.min_freq),
            steps=steps(game_id, script, 3),
            rows=paginate(script.words, p),
            status=lambda w: word_status(w, level=level, min_freq=choices.min_freq, known=known),
            how_common=_how_common,
        )

    @app.get("/games/{game_id}/choose", response_class=HTMLResponse)
    def choose(request: Request, game_id: str, p: int = 1) -> HTMLResponse:
        return choose_page(request, game_id, load_choices(workspace, game_id), p)

    @app.post("/games/{game_id}/choose", response_model=None)
    def choose_save(
        request: Request,
        game_id: str,
        level: Annotated[str, Form()] = "starting",
        min_freq: Annotated[str, Form()] = "",
        p: Annotated[int, Form()] = 1,
    ) -> Response:
        """Remember the choices. A page that updates itself (htmx) gets the new page back; a
        plain form post is sent back to the page."""
        script = load(game_id)
        saved = load_choices(workspace, game_id)
        choices = Choices(
            # an older script offers "starting" only; keep the level picked for the other games
            parse_level(level) if _ranked(script) else saved.level,
            _number(min_freq, saved.min_freq, 1, MAX_MIN_FREQ) or saved.min_freq,
        )
        save_choices(workspace, game_id, choices)
        if request.headers.get("hx-request"):
            return choose_page(request, game_id, choices, p)
        return RedirectResponse(f"/games/{game_id}/choose", status_code=303)

    @app.post("/games/{game_id}/known", response_model=None)
    def known_word(
        request: Request,
        game_id: str,
        word: Annotated[int, Form()],
        action: Annotated[str, Form()],
        back: Annotated[str, Form()] = "choose",
        p: Annotated[int, Form()] = 1,
        q: Annotated[str, Form()] = "",
        min_freq: Annotated[int, Form()] = 1,
    ) -> Response:
        """Mark a word "I know this" (or undo it) for every game. Only its JMdict id is kept.
        A page that updates itself (htmx) gets the page back with the new card count."""
        script = load(game_id)
        if word not in {w.jmdict_id for w in script.words}:
            raise YominekoError("That word is not in this game. Reload the page.")
        if action == "know":
            mark_known(workspace, [word])
        elif action == "undo":
            unmark_known(workspace, [word])
        else:
            raise YominekoError("Unknown action.")
        live = bool(request.headers.get("hx-request"))
        if back == "words":
            if live:
                return words_page(request, game_id, q, min_freq, p)
            query = QueryParams({"q": q, "min_freq": min_freq, "p": p})
            return RedirectResponse(f"/games/{game_id}/words?{query}", status_code=303)
        if live:
            return choose_page(request, game_id, load_choices(workspace, game_id), p)
        return RedirectResponse(f"/games/{game_id}/choose?p={p}", status_code=303)

    # ----------------------------------------------------------------- export

    @app.get("/games/{game_id}/export", response_class=HTMLResponse)
    def export_form(request: Request, game_id: str) -> HTMLResponse:
        script = load(game_id)
        choices = load_choices(workspace, game_id)
        level = _level(script, choices)
        known = load_known(workspace)
        return page(
            request,
            "export.html",
            game_id=game_id,
            title=script.game.title,
            analysed=bool(script.words),
            player_name=DEFAULT_PLAYER_NAME,
            min_freq=choices.min_freq,
            level=LEVELS[level],
            known=len(known),
            count=SENTENCE_COUNT,
            cards=choose_words(script, level=level, min_freq=choices.min_freq, known=known).cards,
            steps=steps(game_id, script, 5),
        )

    @app.post("/games/{game_id}/export")
    def export_download(
        game_id: str,
        kind: Annotated[str, Form()],
        content: Annotated[str, Form()] = "words",
        decks: Annotated[list[str] | None, Form()] = None,
        min_freq: Annotated[str, Form()] = "",
        sentences: Annotated[str, Form()] = "",
        order: Annotated[str, Form()] = "frequency",
        player_name: Annotated[str, Form()] = DEFAULT_PLAYER_NAME,
        deck_name: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """Build the file and send the page to an address that serves it. The macOS window
        (pywebview on WebKit) saves a download by fetching its address again with a GET, so the
        file must not be the answer to the post itself."""
        script = load(game_id)
        choices = load_choices(workspace, game_id)
        if kind not in FORMATS or content not in CONTENTS or order not in ("frequency", "rom"):
            raise YominekoError("Choose what to export.")
        if kind in STUDY_FORMATS and not decks:
            raise YominekoError("Choose at least one of words, sentences and terms.")
        count = _number(sentences, SENTENCE_COUNT, 1, 5000) or SENTENCE_COUNT
        made = build_export(
            script,
            ExportRequest(
                format=kind,  # type: ignore[arg-type]  # checked against FORMATS above
                content=content,  # type: ignore[arg-type]
                min_freq=_number(min_freq, choices.min_freq, 1, 100000),
                level=_level(script, choices),
                known=load_known(workspace),
                sentences=count,
                order=order,  # type: ignore[arg-type]
                decks=parse_decks(",".join(decks or [])),
                deck_name=deck_name.strip() or None,
                player_name=player_name.strip() or DEFAULT_PLAYER_NAME,
                review_files=review_files(game_id),
            ),
        )
        name = made.filename(game_id, content if kind in ("csv", "json") else "")
        key = security.new_token()
        with downloads_lock:
            downloads[key] = Download(name, SAVED_AS_FILE, made.data)
            while len(downloads) > KEPT_DOWNLOADS:
                del downloads[next(iter(downloads))]  # the oldest
        return RedirectResponse(f"/downloads/{key}", status_code=303)

    @app.get("/downloads/{key}")
    def download_file(key: str) -> Response:
        """A file the export form built. The address is a secret only the page that posted the
        form learns, so the GET needs no token."""
        with downloads_lock:
            made = downloads.get(key)
        if made is None:
            raise YominekoError("That download is no longer kept. Export the file again.")
        return Response(
            made.data,
            media_type=made.media_type,
            headers={"Content-Disposition": f'attachment; filename="{made.filename}"'},
        )

    # ----------------------------------------------------------------- review

    def pending_changes(game_id: str) -> bool:
        """Corrections saved after the last analysis: the word list does not show them yet."""
        review = workspace.review_path(game_id)
        script = workspace.script_path(game_id)
        return review.is_file() and review.stat().st_mtime_ns > script.stat().st_mtime_ns

    @app.get("/games/{game_id}/review", response_class=HTMLResponse)
    def review(request: Request, game_id: str, p: int = 1) -> HTMLResponse:
        script = load(game_id)
        items = worklists.get(game_id)
        rules = []
        mine = user_review(workspace, game_id)
        if mine.words and dictionary_info() is not None:
            with open_dictionary() as dictionary:
                for w in mine.words:
                    rules.append(
                        {
                            "id": w.from_,
                            "word": describe_entry(dictionary, w.from_),
                            "to": describe_entry(dictionary, w.to) if w.to else None,
                            "drop": w.drop,
                            "gloss": w.gloss,
                            "partial": not w.sentence_safe,
                        }
                    )
        return page(
            request,
            "review.html",
            game_id=game_id,
            title=script.game.title,
            analysed=bool(script.words),
            rows=paginate(items, p, REVIEW_PAGE_SIZE) if items is not None else None,
            prepared=items is not None,
            rules=rules,
            pending=pending_changes(game_id),
            steps=steps(game_id, script, 4),
        )

    @app.post("/games/{game_id}/review/prepare")
    def prepare_review(game_id: str) -> RedirectResponse:
        script = load(game_id)
        if dictionary_info() is None:
            raise DictionaryError("Download the dictionary first (on the start page).")

        def work(say: Callable[[str], None]) -> Outcome:
            say("Looking for words the dictionary could mean in more than one way")
            items = prepare_worklist(workspace, game_id, script, make_tokenizer)
            worklists[game_id] = items
            return Outcome(f"/games/{game_id}/review", [f"{len(items):,} words to look at."])

        return to_job(_start(jobs, "Preparing the words to review", work))

    @app.post("/games/{game_id}/review/rule")
    def review_rule(
        game_id: str,
        pick: Annotated[int, Form()],
        action: Annotated[str, Form()],
        to: Annotated[int | None, Form()] = None,
        gloss: Annotated[str, Form()] = "",
        partial: Annotated[str, Form()] = "",
        p: Annotated[int, Form()] = 1,
    ) -> RedirectResponse:
        script = load(game_id)
        items = worklists.get(game_id) or []
        item = next((i for i in items if i.pick.entry_id == pick), None)
        if item is None:
            raise RuleError("That word is not on the list any more. Reload the page.")
        try:
            if action == "use":
                if to not in {a.entry_id for a in item.alternatives}:
                    raise RuleError("That is not one of the alternatives for this word.")
                rule = WordRule(**{"from": pick, "to": to, "sentence_safe": not partial})
            elif action == "drop":
                rule = WordRule(**{"from": pick, "drop": True})
            elif action == "gloss":
                rule = WordRule(**{"from": pick, "gloss": gloss})
            elif action == "confirm":
                confirm(workspace, game_id, pick)
                worklists[game_id] = [i for i in items if i is not item]
                return RedirectResponse(f"/games/{game_id}/review?p={p}", status_code=303)
            else:
                raise RuleError("Unknown action.")
        except ValidationError as e:
            raise RuleError("; ".join(str(err["msg"]) for err in e.errors())) from e
        set_word_rule(workspace, game_id, script, rule)
        worklists[game_id] = [i for i in items if i is not item]
        return RedirectResponse(f"/games/{game_id}/review?p={p}", status_code=303)

    @app.post("/games/{game_id}/review/remove")
    def review_remove(game_id: str, pick: Annotated[int, Form()]) -> RedirectResponse:
        load(game_id)
        remove_word_rule(workspace, game_id, pick)
        worklists.pop(game_id, None)  # the word may belong on the list again: rebuild it
        return RedirectResponse(f"/games/{game_id}/review", status_code=303)

    return app
