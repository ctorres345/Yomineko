"""Small text helpers for matching Japanese words."""

from __future__ import annotations


def kata_to_hira(s: str) -> str:
    """Katakana to hiragana (readings are compared in hiragana)."""
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)
