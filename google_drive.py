"""
google_drive.py - Browser-based Google Drive export helper.

Opens the Google Docs export URL in the user's default browser
(using their existing Google session — no API keys or credentials needed),
then watches the Downloads folder for the file to appear.
"""

from __future__ import annotations

import os
import re
import time
import webbrowser
from pathlib import Path

# How long to wait for the browser download to complete (seconds)
DOWNLOAD_TIMEOUT = 60
POLL_INTERVAL = 0.5

# Export URL templates per doc type (detected from URL pattern)
_EXPORT_URLS = {
    "document":     "https://docs.google.com/document/d/{id}/export?format=html",
    "spreadsheets": "https://docs.google.com/spreadsheets/d/{id}/export?format=csv",
    "presentation": "https://docs.google.com/presentation/d/{id}/export/html",
    "drawings":     "https://docs.google.com/drawings/d/{id}/export/png",
}

# Expected file extensions per doc type
_EXPORT_EXT = {
    "document":     ".html",
    "spreadsheets": ".csv",
    "presentation": ".html",
    "drawings":     ".png",
}

# Fallback: plain Drive file download
_DRIVE_DOWNLOAD_URL = "https://drive.google.com/uc?export=download&id={id}"


def _get_downloads_folder() -> Path:
    """Return the user's Downloads folder path."""
    return Path.home() / "Downloads"


def extract_file_id(url_or_id: str) -> tuple[str, str | None]:
    """
    Extract (file_id, doc_type) from a Google Drive/Docs URL.
    doc_type is one of: 'document', 'spreadsheets', 'presentation', 'drawings', or None.
    """
    # Folder URL — not exportable as a single file
    if re.search(r"drive\.google\.com/drive/folders/", url_or_id):
        raise ValueError(
            "That URL is a Google Drive folder, not a file.\n\n"
            "Open the folder in your browser, then open the individual document "
            "you want to convert and copy its URL (it will contain /document/d/ or /file/d/)."
        )

    # Google Docs/Sheets/Slides URL: /document/d/{id}, /spreadsheets/d/{id}, etc.
    m = re.search(r"google\.com/(document|spreadsheets|presentation|drawings)/d/([a-zA-Z0-9_-]{20,})", url_or_id)
    if m:
        return m.group(2), m.group(1)

    # Standard Drive file URL: drive.google.com/file/d/{id}
    m = re.search(r"/file/d/([a-zA-Z0-9_-]{20,})", url_or_id)
    if m:
        return m.group(1), None

    # Shorthand /d/{id} (older sharing links)
    m = re.search(r"(?<!/folders)/d/([a-zA-Z0-9_-]{20,})", url_or_id)
    if m:
        return m.group(1), None

    # open?id= style
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]{20,})", url_or_id)
    if m:
        return m.group(1), None

    # Raw ID
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", url_or_id.strip()):
        return url_or_id.strip(), None

    raise ValueError(
        f"Could not extract a Google Drive file ID from the URL.\n\n"
        f"Make sure you copy the URL of an individual file (Google Doc, Sheet, PDF, etc.), "
        f"not a folder."
    )


def _snapshot_downloads(downloads: Path) -> set[Path]:
    """Return the current set of files in the Downloads folder."""
    try:
        return set(downloads.iterdir())
    except Exception:
        return set()


def download(
    url_or_id: str,
    dest_dir: Path | None = None,
    progress_cb=None,
) -> Path:
    """
    Export a Google Drive document by opening the export URL in the browser.

    The user's existing browser session handles authentication automatically.
    Watches the Downloads folder for the new file, then moves it to dest_dir.

    Returns the path to the downloaded file.
    """
    file_id, doc_type = extract_file_id(url_or_id)

    if doc_type and doc_type in _EXPORT_URLS:
        export_url = _EXPORT_URLS[doc_type].format(id=file_id)
        expected_ext = _EXPORT_EXT[doc_type]
    else:
        export_url = _DRIVE_DOWNLOAD_URL.format(id=file_id)
        expected_ext = None

    downloads = _get_downloads_folder()
    before = _snapshot_downloads(downloads)

    if progress_cb:
        progress_cb("Opening export URL in browser — waiting for download…")

    webbrowser.open(export_url)

    # Poll for a new file to appear in Downloads
    deadline = time.time() + DOWNLOAD_TIMEOUT
    new_file: Path | None = None

    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        after = _snapshot_downloads(downloads)
        new_files = after - before

        # Filter out .crdownload / .tmp (still downloading)
        completed = {
            f for f in new_files
            if f.suffix.lower() not in {".crdownload", ".tmp", ".part"}
            and not f.name.startswith(".")
        }

        if completed:
            # If multiple new files somehow appeared, pick the most recently modified
            new_file = max(completed, key=lambda f: f.stat().st_mtime)
            break

        if progress_cb:
            remaining = int(deadline - time.time())
            progress_cb(f"Waiting for browser download… ({remaining}s remaining)")

    if new_file is None:
        raise TimeoutError(
            f"No new file appeared in {downloads} within {DOWNLOAD_TIMEOUT}s.\n"
            "Make sure you are logged into Google in your browser and the export URL opened correctly."
        )

    if progress_cb:
        progress_cb(f"Download detected: {new_file.name}")

    # Move to dest_dir if specified
    if dest_dir:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / new_file.name
        new_file.replace(dest)
        return dest

    return new_file
