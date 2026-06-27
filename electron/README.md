# Doc to Markdown Converter v2.0 (Electron)

Cross-platform desktop app for converting documents to Markdown.

## Features

- Cross-platform (Mac, Windows, Linux)
- Same conversion functionality as v1.0
- Native desktop interface via Electron
- Drag-and-drop file upload
- Browser-based UI embedded in Electron window

## Installation

### Prerequisites

1. **Node.js** (v18 or higher)
   - Download from https://nodejs.org/

2. **Python 3.9+**
   - Download from https://www.python.org/downloads/

3. **Python dependencies**
   ```bash
   cd python
   pip install -r requirements.txt
   ```

4. **Node dependencies**
   ```bash
   cd electron
   npm install
   ```

## Running the App

### Development mode
```bash
cd electron
npm start
```

### Building for production
```bash
cd electron
npm run build
```

Build artifacts will be in `electron/dist/`.

## Project Structure

```
doc2md-electron/
├── electron/
│   ├── main.js (Electron main process)
│   ├── preload.js (Bridge between main and renderer)
│   └── package.json
├── python/
│   ├── web_app.py (Flask backend)
│   ├── converter.py (Conversion logic)
│   ├── google_drive.py (Google Drive integration)
│   └── requirements.txt
└── ui/
    └── templates/index.html (Web UI)
```

## Architecture

- Electron spawns Python Flask backend
- Flask backend runs on localhost:5000
- Electron loads Flask app in embedded browser window
- Python backend handles all document conversion
- Electron handles native desktop features

## v1.0 vs v2.0

- **v1.0**: Windows-only native app (CustomTkinter)
- **v2.0**: Cross-platform Electron app (Mac/Windows/Linux)

Both versions share the same conversion logic and web UI.
