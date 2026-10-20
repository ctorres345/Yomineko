"""The web interface's colours: only the five greys, and every text pair readable (WCAG 4.5:1)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from yomineko.web import app as web_app

STATIC = Path(web_app.__file__).parent / "static"
TEMPLATES = Path(web_app.__file__).parent / "templates"
CSS = (STATIC / "app.css").read_text(encoding="utf-8")
PALETTE = {"#ffffff", "#bfbfbf", "#7f7f7f", "#404040", "#000000"}
TOKEN = re.compile(r"--yk-([a-z0-9]+):\s*(#[0-9a-fA-F]{6})")

# (text, background) for every place text sits on a colour: running text, headings and links,
# secondary text, inverted labels and the filled button, its hover, and selected text.
TEXT_PAIRS = [
    ("body", "bg"),
    ("fg", "bg"),
    ("fg2", "bg"),
    ("bg", "fg"),
    ("bg", "fg2"),
    ("body", "line"),
]


def block(selector: str) -> str:
    start = CSS.index(selector + " {")
    return CSS[start : CSS.index("}", start)]


def tokens(text: str) -> dict[str, str]:
    return {name: value.lower() for name, value in TOKEN.findall(text)}


def luminance(hex_colour: str) -> float:
    def channel(c: int) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


LIGHT = tokens(block(":root"))
DARK = tokens(block("[data-theme=dark]"))


def test_contrast_matches_the_known_values():
    assert round(contrast("#7f7f7f", "#ffffff"), 1) == 4.0
    assert round(contrast("#bfbfbf", "#ffffff"), 1) == 1.8
    assert round(contrast("#000000", "#ffffff"), 1) == 21.0


def test_both_themes_define_every_token():
    assert set(LIGHT) == set(DARK) == {"bg", "fg", "body", "fg2", "line", "ctl"}


def test_automatic_dark_mode_uses_the_same_tokens_as_forced_dark():
    assert tokens(block(":root:not([data-theme=light])")) == DARK


@pytest.mark.parametrize("theme", [LIGHT, DARK], ids=["light", "dark"])
@pytest.mark.parametrize(("text", "background"), TEXT_PAIRS)
def test_every_text_pair_is_readable(theme, text, background):
    assert contrast(theme[text], theme[background]) >= 4.5


@pytest.mark.parametrize("theme", [LIGHT, DARK], ids=["light", "dark"])
def test_control_borders_are_visible(theme):
    assert contrast(theme["ctl"], theme["bg"]) >= 3.0


def test_only_the_palette_is_used():
    colours = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{3,8}\b", CSS)}
    assert colours <= PALETTE
    assert not re.search(r"\b(rgba?|hsla?)\(", CSS)


def test_fonts_are_bundled_and_nothing_is_fetched_from_elsewhere():
    for name in re.findall(r'url\("([^"]+)"\)', CSS):
        assert not name.startswith(("http:", "https:", "//")) and (STATIC / name).is_file()
    assert (STATIC / "fonts" / "OFL.txt").is_file()
    for page in TEMPLATES.glob("*.html"):
        html = page.read_text(encoding="utf-8")
        assert not re.search(r'src="(https?:)?//', html), page
        assert not re.search(r'<link[^>]*href="(https?:)?//', html), page
        # a link the user clicks is not a fetch; the only one is the Ko-fi link, in the footer
        for link in re.findall(r'<a [^>]*href="(?:https?:)?//[^"]*"', html):
            assert page.name == "base.html" and "ko-fi.com/pandaveloper" in link, page
