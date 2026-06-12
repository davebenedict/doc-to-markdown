"""
google_drive.py - Google Drive OAuth download helper.

Downloads a Google Doc/Sheet/Slide as HTML (or PDF for binary files)
using the Drive export API with OAuth 2.0 credentials.

Requires:
  - credentials.json  (OAuth client secret from Google Cloud Console)
  - token.json        (auto-created on first run via browser auth)
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"
TOKEN_FILE = Path(__file__).parent / "token.json"

# Maps Google MIME types to export format + file extension
_EXPORT_MAP = {
    "application/vnd.google-apps.document":     ("text/html", ".html"),
    "application/vnd.google-apps.spreadsheet":  ("text/csv", ".csv"),
    "application/vnd.google-apps.presentation": ("text/html", ".html"),
    "application/vnd.google-apps.drawing":      ("image/png", ".png"),
}

# Non-Google native files (regular Drive files) — download directly
_DIRECT_MIME_EXT = {
    "application/pdf":                                           ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/html":                                                 ".html",
    "text/plain":                                                ".txt",
}


def _get_creds():
    """Return valid OAuth credentials, refreshing or re-authorizing as needed."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            f"credentials.json not found at {CREDENTIALS_FILE}\n"
            "Download it from Google Cloud Console → APIs & Services → Credentials."
        )

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())

    return creds


def extract_file_id(url_or_id: str) -> str:
    """Extract a Drive file ID from a sharing URL or return the raw ID."""
    # Standard sharing URL: /d/{id}/ or /d/{id}/edit
    m = re.search(r"/d/([a-zA-Z0-9_-]{20,})", url_or_id)
    if m:
        return m.group(1)
    # open?id= style
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]{20,})", url_or_id)
    if m:
        return m.group(1)
    # Assume raw ID if it looks like one
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", url_or_id.strip()):
        return url_or_id.strip()
    raise ValueError(f"Could not extract a Google Drive file ID from: {url_or_id!r}")


def download(
    url_or_id: str,
    dest_dir: Path | None = None,
    progress_cb=None,
) -> Path:
    """
    Download a Google Drive file, exporting Google Docs formats as HTML.

    Returns the path to the downloaded temp file.
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    import io

    file_id = extract_file_id(url_or_id)

    if progress_cb:
        progress_cb("Authenticating with Google…")

    creds = _get_creds()
    service = build("drive", "v3", credentials=creds, cache_discovery=False)

    if progress_cb:
        progress_cb("Fetching file metadata…")

    meta = service.files().get(fileId=file_id, fields="name,mimeType").execute()
    name: str = meta["name"]
    mime: str = meta["mimeType"]

    out_dir = dest_dir or Path(tempfile.gettempdir())
    out_dir.mkdir(parents=True, exist_ok=True)

    if mime in _EXPORT_MAP:
        export_mime, ext = _EXPORT_MAP[mime]
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", name)
        dest = out_dir / (safe_name + ext)

        if progress_cb:
            progress_cb(f"Exporting '{name}' as {ext}…")

        data = service.files().export(fileId=file_id, mimeType=export_mime).execute()
        dest.write_bytes(data)

    elif mime in _DIRECT_MIME_EXT:
        ext = _DIRECT_MIME_EXT[mime]
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", name)
        dest = out_dir / (safe_name + ext)

        if progress_cb:
            progress_cb(f"Downloading '{name}'…")

        request = service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = dl.next_chunk()
        dest.write_bytes(buf.getvalue())

    else:
        raise ValueError(
            f"Unsupported Google Drive MIME type: {mime}\n"
            f"File: {name}"
        )

    return dest
