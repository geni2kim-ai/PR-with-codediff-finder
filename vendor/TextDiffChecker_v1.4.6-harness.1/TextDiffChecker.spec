# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('syntax_db.json', '.')]
binaries = []
hiddenimports = []
tmp_ret = collect_all('tkinterdnd2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# 사용자 정규식 ReDoS 보호(regex 타임아웃)가 exe에서도 동작하도록 번들한다.
# 없으면 stdlib re로 조용히 폴백되어 시간 제한이 꺼진다.
try:
    tmp_rx = collect_all('regex')
    datas += tmp_rx[0]; binaries += tmp_rx[1]; hiddenimports += tmp_rx[2]
except Exception:
    hiddenimports.append('regex')


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    a.binaries,
    a.datas,
    [],
    name='TextDiffChecker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
)
