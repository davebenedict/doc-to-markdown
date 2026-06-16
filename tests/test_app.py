"""
Tests for app.py — pure-logic helpers that don't require a running GUI.

We replicate _parse_dnd_paths here to avoid importing app.py, which pulls
in customtkinter and tkinterdnd2 (GUI dependencies not available in CI).
"""

from __future__ import annotations

import re

import pytest


def _parse_dnd_paths(raw: str) -> list[str]:
    """Mirror of App._parse_dnd_paths — kept in sync manually."""
    braced = re.findall(r"\{([^}]+)\}", raw)
    remainder = re.sub(r"\{[^}]+\}", "", raw).split()
    return braced + remainder


# ---------------------------------------------------------------------------
# _parse_dnd_paths
# ---------------------------------------------------------------------------

class TestParseDndPaths:
    def test_single_simple_path(self):
        assert _parse_dnd_paths(r"C:\docs\file.pdf") == [r"C:\docs\file.pdf"]

    def test_multiple_simple_paths(self):
        result = _parse_dnd_paths(r"C:\a.pdf C:\b.docx")
        assert result == [r"C:\a.pdf", r"C:\b.docx"]

    def test_braced_path_with_spaces(self):
        result = _parse_dnd_paths(r"{C:\My Documents\file.pdf}")
        assert result == [r"C:\My Documents\file.pdf"]

    def test_mixed_braced_and_simple(self):
        raw = r"{C:\My Docs\a.pdf} C:\b.docx {C:\Other Folder\c.html}"
        result = _parse_dnd_paths(raw)
        assert r"C:\My Docs\a.pdf" in result
        assert r"C:\b.docx" in result
        assert r"C:\Other Folder\c.html" in result
        assert len(result) == 3

    def test_empty_string(self):
        assert _parse_dnd_paths("") == []

    def test_only_braces(self):
        result = _parse_dnd_paths(r"{C:\path one\f.pdf} {C:\path two\g.pdf}")
        assert len(result) == 2

    def test_no_leftover_braces_in_results(self):
        result = _parse_dnd_paths(r"{C:\a b\f.pdf}")
        for p in result:
            assert "{" not in p
            assert "}" not in p
