"""
app.py - Doc -> Markdown Converter
Native Windows desktop app using CustomTkinter + tkinterdnd2.

Usage:
    python app.py
"""

from __future__ import annotations

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

class FileRow(ctk.CTkFrame):
    def __init__(self, master, md_path: Path, token_stats: dict | None = None, src_ext: str | None = None, **kwargs):
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
            ext_label.pack(side="left", padx=(0, 4), pady=6)

        if token_stats:
            pct = token_stats.get("savings_pct")
            out_tokens = token_stats.get("out_tokens", 1)
            if pct is not None:
                if out_tokens == 0:
                    badge_text = "⚠ empty output"
                    badge_color = "#6b4a00"
                    text_color = "#f0a500"
                elif pct > 0:
                    badge_text = f"↓{pct}% tokens"
                    badge_color = "#2d6a2d"
                    text_color = "#7ec87e"
                elif pct < 0:
                    badge_text = f"↑{abs(pct)}% tokens"
                    badge_color = "#5a2d2d"
                    text_color = "#e06c75"
                else:
                    badge_text = "≈ same tokens"
                    badge_color = "gray30"
                    text_color = "gray60"
                badge = ctk.CTkLabel(
                    self,
                    text=badge_text,
                    font=("Segoe UI", 10),
                    fg_color=badge_color,
                    text_color=text_color,
                    corner_radius=4,
                    padx=6,
                )
                badge.pack(side="left", padx=(0, 6), pady=6)

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

        supported_label = " · ".join(
            ext.lstrip(".").upper()
            for ext in sorted(conv.SUPPORTED_EXTENSIONS)
        )
        self._drop_sub = ctk.CTkLabel(
            self._drop_frame,
            text=supported_label,
            font=FONT_SMALL,
            text_color="gray50",
            wraplength=480,
        )
        self._drop_sub.pack(pady=(2, 0))

        # Make the drop zone clickable to browse
        for widget in (self._drop_frame, self._drop_icon, self._drop_label, self._drop_sub):
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
            out_path = conv.convert(
                downloaded,
                output_dir=self._output_dir or downloaded.parent,
                progress_cb=self._set_status,
            )
            stats = conv.token_stats(downloaded, out_path)
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
        total = len(files)
        details: list[str] = list(skipped) if skipped else []
        try:
            self._drop_frame.configure(border_color="orange")

            while files:
                for i, src in enumerate(files, 1):
                    self._set_status(f"[{ok + failed + 1}/{total}] Converting {src.name}…" if total > 1 else f"Converting {src.name}…")
                    try:
                        out_path = conv.convert(
                            src,
                            output_dir=self._output_dir,
                            progress_cb=self._set_status,
                        )
                        stats = conv.token_stats(src, out_path)
                        self.after(0, self._add_file_row, out_path, stats, src.suffix.lower())
                        ok += 1
                    except Exception as exc:
                        details.append(f"{src.name}  (error: {exc})")
                        failed += 1

                # Drain any files queued while we were working
                files = list(self._queue)
                self._queue.clear()
                total += len(files)

            if details:
                self._skipped_files = details
            n_details = len(details)
            if total == 1 and not n_details:
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

        ok, failed = 0, 0
        errors: list[str] = []
        for i, src in enumerate(files, 1):
            self._set_status(f"[{i}/{len(files)}] {src.name}…")
            try:
                out_path = conv.convert(src, output_dir=self._output_dir, progress_cb=self._set_status)
                stats = conv.token_stats(src, out_path)
                self.after(0, self._add_file_row, out_path, stats, src.suffix.lower())
                ok += 1
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

        row = FileRow(self._file_list_frame, md_path, token_stats=token_stats, src_ext=src_ext)
        row.pack(fill="x", pady=(0, 4))

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
