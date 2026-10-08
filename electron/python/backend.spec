from pathlib import Path

root = Path(SPECPATH)

a = Analysis(
    [str(root / "web_app.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "templates"), "templates")],
    hiddenimports=[
        "google_drive",
        "PIL",
        "PIL.Image",
        "pytesseract",
        "pdf2image",
        "fitz",
        "docx",
        "markdownify",
        "openpyxl",
        "xlrd",
        "pptx",
        "ebooklib",
        "striprtf",
        "striprtf.striprtf",
        "odf",
        "tiktoken",
        "tiktoken_ext",
        "tiktoken_ext.openai_public",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="doc2md-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="doc2md-backend",
)
