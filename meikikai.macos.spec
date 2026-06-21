# -*- mode: python ; coding: utf-8 -*-

import re
from pathlib import Path

from PyInstaller.config import CONF


def _get_build_version() -> str:
    config_path = Path(CONF['specpath']) / 'src' / 'meikikai' / 'config' / 'config.py'
    match = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', config_path.read_text(encoding='utf-8'), re.M)
    if not match:
        return '0.0.0'

    version = match.group(1)
    if version.startswith('v.'):
        return version[2:]
    if version.startswith('v'):
        return version[1:]
    return version


BUILD_VERSION = _get_build_version()

a = Analysis(
    ['src/meikikai/main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('src/meikikai/resources/app_icon.icns', 'meikikai/resources'),
        ('src/meikikai/resources/menubar_icon.png', 'meikikai/resources'),
        ('src/meikikai/resources/menubar_icon.inactive.png', 'meikikai/resources'),
        ('src/meikikai/scripts/deconjugator.json', 'meikikai/scripts'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'keyboard',
        'Xlib',
        'pynput._util.win32',
        'pynput._util.xorg',
        'pynput.keyboard._win32',
        'pynput.keyboard._xorg',
        'pynput.keyboard._uinput',
        'pynput.mouse._win32',
        'pynput.mouse._xorg',
        'pynput.mouse._uinput',
        'mss.linux',
        'mss.linux.base',
        'mss.linux.xcb',
        'mss.linux.xcbhelpers',
        'mss.linux.xlib',
        'mss.linux.xshmgetimage',
        'mss.windows',
        'mss.windows.gdi',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MeikiKai',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MeikiKai',
)

app = BUNDLE(
    coll,
    name='MeikiKai.app',
    icon='src/meikikai/resources/app_icon.icns',
    bundle_identifier='dev.hectahertz.meikikai',
    version=BUILD_VERSION,
    info_plist={
        'CFBundleName': 'MeikiKai',
        'CFBundleDisplayName': 'MeikiKai',
        'CFBundleVersion': BUILD_VERSION,
        'NSScreenCaptureUsageDescription': 'MeikiKai needs Screen Recording access to OCR Japanese text visible on your screen.',
        'NSAppleEventsUsageDescription': 'MeikiKai restores focus to the previously active app after showing a popup.',
    },
)