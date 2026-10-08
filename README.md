# Doc → Markdown Converter

Convert documents into clean Markdown for LLMs and RAG pipelines. The repository contains two desktop apps and an optional browser-based Flask app.

## Choose a desktop app

| App | Interface | Platforms | Runtime requirements |
|-----|-----------|-----------|----------------------|
| **Native Windows** | CustomTkinter desktop UI with drag-and-drop | Windows | The downloaded executable does not require Python. Tesseract and Poppler are needed for image/scanned-PDF OCR. |
| **Electron** | Electron desktop window with a bundled Flask/Python backend | Windows, macOS, Linux | Packaged app needs no Python installation. Tesseract and Poppler are needed for OCR. Python and build dependencies are needed to run from source or create a release. |

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

The packaged Electron app includes a PyInstaller-bundled Flask backend and Python dependencies, so end users do not need to install Python or pip packages. Tesseract and Poppler remain separate system prerequisites for OCR.

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

Build on the same operating system and architecture as the target. Install Tesseract and Poppler on target computers only if OCR is needed; these system tools are not bundled.

### macOS setup (Electron)

Install Homebrew if needed, then use Terminal to install Node.js, Python, Tesseract, and Poppler:

```sh
brew install node python@3.13 tesseract poppler
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
