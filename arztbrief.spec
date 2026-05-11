# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spec für die Arztbrief-App (Windows, onedir-Bundle)."""

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# pypdfium2 hat native DLLs — vollständig einsammeln
_pdf_datas, _pdf_binaries, _pdf_hidden = collect_all("pypdfium2")

a = Analysis(
    ["backend/launcher.py"],
    pathex=["backend"],
    binaries=_pdf_binaries,
    datas=[
        # Prompt-Dateien und Lernlog-Templates
        ("backend/workflows", "workflows"),
        ("backend/skills", "skills"),
        # Gebautes React-Frontend
        ("frontend/dist", "frontend_dist"),
        *_pdf_datas,
    ],
    hiddenimports=[
        # uvicorn internals
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # FastAPI / Starlette
        "fastapi",
        "fastapi.staticfiles",
        "starlette.staticfiles",
        # python-docx
        "docx",
        # openpyxl
        "openpyxl",
        "openpyxl.cell._writer",
        # email (stdlib, manchmal nicht automatisch erkannt)
        "email.mime.text",
        "email.mime.multipart",
        *_pdf_hidden,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "test", "tests"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="arztbrief",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Kein Terminal-Fenster
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="arztbrief",
)
