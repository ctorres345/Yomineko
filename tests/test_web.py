"""The web pages, on synthetic ROMs."""

import io
import re
import zipfile

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient
from support.study import make_script
from support.synthrom import SynthRom

from yomineko.pipeline.workspace import Workspace
from yomineko.profile.loader import load_profile
from yomineko.script_io import write_script
from yomineko.web.app import NOTICE_FILE, THEME_FILE, create_app

ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture
def workspace(tmp_path):
    return Workspace(tmp_path / "games")


@pytest.fixture
def client(workspace):
    return TestClient(create_app(workspace), base_url="http://localhost")


@pytest.fixture
def synth_profile(sjis_rom, monkeypatch):
    """Make the synthetic ROM's profile the one found for it (no packaged profile matches)."""
    loaded = load_profile(sjis_rom.profile_path)
    monkeypatch.setattr("yomineko.pipeline.extraction.find_profile", lambda sha1, extra=(): loaded)
    return loaded


def upload(client, data, name="game.gba"):
    client.get("/")  # the page sets the cookie a form post needs
    return client.post(
        "/extract", files={"file": (name, data)}, headers=ORIGIN, follow_redirects=False
    )


# ------------------------------------------------------------------------ home


def test_the_home_page_shows_the_notice_until_it_is_accepted(client, workspace):
    page = client.get("/")
    assert page.status_code == 200 and "for games you own" in page.text
    assert 'name="file"' in page.text and "viewport" in page.text
    accepted = client.post("/notice", headers=ORIGIN, follow_redirects=False)
    assert accepted.status_code == 303 and (workspace.root / NOTICE_FILE).is_file()
    assert "for games you own" not in client.get("/").text


def test_the_theme_button_steps_through_system_light_and_dark(client, workspace):
    page = client.get("/")
    assert "data-theme" not in page.text.split("<head>")[0]  # follows the system setting
    assert 'content="light dark"' in page.text and "Theme: Match system" in page.text
    for theme, label in (("light", "Light"), ("dark", "Dark")):
        assert f'name="theme" value="{theme}"' in page.text  # the button offers the next one
        moved = client.post(
            "/theme", data={"theme": theme, "back": "/"}, headers=ORIGIN, follow_redirects=False
        )
        assert moved.status_code == 303 and (workspace.root / THEME_FILE).is_file()
        page = client.get("/")
        assert f'<html lang="en" data-theme="{theme}">' in page.text
        assert f'name="color-scheme" content="{theme}"' in page.text
        assert f"Theme: {label}" in page.text
    assert 'name="theme" value=""' in page.text  # after dark, back to the system setting
    client.post("/theme", data={"theme": ""}, headers=ORIGIN)
    assert not (workspace.root / THEME_FILE).exists()
    assert "Theme: Match system" in client.get("/").text


def test_the_theme_is_kept_by_a_new_window(workspace):
    first = TestClient(create_app(workspace), base_url="http://localhost")
    first.get("/")
    first.post("/theme", data={"theme": "dark"}, headers=ORIGIN)
    again = TestClient(create_app(workspace), base_url="http://localhost")
    assert 'data-theme="dark"' in again.get("/").text


@pytest.mark.parametrize(
    ("back", "to"),
    [
        ("/games/demo/choose?p=2", "/games/demo/choose?p=2"),
        ("https://example.com/", "/"),
        ("//example.com/", "/"),
        ("/\\example.com/", "/"),
        ("/a\r\nSet-Cookie: x=1", "/"),
    ],
)
def test_the_theme_button_only_returns_to_a_page_on_this_server(client, back, to):
    client.get("/")
    moved = client.post(
        "/theme", data={"theme": "light", "back": back}, headers=ORIGIN, follow_redirects=False
    )
    assert moved.headers["location"] == to


def test_the_theme_button_returns_to_the_page_it_is_on(client):
    page = client.get("/?x=1")
    assert 'name="back" value="/?x=1"' in page.text


def test_an_unknown_theme_is_refused(client, workspace):
    client.get("/")
    refused = client.post("/theme", data={"theme": "pink"}, headers=ORIGIN)
    assert refused.status_code == 400 and not (workspace.root / THEME_FILE).exists()


def test_the_pages_load_nothing_from_other_sites(client):
    html = client.get("/").text
    assert not re.findall(r'src="(?:https?:)?//', html)
    assert not re.findall(r'<link[^>]*href="(?:https?:)?//', html)
    # the one link to another site is the donation link, opened outside the app on a click
    links = re.findall(r'<a [^>]*href="(?:https?:)?//[^>]*>', html)
    assert links == [
        '<a href="https://ko-fi.com/pandaveloper" target="_blank" rel="noopener noreferrer">'
    ]
    assert client.get("/static/htmx.min.js").status_code == 200
    assert client.get("/static/pico.min.css").status_code == 200


def test_games_in_the_workspace_are_listed(client, workspace):
    write_script(make_script(), workspace.script_path("demo"))
    page = client.get("/")
    assert '<a href="/games/demo">demo</a>' in page.text


# --------------------------------------------------------------------- extract


def test_uploading_a_rom_extracts_it_and_shows_the_result(
    client, workspace, sjis_rom, synth_profile
):
    response = upload(client, sjis_rom.rom)
    assert response.status_code == 303 and response.headers["location"] == "/games/synth-sjis"
    assert workspace.script_path("synth-sjis").is_file()
    page = client.get("/games/synth-sjis")
    assert page.status_code == 200 and 'class="status">' in page.text
    assert "Rebuild check passed</span>" in page.text
    assert sjis_rom.sha1 in page.text and "finds each word" in page.text
    assert "Dialogue" in page.text and "strings found in" in page.text


def test_a_zip_with_one_rom_works(client, sjis_rom, synth_profile):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("Game.GBA", sjis_rom.rom)
    response = upload(client, buffer.getvalue(), "game.zip")
    assert response.status_code == 303


def test_the_uploaded_rom_is_not_kept(client, workspace, sjis_rom, synth_profile):
    upload(client, sjis_rom.rom)
    kept = {p.name for p in workspace.root.rglob("*") if p.is_file()}
    assert kept == {"script.json", "game.json"}


def test_a_file_that_is_not_a_rom_is_explained(client):
    response = upload(client, b"just some text", "notes.txt")
    assert response.status_code == 400 and "not a GBA or Game Boy ROM" in response.text


def test_a_rom_that_is_not_japanese_is_explained(client):
    rom = SynthRom("USA GAME", "USAE", size=0x4000).finish()[0]
    response = upload(client, rom)
    assert response.status_code == 400
    assert "reads Japanese games" in response.text and "USAE" in response.text


def test_a_rom_without_a_profile_says_which_games_are_supported(client, sjis_rom):
    response = upload(client, sjis_rom.rom)
    assert response.status_code == 400
    assert "no profile for this ROM" in response.text and "pmd-red-jp" in response.text


# ----------------------------------------------------------------------- game


def test_a_game_that_was_not_extracted_is_a_404(client):
    page = client.get("/games/nothing")
    assert page.status_code == 404 and "not been extracted" in page.text


@pytest.mark.parametrize("bad", ["A", "-x", "a.b", "%2e%2e", "a%5Cb"])
def test_a_game_id_that_is_not_a_folder_name_is_refused(client, bad):
    page = client.get(f"/games/{bad}")
    assert page.status_code in (400, 404) and "Traceback" not in page.text


def test_game_text_is_escaped(client, workspace):
    game = make_script().game.model_copy(update={"title": "<script>alert(1)</script>"})
    write_script(make_script(game=game), workspace.script_path("demo"))
    html = client.get("/games/demo").text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_an_analysed_game_shows_its_word_count(client, workspace):
    write_script(make_script(), workspace.script_path("demo"))
    assert "60 distinct words" in client.get("/games/demo").text
