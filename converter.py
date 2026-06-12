"""
converter.py - Document-to-Markdown conversion logic.

Supported formats:
  .pdf   - text-layer (PyMuPDF) or scanned (pdf2image + Tesseract OCR)
  .jpg/.jpeg/.png/.tiff/.tif/.bmp  - Tesseract OCR
  .docx  - python-docx (heading styles, lists, tables)
  .doc   - unsupported (returns informative error)
  .html/.htm  - markdownify
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Optional-import helpers — give clear errors when deps are missing
# ---------------------------------------------------------------------------

def _require(pkg_name: str, import_name: str | None = None):
    import importlib
    name = import_name or pkg_name
    try:
        return importlib.import_module(name)
    except ImportError:
        raise ImportError(
            f"Required package '{pkg_name}' is not installed. "
            f"Run: pip install -r requirements.txt"
        )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".docx", ".html", ".htm"}
OCR_TEXT_THRESHOLD = 50  # characters per page below which we treat PDF as scanned


# ---------------------------------------------------------------------------
# PDF conversion
# ---------------------------------------------------------------------------

def _convert_pdf(path: Path, progress_cb: Callable[[str], None] | None = None) -> str:
    fitz = _require("PyMuPDF", "fitz")
    doc = fitz.open(str(path))
    total_pages = len(doc)

    # Probe first few pages for text to decide strategy
    sample_text = ""
    for i in range(min(3, total_pages)):
        sample_text += doc[i].get_text()

    if len(sample_text.strip()) >= OCR_TEXT_THRESHOLD:
        return _pdf_text_layer(doc, total_pages, progress_cb)
    else:
        doc.close()
        return _pdf_ocr(path, total_pages, progress_cb)


def _pdf_text_layer(doc, total_pages: int, progress_cb) -> str:
    fitz = _require("PyMuPDF", "fitz")
    parts: list[str] = []

    for page_num in range(total_pages):
        if progress_cb:
            progress_cb(f"Extracting page {page_num + 1}/{total_pages}…")

        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        page_lines: list[str] = []

        # Collect font sizes for heading inference
        all_sizes: list[float] = []
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("size"):
                        all_sizes.append(span["size"])

        body_size = sorted(all_sizes)[len(all_sizes) // 2] if all_sizes else 12.0

        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_text = ""
                max_size = 0.0
                bold = False
                for span in line.get("spans", []):
                    line_text += span.get("text", "")
                    sz = span.get("size", 0)
                    if sz > max_size:
                        max_size = sz
                    if span.get("flags", 0) & 2 ** 4:
                        bold = True

                line_text = line_text.strip()
                if not line_text:
                    continue

                ratio = max_size / body_size if body_size else 1.0
                if ratio >= 1.6 or (ratio >= 1.3 and bold):
                    line_text = f"# {line_text}"
                elif ratio >= 1.3 or (ratio >= 1.1 and bold):
                    line_text = f"## {line_text}"
                elif ratio >= 1.1:
                    line_text = f"### {line_text}"

                page_lines.append(line_text)

        if page_lines:
            parts.append("\n".join(page_lines))
            if total_pages > 1:
                parts.append(f"\n\n---\n<!-- Page {page_num + 2} -->\n")

    doc.close()
    return "\n".join(parts)


def _pdf_ocr(path: Path, total_pages: int, progress_cb) -> str:
    pdf2image = _require("pdf2image")
    pytesseract = _require("pytesseract")

    parts: list[str] = []

    images = pdf2image.convert_from_path(str(path))
    for i, img in enumerate(images):
        if progress_cb:
            progress_cb(f"OCR page {i + 1}/{len(images)}…")
        text = pytesseract.image_to_string(img)
        parts.append(text.strip())
        if len(images) > 1:
            parts.append(f"\n\n---\n<!-- Page {i + 2} -->\n")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Image conversion (OCR)
# ---------------------------------------------------------------------------

def _convert_image(path: Path, progress_cb: Callable[[str], None] | None = None) -> str:
    pytesseract = _require("pytesseract")
    Image = _require("Pillow", "PIL.Image")

    if progress_cb:
        progress_cb(f"Running OCR on {path.name}…")

    img = Image.open(str(path))
    return pytesseract.image_to_string(img).strip()


# ---------------------------------------------------------------------------
# DOCX conversion
# ---------------------------------------------------------------------------

_HEADING_PREFIX = {
    "Heading 1": "#",
    "Heading 2": "##",
    "Heading 3": "###",
    "Heading 4": "####",
    "Heading 5": "#####",
    "Heading 6": "######",
}


def _convert_docx(path: Path, progress_cb: Callable[[str], None] | None = None) -> str:
    docx = _require("python-docx", "docx")
    Document = docx.Document

    if progress_cb:
        progress_cb(f"Parsing {path.name}…")

    doc = Document(str(path))
    parts: list[str] = []

    for element in doc.element.body:
        tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

        if tag == "p":
            para = _find_paragraph(doc, element)
            if para is None:
                continue
            style = para.style.name if para.style else "Normal"
            text = para.text.strip()
            if not text:
                parts.append("")
                continue

            if style in _HEADING_PREFIX:
                parts.append(f"{_HEADING_PREFIX[style]} {text}")
            elif style in ("List Bullet", "List Bullet 2", "List Bullet 3"):
                parts.append(f"- {text}")
            elif style in ("List Number", "List Number 2", "List Number 3"):
                parts.append(f"1. {text}")
            else:
                # Inline bold/italic
                md_text = _inline_runs(para)
                parts.append(md_text)

        elif tag == "tbl":
            tbl = _find_table(doc, element)
            if tbl is None:
                continue
            parts.append(_table_to_md(tbl))

    return "\n".join(parts)


def _find_paragraph(doc, element):
    from docx.oxml.ns import qn
    from docx.text.paragraph import Paragraph
    try:
        return Paragraph(element, doc)
    except Exception:
        return None


def _find_table(doc, element):
    from docx.table import Table
    try:
        return Table(element, doc)
    except Exception:
        return None


def _inline_runs(para) -> str:
    parts = []
    for run in para.runs:
        text = run.text
        if not text:
            continue
        if run.bold and run.italic:
            text = f"***{text}***"
        elif run.bold:
            text = f"**{text}**"
        elif run.italic:
            text = f"*{text}*"
        parts.append(text)
    return "".join(parts)


def _table_to_md(tbl) -> str:
    rows = tbl.rows
    if not rows:
        return ""
    lines = []
    for i, row in enumerate(rows):
        cells = [cell.text.strip().replace("|", "\\|") for cell in row.cells]
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML conversion
# ---------------------------------------------------------------------------

def _convert_html(path: Path, progress_cb: Callable[[str], None] | None = None) -> str:
    markdownify = _require("markdownify")

    if progress_cb:
        progress_cb(f"Converting HTML {path.name}…")

    html = path.read_text(encoding="utf-8", errors="replace")
    return markdownify.markdownify(html, heading_style="ATX").strip()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def convert(
    input_path: str | Path,
    output_dir: str | Path | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> Path:
    """
    Convert *input_path* to a markdown file.

    Parameters
    ----------
    input_path : path to the source document
    output_dir : directory for the .md file; defaults to same folder as input
    progress_cb : optional callable(str) for progress messages

    Returns
    -------
    Path to the generated .md file
    """
    src = Path(input_path).resolve()
    ext = src.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    if ext == ".doc":
        raise ValueError(
            "Legacy .doc files are not supported. "
            "Please save the file as .docx in Word and try again."
        )

    # Determine output path
    out_dir = Path(output_dir).resolve() if output_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / (src.stem + ".md")

    # Route to converter
    if ext == ".pdf":
        md = _convert_pdf(src, progress_cb)
    elif ext in {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}:
        md = _convert_image(src, progress_cb)
    elif ext == ".docx":
        md = _convert_docx(src, progress_cb)
    elif ext in {".html", ".htm"}:
        md = _convert_html(src, progress_cb)
    else:
        raise ValueError(f"No converter registered for '{ext}'")

    # Post-process: collapse excessive blank lines
    md = re.sub(r"\n{3,}", "\n\n", md)

    out_path.write_text(md, encoding="utf-8")

    if progress_cb:
        progress_cb(f"Done — {out_path.name}")

    return out_path
