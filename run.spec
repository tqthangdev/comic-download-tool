# run.spec
import playwright
from pathlib import Path

block_cipher = None

# Tìm thư mục driver thực tế của playwright đã cài trên máy build
playwright_driver_path = Path(playwright.__file__).parent / "driver"

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('config.json', '.'),
        (str(playwright_driver_path), 'playwright/driver'),   # bắt buộc để playwright driver chạy được
    ],
    hiddenimports=[
        'playwright.async_api',
        'playwright.__main__',
        'qasync',
        'aiohttp',
        'bs4',
        'lxml',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ComicDownloadTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=['assets/icon.ico'],
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
    name='ComicDownloadTool',
)