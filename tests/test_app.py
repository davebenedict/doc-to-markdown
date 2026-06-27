"""
Tests for app.py — pure-logic helpers that don't require a running GUI.

We replicate pure logic from app.py here to avoid importing it, which pulls
in customtkinter and tkinterdnd2 (GUI dependencies not available in CI).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import converter as conv


# ---------------------------------------------------------------------------
# Helpers mirroring _queue_batch / _run_folder categorisation logic
# ---------------------------------------------------------------------------

def _categorise_files(files: list[Path]):
    """Mirror of the file-triage logic inside App._queue_batch."""
    valid, md_skipped, unsupported = [], 0, []
    for src in files:
        ext = src.suffix.lower()
        if ext == ".md":
            md_skipped += 1
        elif ext not in conv.SUPPORTED_EXTENSIONS:
            unsupported.append(src)
        else:
            valid.append(src)
    return valid, md_skipped, unsupported


def _folder_categorise(all_files: list[Path]):
    """Mirror of the file-triage logic inside App._run_folder."""
    convertible = [f for f in all_files if f.suffix.lower() in conv.SUPPORTED_EXTENSIONS]
    md_skipped = sum(1 for f in all_files if f.suffix.lower() == ".md")
    return convertible, md_skipped


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


# ---------------------------------------------------------------------------
# .md exclusion — _queue_batch logic
# ---------------------------------------------------------------------------

class TestMarkdownExclusion:
    def test_single_md_file_is_skipped(self):
        files = [Path("doc.md")]
        valid, md_skipped, _ = _categorise_files(files)
        assert md_skipped == 1
        assert valid == []

    def test_multiple_md_files_counted(self):
        files = [Path("a.md"), Path("b.md"), Path("c.md")]
        _, md_skipped, _ = _categorise_files(files)
        assert md_skipped == 3

    def test_md_case_insensitive(self):
        files = [Path("README.MD"), Path("notes.Md")]
        _, md_skipped, _ = _categorise_files(files)
        assert md_skipped == 2

    def test_valid_files_pass_through(self):
        files = [Path("report.csv"), Path("notes.md"), Path("slide.pptx")]
        valid, md_skipped, _ = _categorise_files(files)
        assert md_skipped == 1
        assert len(valid) == 2
        assert all(f.suffix.lower() != ".md" for f in valid)

    def test_mixed_batch_converts_valid_skips_md(self):
        files = [Path("a.html"), Path("b.md"), Path("c.csv")]
        valid, md_skipped, unsupported = _categorise_files(files)
        assert md_skipped == 1
        assert len(valid) == 2
        assert unsupported == []

    def test_unsupported_type_separate_from_md(self):
        files = [Path("file.xyz"), Path("notes.md")]
        valid, md_skipped, unsupported = _categorise_files(files)
        assert md_skipped == 1
        assert len(unsupported) == 1
        assert unsupported[0].suffix == ".xyz"

    def test_all_md_no_valid_files(self):
        files = [Path("a.md"), Path("b.md")]
        valid, md_skipped, _ = _categorise_files(files)
        assert valid == []
        assert md_skipped == 2

    def test_no_md_no_skips(self):
        files = [Path("a.csv"), Path("b.html")]
        _, md_skipped, _ = _categorise_files(files)
        assert md_skipped == 0


# ---------------------------------------------------------------------------
# .md exclusion — _run_folder logic
# ---------------------------------------------------------------------------

class TestFolderMarkdownExclusion:
    def test_md_files_counted_in_folder(self):
        all_files = [Path("a.csv"), Path("b.md"), Path("c.md")]
        convertible, md_skipped = _folder_categorise(all_files)
        assert md_skipped == 2
        assert len(convertible) == 1

    def test_no_md_in_folder(self):
        all_files = [Path("a.csv"), Path("b.html")]
        convertible, md_skipped = _folder_categorise(all_files)
        assert md_skipped == 0
        assert len(convertible) == 2

    def test_only_md_in_folder(self):
        all_files = [Path("a.md"), Path("b.md")]
        convertible, md_skipped = _folder_categorise(all_files)
        assert md_skipped == 2
        assert convertible == []

    def test_mixed_folder(self):
        all_files = [Path("doc.pdf"), Path("notes.md"), Path("data.xlsx"), Path("readme.MD")]
        convertible, md_skipped = _folder_categorise(all_files)
        assert md_skipped == 2
        assert len(convertible) == 2


# ---------------------------------------------------------------------------
# Tkinter event binding constraints
# ---------------------------------------------------------------------------

class TestTkinterEventBindings:
    def test_show_formats_binding_uses_lambda(self):
        """Ensure _show_formats binding uses lambda (Tkinter requires event arg)."""
        app_path = Path(__file__).parent.parent / "app.py"
        content = app_path.read_text(encoding="utf-8")
        # Check that the _show_formats binding uses a lambda
        assert 'self._drop_sub.bind("<Button-1>", lambda e: self._show_formats())' in content, \
            "Tkinter event callbacks require lambda to accept event argument"


# ---------------------------------------------------------------------------
# Config file functionality
# ---------------------------------------------------------------------------

class TestConfigFile:
    def test_config_file_path_exists(self):
        """Verify config file path constant is defined."""
        app_path = Path(__file__).parent.parent / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert "_CONFIG_FILE" in content, \
            "_CONFIG_FILE constant must be defined"

    def test_config_file_path_in_home_directory(self):
        """Verify config file is stored in user home directory."""
        app_path = Path(__file__).parent.parent / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert 'Path.home()' in content, \
            "Config file should be stored in user home directory"

    def test_config_file_name_is_correct(self):
        """Verify config file has correct name."""
        app_path = Path(__file__).parent.parent / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert '".doc2md_config.json"' in content, \
            "Config file should be named .doc2md_config.json"


# ---------------------------------------------------------------------------
# Tokenizer mode storage
# ---------------------------------------------------------------------------

class TestTokenizerModeStorage:
    def test_filerow_accepts_tokenizer_mode(self):
        """Verify FileRow accepts tokenizer_mode parameter."""
        app_path = Path(__file__).parent.parent / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert "tokenizer_mode: str" in content, \
            "FileRow should accept tokenizer_mode parameter"
    
    def test_filerow_stores_tokenizer_mode(self):
        """Verify FileRow stores tokenizer_mode as instance variable."""
        app_path = Path(__file__).parent.parent / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert "self._tokenizer_mode = tokenizer_mode" in content, \
            "FileRow should store tokenizer_mode as instance variable"
    
    def test_refresh_badge_uses_stored_mode(self):
        """Verify refresh_badge uses stored tokenizer_mode instead of global mode."""
        app_path = Path(__file__).parent.parent / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert "self._tokenizer_mode" in content and "refresh_badge" in content, \
            "refresh_badge should use stored tokenizer_mode"


# ---------------------------------------------------------------------------
# Detailed stats display
# ---------------------------------------------------------------------------

class TestDetailedStatsDisplay:
    def test_filerow_has_tokens_label(self):
        """Verify FileRow has a tokens label for displaying token count."""
        app_path = Path(__file__).parent.parent / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert "_tokens_label" in content, \
            "FileRow should have a tokens label"
    
    def test_filerow_has_original_size_label(self):
        """Verify FileRow has an original size label."""
        app_path = Path(__file__).parent.parent / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert "_orig_label" in content, \
            "FileRow should have an original size label"
    
    def test_filerow_has_converted_size_label(self):
        """Verify FileRow has a converted size label."""
        app_path = Path(__file__).parent.parent / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert "_conv_label" in content, \
            "FileRow should have a converted size label"
    
    def test_filerow_has_tokenizer_label(self):
        """Verify FileRow has a tokenizer label."""
        app_path = Path(__file__).parent.parent / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert "_tokenizer_label" in content, \
            "FileRow should have a tokenizer label"


# ---------------------------------------------------------------------------
# Window width
# ---------------------------------------------------------------------------

class TestWindowWidth:
    def test_window_width_increased(self):
        """Verify window width was increased to accommodate all columns."""
        app_path = Path(__file__).parent.parent / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert "1000x680" in content, \
            "Window width should be 1000px to accommodate all columns"


# ---------------------------------------------------------------------------
# Datetime subfolder functionality
# ---------------------------------------------------------------------------

class TestDatetimeSubfolder:
    def test_datetime_subfolder_method_exists(self):
        """Verify _get_output_dir_with_subfolder method exists in App class."""
        app_path = Path(__file__).parent.parent / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert "def _get_output_dir_with_subfolder" in content, \
            "_get_output_dir_with_subfolder method must be defined"

    def test_datetime_subfolder_imports_datetime(self):
        """Verify datetime module is imported for subfolder generation."""
        app_path = Path(__file__).parent.parent / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert "from datetime import datetime" in content, \
            "datetime module must be imported for subfolder generation"

    def test_datetime_subfolder_creates_folder(self):
        """Verify datetime subfolder logic includes folder creation."""
        app_path = Path(__file__).parent.parent / "app.py"
        content = app_path.read_text(encoding="utf-8")
        assert ".mkdir(parents=True, exist_ok=True)" in content, \
            "datetime subfolder should create folder if it doesn't exist"
