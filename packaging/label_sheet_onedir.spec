# -*- mode: python ; coding: utf-8 -*-
"""本地验证用的 ``--onedir`` 打包配置。

官方 Release 仍用 ``label_sheet.spec`` 打单文件 exe；单文件在本机沙箱里解压到临时目录会失败，
所以本地冒烟测试用这个 onedir 配置（产物：dist/标签排版/标签排版.exe）。
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(SPECPATH)) if "SPECPATH" in globals() else os.getcwd()
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

a = Analysis(
    [os.path.join(ROOT, "packaging", "entry.py")],
    pathex=[SRC],
    binaries=[],
    datas=[(os.path.join(SRC, "label_sheet", "locales"), "label_sheet/locales")],
    hiddenimports=["tkinter", "tkinter.filedialog", "tkinter.messagebox", "tkinter.ttk"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["numpy", "pandas", "matplotlib", "scipy", "pytest", "PyInstaller"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="标签排版",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="标签排版",
)
