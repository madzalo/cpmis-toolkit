# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for CPMIS Toolkit
# Build a single-file Windows exe that prompts for DHIS2 credentials at runtime

import tomllib
import os

with open('pyproject.toml', 'rb') as f:
    _pyproject = tomllib.load(f)
APP_VERSION = _pyproject['project']['version']

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        # Bundle the malawi_districts.csv for Phase 1
        (os.path.join('src', 'cleanup', 'malawi_districts.csv'), os.path.join('cleanup')),
    ],
    hiddenimports=[
        'requests',
        'dotenv',
        'rich',
        'rich.console',
        'rich.table',
        'rich.progress',
        'rich.box',
        # Shared modules
        'shared',
        'shared.ui',
        'shared.auth',
        'shared.settings',
        'shared.dhis2_client',
        'shared.ou_picker',
        'shared.id_utils',
        # Cleanup modules
        'cleanup',
        'cleanup.phase1',
        'cleanup.phase2',
        # Transfer modules
        'transfer',
        # Sync modules
        'sync',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'pytest',
        'IPython',
        'jupyter',
        'notebook',
        'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=f'CPMIS Toolkit v{APP_VERSION.replace(".", "-")}.exe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='cpmis.ico',
)
