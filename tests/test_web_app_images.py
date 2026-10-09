import base64
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest


def _load_module(name, path):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


root_path = Path(__file__).resolve().parents[1]
root_converter = _load_module("doc2md_root_converter", root_path / "converter.py")
web_app = _load_module("doc2md_root_web_app", root_path / "web_app.py")
web_app.conv = root_converter


def test_browser_download_includes_markdown_and_extracted_images(tmp_path, monkeypatch):
    upload_dir = tmp_path / "upload"
    upload_dir.mkdir()
    monkeypatch.setattr(web_app.tempfile, "mkdtemp", lambda: str(upload_dir))
    monkeypatch.setitem(web_app.app.config, "TESTING", True)
    encoded_image = "R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
    html = (
        f'<p>Body text</p><img src="data:image/gif;base64,{encoded_image}" alt="Embedded diagram">'
    ).encode("utf-8")

    with web_app.app.test_client() as client:
        response = client.post(
            "/convert",
            data={"file": (BytesIO(html), "images.html")},
        )

    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    with ZipFile(BytesIO(response.data)) as archive:
        assert set(archive.namelist()) == {
            "images.html.md",
            "images.html_images/image_001.gif",
        }
        markdown = archive.read("images.html.md").decode("utf-8")
        assert "![Embedded diagram](images.html_images/image_001.gif)" in markdown
        assert encoded_image not in markdown
        assert archive.read("images.html_images/image_001.gif") == base64.b64decode(encoded_image)


def test_browser_download_preserves_scanned_pdf_page_without_ocr(tmp_path, monkeypatch):
    fitz = pytest.importorskip("fitz")
    upload_dir = tmp_path / "upload"
    upload_dir.mkdir()
    monkeypatch.setattr(web_app.tempfile, "mkdtemp", lambda: str(upload_dir))
    monkeypatch.setitem(web_app.app.config, "TESTING", True)
    document = fitz.open()
    text_page = document.new_page()
    text_page.insert_text((72, 72), "This searchable page has enough text to remain on the text extraction path.")
    scanned_page = document.new_page()
    scanned_page.insert_text((72, 72), "tiny")
    pdf_bytes = document.tobytes()
    document.close()
    monkeypatch.setattr(web_app.conv, "_ocr_image_bytes", lambda image_data: None)

    with web_app.app.test_client() as client:
        response = client.post(
            "/convert",
            data={"file": (BytesIO(pdf_bytes), "mixed.pdf")},
        )

    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    with ZipFile(BytesIO(response.data)) as archive:
        assert "mixed.pdf.md" in archive.namelist()
        assert "mixed.pdf_images/image_001.png" in archive.namelist()
        markdown = archive.read("mixed.pdf.md").decode("utf-8")
        assert "OCR text unavailable" in markdown
