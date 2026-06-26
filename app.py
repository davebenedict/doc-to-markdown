"""
app.py - Doc -> Markdown Converter
Native Windows desktop app using CustomTkinter + tkinterdnd2.

Usage:
    python app.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from tkinterdnd2 import DND_FILES, Tk as DnDTk

import converter as conv
import google_drive as gdrive

# Config file for remembering settings
_CONFIG_FILE = Path.home() / ".doc2md_config.json"

# ---------------------------------------------------------------------------
# App-level appearance defaults
# ---------------------------------------------------------------------------

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT = "#1f6aa5"
DROP_NORMAL_BG = "#2b2b2b"
DROP_HOVER_BG = "#1a3d5c"
FONT_TITLE = ("Segoe UI", 22, "bold")
FONT_LABEL = ("Segoe UI", 12)
FONT_SMALL = ("Segoe UI", 11)
FONT_MONO = ("Consolas", 11)

def _build_accepted_types():
    _IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}
    _SHEET_EXTS = {".xlsx", ".xls", ".csv"}
    _DOC_EXTS = {".pdf", ".docx", ".html", ".htm", ".pptx"}

    exts = conv.SUPPORTED_EXTENSIONS
    all_glob = " ".join(f"*{e}" for e in sorted(exts))
    doc_glob = " ".join(f"*{e}" for e in sorted(exts & _DOC_EXTS))
    sheet_glob = " ".join(f"*{e}" for e in sorted(exts & _SHEET_EXTS))
    img_glob = " ".join(f"*{e}" for e in sorted(exts & _IMAGE_EXTS))

    types = []
    if doc_glob:
        types.append(("Documents", doc_glob))
    if sheet_glob:
        types.append(("Spreadsheets", sheet_glob))
    if img_glob:
        types.append(("Images", img_glob))
    types.append(("All supported", all_glob))
    types.append(("All files", "*.*"))
    return types

ACCEPTED_TYPES = _build_accepted_types()


# ---------------------------------------------------------------------------
# FileRow widget — one converted file entry
# ---------------------------------------------------------------------------

def _badge_parts(pct: int | None, out_tokens: int) -> tuple[str, str, str]:
    """Return (text, fg_color, text_color) for a token savings badge."""
    if out_tokens == 0:
        return "⚠ empty output", "#6b4a00", "#f0a500"
    if pct is None:
        return "— tokens", "gray30", "gray60"
    if pct > 0:
        return f"↓{pct}% tokens", "#2d6a2d", "#7ec87e"
    if pct < 0:
        return f"↑{abs(pct)}% tokens", "#5a2d2d", "#e06c75"
    return "≈ same tokens", "gray30", "gray60"


class FileRow(ctk.CTkFrame):
    def __init__(self, master, md_path: Path, token_stats: dict | None = None, src_ext: str | None = None, **kwargs):
        super().__init__(master, corner_radius=6, **kwargs)
        self.md_path = md_path
        self._token_stats = token_stats

        self.configure(fg_color=("gray20", "gray20"))

        # Column layout with fixed widths
        # Column 0: Icon (30px)
        # Column 1: Filename (180px with wrap)
        # Column 2: Extension (45px)
        # Column 3: Badge (70px)
        # Column 4: Hint (120px, conditionally shown)
        # Column 5: Reveal button (60px)
        # Column 6: Open button (60px)

        # Configure grid weights
        self.grid_columnconfigure(0, weight=0, minsize=30)
        self.grid_columnconfigure(1, weight=0, minsize=180)
        self.grid_columnconfigure(2, weight=0, minsize=45)
        self.grid_columnconfigure(3, weight=0, minsize=70)
        self.grid_columnconfigure(4, weight=0, minsize=120)
        self.grid_columnconfigure(5, weight=0, minsize=60)
        self.grid_columnconfigure(6, weight=0, minsize=60)

        icon = ctk.CTkLabel(self, text="📄", font=("Segoe UI Emoji", 14))
        icon.grid(row=0, column=0, padx=(8, 4), pady=6, sticky="w")

        name = ctk.CTkLabel(
            self,
            text=md_path.name,
            font=FONT_SMALL,
            anchor="w",
            wraplength=170,
        )
        name.grid(row=0, column=1, padx=4, pady=6, sticky="w")

        if src_ext:
            ext_label = ctk.CTkLabel(
                self,
                text=src_ext.lstrip(".").upper(),
                font=("Segoe UI", 10),
                fg_color="gray30",
                text_color="gray65",
                corner_radius=4,
                padx=6,
            )
            ext_label.grid(row=0, column=2, padx=(0, 4), pady=6, sticky="w")
        else:
            # Placeholder to maintain grid structure
            ctk.CTkLabel(self, text="").grid(row=0, column=2, padx=(0, 4), pady=6)

        if token_stats:
            self._badge = ctk.CTkLabel(
                self,
                text="",
                font=("Segoe UI", 10),
                corner_radius=4,
                padx=6,
            )
            self._badge.grid(row=0, column=3, padx=(0, 6), pady=6, sticky="w")
            self._hint = ctk.CTkLabel(
                self,
                text="structure quality improved",
                font=("Segoe UI", 9),
                text_color="gray45",
                wraplength=110,
            )
            self._hint.grid(row=0, column=4, padx=(0, 6), pady=6, sticky="w")
            self.refresh_badge(use_tiktoken=token_stats.get("tiktoken_available", False))
        else:
            self._badge = None
            self._hint = None
            # Placeholders to maintain grid structure
            ctk.CTkLabel(self, text="").grid(row=0, column=3, padx=(0, 6), pady=6)
            ctk.CTkLabel(self, text="").grid(row=0, column=4, padx=(0, 6), pady=6)

        reveal_btn = ctk.CTkButton(
            self,
            text="Reveal",
            width=68,
            height=28,
            font=FONT_SMALL,
            fg_color="gray35",
            hover_color="gray45",
            command=self._reveal,
        )
        reveal_btn.grid(row=0, column=5, padx=(4, 4), pady=6)

        open_btn = ctk.CTkButton(
            self,
            text="Open",
            width=68,
            height=28,
            font=FONT_SMALL,
            command=self._open,
        )
        open_btn.grid(row=0, column=6, padx=(4, 8), pady=6)

    def refresh_badge(self, use_tiktoken: bool):
        if self._badge is None or self._token_stats is None:
            return
        stats = self._token_stats
        if use_tiktoken and stats.get("tiktoken_available"):
            pct = stats.get("tiktoken_pct")
            out_tok = stats.get("tiktoken_out", 1)
        else:
            pct = stats.get("fallback_pct")
            out_tok = stats.get("fallback_out", 1)
        text, fg, tc = _badge_parts(pct, out_tok)
        self._badge.configure(text=text, fg_color=fg, text_color=tc)
        if self._hint is not None:
            show_hint = (
                use_tiktoken
                and stats.get("tiktoken_available")
                and pct is not None
                and out_tok > 0
                and abs(pct) <= 10
            )
            if show_hint:
                self._hint.grid(row=0, column=4, padx=(0, 6), pady=6, sticky="w")
            else:
                self._hint.grid_forget()

    def _open(self):
        if sys.platform == "win32":
            os.startfile(str(self.md_path))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(self.md_path)])
        else:
            subprocess.run(["xdg-open", str(self.md_path)])

    def _reveal(self):
        if sys.platform == "win32":
            subprocess.run(["explorer", "/select,", str(self.md_path)])
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", str(self.md_path)])
        else:
            subprocess.run(["xdg-open", str(self.md_path.parent)])


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class App(DnDTk):
    def __init__(self):
        super().__init__()
        self.title("Doc \u2192 Markdown Converter")
        self.geometry("560x680")
        self.minsize(480, 560)
        self.configure(bg="#1a1a1a")

        # Apply CTk styling manually to the Tk root (TkinterDnD bypasses CTk root)
        ctk.set_appearance_mode("dark")

        self._output_dir: Path | None = None
        self._busy = False
        self._queue: list[Path] = []
        self._skipped_files: list[str] = []
        self._file_rows: list[FileRow] = []
        self._use_tiktoken_var = ctk.BooleanVar(value=conv.TIKTOKEN_AVAILABLE)

        self._build_ui()
        self._register_dnd()

        # Load remembered output directory after UI is built
        self._load_config()

        # Set minimum width to ensure FileRow buttons fit on screen
        # Set minimum height to ensure status bar is visible
        self.minsize(700, 780)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Title row
        title_row = ctk.CTkFrame(self, fg_color="transparent")
        title_row.pack(fill="x", padx=24, pady=(20, 4))

        title = ctk.CTkLabel(title_row, text="Doc \u2192 Markdown", font=FONT_TITLE)
        title.pack(side="left", expand=True)

        why_btn = ctk.CTkButton(
            title_row,
            text="? Why use this",
            width=110,
            height=24,
            font=("Segoe UI", 10),
            fg_color="gray25",
            hover_color="gray35",
            text_color="gray70",
            command=self._show_why,
        )
        why_btn.pack(side="right")

        subtitle = ctk.CTkLabel(
            self,
            text="Convert PDFs, Word docs, images & HTML to Markdown",
            font=FONT_SMALL,
            text_color="gray60",
        )
        subtitle.pack(pady=(0, 16))

        # Drop zone frame
        self._drop_frame = ctk.CTkFrame(
            self,
            corner_radius=12,
            border_width=2,
            border_color=ACCENT,
            fg_color=DROP_NORMAL_BG,
            height=130,
        )
        self._drop_frame.pack(fill="x", padx=24, pady=(0, 8))
        self._drop_frame.pack_propagate(False)

        self._drop_icon = ctk.CTkLabel(
            self._drop_frame, text="⬇", font=("Segoe UI Emoji", 32)
        )
        self._drop_icon.pack(pady=(18, 4))

        self._drop_label = ctk.CTkLabel(
            self._drop_frame,
            text="Drop files here  or  click to browse",
            font=FONT_LABEL,
            text_color="gray70",
        )
        self._drop_label.pack()

        self._drop_sub = ctk.CTkLabel(
            self._drop_frame,
            text="View supported formats ▾",
            font=FONT_SMALL,
            text_color="gray50",
            cursor="hand2",
        )
        self._drop_sub.pack(pady=(2, 0))
        # Lambda required: Tkinter event callbacks always receive an event argument
        self._drop_sub.bind("<Button-1>", lambda e: self._show_formats())

        # Make the drop zone clickable to browse
        for widget in (self._drop_frame, self._drop_icon, self._drop_label):
            widget.bind("<Button-1>", lambda e: self._browse_files())
            widget.bind("<Enter>", lambda e: self._drop_frame.configure(fg_color=DROP_HOVER_BG))
            widget.bind("<Leave>", lambda e: self._drop_frame.configure(fg_color=DROP_NORMAL_BG))

        # Folder row
        folder_row = ctk.CTkFrame(self, fg_color="transparent")
        folder_row.pack(fill="x", padx=24, pady=(6, 0))

        folder_btn = ctk.CTkButton(
            folder_row,
            text="Convert Folder…",
            width=130,
            height=28,
            font=FONT_SMALL,
            fg_color="gray35",
            hover_color="gray45",
            command=self._browse_folder,
        )
        folder_btn.pack(side="left")

        self._recurse_var = ctk.BooleanVar(value=False)
        recurse_chk = ctk.CTkCheckBox(
            folder_row,
            text="Include subfolders",
            variable=self._recurse_var,
            font=FONT_SMALL,
            height=28,
        )
        recurse_chk.pack(side="left", padx=(12, 0))

        # Output folder row
        out_row = ctk.CTkFrame(self, fg_color="transparent")
        out_row.pack(fill="x", padx=24, pady=(4, 0))

        out_label = ctk.CTkLabel(out_row, text="Output folder:", font=FONT_SMALL)
        out_label.pack(side="left")

        self._out_dir_label = ctk.CTkLabel(
            out_row,
            text="Same folder as input",
            font=FONT_SMALL,
            text_color="gray60",
            anchor="w",
        )
        self._out_dir_label.pack(side="left", fill="x", expand=True, padx=8)

        self._remember_out_dir_var = ctk.BooleanVar(value=False)
        remember_chk = ctk.CTkCheckBox(
            out_row,
            text="Remember",
            font=("Segoe UI", 10),
            variable=self._remember_out_dir_var,
            command=self._on_remember_change,
        )
        remember_chk.pack(side="right", padx=(0, 8))

        self._datetime_subfolder_var = ctk.BooleanVar(value=False)
        datetime_chk = ctk.CTkCheckBox(
            out_row,
            text="Date subfolder",
            font=("Segoe UI", 10),
            variable=self._datetime_subfolder_var,
            command=self._on_datetime_change,
        )
        datetime_chk.pack(side="right", padx=(0, 8))

        browse_btn = ctk.CTkButton(
            out_row,
            text="Browse",
            width=72,
            height=28,
            font=FONT_SMALL,
            fg_color="gray35",
            hover_color="gray45",
            command=self._browse_output,
        )
        browse_btn.pack(side="right", padx=(0, 12))

        clear_btn = ctk.CTkButton(
            out_row,
            text="Clear",
            width=56,
            height=28,
            font=FONT_SMALL,
            fg_color="gray25",
            hover_color="gray35",
            command=self._clear_output_dir,
        )
        clear_btn.pack(side="right", padx=(0, 4))

        # Google Drive section
        gdrive_sep = ctk.CTkFrame(self, height=1, fg_color="gray30")
        gdrive_sep.pack(fill="x", padx=24, pady=(12, 8))

        gdrive_header = ctk.CTkLabel(
            self, text="Google Drive", font=("Segoe UI", 13, "bold"), anchor="w"
        )
        gdrive_header.pack(fill="x", padx=24, pady=(0, 4))

        gdrive_row = ctk.CTkFrame(self, fg_color="transparent")
        gdrive_row.pack(fill="x", padx=24, pady=(0, 4))

        self._gdrive_entry = ctk.CTkEntry(
            gdrive_row,
            placeholder_text="Paste Google Drive sharing URL or file ID…",
            font=FONT_SMALL,
            height=32,
        )
        self._gdrive_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        gdrive_btn = ctk.CTkButton(
            gdrive_row,
            text="Convert",
            width=80,
            height=32,
            font=FONT_SMALL,
            command=self._on_gdrive_convert,
        )
        gdrive_btn.pack(side="right")

        gdrive_note = ctk.CTkLabel(
            self,
            text="Uses your existing browser session — no login or setup required.",
            font=("Segoe UI", 10),
            text_color="gray45",
            anchor="w",
        )
        gdrive_note.pack(fill="x", padx=24, pady=(0, 4))

        # Separator
        sep = ctk.CTkFrame(self, height=1, fg_color="gray30")
        sep.pack(fill="x", padx=24, pady=(8, 14))

        # Converted files section
        files_hdr_row = ctk.CTkFrame(self, fg_color="transparent")
        files_hdr_row.pack(fill="x", padx=24, pady=(0, 6))

        files_header = ctk.CTkLabel(files_hdr_row, text="Converted Files", font=("Segoe UI", 13, "bold"), anchor="w")
        files_header.pack(side="left")

        self._token_mode_btn = ctk.CTkSegmentedButton(
            files_hdr_row,
            values=["tiktoken", "file size"],
            command=self._on_token_mode_change,
            font=("Segoe UI", 10),
            width=160,
            height=24,
        )
        if conv.TIKTOKEN_AVAILABLE:
            self._token_mode_btn.set("tiktoken")
        else:
            self._token_mode_btn.set("file size")
            self._token_mode_btn.configure(state="disabled")
        self._token_mode_btn.pack(side="right")

        if not conv.TIKTOKEN_AVAILABLE:
            tiktoken_hint = ctk.CTkLabel(
                files_hdr_row,
                text="pip install tiktoken for exact counts",
                font=("Segoe UI", 9),
                text_color="#e5a000",
            )
            tiktoken_hint.pack(side="right", padx=(0, 8))

        # Scrollable file list
        self._file_list_frame = ctk.CTkScrollableFrame(
            self,
            corner_radius=8,
            fg_color="gray15",
            label_text="",
        )
        self._file_list_frame.pack(fill="both", expand=True, padx=24, pady=(0, 8))

        # Column headings row - inside scrollable frame for alignment
        col_header_frame = ctk.CTkFrame(self._file_list_frame, fg_color="gray15", corner_radius=8)
        col_header_frame.pack(fill="x", pady=(0, 4))

        # Configure grid weights to match FileRow
        col_header_frame.grid_columnconfigure(0, weight=0, minsize=30)
        col_header_frame.grid_columnconfigure(1, weight=0, minsize=180)
        col_header_frame.grid_columnconfigure(2, weight=0, minsize=45)
        col_header_frame.grid_columnconfigure(3, weight=0, minsize=70)
        col_header_frame.grid_columnconfigure(4, weight=0, minsize=120)
        col_header_frame.grid_columnconfigure(5, weight=0, minsize=60)
        col_header_frame.grid_columnconfigure(6, weight=0, minsize=60)

        # Header labels
        ctk.CTkLabel(col_header_frame, text="", font=("Segoe UI", 10, "bold"), text_color="gray50").grid(
            row=0, column=0, padx=(8, 4), pady=6, sticky="w"
        )
        ctk.CTkLabel(col_header_frame, text="Filename", font=("Segoe UI", 10, "bold"), text_color="gray50").grid(
            row=0, column=1, padx=4, pady=6, sticky="w"
        )
        ctk.CTkLabel(col_header_frame, text="Type", font=("Segoe UI", 10, "bold"), text_color="gray50").grid(
            row=0, column=2, padx=(0, 4), pady=6, sticky="w"
        )
        ctk.CTkLabel(col_header_frame, text="Tokens", font=("Segoe UI", 10, "bold"), text_color="gray50").grid(
            row=0, column=3, padx=(0, 6), pady=6, sticky="w"
        )
        ctk.CTkLabel(col_header_frame, text="Note", font=("Segoe UI", 10, "bold"), text_color="gray50").grid(
            row=0, column=4, padx=(0, 6), pady=6, sticky="w"
        )
        ctk.CTkLabel(col_header_frame, text="Reveal", font=("Segoe UI", 10, "bold"), text_color="gray50").grid(
            row=0, column=5, padx=(4, 4), pady=6, sticky="w"
        )
        ctk.CTkLabel(col_header_frame, text="Open", font=("Segoe UI", 10, "bold"), text_color="gray50").grid(
            row=0, column=6, padx=(4, 8), pady=6, sticky="w"
        )

        self._empty_label = ctk.CTkLabel(
            self._file_list_frame,
            text="No files converted yet.",
            font=FONT_SMALL,
            text_color="gray50",
        )
        self._empty_label.pack(pady=20)

        # Status bar
        self._status_var = ctk.StringVar(value="Ready")
        self._status_label = ctk.CTkLabel(
            self,
            textvariable=self._status_var,
            font=FONT_SMALL,
            text_color="gray60",
            anchor="w",
        )
        self._status_label.pack(fill="x", padx=28, pady=(0, 14))
        self._status_label.bind("<Button-1>", lambda e: self._on_status_click())

    # ------------------------------------------------------------------
    # Drag-and-drop registration
    # ------------------------------------------------------------------

    def _register_dnd(self):
        self._drop_frame.drop_target_register(DND_FILES)
        self._drop_frame.dnd_bind("<<Drop>>", self._on_drop)
        self._drop_frame.dnd_bind("<<DragEnter>>", lambda e: self._drop_frame.configure(fg_color=DROP_HOVER_BG))
        self._drop_frame.dnd_bind("<<DragLeave>>", lambda e: self._drop_frame.configure(fg_color=DROP_NORMAL_BG))

    # ------------------------------------------------------------------
    # Config management
    # ------------------------------------------------------------------

    def _load_config(self):
        """Load saved output directory from config file."""
        if _CONFIG_FILE.exists():
            try:
                with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    if config.get("remember_output_dir") and config.get("output_dir"):
                        self._output_dir = Path(config["output_dir"])
                        if self._output_dir.exists():
                            self._remember_out_dir_var.set(True)
                            # Update the label after UI is built
                            self.after(100, self._update_out_dir_label)
                        else:
                            # Saved directory doesn't exist, clear it
                            self._output_dir = None
                    if config.get("datetime_subfolder"):
                        self._datetime_subfolder_var.set(True)
            except (json.JSONDecodeError, KeyError, IOError):
                pass

    def _update_out_dir_label(self):
        """Update the output directory label after config is loaded."""
        if self._output_dir:
            display = str(self._output_dir)
            if len(display) > 45:
                display = "…" + display[-43:]
            self._out_dir_label.configure(text=display, text_color="gray80")

    def _get_output_dir_with_subfolder(self):
        """Get the output directory, optionally with a datetime subfolder."""
        if not self._output_dir:
            return None
        if not self._datetime_subfolder_var.get():
            return self._output_dir
        # Create datetime subfolder
        from datetime import datetime
        datetime_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        subfolder = self._output_dir / datetime_str
        subfolder.mkdir(parents=True, exist_ok=True)
        return subfolder

    def _save_config(self):
        """Save output directory to config file if checkbox is checked."""
        if self._remember_out_dir_var.get() and self._output_dir:
            config = {
                "remember_output_dir": True,
                "output_dir": str(self._output_dir),
                "datetime_subfolder": self._datetime_subfolder_var.get()
            }
            try:
                with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2)
            except IOError:
                pass
        elif _CONFIG_FILE.exists():
            # Remove config file if checkbox is unchecked
            try:
                _CONFIG_FILE.unlink()
            except IOError:
                pass

    def _on_remember_change(self):
        """Handle checkbox state change."""
        if self._remember_out_dir_var.get() and self._output_dir:
            self._save_config()
        elif not self._remember_out_dir_var.get() and _CONFIG_FILE.exists():
            try:
                _CONFIG_FILE.unlink()
            except IOError:
                pass

    def _on_datetime_change(self):
        """Handle datetime subfolder checkbox state change."""
        if self._remember_out_dir_var.get():
            self._save_config()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_drop(self, event):
        self._drop_frame.configure(fg_color=DROP_NORMAL_BG)
        raw = event.data.strip()
        # tkinterdnd2 returns space-separated paths; braces around paths with spaces
        paths = self._parse_dnd_paths(raw)

        files = []
        for p in paths:
            p = Path(p)
            if p.is_dir():
                self._confirm_and_queue_folder(p)
            else:
                files.append(p)

        if files:
            self._queue_batch(files)

    @staticmethod
    def _parse_dnd_paths(raw: str) -> list[str]:
        # Paths wrapped in {} for paths with spaces
        braced = re.findall(r"\{([^}]+)\}", raw)
        remainder = re.sub(r"\{[^}]+\}", "", raw).split()
        return braced + remainder

    def _browse_files(self):
        paths = filedialog.askopenfilenames(
            title="Select files to convert",
            filetypes=ACCEPTED_TYPES,
        )
        for p in paths:
            self._queue_conversion(Path(p))

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Select folder to convert")
        if folder:
            self._confirm_and_queue_folder(Path(folder))

    def _browse_output(self):
        d = filedialog.askdirectory(title="Select output folder")
        if d:
            self._output_dir = Path(d)
            # Truncate long paths for display
            display = str(self._output_dir)
            if len(display) > 45:
                display = "…" + display[-43:]
            self._out_dir_label.configure(text=display, text_color="gray80")
            # Save config if checkbox is checked
            if self._remember_out_dir_var.get():
                self._save_config()

    def _clear_output_dir(self):
        self._output_dir = None
        self._out_dir_label.configure(text="Same folder as input", text_color="gray60")

    def _on_gdrive_convert(self):
        url = self._gdrive_entry.get().strip()
        if not url:
            self._set_status("Paste a Google Drive URL or file ID first.", error=True)
            return
        threading.Thread(target=self._run_gdrive_conversion, args=(url,), daemon=True).start()

    def _run_gdrive_conversion(self, url: str):
        self._set_status("Opening export URL in browser…")
        self._drop_frame.configure(border_color="orange")
        try:
            downloaded = gdrive.download(url, dest_dir=self._output_dir, progress_cb=self._set_status)
            self._set_status(f"Downloaded — converting {downloaded.name}…")
            out_path, src_text = conv.convert(
                downloaded,
                output_dir=self._get_output_dir_with_subfolder() or downloaded.parent,
                progress_cb=self._set_status,
                return_text=True,
            )
            stats = conv.token_stats(src_text, out_path, src=downloaded)
            self.after(0, self._add_file_row, out_path, stats, downloaded.suffix.lower())
            self._set_status(f"Done — {out_path.name}")
        except TimeoutError as exc:
            self._set_status("Timed out waiting for download.", error=True)
            self.after(0, lambda: messagebox.showerror("Download timed out", str(exc)))
        except Exception as exc:
            self._set_status(f"Error: {exc}", error=True)
            self.after(0, lambda: messagebox.showerror("Google Drive conversion failed", str(exc)))
        finally:
            self.after(0, lambda: self._drop_frame.configure(border_color=ACCENT))

    # ------------------------------------------------------------------
    # Conversion pipeline
    # ------------------------------------------------------------------

    def _confirm_and_queue_folder(self, folder: Path):
        if self._output_dir is None:
            confirmed = messagebox.askyesno(
                "No output folder set",
                f"Converted files will be written into the source folder:\n\n"
                f"{folder}\n\n"
                f"This may create many .md files alongside your originals.\n\n"
                f"Set a separate output folder instead, or click Yes to continue.",
                icon="warning",
            )
            if not confirmed:
                return
        self._queue_folder(folder)

    def _queue_folder(self, folder: Path):
        threading.Thread(target=self._run_folder, args=(folder,), daemon=True).start()

    def _queue_conversion(self, src: Path):
        ext = src.suffix.lower()
        if ext not in conv.SUPPORTED_EXTENSIONS:
            self._set_status(f"Skipped: unsupported type '{ext}'", error=True)
            return
        if not src.exists():
            self._set_status(f"File not found: {src.name}", error=True)
            return

        self._queue_batch([src])

    def _queue_batch(self, files: list[Path]):
        """Queue files for sequential conversion on a single background thread."""
        valid = []
        skipped: list[str] = []
        for src in files:
            ext = src.suffix.lower()
            if ext == ".md":
                skipped.append(f"{src.name}  (already Markdown)")
                continue
            if ext not in conv.SUPPORTED_EXTENSIONS:
                skipped.append(f"{src.name}  (unsupported type '{ext}')")
                continue
            if not src.exists():
                self._set_status(f"File not found: {src.name}", error=True)
                continue
            valid.append(src)

        if skipped:
            self._skipped_files = skipped
            noun = "file" if len(skipped) == 1 else "files"
            self._set_status(
                f"Skipped {len(skipped)} {noun} — click for details.",
                error=True,
            )

        if not valid:
            return

        if self._busy:
            self._queue.extend(valid)
            self._set_status(f"Queued {len(valid)} file(s) — conversion in progress…")
            return

        self._busy = True
        threading.Thread(target=self._run_batch, args=(valid, skipped), daemon=True).start()

    def _run_batch(self, files: list[Path], skipped: list[str] | None = None):
        ok, failed = 0, 0
        processed = 0
        details: list[str] = list(skipped) if skipped else []
        seen_hints: set[str] = set()
        try:
            self._drop_frame.configure(border_color="orange")

            # Get output directory (with datetime subfolder if enabled) once for all files
            output_dir = self._get_output_dir_with_subfolder()

            while files:
                for i, src in enumerate(files, 1):
                    processed += 1
                    self._set_status(f"[{processed}/{processed + len(self._queue)}] Converting {src.name}…" if len(files) > 1 or self._queue else f"Converting {src.name}…")
                    try:
                        out_path, src_text = conv.convert(
                            src,
                            output_dir=output_dir,
                            progress_cb=self._set_status,
                            return_text=True,
                        )
                        stats = conv.token_stats(src_text, out_path, src=src)
                        self.after(0, self._add_file_row, out_path, stats, src.suffix.lower())
                        ok += 1
                    except ImportError as exc:
                        pkg = conv.MISSING_DEPS.get(src.suffix.lower(), str(exc))
                        hint = f"missing library — pip install {pkg}"
                        if hint not in seen_hints:
                            details.append(f"{src.suffix.lower()} files  ({hint})")
                            seen_hints.add(hint)
                        failed += 1
                    except Exception as exc:
                        details.append(f"{src.name}  (error: {exc})")
                        failed += 1

                # Drain any files queued while we were working
                files = list(self._queue)
                self._queue.clear()

            if details:
                self._skipped_files = details
            n_details = len(details)
            if processed == 1 and not n_details:
                if ok:
                    self._set_status("Done — conversion complete")
            else:
                summary = f"Done — {ok} converted"
                if failed:
                    summary += f", {failed} failed"
                if skipped:
                    summary += f", {len(skipped)} skipped"
                if n_details:
                    summary += " — click for details."
                self._set_status(summary, error=bool(failed or skipped))
        finally:
            self._busy = False
            self.after(0, lambda: self._drop_frame.configure(border_color=ACCENT))

    def _run_folder(self, folder: Path):
        recurse = self._recurse_var.get()
        pattern = "**/*" if recurse else "*"
        all_files = [f for f in folder.glob(pattern) if f.is_file()]
        files = [f for f in all_files if f.suffix.lower() in conv.SUPPORTED_EXTENSIONS]

        skipped: list[str] = []
        for f in all_files:
            ext = f.suffix.lower()
            if ext == ".md":
                skipped.append(f"{f.name}  (already Markdown)")
            elif ext not in conv.SUPPORTED_EXTENSIONS:
                skipped.append(f"{f.name}  (unsupported type '{ext}')")

        if skipped:
            self._skipped_files = skipped

        if not files:
            noun = "file" if len(skipped) == 1 else "files"
            msg = f"No supported files found in {folder.name}"
            if skipped:
                msg += f" — {len(skipped)} {noun} skipped, click for details."
            self._set_status(msg, error=True)
            return

        self._set_status(f"Found {len(files)} file(s) in {folder.name} — converting…")
        self._drop_frame.configure(border_color="orange")

        # Get output directory (with datetime subfolder if enabled) once for all files
        output_dir = self._get_output_dir_with_subfolder()

        ok, failed = 0, 0
        errors: list[str] = []
        seen_hints: set[str] = set()
        for i, src in enumerate(files, 1):
            self._set_status(f"[{i}/{len(files)}] {src.name}…")
            try:
                out_path, src_text = conv.convert(src, output_dir=output_dir, progress_cb=self._set_status, return_text=True)
                stats = conv.token_stats(src_text, out_path, src=src)
                self.after(0, self._add_file_row, out_path, stats, src.suffix.lower())
                ok += 1
            except ImportError as exc:
                pkg = conv.MISSING_DEPS.get(src.suffix.lower(), str(exc))
                hint = f"missing library — pip install {pkg}"
                if hint not in seen_hints:
                    errors.append(f"{src.suffix.lower()} files  ({hint})")
                    seen_hints.add(hint)
                failed += 1
            except Exception as exc:
                errors.append(f"{src.name}  (error: {exc})")
                failed += 1

        details = skipped + errors
        if details:
            self._skipped_files = details
        self.after(0, lambda: self._drop_frame.configure(border_color=ACCENT))
        summary = f"Folder done — {ok} converted"
        if failed:
            summary += f", {failed} failed"
        if skipped:
            summary += f", {len(skipped)} skipped"
        if details:
            summary += " — click for details."
        self._set_status(summary, error=bool(failed or skipped))


    # ------------------------------------------------------------------
    # UI update helpers (always called on main thread via after())
    # ------------------------------------------------------------------

    def _add_file_row(self, md_path: Path, token_stats: dict | None = None, src_ext: str | None = None):
        # Remove the "no files" placeholder if present
        if self._empty_label.winfo_exists():
            try:
                self._empty_label.destroy()
            except Exception:
                pass

        use_tiktoken = self._use_tiktoken_var.get()
        row = FileRow(self._file_list_frame, md_path, token_stats=token_stats, src_ext=src_ext)
        row.refresh_badge(use_tiktoken=use_tiktoken)
        row.pack(fill="x", pady=(0, 4))
        self._file_rows.append(row)

    def _show_formats(self):
        def _fmt(label: str, exts: list[str], note: str) -> str:
            missing = set(conv.MISSING_DEPS.get(e) for e in exts if e in conv.MISSING_DEPS)
            suffix = f"  ⚠ pip install {', '.join(sorted(missing))}" if missing else ""
            return f"  {label:<14}{note}{suffix}"

        lines = [
            "Significant token savings (40–80%+) + smaller file size",
            "  These formats carry heavy markup, tags, or binary overhead",
            "  stripped on conversion — often 50–200x smaller as a file.",
            "  Helps with platform upload limits (Claude 30MB, etc.).",
            "",
            _fmt("HTML / HTM",   [".html", ".htm"],       "— tags, scripts, nav menus stripped"),
            _fmt("EPUB",         [".epub"],                "— XML/CSS/nav boilerplate stripped"),
            _fmt("XML",          [".xml"],                 "— all markup removed, text preserved"),
            _fmt("RTF",          [".rtf"],                 "— control words and formatting stripped"),
            _fmt("XLSX / XLS",   [".xlsx", ".xls"],        "— cell structure compressed to tables"),
            _fmt("PPTX",         [".pptx"],                "— slide layout markup removed"),
            _fmt("CSV",          [".csv"],                 "— reformatted as clean markdown table"),
            "",
            "─" * 52,
            "",
            "Structural quality improvement (tokens similar)",
            "  Token count stays about the same, but LLM accuracy improves.",
            "",
            _fmt("PDF",          [".pdf"],                 "— text extracted, layout noise removed"),
            _fmt("DOCX",         [".docx"],                "— heading hierarchy and tables preserved"),
            _fmt("ODT",          [".odt"],                 "— headings and paragraphs preserved"),
            _fmt("JSON",         [".json"],                "— pretty-printed as fenced code block"),
            "",
            "─" * 52,
            "",
            "Image / OCR (savings depend on image content)",
            "",
            _fmt("JPG/PNG/TIFF", [".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"],
                                 "— Tesseract OCR extracts text from images"),
        ]
        missing_pkgs = sorted(set(conv.MISSING_DEPS.values()))
        if missing_pkgs:
            lines += [
                "",
                "─" * 52,
                "",
                "⚠  Missing libraries detected. Install with:",
                f"   pip install {' '.join(missing_pkgs)}",
            ]
        messagebox.showinfo("Supported Formats", "\n".join(lines))

    def _show_why(self):
        msg = (
            "Why convert to Markdown even when token counts look similar?\n"
            "\n"
            "✓  Better LLM comprehension\n"
            "    LLMs parse Markdown structure natively. A PDF table becomes\n"
            "    garbled prose after extraction; the same table as | col | col |\n"
            "    is unambiguous. The model reasons better on clean structure.\n"
            "\n"
            "✓  Dramatically better RAG chunking\n"
            "    RAG pipelines split documents into chunks. PDFs split\n"
            "    arbitrarily — mid-sentence or mid-table. Markdown splits\n"
            "    cleanly on ## headings, giving higher-quality retrieval\n"
            "    and fewer hallucinations.\n"
            "\n"
            "✓  You control what the LLM sees\n"
            "    Every tool re-extracts PDFs differently. The Markdown is a\n"
            "    canonical, inspectable version you can review and correct\n"
            "    before it reaches the model.\n"
            "\n"
            "✓  Real token savings for HTML, Excel, and PPTX\n"
            "    Stripping HTML tags, layout markup, and slide structure\n"
            "    typically saves 40–80% of tokens for those formats.\n"
            "\n"
            "✓  Portable and reusable\n"
            "    One Markdown file works in NotebookLM, ChatGPT, Claude,\n"
            "    LangChain, LlamaIndex — no re-extraction on each use.\n"
            "\n"
            "✓  Bypass file size limits\n"
            "    A 50MB PDF may contain 48MB of fonts, images, and binary\n"
            "    encoding — the actual text is often under 1MB. The markdown\n"
            "    version can be 50–200x smaller as a file, letting you upload\n"
            "    documents that would otherwise hit platform limits:\n"
            "      NotebookLM  25M token cap across all sources\n"
            "      Claude      30MB per file\n"
            "      ChatGPT     512MB per file (images bloat PDFs fast)\n"
            "      Self-hosted RAG stacks often cap at 10–20MB per file"
        )
        messagebox.showinfo("Why convert to Markdown?", msg)

    def _on_token_mode_change(self, value: str):
        use_tiktoken = (value == "tiktoken")
        self._use_tiktoken_var.set(use_tiktoken)
        for row in self._file_rows:
            row.refresh_badge(use_tiktoken=use_tiktoken)

    def _on_status_click(self):
        if not self._skipped_files:
            return
        detail = "\n".join(f"  • {f}" for f in self._skipped_files)
        messagebox.showinfo(
            f"Skipped files ({len(self._skipped_files)})",
            detail,
        )

    def _set_status(self, msg: str, error: bool = False):
        color = "#e06c75" if error else "gray60"
        self.after(0, lambda: self._status_var.set(msg))
        self.after(0, lambda: self._status_label.configure(text_color=color))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()
