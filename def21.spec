# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['def21.py'],
    pathex=[],
    binaries=[],
    datas=[('resources/license.txt', 'resources'), ('icons/*', 'icons'), ('resources/Tesseract-OCR', 'resources/Tesseract-OCR'), ('support/*', 'support')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='def21',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='resources\\file_version.txt',
    icon=['icons\\desk-icon.ico'],
)
