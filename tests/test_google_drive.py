"""
Tests for google_drive.py — extract_file_id() URL parsing.
"""

from __future__ import annotations

import pytest

import google_drive as gdrive


# ---------------------------------------------------------------------------
# extract_file_id
# ---------------------------------------------------------------------------

class TestExtractFileId:
    # -- Google Docs URLs --
    def test_google_doc_url(self):
        url = "https://docs.google.com/document/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345/edit"
        file_id, doc_type = gdrive.extract_file_id(url)
        assert file_id == "1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345"
        assert doc_type == "document"

    def test_google_sheets_url(self):
        url = "https://docs.google.com/spreadsheets/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345/edit#gid=0"
        file_id, doc_type = gdrive.extract_file_id(url)
        assert file_id == "1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345"
        assert doc_type == "spreadsheets"

    def test_google_slides_url(self):
        url = "https://docs.google.com/presentation/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345/edit"
        file_id, doc_type = gdrive.extract_file_id(url)
        assert file_id == "1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345"
        assert doc_type == "presentation"

    def test_google_drawings_url(self):
        url = "https://docs.google.com/drawings/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345/edit"
        file_id, doc_type = gdrive.extract_file_id(url)
        assert file_id == "1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345"
        assert doc_type == "drawings"

    # -- Standard Drive file URLs --
    def test_drive_file_url(self):
        url = "https://drive.google.com/file/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345/view?usp=sharing"
        file_id, doc_type = gdrive.extract_file_id(url)
        assert file_id == "1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345"
        assert doc_type is None

    # -- open?id= style --
    def test_open_id_url(self):
        url = "https://drive.google.com/open?id=1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345"
        file_id, doc_type = gdrive.extract_file_id(url)
        assert file_id == "1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345"
        assert doc_type is None

    def test_open_id_with_extra_params(self):
        url = "https://drive.google.com/open?foo=bar&id=1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345&baz=1"
        file_id, _ = gdrive.extract_file_id(url)
        assert file_id == "1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345"

    # -- Raw ID --
    def test_raw_id(self):
        raw = "1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345"
        file_id, doc_type = gdrive.extract_file_id(raw)
        assert file_id == raw
        assert doc_type is None

    def test_raw_id_with_whitespace(self):
        raw = "  1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345  "
        file_id, _ = gdrive.extract_file_id(raw)
        assert file_id == raw.strip()

    # -- Folder URL (rejected) --
    def test_folder_url_raises(self):
        url = "https://drive.google.com/drive/folders/1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345"
        with pytest.raises(ValueError, match="folder"):
            gdrive.extract_file_id(url)

    # -- Invalid input --
    def test_garbage_raises(self):
        with pytest.raises(ValueError, match="Could not extract"):
            gdrive.extract_file_id("not-a-url-at-all")

    def test_short_id_raises(self):
        with pytest.raises(ValueError, match="Could not extract"):
            gdrive.extract_file_id("abc123")

    # -- Edge cases --
    def test_id_with_hyphens_and_underscores(self):
        raw = "abc-DEF_123-ghijklmnopqrst"
        file_id, _ = gdrive.extract_file_id(raw)
        assert file_id == raw

    def test_older_sharing_link_d_style(self):
        url = "https://drive.google.com/d/1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345/view"
        file_id, doc_type = gdrive.extract_file_id(url)
        assert file_id == "1aBcDeFgHiJkLmNoPqRsTuVwXyZ012345"
        assert doc_type is None


# ---------------------------------------------------------------------------
# Export URL mapping
# ---------------------------------------------------------------------------

class TestExportUrlMapping:
    def test_all_doc_types_have_export_url(self):
        for key in gdrive._EXPORT_EXT:
            assert key in gdrive._EXPORT_URLS

    def test_all_doc_types_have_ext(self):
        for key in gdrive._EXPORT_URLS:
            assert key in gdrive._EXPORT_EXT

    def test_export_url_contains_id_placeholder(self):
        for url_template in gdrive._EXPORT_URLS.values():
            assert "{id}" in url_template
