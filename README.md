# Doc → Markdown Converter

A native Windows desktop app that converts scanned PDFs, native PDFs, images, Word documents, and Google Docs HTML exports into Markdown files via drag-and-drop.

---

## Supported Formats

| Format | Strategy |
|--------|----------|
| `.pdf` (text layer) | Direct text extraction via PyMuPDF; headings inferred from font size |
| `.pdf` (scanned/image) | pdf2image renders pages → Tesseract OCR |
| `.jpg` `.jpeg` `.png` `.tiff` `.tif` `.bmp` | Tesseract OCR |
| `.docx` | python-docx; preserves heading styles, lists, tables |
| `.html` `.htm` | markdownify (Google Docs export-ready) |
| `.doc` | **Not supported** — open in Word and save as `.docx` first |

---

## Prerequisites

### 1. Python 3.9+

Download from https://www.python.org/downloads/windows/

Verify: `python --version`

### 2. Tesseract OCR (required for scanned PDFs and images)

1. Download the installer from: https://github.com/UB-Mannheim/tesseract/wiki
   - Recommended: `tesseract-ocr-w64-setup-5.x.x.exe`
2. Run the installer (default path: `C:\Program Files\Tesseract-OCR\`)
3. During install, check **"Add to PATH"** or add it manually:
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

---

## Usage

1. **Drop a file** onto the drop zone, or click the zone to browse.
2. The status bar shows conversion progress (page-by-page for OCR).
3. Converted files appear in the **Converted Files** list:
   - **Open** — opens the `.md` file in your default Markdown editor.
   - **Reveal** — opens Windows Explorer with the file selected.
4. To change the output folder, click **Browse** next to "Output folder". Click **Clear** to reset to same-folder-as-input.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `TesseractNotFoundError` | Tesseract is not on PATH. See Prerequisites §2. |
| `PDFInfoNotInstalledError` | Poppler not found. See Prerequisites §3. |
| `ImportError: No module named 'fitz'` | Run `pip install PyMuPDF` |
| App opens but won't accept drops | Ensure `tkinterdnd2` is installed: `pip install tkinterdnd2==0.3.0` |
| Scanned PDF produces garbled text | OCR quality depends on scan resolution. 300 DPI recommended. |

---

## File Structure

```
E:\Source\doc2md\
  app.py          — Desktop UI (CustomTkinter + tkinterdnd2)
  converter.py    — Conversion logic (format routing)
  requirements.txt
  README.md
```
