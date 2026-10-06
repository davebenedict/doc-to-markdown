from pathlib import Path
from unittest.mock import Mock
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / 'python'))

import google_drive as gd
from web_app import app

FILE_ID = "1Abcdefghijklmnopqrstuvwx"
DOC_URL = f"https://docs.google.com/document/d/{FILE_ID}/edit"


@pytest.fixture
def client():
    with app.test_client() as client:
        yield client


class TestGoogleDriveExtraction:
    @pytest.mark.parametrize(
        ("url", "expected_type"),
        [
            (DOC_URL, "document"),
            (f"https://docs.google.com/spreadsheets/d/{FILE_ID}/edit", "spreadsheets"),
            (f"https://drive.google.com/file/d/{FILE_ID}/view", None),
        ],
    )
    def test_extract_file_id_from_url(self, url, expected_type):
        assert gd.extract_file_id(url) == (FILE_ID, expected_type)

    def test_extract_file_id_from_raw_id(self):
        assert gd.extract_file_id(FILE_ID) == (FILE_ID, None)

    def test_invalid_url_raises(self):
        with pytest.raises(ValueError, match="Could not extract"):
            gd.extract_file_id("https://example.com/file")

    def test_folder_url_raises(self):
        with pytest.raises(ValueError, match="folder"):
            gd.extract_file_id("https://drive.google.com/drive/folders/abc")


class TestGoogleDriveDownload:
    def test_download_opens_export_url(self, monkeypatch, tmp_path):
        open_browser = Mock()
        monkeypatch.setattr(gd.webbrowser, "open", open_browser)
        monkeypatch.setattr(gd, "_get_downloads_folder", lambda: tmp_path)
        monkeypatch.setattr(gd, "_snapshot_downloads", lambda _: set())
        monkeypatch.setattr(gd, "DOWNLOAD_TIMEOUT", -1)

        with pytest.raises(TimeoutError):
            gd.download(DOC_URL, tmp_path)

        open_browser.assert_called_once_with(
            f"https://docs.google.com/document/d/{FILE_ID}/export?format=html"
        )


class TestGoogleDriveIntegration:
    def test_gdrive_endpoint_requires_url(self, client):
        response = client.post('/convert-gdrive', json={})
        assert response.status_code == 400
        assert 'error' in response.get_json()

    def test_gdrive_endpoint_calls_downloader(self, client, monkeypatch):
        download = Mock(side_effect=TimeoutError("test download timeout"))
        monkeypatch.setattr(gd, "download", download)

        response = client.post('/convert-gdrive', json={'url': DOC_URL})

        assert response.status_code == 500
        download.assert_called_once()
        assert download.call_args.args[0] == DOC_URL
