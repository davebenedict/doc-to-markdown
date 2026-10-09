"""
converter.py - Document-to-Markdown conversion logic.

Supported formats:
  .pdf              - text-layer (PyMuPDF) or per-page OCR from PyMuPDF-rendered images
  .jpg/.jpeg/.png/.tiff/.tif/.bmp  - Tesseract OCR
  .docx             - python-docx (heading styles, lists, tables)
  .html/.htm        - markdownify
  .xlsx/.xls        - openpyxl/xlrd (each sheet as a markdown table)
  .csv              - built-in csv module
  .pptx             - python-pptx (each slide as a markdown section)
  .epub             - ebooklib + markdownify (chapters as sections)
  .rtf              - striprtf (plain text extraction)
  .xml              - stdlib ElementTree (tags stripped, text preserved)
  .json             - stdlib json (pretty-printed as fenced code block)
  .odt              - odfpy (paragraphs and headings)
"""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from io import BytesIO
import os
import re
import sys
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


def friendly_error_message(exc: Exception) -> str:
    message = str(exc).strip()
    error_name = type(exc).__name__

    if error_name == "TesseractNotFoundError":
        return "Tesseract OCR was not found. Install Tesseract, ensure the `tesseract` command is on PATH, then restart the app. On macOS, run `brew install tesseract`."
    if isinstance(exc, ImportError):
        match = re.search(r"Required package '([^']+)' is not installed", message)
        if not match:
            match = re.search(r"No module named ['\"]([^'\"]+)['\"]", message)
        package = match.group(1) if match else None
        if getattr(sys, "frozen", False):
            missing = f" {package}" if package else ""
            return f"This app build could not load a bundled Python dependency{missing}. Install a complete app build; installing it into system Python will not repair this executable."
        requirements_file = Path(__file__).with_name("requirements.txt")
        install_all = f'"{sys.executable}" -m pip install -r "{requirements_file}"'
        if package:
            package = {"fitz": "PyMuPDF", "PIL": "Pillow", "docx": "python-docx", "pptx": "python-pptx", "odf": "odfpy"}.get(package, package)
            install_package = f'"{sys.executable}" -m pip install {package}'
            return f"Required Python package '{package}' is missing. Install it into this app's Python environment with `{install_package}`. For a source checkout, install all project dependencies with `{install_all}`."
        return f"A Python dependency could not be loaded ({message}). Reinstall all project dependencies with `{install_all}`, then restart the app."
    if isinstance(exc, PermissionError):
        return "Access was denied while reading a file or writing the output folder. Choose a folder where you have write permission and close the file if it is open elsewhere."
    if isinstance(exc, FileNotFoundError):
        return f"A file or required program was not found. Check the selected path; OCR needs Tesseract on PATH. Details: {message}"
    if isinstance(exc, OSError):
        return f"A system error prevented conversion. Check file paths, output-folder permissions, and required OCR tools. Details: {message}"
    return message or "An unexpected error prevented conversion."


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp",
    ".docx", ".html", ".htm",
    ".xlsx", ".xls", ".csv", ".pptx",
    ".epub", ".rtf", ".xml", ".json", ".odt",
}
OCR_TEXT_THRESHOLD = 50  # characters per page below which we treat PDF as scanned

# Maps extension -> pip install hint for any optional dep missing at startup.
# Populated lazily below after optional imports are attempted.
MISSING_DEPS: dict[str, str] = {}


def _probe_optional_deps():
    """Check optional deps once at startup and populate MISSING_DEPS."""
    import importlib
    checks = [
        (["fitz"],               [".pdf"],                          "PyMuPDF"),
        (["PIL"],                [".jpg", ".jpeg", ".png",
                                  ".tiff", ".tif", ".bmp"],         "Pillow"),
        (["pytesseract"],        [".jpg", ".jpeg", ".png",
                                  ".tiff", ".tif", ".bmp"],         "pytesseract"),
        (["surya"],              [".jpg", ".jpeg", ".png",
                                  ".tiff", ".tif", ".bmp"],         "surya-ocr"),
        (["docx"],               [".docx"],                         "python-docx"),
        (["markdownify"],        [".html", ".htm"],                  "markdownify"),
        (["openpyxl"],           [".xlsx"],                          "openpyxl"),
        (["xlrd"],               [".xls"],                           "xlrd"),
        (["pptx"],               [".pptx"],                          "python-pptx"),
        (["ebooklib"],           [".epub"],                          "ebooklib"),
        (["striprtf.striprtf"],  [".rtf"],                           "striprtf"),
        (["odf"],                [".odt"],                           "odfpy"),
    ]
    for modules, exts, pkg in checks:
        all_failed = True
        for mod in modules:
            try:
                importlib.import_module(mod)
                all_failed = False
            except ImportError:
                pass
        if all_failed:
            for ext in exts:
                if ext not in MISSING_DEPS:
                    MISSING_DEPS[ext] = pkg


def _configure_tesseract():
    """Configure pytesseract path on Windows if not set."""
    if sys.platform == "win32":
        try:
            import pytesseract
            current_cmd = pytesseract.pytesseract.tesseract_cmd
            if not current_cmd or not os.path.exists(current_cmd):
                common_paths = [
                    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                    r"C:\Users\{}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe".format(os.getenv("USERNAME", "")),
                ]
                for tesseract_path in common_paths:
                    if os.path.exists(tesseract_path):
                        pytesseract.pytesseract.tesseract_cmd = tesseract_path
                        break
        except (ImportError, AttributeError):
            pass


_probe_optional_deps()
_configure_tesseract()


# ---------------------------------------------------------------------------
# PDF conversion
# ---------------------------------------------------------------------------

def _convert_pdf(
    path: Path,
    progress_cb: Callable[[str], None] | None = None,
    image_assets: dict[str, bytes] | None = None,
    image_dir_name: str | None = None,
) -> tuple[str, str | None]:
    fitz = _require("PyMuPDF", "fitz")
    doc = fitz.open(str(path))
    total_pages = len(doc)
    markdown_parts: list[str] = []
    source_parts: list[str] = []
    source_text_complete = True

    try:
        for page_num, page in enumerate(doc):
            page_text = page.get_text().strip()
            if len(page_text) >= OCR_TEXT_THRESHOLD:
                page_markdown, image_texts, page_source_complete = _pdf_text_layer_page(
                    page, page_num, progress_cb, image_assets, image_dir_name
                )
                source_parts.append(page_text)
                source_parts.extend(image_texts)
                source_text_complete = source_text_complete and page_source_complete
            else:
                if progress_cb:
                    progress_cb(f"Rendering scanned page {page_num + 1}/{total_pages}…")
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image_data = pixmap.tobytes("png")
                image_path, image_text = _save_image_asset(
                    image_data, ".png", image_assets, image_dir_name
                )
                page_parts = []
                if image_path:
                    page_parts.append(f"![Scanned PDF page {page_num + 1}]({image_path})")
                if image_text:
                    if page_text and page_text not in image_text:
                        page_parts.append(page_text)
                        source_parts.append(page_text)
                    page_parts.append(f"OCR text: {image_text}")
                    source_parts.append(image_text)
                else:
                    source_text_complete = False
                    if page_text:
                        page_parts.append(page_text)
                        source_parts.append(page_text)
                    if image_path:
                        note = "OCR text unavailable" if image_text is None else "No text recognized by OCR"
                        page_parts.append(f"{note}; inspect the linked page image.")
                page_markdown = "\n\n".join(page_parts)

            if page_markdown:
                markdown_parts.append(page_markdown)
            if total_pages > 1:
                markdown_parts.append(f"\n\n---\n<!-- Page {page_num + 1} -->\n")
    finally:
        doc.close()

    source_text = "\n\n".join(source_parts) if source_text_complete else None
    return "\n".join(markdown_parts), source_text


def _pdf_text_layer_page(
    page,
    page_num: int,
    progress_cb: Callable[[str], None] | None,
    image_assets: dict[str, bytes] | None,
    image_dir_name: str | None,
) -> tuple[str, list[str], bool]:
    if progress_cb:
        progress_cb(f"Extracting page {page_num + 1} text…")

    blocks = page.get_text("dict")["blocks"]
    page_lines: list[str] = []
    image_texts: list[str] = []
    source_text_complete = True

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
        if block.get("type") == 0:
            for line in block.get("lines", []):
                line_text = ""
                max_size = 0.0
                bold = False
                for span in line.get("spans", []):
                    line_text += span.get("text", "")
                    size = span.get("size", 0)
                    max_size = max(max_size, size)
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
        elif block.get("type") == 1 and block.get("image"):
            extension = block.get("ext", "png")
            image_path, image_text = _save_image_asset(
                block["image"], extension, image_assets, image_dir_name
            )
            if image_path:
                page_lines.append(f"![Image on PDF page {page_num + 1}]({image_path})")
            if image_text:
                page_lines.append(f"OCR text: {image_text}")
                image_texts.append(image_text)
            else:
                source_text_complete = False
                if image_path:
                    note = "OCR text unavailable" if image_text is None else "No text recognized by OCR"
                    page_lines.append(f"{note}; inspect the linked image.")

    return "\n".join(page_lines), image_texts, source_text_complete


# ---------------------------------------------------------------------------
# Image conversion (OCR)
# ---------------------------------------------------------------------------

def _convert_image(
    path: Path,
    progress_cb: Callable[[str], None] | None = None,
    image_assets: dict[str, bytes] | None = None,
    image_dir_name: str | None = None,
) -> str:
    if progress_cb:
        progress_cb(f"Extracting image content from {path.name}…")

    image_path, image_text = _save_image_asset(
        path.read_bytes(), path.suffix.lower(), image_assets, image_dir_name
    )
    parts = []
    if image_path:
        parts.append(f"![{path.stem}]({image_path})")
    if image_text:
        parts.append(f"OCR text: {image_text}")
    elif image_text is None:
        parts.append("OCR text unavailable; inspect the image asset." if image_path else "OCR text unavailable.")
    else:
        parts.append("No text recognized by OCR; inspect the image asset." if image_path else "No text recognized by OCR.")
    return "\n\n".join(parts)


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


def _convert_docx(
    path: Path,
    progress_cb: Callable[[str], None] | None = None,
    image_assets: dict[str, bytes] | None = None,
    image_dir_name: str | None = None,
) -> str:
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

    if image_assets is not None and image_dir_name is not None:
        image_parts = _docx_embedded_images(doc, image_assets, image_dir_name)
        if image_parts:
            parts.extend(["## Embedded images", *image_parts])

    return "\n".join(parts)


def _docx_embedded_images(doc, image_assets: dict[str, bytes], image_dir_name: str) -> list[str]:
    parts: list[str] = []
    image_number = 0
    for image_part in doc.part.related_parts.values():
        content_type = getattr(image_part, "content_type", "").lower()
        if not content_type.startswith("image/"):
            continue
        extension = _IMAGE_MIME_EXTENSIONS.get(content_type, Path(str(image_part.partname)).suffix.lower() or ".bin")
        image_path, image_text = _save_image_asset(
            image_part.blob, extension, image_assets, image_dir_name
        )
        if not image_path:
            continue
        image_number += 1
        image_label = f"Embedded DOCX image {image_number}"
        parts.append(f"![{image_label}]({image_path})")
        if image_text:
            parts.append(f"OCR text: {image_text}")
        elif image_text is None:
            parts.append("OCR text unavailable; inspect the linked image.")
        else:
            parts.append("No text recognized by OCR; inspect the linked image.")
    return parts


def _find_paragraph(doc, element):
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
# Excel conversion (.xlsx, .xls)
# ---------------------------------------------------------------------------

def _convert_excel(path: Path, progress_cb: Callable[[str], None] | None = None) -> str:
    ext = path.suffix.lower()
    parts: list[str] = []

    if ext == ".xlsx":
        openpyxl = _require("openpyxl")
        formula_wb = openpyxl.load_workbook(str(path), data_only=False)
        value_wb = openpyxl.load_workbook(str(path), data_only=True)
        try:
            for sheet_name in formula_wb.sheetnames:
                if progress_cb:
                    progress_cb(f"Converting sheet '{sheet_name}'…")
                formula_sheet = formula_wb[sheet_name]
                value_sheet = value_wb[sheet_name]
                rows = []
                for row_index in range(1, formula_sheet.max_row + 1):
                    row = []
                    for column_index in range(1, formula_sheet.max_column + 1):
                        formula_cell = formula_sheet.cell(row_index, column_index)
                        value = value_sheet.cell(row_index, column_index).value
                        if formula_cell.data_type == "f":
                            formula = str(formula_cell.value)
                            value = (
                                f"{value} [formula: {formula}]"
                                if value is not None
                                else f"{formula} [cached value unavailable]"
                            )
                        row.append(value)
                    rows.append(row)
                if rows:
                    parts.append(f"## {sheet_name}\n")
                    parts.append(_rows_to_md(rows))
        finally:
            formula_wb.close()
            value_wb.close()
    else:
        xlrd = _require("xlrd")
        wb = xlrd.open_workbook(str(path))
        parts.append("> Legacy XLS conversion preserves stored cell values; formula expressions are unavailable.")
        for sheet in wb.sheets():
            if progress_cb:
                progress_cb(f"Converting sheet '{sheet.name}'…")
            rows = [sheet.row_values(i) for i in range(sheet.nrows)]
            if not rows:
                continue
            parts.append(f"## {sheet.name}\n")
            parts.append(_rows_to_md(rows))

    return "\n\n".join(parts)


def _rows_to_md(rows: list) -> str:
    if not rows:
        return ""
    lines: list[str] = []
    for i, row in enumerate(rows):
        cells = [str(cell) if cell is not None else "" for cell in row]
        cells = [c.replace("|", "\\|").replace("\n", " ") for c in cells]
        lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CSV conversion
# ---------------------------------------------------------------------------

def _convert_csv(path: Path, progress_cb: Callable[[str], None] | None = None) -> str:
    if progress_cb:
        progress_cb(f"Converting {path.name}…")

    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        rows = list(csv.reader(f))

    return _rows_to_md(rows)


# ---------------------------------------------------------------------------
# PowerPoint conversion (.pptx)
# ---------------------------------------------------------------------------

def _convert_pptx(
    path: Path,
    progress_cb: Callable[[str], None] | None = None,
    image_assets: dict[str, bytes] | None = None,
    image_dir_name: str | None = None,
) -> str:
    pptx = _require("python-pptx", "pptx")
    Presentation = pptx.Presentation

    if progress_cb:
        progress_cb(f"Parsing {path.name}…")

    prs = Presentation(str(path))
    parts: list[str] = []

    for i, slide in enumerate(prs.slides):
        slide_parts: list[str] = []
        title_text = ""

        for shape in slide.shapes:
            if getattr(shape, "has_chart", False):
                chart_markdown = _pptx_chart_to_md(shape.chart)
                if chart_markdown:
                    slide_parts.append(chart_markdown)
                continue
            if shape.shape_type == 13:
                image = shape.image
                image_path, image_text = _save_image_asset(
                    image.blob, f".{image.ext}", image_assets, image_dir_name
                )
                if image_path:
                    slide_parts.append(f"![Image on slide {i + 1}]({image_path})")
                if image_text:
                    slide_parts.append(f"OCR text: {image_text}")
                elif image_path:
                    note = "OCR text unavailable" if image_text is None else "No text recognized by OCR"
                    slide_parts.append(f"{note}; inspect the linked image.")
                continue
            if not shape.has_text_frame:
                continue
            text = shape.text_frame.text.strip()
            if not text:
                continue
            if hasattr(shape, "placeholder_format") and shape.placeholder_format is not None:
                ph_idx = shape.placeholder_format.idx
                if ph_idx == 0:
                    title_text = text
                    continue
            slide_parts.append(text)

        header = f"## Slide {i + 1}"
        if title_text:
            header += f": {title_text}"
        parts.append(header)
        if slide_parts:
            parts.append("\n".join(slide_parts))
        parts.append("")

    return "\n".join(parts)


def _pptx_chart_to_md(chart) -> str:
    try:
        series = list(chart.series)
        if not series:
            return ""
        series_values = [
            [int(value) if isinstance(value, float) and value.is_integer() else value for value in item.values]
            for item in series
        ]
        first_series = series[0]
        if hasattr(first_series, "x_values"):
            categories = [str(value) for value in first_series.x_values]
            category_header = "X"
        else:
            categories = [str(category.label) for category in chart.plots[0].categories]
            category_header = "Category"
        row_count = max([len(categories), *(len(values) for values in series_values)])
        headers = [category_header] + [item.name or f"Series {i + 1}" for i, item in enumerate(series)]
        rows = [headers]
        for row_index in range(row_count):
            category = categories[row_index] if row_index < len(categories) else str(row_index + 1)
            rows.append([
                category,
                *[values[row_index] if row_index < len(values) else "" for values in series_values],
            ])
        title = chart.chart_title.text_frame.text.strip() if chart.has_title else ""
        heading = f"### Chart: {title}" if title else "### Chart data"
        return f"{heading}\n\n{_rows_to_md(rows)}"
    except Exception:
        return "### Chart data unavailable"


# ---------------------------------------------------------------------------
# HTML conversion
# ---------------------------------------------------------------------------

_IMAGE_MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/svg+xml": ".svg",
    "image/avif": ".avif",
    "image/x-icon": ".ico",
}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".svg", ".avif", ".ico"}


def _decode_base64_image(src: str) -> tuple[str, bytes] | None:
    if not src.strip().lower().startswith("data:image/"):
        return None
    header, separator, encoded = src.strip()[5:].partition(",")
    if not separator:
        return None
    parameters = header.split(";")
    extension = _IMAGE_MIME_EXTENSIONS.get(parameters[0].lower())
    if extension is None or "base64" not in {part.strip().lower() for part in parameters[1:]}:
        return None
    try:
        image_data = base64.b64decode("".join(encoded.split()), validate=True)
    except (binascii.Error, ValueError):
        return None
    return (extension, image_data) if image_data else None


def _image_asset_dir_name(out_path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", out_path.stem).strip("._")
    return f"{stem[:80] or 'document'}_images"


@lru_cache(maxsize=1)
def _surya_recognition_predictor():
    from surya.inference import SuryaInferenceManager
    from surya.recognition import RecognitionPredictor

    return RecognitionPredictor(SuryaInferenceManager())


_SURYA_INFERENCE_LOCK = threading.Lock()
_OCR_WORKER_COUNT = 4
_OCR_EXECUTOR = ThreadPoolExecutor(max_workers=_OCR_WORKER_COUNT)
_OCR_WORKER_SLOTS = threading.BoundedSemaphore(_OCR_WORKER_COUNT)
_OCR_TEXT_CACHE_LIMIT = 128
_OCR_TEXT_CACHE: dict[bytes, str | None] = {}
_OCR_CACHE_LOCK = threading.Lock()


class ImageAssetCollection(dict[str, bytes]):
    def __init__(self):
        super().__init__()
        self.ocr_jobs = {}
        self.asset_ocr_tokens: dict[str, str] = {}
        self._ocr_job_number = 0

    def schedule_ocr(self, image_data: bytes) -> str:
        token = f"__DOC2MD_OCR_{self._ocr_job_number:05d}__"
        self._ocr_job_number += 1
        _OCR_WORKER_SLOTS.acquire()
        try:
            future = _OCR_EXECUTOR.submit(_ocr_image_bytes, image_data)
        except Exception:
            _OCR_WORKER_SLOTS.release()
            raise
        future.add_done_callback(lambda _: _OCR_WORKER_SLOTS.release())
        self.ocr_jobs[token] = future
        return token


def _resolve_image_ocr(
    markdown: str,
    source_text: str | None,
    image_assets: ImageAssetCollection | None,
    extension: str,
) -> tuple[str, str | None]:
    if image_assets is None:
        return markdown, source_text

    source_text_complete = source_text is not None
    for token, future in image_assets.ocr_jobs.items():
        try:
            image_text = future.result()
        except Exception:
            image_text = None
        if image_text:
            replacement = image_text
        elif image_text is None:
            replacement = "[OCR text unavailable; inspect the linked image]"
            source_text_complete = False
        else:
            replacement = "[No text recognized by OCR; inspect the linked image]"
            source_text_complete = False
        markdown = markdown.replace(token, replacement)
        if source_text is not None:
            source_text = source_text.replace(token, image_text or "")

    if extension == ".pdf" and not source_text_complete:
        source_text = None
    return markdown, source_text


def _ocr_image_bytes(image_data: bytes) -> str | None:
    digest = hashlib.sha256(image_data).digest()
    with _OCR_CACHE_LOCK:
        if digest in _OCR_TEXT_CACHE:
            return _OCR_TEXT_CACHE[digest]

    text = _recognize_image_bytes(image_data)
    with _OCR_CACHE_LOCK:
        if len(_OCR_TEXT_CACHE) >= _OCR_TEXT_CACHE_LIMIT:
            _OCR_TEXT_CACHE.pop(next(iter(_OCR_TEXT_CACHE)))
        _OCR_TEXT_CACHE[digest] = text
    return text


def _recognize_image_bytes(image_data: bytes) -> str | None:
    try:
        Image = _require("Pillow", "PIL.Image")
        with Image.open(BytesIO(image_data)) as image:
            if image.width < 64 or image.height < 32:
                return ""
            try:
                with _SURYA_INFERENCE_LOCK:
                    predictions = _surya_recognition_predictor()([image])
                text = "\n".join(
                    block.text
                    for prediction in predictions
                    for block in prediction.blocks
                    if hasattr(block, "text")
                ).strip()
                if text:
                    return text
            except Exception:
                pass
            try:
                pytesseract = _require("pytesseract")
                return pytesseract.image_to_string(image, timeout=15).strip()
            except Exception:
                return None
    except Exception:
        return None


def _save_image_asset(
    image_data: bytes,
    extension: str,
    image_assets: dict[str, bytes] | None,
    image_dir_name: str | None,
) -> tuple[str | None, str | None]:
    extension = extension.lower()
    if not extension.startswith("."):
        extension = f".{extension}"
    if extension not in _IMAGE_EXTENSIONS:
        try:
            Image = _require("Pillow", "PIL.Image")
            with Image.open(BytesIO(image_data)) as image:
                converted = BytesIO()
                image.save(converted, format="PNG")
                image_data = converted.getvalue()
            extension = ".png"
        except Exception:
            extension = ".bin"
    if image_assets is None or image_dir_name is None:
        return None, _ocr_image_bytes(image_data)
    for filename, existing_data in image_assets.items():
        if existing_data == image_data:
            if isinstance(image_assets, ImageAssetCollection):
                return f"{image_dir_name}/{filename}", image_assets.asset_ocr_tokens[filename]
            return f"{image_dir_name}/{filename}", _ocr_image_bytes(image_data)
    filename = f"image_{len(image_assets) + 1:03d}{extension}"
    image_assets[filename] = image_data
    if isinstance(image_assets, ImageAssetCollection):
        image_text = image_assets.schedule_ocr(image_data)
        image_assets.asset_ocr_tokens[filename] = image_text
        return f"{image_dir_name}/{filename}", image_text
    return f"{image_dir_name}/{filename}", _ocr_image_bytes(image_data)


def _markdownify_html(
    html: str,
    markdownify,
    image_assets: dict[str, bytes] | None = None,
    image_dir_name: str | None = None,
) -> str:
    class _ImageAssetMarkdownConverter(markdownify.MarkdownConverter):
        def convert_img(self, el, text, convert_as_inline):
            src = el.attrs.get("src", "") or ""
            alt = el.attrs.get("alt", "") or ""
            if not isinstance(src, str) or not src.strip().lower().startswith("data:image/"):
                return super().convert_img(el, text, convert_as_inline)
            decoded = _decode_base64_image(src)
            if decoded is None:
                return alt
            extension, image_data = decoded
            relative_path, image_text = _save_image_asset(
                image_data, extension, image_assets, image_dir_name
            )
            if relative_path is None:
                return alt
            el.attrs["src"] = relative_path
            try:
                converted = super().convert_img(el, text, False)
            finally:
                el.attrs["src"] = src
            if image_text:
                converted += f"\n\nOCR text: {image_text}"
            else:
                note = "OCR text unavailable" if image_text is None else "No text recognized by OCR"
                converted += f"\n\n{note}; inspect the linked image."
            return converted

    return _ImageAssetMarkdownConverter(heading_style="ATX").convert(html).strip()


def _convert_html(
    path: Path,
    progress_cb: Callable[[str], None] | None = None,
    image_assets: dict[str, bytes] | None = None,
    image_dir_name: str | None = None,
) -> str:
    markdownify = _require("markdownify")

    if progress_cb:
        progress_cb(f"Converting HTML {path.name}…")

    html = path.read_text(encoding="utf-8", errors="replace")
    return _markdownify_html(html, markdownify, image_assets, image_dir_name)


def _convert_epub(
    path: Path,
    progress_cb: Callable[[str], None] | None = None,
    image_assets: dict[str, bytes] | None = None,
    image_dir_name: str | None = None,
) -> str:
    ebooklib = _require("ebooklib")
    markdownify = _require("markdownify")
    epub = ebooklib.epub

    if progress_cb:
        progress_cb(f"Converting EPUB {path.name}\u2026")

    book = epub.read_epub(str(path), options={"ignore_ncx": True})
    parts: list[str] = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        html = item.get_content().decode("utf-8", errors="replace")
        md = _markdownify_html(html, markdownify, image_assets, image_dir_name)
        if md:
            parts.append(md)
    return "\n\n".join(parts)


def _convert_rtf(path: Path, progress_cb: Callable[[str], None] | None = None) -> str:
    _require("striprtf", import_name="striprtf.striprtf")
    from striprtf.striprtf import rtf_to_text

    if progress_cb:
        progress_cb(f"Converting RTF {path.name}\u2026")

    raw = path.read_text(encoding="utf-8", errors="replace")
    text = rtf_to_text(raw)
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def _convert_xml(path: Path, progress_cb: Callable[[str], None] | None = None) -> str:
    import xml.etree.ElementTree as ET

    if progress_cb:
        progress_cb(f"Converting XML {path.name}\u2026")

    try:
        tree = ET.parse(str(path))
        root = tree.getroot()
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML: {exc}")

    def _walk(node: ET.Element, depth: int, lines: list[str]) -> None:
        tag = node.tag.split("}")[-1] if "}" in node.tag else node.tag
        text = (node.text or "").strip()
        prefix = "#" * min(depth + 1, 6)
        if depth == 0 or text or list(node):
            lines.append(f"{prefix} {tag}")
        if text:
            lines.append(text)
        for child in node:
            _walk(child, depth + 1, lines)
        tail = (node.tail or "").strip()
        if tail:
            lines.append(tail)

    lines: list[str] = []
    _walk(root, 0, lines)
    return "\n\n".join(line for line in lines if line)


def _convert_json(path: Path, progress_cb: Callable[[str], None] | None = None) -> str:
    import json

    if progress_cb:
        progress_cb(f"Converting JSON {path.name}\u2026")

    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}")

    pretty = json.dumps(data, indent=2, ensure_ascii=False)
    return f"```json\n{pretty}\n```"


def _convert_odt(path: Path, progress_cb: Callable[[str], None] | None = None) -> str:
    _require("odf", import_name="odf")
    from odf.opendocument import load as odf_load

    if progress_cb:
        progress_cb(f"Converting ODT {path.name}\u2026")

    doc = odf_load(str(path))
    lines: list[str] = []

    def _get_text(node) -> str:
        parts = []
        if node.nodeType == node.TEXT_NODE:
            parts.append(node.data)
        for child in node.childNodes:
            parts.append(_get_text(child))
        return "".join(parts)

    for el in doc.text.childNodes:
        tag = el.__class__.__name__
        text = _get_text(el).strip()
        if not text:
            continue
        if tag == "H":
            try:
                level = int(el.getAttribute("text:outline-level") or 1)
            except (ValueError, TypeError):
                level = 1
            prefix = "#" * min(level, 6)
            lines.append(f"{prefix} {text}")
        else:
            lines.append(text)

    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

try:
    import tiktoken as _tiktoken
    _enc = _tiktoken.get_encoding("cl100k_base")
    def _count_tokens(text: str) -> int:
        return len(_enc.encode(text))
except ImportError:
    _enc = None
    def _count_tokens(text: str) -> int:  # type: ignore[misc]
        return len(text) // 4

TIKTOKEN_AVAILABLE: bool = _enc is not None


def token_stats(src_text: str | None, out: Path, src: Path | None = None) -> dict:
    """
    Return exact token counts when extracted source text is available, plus approximate estimates.

    Parameters
    ----------
    src_text : extracted source text, or None when no comparable baseline is available
    out      : path to the generated .md file
    src      : path to the original source file (used for the file-size estimate)
    """
    out_text = out.read_text(encoding="utf-8", errors="replace")

    if _enc is not None:
        tiktoken_src = _count_tokens(src_text) if src_text is not None else None
        tiktoken_out = _count_tokens(out_text)
        tiktoken_pct = round((1 - tiktoken_out / tiktoken_src) * 100) if tiktoken_src else None
    else:
        tiktoken_src = tiktoken_out = tiktoken_pct = None

    fallback_src = (src.stat().st_size // 4) if src is not None else (len(src_text) // 4 if src_text is not None else None)
    fallback_out = len(out_text) // 4
    fallback_pct = round((1 - fallback_out / fallback_src) * 100) if fallback_src else None
    fallback_method = "file bytes÷4" if src is not None else "chars÷4" if src_text is not None else "unavailable"

    if _enc is not None and src_text is not None:
        src_tokens, out_tokens, savings_pct, method = tiktoken_src, tiktoken_out, tiktoken_pct, "tiktoken cl100k_base"
    else:
        src_tokens, out_tokens, savings_pct, method = fallback_src, fallback_out, fallback_pct, fallback_method

    return {
        "tiktoken_available": _enc is not None,
        "tiktoken_source_available": _enc is not None and src_text is not None,
        "tiktoken_src": tiktoken_src,
        "tiktoken_out": tiktoken_out,
        "tiktoken_pct": tiktoken_pct,
        "fallback_src": fallback_src,
        "fallback_out": fallback_out,
        "fallback_pct": fallback_pct,
        "fallback_method": fallback_method,
        "src_tokens": src_tokens,
        "out_tokens": out_tokens,
        "savings_pct": savings_pct,
        "method": method,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def convert(
    input_path: str | Path,
    output_dir: str | Path | None = None,
    progress_cb: Callable[[str], None] | None = None,
    return_text: bool = False,
) -> Path | tuple[Path, str | None]:
    """
    Convert *input_path* to a markdown file.

    Parameters
    ----------
    input_path : path to the source document
    output_dir : directory for the .md file; defaults to same folder as input
    progress_cb : optional callable(str) for progress messages
    return_text : include extracted source text when a comparable baseline is available

    Returns
    -------
    Path to the generated .md file, optionally paired with source text
    """
    src = Path(input_path).resolve()
    ext = src.suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    # Determine output path
    out_dir = Path(output_dir).resolve() if output_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / (src.name + ".md")
    extract_images = ext in {
        ".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp",
        ".docx", ".pptx", ".html", ".htm", ".epub",
    }
    image_dir_name = _image_asset_dir_name(out_path) if extract_images else None

    # Avoid silently overwriting existing files
    counter = 1
    while out_path.exists() or (image_dir_name and (out_dir / image_dir_name).exists()):
        out_path = out_dir / f"{src.name}_{counter}.md"
        image_dir_name = _image_asset_dir_name(out_path) if extract_images else None
        counter += 1

    image_assets: ImageAssetCollection | None = ImageAssetCollection() if image_dir_name else None

    source_text: str | None = None

    # Route to converter
    if ext == ".pdf":
        md, source_text = _convert_pdf(src, progress_cb, image_assets, image_dir_name)
    elif ext in {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}:
        md = _convert_image(src, progress_cb, image_assets, image_dir_name)
    elif ext == ".docx":
        md = _convert_docx(src, progress_cb, image_assets, image_dir_name)
    elif ext in {".html", ".htm"}:
        md = _convert_html(src, progress_cb, image_assets, image_dir_name)
    elif ext in {".xlsx", ".xls"}:
        md = _convert_excel(src, progress_cb)
    elif ext == ".csv":
        md = _convert_csv(src, progress_cb)
    elif ext == ".pptx":
        md = _convert_pptx(src, progress_cb, image_assets, image_dir_name)
    elif ext == ".epub":
        md = _convert_epub(src, progress_cb, image_assets, image_dir_name)
    elif ext == ".rtf":
        md = _convert_rtf(src, progress_cb)
    elif ext == ".xml":
        md = _convert_xml(src, progress_cb)
    elif ext == ".json":
        md = _convert_json(src, progress_cb)
    elif ext == ".odt":
        md = _convert_odt(src, progress_cb)
    else:
        raise ValueError(f"No converter registered for '{ext}'")

    md, source_text = _resolve_image_ocr(md, source_text, image_assets, ext)
    md = re.sub(r"\n{3,}", "\n\n", md)

    if image_assets and image_dir_name:
        image_dir = out_dir / image_dir_name
        image_dir.mkdir()
        try:
            for filename, image_data in image_assets.items():
                (image_dir / filename).write_bytes(image_data)
            out_path.write_text(md, encoding="utf-8")
        except Exception:
            for filename in image_assets:
                image_path = image_dir / filename
                if image_path.exists():
                    image_path.unlink()
            try:
                image_dir.rmdir()
            except OSError:
                pass
            raise
    else:
        out_path.write_text(md, encoding="utf-8")

    if progress_cb:
        if not md.strip():
            progress_cb(f"Warning — {out_path.name} is empty (no extractable text found)")
        else:
            progress_cb(f"Done — {out_path.name}")

    if return_text:
        return out_path, source_text
    return out_path
