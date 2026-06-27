# Doc → Markdown Converter

A native Windows desktop app that converts documents of many formats into clean Markdown via drag-and-drop. Useful for feeding documents into LLMs and RAG pipelines — stripping binary overhead, markup, and formatting noise that inflates file sizes and token counts.

---

## Download

**Windows Desktop App (Recommended for Windows)**
[Download DocToMarkdown.exe](https://drive.google.com/file/d/1lqGdUWcEciDkeU9_fxH5FDo7XGxEJLVp/view?usp=sharing) *(No Python installation required)*

The Windows desktop app has full drag-and-drop UI and is the recommended option for Windows users.

**Web App (Cross-Platform)**
For Mac, Linux, or Windows users who prefer a browser-based interface:
```bash
pip install Flask
python web_app.py
```
Then open http://localhost:5000 in your browser.

The web app provides the same conversion functionality in a browser interface.

**Source Code**
Clone or download from GitHub: https://github.com/davebenedict/doc-to-markdown

---

## Why convert to Markdown?

- **Better LLM comprehension** — LLMs parse Markdown structure natively; tables, headings, and lists are unambiguous.
- **Better RAG chunking** — Markdown splits cleanly on `##` headings rather than mid-sentence or mid-table.
- **Bypass file size limits** — A 50 MB PDF may be 48 MB of fonts and images; the extracted Markdown can be 50–200× smaller, fitting within platform limits (Claude 30 MB/file, etc.).
- **Real token savings for markup-heavy formats** — HTML, EPUB, XML, RTF, PPTX typically save 40–80% of tokens after stripping tags and layout overhead.
- **Portable and reusable** — One Markdown file works in NotebookLM, ChatGPT, Claude, LangChain, LlamaIndex.

---

## Supported Formats

### Significant token savings + smaller file size

Stripping markup, tags, or binary overhead typically saves 40–80% of tokens and reduces file size dramatically.

| Format | Strategy |
|--------|----------|
| `.html` `.htm` | markdownify — strips tags, scripts, nav menus |
| `.epub` | ebooklib + markdownify — strips XML/CSS/nav boilerplate |
| `.xml` | stdlib ElementTree — tag names become headings, text preserved |
| `.rtf` | striprtf — strips RTF control words and formatting codes |
| `.xlsx` `.xls` | openpyxl/xlrd — each sheet as a Markdown table |
| `.pptx` | python-pptx — each slide as a Markdown section |
| `.csv` | stdlib csv — reformatted as a clean Markdown table |

### Structural quality improvement (token count similar)

Token count stays roughly the same, but the LLM reads the content more accurately — clean heading hierarchy, tables, and chunking boundaries.

| Format | Strategy |
|--------|----------|
| `.pdf` (text layer) | PyMuPDF — direct text extraction; headings inferred from font size |
| `.pdf` (scanned/image) | pdf2image → Tesseract OCR |
| `.docx` | python-docx — preserves heading styles, lists, tables |
| `.odt` | odfpy — preserves headings and paragraphs |
| `.json` | stdlib json — pretty-printed as a fenced code block |

### Image / OCR (savings depend on image content)

| Format | Strategy |
|--------|----------|
| `.jpg` `.jpeg` `.png` `.tiff` `.tif` `.bmp` | Tesseract OCR |

---

## Prerequisites

### 1. Python 3.9+

Download from https://www.python.org/downloads/windows/

Verify: `python --version`

### 2. Tesseract OCR (required for scanned PDFs and images)

1. Download the installer from: https://github.com/UB-Mannheim/tesseract/wiki
   - Recommended: `tesseract-ocr-w64-setup-5.x.x.exe`
2. Run the installer (default path: `C:\Program Files\Tesseract-OCR\`)
3. During install, check **"Add to PATH"** or add manually:
   - Open **System Properties → Environment Variables**
   - Add `C:\Program Files\Tesseract-OCR\` to the `Path` variable

Verify: `tesseract --version`

> If Tesseract is installed at a non-default path, set it in `converter.py`:
> ```python
> import pytesseract
> pytesseract.pytesseract.tesseract_cmd = r"C:\custom\path\tesseract.exe"
> ```

### 3. Poppler (required for scanned PDF → image rendering)

`pdf2image` depends on the Poppler `pdftoppm` utility.

1. Download from: https://github.com/oschwartz10612/poppler-windows/releases
2. Extract to e.g. `C:\Tools\poppler\`
3. Add `C:\Tools\poppler\Library\bin\` to your `Path` environment variable

Verify: `pdftoppm -v`

---

## Setup

```powershell
cd E:\Source\doc2md

# Create and activate a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

---

## Running the App

```powershell
cd E:\Source\doc2md
python app.py
```

Or double-click `run.bat` if present.

---

## Usage

1. **Drop files or a folder** onto the drop zone, or click the zone to browse.
2. The status bar shows conversion progress (page-by-page for OCR).
3. Converted files appear in the **Converted Files** list:
   - **Open** — opens the `.md` file in your default Markdown editor.
   - **Reveal** — opens Windows Explorer with the file selected.
4. To change the output folder, click **Browse** next to "Output folder". Click **Clear** to reset to same-folder-as-input.
5. The **token savings badge** on each file shows estimated token reduction. Toggle between **tiktoken** (exact) and **file size** (approximation) using the segmented button above the list. If tiktoken is not installed, the toggle is disabled and an amber install hint is shown.
6. Click **? Why use this** (top right) for an explanation of the value of Markdown conversion.
7. Click **View supported formats ▾** in the drop zone for a full list grouped by savings type, including install hints for any missing libraries.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `customtkinter` | Modern dark-mode UI framework |
| `tkinterdnd2` | Drag-and-drop support |
| `PyMuPDF` | PDF text extraction |
| `pdf2image` | Scanned PDF → image rendering |
| `pytesseract` | OCR |
| `Pillow` | Image handling |
| `python-docx` | DOCX conversion |
| `markdownify` | HTML → Markdown |
| `openpyxl` / `xlrd` | XLSX / XLS conversion |
| `python-pptx` | PPTX conversion |
| `ebooklib` | EPUB conversion |
| `striprtf` | RTF conversion |
| `odfpy` | ODT conversion |
| `tiktoken` | Exact token counting (optional but recommended) |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `TesseractNotFoundError` | Tesseract is not on PATH. See Prerequisites §2. |
| `PDFInfoNotInstalledError` | Poppler not found. See Prerequisites §3. |
| `ImportError: No module named 'fitz'` | Run `pip install PyMuPDF` |
| App opens but won't accept drops | Ensure `tkinterdnd2` is installed: `pip install tkinterdnd2` |
| Scanned PDF produces garbled text | OCR quality depends on scan resolution. 300 DPI recommended. |
| Token toggle greyed out | tiktoken not installed. Run `pip install tiktoken` |
| EPUB / RTF / ODT fails with missing library | Run `pip install -r requirements.txt` to install all optional deps |

---

## File Structure

```
doc2md\
  app.py              — Desktop UI (CustomTkinter + tkinterdnd2)
  converter.py        — Conversion logic and format routing
  google_drive.py     — Browser-based Google Drive export helper
  requirements.txt    — All dependencies
  README.md
  tests\
    test_converter.py
    test_google_drive.py
```
