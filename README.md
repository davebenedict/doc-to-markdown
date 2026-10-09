# Doc → Markdown Converter

Convert documents into clean Markdown for LLMs and RAG pipelines. The repository contains two desktop apps and an optional browser-based Flask app.

## Choose a desktop app

| App | Interface | Platforms | Runtime requirements |
|-----|-----------|-----------|----------------------|
| **Native Windows** | CustomTkinter desktop UI with drag-and-drop | Windows | The downloaded executable does not require Python. Tesseract is needed for image/scanned-PDF OCR. |
| **Electron** | Electron desktop window with a bundled Flask/Python backend | Windows, macOS, Linux | Packaged app needs no Python installation. Tesseract is needed for OCR. Python and build dependencies are needed to run from source or create a release. |

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

The executable is created at `dist\DocToMarkdown.exe`. Its image and scanned-PDF OCR requires Tesseract to be installed separately and available on `PATH`; source runs can alternatively use Surya OCR if installed in the app's Python environment.

## Electron app

The packaged Electron app includes a PyInstaller-bundled Flask backend and Python dependencies, so end users do not need to install Python or pip packages. Tesseract remains a separate system prerequisite for OCR.

To run from source on Windows, install the Python/build dependencies and Node packages from the repository root:

```powershell
cd electron\python
py -3 -m pip install -r requirements.txt
cd ..\electron
npm install
npm start
```

To build a release, run `npm run build` from `electron\electron`. The build script creates the backend bundle for the current OS/architecture and then packages it with Electron. Artifacts are written to `electron\electron\dist`:

- Windows: NSIS installer and portable executable
- macOS: DMG
- Linux: AppImage and DEB

Build on the same operating system and architecture as the target. Install Tesseract on target computers only if OCR is needed; it is not bundled.

### macOS setup (Electron)

Install Homebrew if needed, then use Terminal to install Node.js, Python, and Tesseract:

```sh
brew install node python@3.13 tesseract
```

From the repository root, install the Python build dependencies and run the app in development mode:

```sh
cd electron/python
python3 -m pip install -r requirements.txt
cd ../electron
npm install
npm start
```

The `npm run build` command automatically freezes the backend before creating the DMG. Python is required to build or run from source, but not to run the packaged DMG.

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
| `.pdf` | PyMuPDF extracts text and renders low-text pages individually; scanned pages require a working OCR provider |
| `.jpg` `.jpeg` `.png` `.tiff` `.tif` `.bmp` | Requires a working OCR provider to create Markdown |
| `.docx` | Preserves headings, lists, and tables; extracts embedded images and OCR text when available |
| `.html` `.htm` | Removes markup and converts structure to Markdown |
| `.xlsx` | Converts worksheets to Markdown tables, preserving formulas and cached values when available |
| `.xls` | Converts stored cell values to Markdown tables; formula expressions are unavailable through the current reader |
| `.pptx` | Converts slides to Markdown sections, extracts native chart data to tables, and preserves images with OCR text when available |
| `.csv` | Converts rows to Markdown tables |
| `.epub` | Converts chapters to Markdown sections |
| `.rtf` `.odt` `.xml` `.json` | Extracts and formats document content as Markdown |

Raster image files and scanned PDF pages require a working OCR provider; conversion stops without writing Markdown if OCR is unavailable or fails. Images embedded in DOCX/PPTX and HTML/EPUB are saved in a sibling `<markdown-file-stem>_images/` folder and linked from the Markdown; OCR text is added when available, otherwise the image is preserved with a note. Desktop apps save the Markdown and image folder together; the optional browser app returns a ZIP containing both when assets were extracted. External HTML image links remain unchanged. OCR can recover text in an image, but it does not generate semantic captions for non-text diagrams; those need a vision-capable downstream RAG pipeline.

For PDFs, the token-savings display compares extracted/OCR text with Markdown using `tiktoken` when available. Other formats use a rough file-size estimate for the source baseline; this is an estimate, not a measure of RAG retrieval quality.

## OCR prerequisites

- **Tesseract OCR:** [Windows installer](https://github.com/UB-Mannheim/tesseract/wiki). Add the installation directory to `PATH`.
Verify the installation with `tesseract --version`.

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
