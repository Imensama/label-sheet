# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：生成单文件 exe。

在仓库根目录执行：
    pyinstaller packaging/label_sheet.spec --noconfirm
"""

import os
import sys

# PyInstaller 会注入 SPECPATH（spec 文件所在目录）
ROOT = os.path.dirname(os.path.abspath(SPECPATH)) if "SPECPATH" in globals() else os.getcwd()
SRC = os.path.join(ROOT, "src")
sys.path.insert(0, SRC)

block_cipher = None

a = Analysis(
    [os.path.join(ROOT, "packaging", "entry.py")],
    pathex=[SRC],
    binaries=[],
    datas=[],
    hiddenimports=["tkinter", "tkinter.filedialog", "tkinter.messagebox", "tkinter.ttk"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["numpy", "pandas", "matplotlib", "scipy", "pytest", "PyInstaller"],
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
    name="标签排版",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 不带黑框；带参数时仍可做命令行调用
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
