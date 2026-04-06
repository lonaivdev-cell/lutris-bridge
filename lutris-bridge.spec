# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for lutris-bridge single-file executable."""

block_cipher = None

a = Analysis(
    ['lutris_bridge/cli.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'lutris_bridge',
        'lutris_bridge.artwork',
        'lutris_bridge.cli',
        'lutris_bridge.config',
        'lutris_bridge.lutris_config',
        'lutris_bridge.lutris_db',
        'lutris_bridge.script_gen',
        'lutris_bridge.state',
        'lutris_bridge.steam_appid',
        'lutris_bridge.steam_shortcuts',
        'lutris_bridge.sync',
        'yaml',
        'sqlite3',
        'requests',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PIL', 'Pillow', 'tkinter', '_tkinter', 'unittest', 'test'],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='lutris-bridge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    console=True,
)
