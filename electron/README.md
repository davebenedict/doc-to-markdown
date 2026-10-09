# Doc to Markdown Converter — Electron

Cross-platform desktop app with an Electron interface and a PyInstaller-bundled Flask/Python backend.

## Requirements

- Node.js 18 or later to install, run, or build the Electron project.
- Python 3.9 or later and the packages in `python/requirements.txt` to run from source or create a release.
- Tesseract on the target computer for image and scanned-PDF OCR. It is an external system tool and is not bundled.

The packaged installer bundles Python and the backend dependencies; end users do not need Python or pip packages installed.

## Run from source

From this directory (`doc2md/electron`), install the Python dependencies first.

Windows PowerShell:

```powershell
cd python
py -3 -m pip install -r requirements.txt
cd ..\electron
npm install
npm start
```

macOS or Linux:

```sh
cd python
python3 -m pip install -r requirements.txt
cd ../electron
npm install
npm start
```

## Build installers

Run the build on the target OS and architecture. `npm run build` first creates a PyInstaller backend bundle, then packages it with Electron:

```sh
cd electron
npm run build
```

Artifacts are written to `electron/dist/` relative to this directory:

- Windows: NSIS installer and portable executable
- macOS: DMG
- Linux: AppImage and DEB

## Architecture

- Electron provides the desktop window, native file dialogs, and file open/reveal actions.
- The packaged app launches the bundled Flask backend; development mode launches Python from `python/web_app.py`.
- Converted files are saved to the selected output folder, or Downloads if none is selected.
- Tesseract must be installed separately for OCR.

## Project structure

```text
electron/
  electron/             Electron main process, preload, and package/build config
  python/               Flask backend, converter, Google Drive helper, and HTML template
    backend.spec        PyInstaller configuration for the bundled backend
    requirements.txt    Backend and build dependencies
  tests/                Flask/backend tests
```
