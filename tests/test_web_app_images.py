import base64
from io import BytesIO
from zipfile import ZipFile

import web_app


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
