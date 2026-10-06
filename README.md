# Doc → Markdown Converter

Convert documents into clean Markdown for LLMs and RAG pipelines. The repository contains two desktop apps and an optional browser-based Flask app.

## Choose a desktop app

| App | Interface | Platforms | Runtime requirements |
|-----|-----------|-----------|----------------------|
| **Native Windows** | CustomTkinter desktop UI with drag-and-drop | Windows | The downloaded executable does not require Python. Tesseract and Poppler are needed for image/scanned-PDF OCR. |
| **Electron** | Electron desktop window with a Flask/Python backend | Windows, macOS, Linux | Node.js 18+, Python 3.9+, and the Python dependencies installed on the computer. The package includes backend source, not a Python runtime. |

Both desktop apps support document conversion, output-folder selection, token estimates, and Google Drive URL conversion. The Electron app saves conversions directly to the selected output folder; without one, it uses the user's Downloads folder. Its optional date subfolder groups output by date.

## Native Windows app

**Download:** [DocToMarkdown.exe](https://drive.google.com/file/d/1lqGdUWcEciDkeU9_fxH5FDo7XGxEJLVp/view?usp=sharing)

To run from source, from the repository root:

```powershell
py -m pip install -r requirements.txt
py app.py
```

To build the standalone executable:

```powershell
py -m PyInstaller --noconfirm app.spec
```

The executable is created at `dist\DocToMarkdown.exe`. OCR for scanned PDFs and images requires Tesseract and Poppler to be installed separately and available on `PATH`.

## Electron app

Electron provides the desktop window; Python runs the local Flask conversion backend. To install dependencies and run in development mode from the repository root:

```powershell
cd electron\python
py -m pip install -r requirements.txt
cd ..\electron
npm install
npm start
```

To build for the current platform, run `npm run build` from `electron\electron`. Artifacts are written to `electron\electron\dist`:

- Windows: NSIS installer and portable executable
- macOS: DMG
- Linux: AppImage and DEB

Python and the dependencies in `electron\python\requirements.txt` must also be installed on the target computer. Tesseract and Poppler are required for OCR features.

## Optional browser app

The repository root also includes a Flask web interface. Install the root Python requirements, then run:

```powershell
py -m pip install -r requirements.txt
py web_app.py
```

Open `http://localhost:5000` in a browser.

## Supported formats

| Format | Conversion method |
|--------|-------------------|
| `.pdf` | PyMuPDF text extraction; scanned pages use Poppler and Tesseract OCR |
| `.jpg` `.jpeg` `.png` `.tiff` `.tif` `.bmp` | Tesseract OCR |
| `.docx` | Preserves headings, lists, and tables |
| `.html` `.htm` | Removes markup and converts structure to Markdown |
| `.xlsx` `.xls` | Converts worksheets to Markdown tables |
| `.pptx` | Converts slides to Markdown sections |
| `.csv` | Converts rows to Markdown tables |
| `.epub` | Converts chapters to Markdown sections |
| `.rtf` `.odt` `.xml` `.json` | Extracts and formats document content as Markdown |

The token-savings display uses `tiktoken` when available and a file-size estimate otherwise.

## OCR prerequisites

- **Tesseract OCR:** [Windows installer](https://github.com/UB-Mannheim/tesseract/wiki). Add the installation directory to `PATH`.
- **Poppler:** [Windows releases](https://github.com/oschwartz10612/poppler-windows/releases). Add its `Library\bin` directory to `PATH`.

Verify installations with `tesseract --version` and `pdftoppm -v`.

## Project layout

```text
doc2md/
  app.py, converter.py, google_drive.py, web_app.py   Native Windows and browser apps
  requirements.txt                                    Root Python dependencies
  app.spec                                            PyInstaller config for native Windows app
  electron/
    electron/                                         Electron main process and package config
    python/                                           Flask backend, converter, and HTML UI
    generate_icon.py                                  Regenerates Electron platform icons
```
