"""
app.py - Doc -> Markdown Converter
Native Windows desktop app using CustomTkinter + tkinterdnd2.

Usage:
    python app.py
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from tkinterdnd2 import DND_FILES, Tk as DnDTk

import converter as conv
import google_drive as gdrive

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

ACCEPTED_TYPES = [
    ("Documents", "*.pdf *.docx *.html *.htm"),
    ("Images", "*.jpg *.jpeg *.png *.tiff *.tif *.bmp"),
    ("All supported", "*.pdf *.docx *.html *.htm *.jpg *.jpeg *.png *.tiff *.tif *.bmp"),
    ("All files", "*.*"),
]


# ---------------------------------------------------------------------------
# FileRow widget — one converted file entry
# ---------------------------------------------------------------------------

class FileRow(ctk.CTkFrame):
    def __init__(self, master, md_path: Path, **kwargs):
        super().__init__(master, corner_radius=6, **kwargs)
        self.md_path = md_path

        self.configure(fg_color=("gray20", "gray20"))

        icon = ctk.CTkLabel(self, text="📄", font=("Segoe UI Emoji", 14), width=28)
        icon.pack(side="left", padx=(8, 4), pady=6)

        name = ctk.CTkLabel(
            self,
            text=md_path.name,
            font=FONT_SMALL,
            anchor="w",
            wraplength=280,
        )
        name.pack(side="left", fill="x", expand=True, padx=4, pady=6)

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
        reveal_btn.pack(side="right", padx=(4, 8), pady=6)

        open_btn = ctk.CTkButton(
            self,
            text="Open",
            width=68,
            height=28,
            font=FONT_SMALL,
            command=self._open,
        )
        open_btn.pack(side="right", padx=4, pady=6)

    def _open(self):
        os.startfile(str(self.md_path))

    def _reveal(self):
        subprocess.run(["explorer", "/select,", str(self.md_path)])


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

        self._build_ui()
        self._register_dnd()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Title
        title = ctk.CTkLabel(self, text="Doc \u2192 Markdown", font=FONT_TITLE)
        title.pack(pady=(20, 4))

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
            text="PDF · DOCX · JPG · PNG · TIFF · HTML",
            font=FONT_SMALL,
            text_color="gray50",
        )
        self._drop_sub.pack(pady=(2, 0))

        # Make the drop zone clickable to browse
        for widget in (self._drop_frame, self._drop_icon, self._drop_label, self._drop_sub):
            widget.bind("<Button-1>", lambda e: self._browse_files())
            widget.bind("<Enter>", lambda e: self._drop_frame.configure(fg_color=DROP_HOVER_BG))
            widget.bind("<Leave>", lambda e: self._drop_frame.configure(fg_color=DROP_NORMAL_BG))

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
        browse_btn.pack(side="right")

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
            text="Requires credentials.json — see README for setup instructions.",
            font=("Segoe UI", 10),
            text_color="gray45",
            anchor="w",
        )
        gdrive_note.pack(fill="x", padx=24, pady=(0, 4))

        # Separator
        sep = ctk.CTkFrame(self, height=1, fg_color="gray30")
        sep.pack(fill="x", padx=24, pady=(8, 14))

        # Converted files section
        files_header = ctk.CTkLabel(self, text="Converted Files", font=("Segoe UI", 13, "bold"), anchor="w")
        files_header.pack(fill="x", padx=24, pady=(0, 6))

        # Scrollable file list
        self._file_list_frame = ctk.CTkScrollableFrame(
            self,
            corner_radius=8,
            fg_color="gray15",
            label_text="",
        )
        self._file_list_frame.pack(fill="both", expand=True, padx=24, pady=(0, 8))

        self._empty_label = ctk.CTkLabel(
            self._file_list_frame,
            text="No files converted yet.",
            font=FONT_SMALL,
            text_color="gray50",
        )
        self._empty_label.pack(pady=20)

        # Status bar
        self._status_var = ctk.StringVar(value="Ready")
        status_bar = ctk.CTkLabel(
            self,
            textvariable=self._status_var,
            font=FONT_SMALL,
            text_color="gray60",
            anchor="w",
        )
        status_bar.pack(fill="x", padx=28, pady=(0, 14))

    # ------------------------------------------------------------------
    # Drag-and-drop registration
    # ------------------------------------------------------------------

    def _register_dnd(self):
        self._drop_frame.drop_target_register(DND_FILES)
        self._drop_frame.dnd_bind("<<Drop>>", self._on_drop)
        self._drop_frame.dnd_bind("<<DragEnter>>", lambda e: self._drop_frame.configure(fg_color=DROP_HOVER_BG))
        self._drop_frame.dnd_bind("<<DragLeave>>", lambda e: self._drop_frame.configure(fg_color=DROP_NORMAL_BG))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_drop(self, event):
        raw = event.data.strip()
        # tkinterdnd2 returns space-separated paths; braces around paths with spaces
        paths = self._parse_dnd_paths(raw)
        for p in paths:
            self._queue_conversion(Path(p))

    @staticmethod
    def _parse_dnd_paths(raw: str) -> list[str]:
        import re
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

    def _browse_output(self):
        d = filedialog.askdirectory(title="Select output folder")
        if d:
            self._output_dir = Path(d)
            # Truncate long paths for display
            display = str(self._output_dir)
            if len(display) > 45:
                display = "…" + display[-43:]
            self._out_dir_label.configure(text=display, text_color="gray80")

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
        self._set_status("Connecting to Google Drive…")
        self._drop_frame.configure(border_color="orange")
        try:
            tmp_dir = Path(tempfile.gettempdir()) / "doc2md_gdrive"
            downloaded = gdrive.download(url, dest_dir=tmp_dir, progress_cb=self._set_status)
            self._set_status(f"Downloaded — converting {downloaded.name}…")
            out_path = conv.convert(
                downloaded,
                output_dir=self._output_dir or downloaded.parent,
                progress_cb=self._set_status,
            )
            self.after(0, self._add_file_row, out_path)
            self._set_status(f"Done — {out_path.name}")
        except FileNotFoundError as exc:
            self._set_status(f"Setup needed: {exc}", error=True)
            messagebox.showerror("credentials.json missing", str(exc))
        except Exception as exc:
            self._set_status(f"Error: {exc}", error=True)
            messagebox.showerror("Google Drive conversion failed", str(exc))
        finally:
            self.after(0, lambda: self._drop_frame.configure(border_color=ACCENT))

    # ------------------------------------------------------------------
    # Conversion pipeline
    # ------------------------------------------------------------------

    def _queue_conversion(self, src: Path):
        ext = src.suffix.lower()
        if ext not in conv.SUPPORTED_EXTENSIONS:
            self._set_status(f"Skipped: unsupported type '{ext}'", error=True)
            return
        if not src.exists():
            self._set_status(f"File not found: {src.name}", error=True)
            return

        threading.Thread(target=self._run_conversion, args=(src,), daemon=True).start()

    def _run_conversion(self, src: Path):
        self._set_status(f"Converting {src.name}…")
        self._drop_frame.configure(border_color="orange")

        try:
            out_path = conv.convert(
                src,
                output_dir=self._output_dir,
                progress_cb=self._set_status,
            )
            self.after(0, self._add_file_row, out_path)
            self._set_status(f"Done — {out_path.name}")
        except Exception as exc:
            self._set_status(f"Error: {exc}", error=True)
            messagebox.showerror("Conversion failed", str(exc))
        finally:
            self.after(0, lambda: self._drop_frame.configure(border_color=ACCENT))

    # ------------------------------------------------------------------
    # UI update helpers (always called on main thread via after())
    # ------------------------------------------------------------------

    def _add_file_row(self, md_path: Path):
        # Remove the "no files" placeholder if present
        if self._empty_label.winfo_exists():
            try:
                self._empty_label.destroy()
            except Exception:
                pass

        row = FileRow(self._file_list_frame, md_path)
        row.pack(fill="x", pady=(0, 4))

    def _set_status(self, msg: str, error: bool = False):
        color = "#e06c75" if error else "gray60"
        self.after(0, lambda: self._status_var.set(msg))
        self.after(0, lambda: self._find_status_label_color(color))

    def _find_status_label_color(self, color: str):
        self._status_var.set(self._status_var.get())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = App()
    app.mainloop()
