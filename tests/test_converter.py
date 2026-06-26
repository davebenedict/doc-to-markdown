"""
Tests for converter.py
"""

from __future__ import annotations

import csv
import textwrap
from pathlib import Path
from unittest import mock

import pytest

import converter as conv

try:
    import markdownify as _markdownify
    HAS_MARKDOWNIFY = True
except ImportError:
    HAS_MARKDOWNIFY = False

try:
    import fitz as _fitz
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

skip_no_markdownify = pytest.mark.skipif(not HAS_MARKDOWNIFY, reason="markdownify not installed")
skip_no_fitz = pytest.mark.skipif(not HAS_FITZ, reason="PyMuPDF (fitz) not installed")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_output(tmp_path):
    """Return a clean temp directory for converter output."""
    return tmp_path / "output"


# ---------------------------------------------------------------------------
# SUPPORTED_EXTENSIONS
# ---------------------------------------------------------------------------

class TestSupportedExtensions:
    def test_contains_core_formats(self):
        for ext in (".pdf", ".docx", ".html", ".htm", ".csv", ".xlsx", ".pptx"):
            assert ext in conv.SUPPORTED_EXTENSIONS

    def test_contains_image_formats(self):
        for ext in (".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"):
            assert ext in conv.SUPPORTED_EXTENSIONS

    def test_doc_not_supported(self):
        assert ".doc" not in conv.SUPPORTED_EXTENSIONS


# ---------------------------------------------------------------------------
# convert() — routing, output path, and error handling
# ---------------------------------------------------------------------------

@skip_no_markdownify
class TestConvertRouting:
    def test_unsupported_extension_raises(self, tmp_path):
        bad = tmp_path / "file.xyz"
        bad.write_text("data")
        with pytest.raises(ValueError, match="Unsupported file type"):
            conv.convert(bad)

    def test_output_dir_created(self, tmp_path, tmp_output):
        html = tmp_path / "simple.html"
        html.write_text("<p>hello</p>", encoding="utf-8")
        result = conv.convert(html, output_dir=tmp_output)
        assert result.parent == tmp_output.resolve()
        assert result.exists()

    def test_default_output_same_as_input(self, tmp_path):
        html = tmp_path / "doc.html"
        html.write_text("<b>bold</b>", encoding="utf-8")
        result = conv.convert(html)
        assert result.parent == tmp_path.resolve()

    def test_no_overwrite_existing_md(self, tmp_path):
        html = tmp_path / "report.html"
        html.write_text("<p>v1</p>", encoding="utf-8")
        # Create pre-existing .md
        (tmp_path / "report.md").write_text("old", encoding="utf-8")
        result = conv.convert(html)
        assert result.name == "report_1.md"
        # Original untouched
        assert (tmp_path / "report.md").read_text() == "old"

    def test_no_overwrite_increments(self, tmp_path):
        html = tmp_path / "report.html"
        html.write_text("<p>v3</p>", encoding="utf-8")
        (tmp_path / "report.md").write_text("old", encoding="utf-8")
        (tmp_path / "report_1.md").write_text("old1", encoding="utf-8")
        result = conv.convert(html)
        assert result.name == "report_2.md"

    def test_progress_cb_called(self, tmp_path):
        html = tmp_path / "cb.html"
        html.write_text("<p>test</p>", encoding="utf-8")
        messages = []
        conv.convert(html, progress_cb=messages.append)
        assert any("Done" in m for m in messages)

    def test_excessive_blank_lines_collapsed(self, tmp_path):
        html = tmp_path / "blanks.html"
        html.write_text("<p>a</p><br><br><br><br><p>b</p>", encoding="utf-8")
        result = conv.convert(html)
        content = result.read_text(encoding="utf-8")
        assert "\n\n\n" not in content


# ---------------------------------------------------------------------------
# _rows_to_md (used by CSV and Excel converters)
# ---------------------------------------------------------------------------

class TestRowsToMd:
    def test_empty_rows(self):
        assert conv._rows_to_md([]) == ""

    def test_single_row(self):
        result = conv._rows_to_md([["A", "B"]])
        assert "| A | B |" in result
        assert "| --- | --- |" in result

    def test_multiple_rows(self):
        result = conv._rows_to_md([["H1", "H2"], ["a", "b"], ["c", "d"]])
        lines = result.strip().split("\n")
        assert len(lines) == 4  # header + separator + 2 data rows

    def test_pipe_escaped(self):
        result = conv._rows_to_md([["a|b"]])
        assert "a\\|b" in result

    def test_newline_replaced(self):
        result = conv._rows_to_md([["line1\nline2"]])
        assert "\n" not in result.split("\n")[0].replace("\n", "")  # no literal newline in cell
        assert "line1 line2" in result

    def test_none_cell(self):
        result = conv._rows_to_md([[None, "val"]])
        assert "|  | val |" in result


# ---------------------------------------------------------------------------
# CSV conversion
# ---------------------------------------------------------------------------

class TestCsvConversion:
    def test_basic_csv(self, tmp_path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("Name,Age\nAlice,30\nBob,25", encoding="utf-8")
        result = conv.convert(csv_file)
        content = result.read_text(encoding="utf-8")
        assert "| Name | Age |" in content
        assert "| Alice | 30 |" in content

    def test_empty_csv(self, tmp_path):
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("", encoding="utf-8")
        result = conv.convert(csv_file)
        content = result.read_text(encoding="utf-8")
        assert content.strip() == ""


# ---------------------------------------------------------------------------
# HTML conversion
# ---------------------------------------------------------------------------

@skip_no_markdownify
class TestHtmlConversion:
    def test_basic_html(self, tmp_path):
        html = tmp_path / "page.html"
        html.write_text("<h1>Title</h1><p>Body text</p>", encoding="utf-8")
        result = conv.convert(html)
        content = result.read_text(encoding="utf-8")
        assert "Title" in content
        assert "Body text" in content

    def test_heading_style_atx(self, tmp_path):
        html = tmp_path / "headings.html"
        html.write_text("<h1>H1</h1><h2>H2</h2>", encoding="utf-8")
        result = conv.convert(html)
        content = result.read_text(encoding="utf-8")
        assert "# H1" in content
        assert "## H2" in content

    def test_htm_extension(self, tmp_path):
        htm = tmp_path / "page.htm"
        htm.write_text("<p>works</p>", encoding="utf-8")
        result = conv.convert(htm)
        assert result.exists()
        assert "works" in result.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# _inline_runs (DOCX helper)
# ---------------------------------------------------------------------------

class TestInlineRuns:
    @staticmethod
    def _make_run(text, bold=False, italic=False):
        run = mock.MagicMock()
        run.text = text
        run.bold = bold
        run.italic = italic
        return run

    def test_plain_text(self):
        para = mock.MagicMock()
        para.runs = [self._make_run("hello")]
        assert conv._inline_runs(para) == "hello"

    def test_bold(self):
        para = mock.MagicMock()
        para.runs = [self._make_run("strong", bold=True)]
        assert conv._inline_runs(para) == "**strong**"

    def test_italic(self):
        para = mock.MagicMock()
        para.runs = [self._make_run("emphasis", italic=True)]
        assert conv._inline_runs(para) == "*emphasis*"

    def test_bold_italic(self):
        para = mock.MagicMock()
        para.runs = [self._make_run("both", bold=True, italic=True)]
        assert conv._inline_runs(para) == "***both***"

    def test_mixed_runs(self):
        para = mock.MagicMock()
        para.runs = [
            self._make_run("normal "),
            self._make_run("bold", bold=True),
            self._make_run(" end"),
        ]
        assert conv._inline_runs(para) == "normal **bold** end"

    def test_empty_run_skipped(self):
        para = mock.MagicMock()
        para.runs = [self._make_run(""), self._make_run("visible")]
        assert conv._inline_runs(para) == "visible"


# ---------------------------------------------------------------------------
# token_stats
# ---------------------------------------------------------------------------

class TestTokenStats:
    def test_reduction(self, tmp_path):
        src_text = "word " * 400              # ~400 tokens (tiktoken) or 2000 chars
        out = tmp_path / "small.md"
        out.write_text("a" * 4, encoding="utf-8")  # tiny output
        stats = conv.token_stats(src_text, out)
        assert stats["src_tokens"] > 0
        assert stats["out_tokens"] < stats["src_tokens"]
        assert stats["savings_pct"] > 0

    def test_increase(self, tmp_path):
        src_text = "hello"                     # very short source (~1 token)
        out = tmp_path / "big.md"
        out.write_text("word " * 400, encoding="utf-8")  # large output (~400 tokens)
        stats = conv.token_stats(src_text, out)
        assert stats["savings_pct"] is not None
        assert stats["savings_pct"] < 0

    def test_zero_src_text(self, tmp_path):
        out = tmp_path / "out.md"
        out.write_text("hello", encoding="utf-8")
        stats = conv.token_stats("", out)
        assert stats["savings_pct"] is None

    def test_empty_output_zero_tokens(self, tmp_path):
        out = tmp_path / "out.md"
        out.write_text("", encoding="utf-8")    # empty output
        stats = conv.token_stats("some source text here", out)
        assert stats["out_tokens"] == 0
        assert stats["savings_pct"] == 100

    def test_keys_present(self, tmp_path):
        out = tmp_path / "f.md"
        out.write_text("y" * 100, encoding="utf-8")
        stats = conv.token_stats("x" * 100, out)
        required = {
            "tiktoken_available",
            "tiktoken_src", "tiktoken_out", "tiktoken_pct",
            "fallback_src", "fallback_out", "fallback_pct", "fallback_method",
            "src_tokens", "out_tokens", "savings_pct", "method",
        }
        assert required == set(stats.keys())

    def test_method_key_is_string(self, tmp_path):
        out = tmp_path / "f.md"
        out.write_text("hello", encoding="utf-8")
        stats = conv.token_stats("hello world", out)
        assert isinstance(stats["method"], str)
        assert stats["method"] in ("tiktoken cl100k_base", "chars÷4")


# ---------------------------------------------------------------------------
# _require helper
# ---------------------------------------------------------------------------

class TestRequire:
    def test_existing_module(self):
        mod = conv._require("os")
        assert hasattr(mod, "path")

    def test_missing_module_raises(self):
        with pytest.raises(ImportError, match="not installed"):
            conv._require("nonexistent_package_xyz_12345")

    @skip_no_fitz
    def test_import_name_override(self):
        mod = conv._require("PyMuPDF", "fitz")
        assert mod is not None
