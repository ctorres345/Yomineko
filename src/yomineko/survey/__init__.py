"""``yomineko survey``: read-only checks that show what is different about a game.

Each detector is a pure function over ``bytes`` and returns counts and offsets only, never the
ROM's text. ``run_survey`` runs them all; ``render_report`` turns the result into Markdown.
"""

from yomineko.survey.report import render_report
from yomineko.survey.run import Survey, run_survey

__all__ = ["Survey", "render_report", "run_survey"]
