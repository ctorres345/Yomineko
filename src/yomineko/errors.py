"""The base class for every error yomineko raises on purpose.

The CLI catches ``YominekoError`` and prints its message without a traceback. Anything else
that escapes is a bug and keeps its traceback.
"""


class YominekoError(Exception):
    """An expected failure the user can fix: a bad file, a profile mismatch, and so on."""


class MissingExtraError(YominekoError):
    """An optional part (the analysis tools, the web interface) is not installed."""
