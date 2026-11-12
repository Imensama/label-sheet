# -*- coding: utf-8 -*-
"""PyInstaller 打包入口：带参数走命令行，不带参数开图形界面。

窗口模式下没有控制台，这里把 stdout/stderr 重定向到日志文件，
异常时弹窗提示并把 traceback 写进日志，方便使用者反馈问题。
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback


def _log_path() -> str:
    base = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    return os.path.join(base, "ulpp.log")


def _redirect_streams() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        path = os.path.join(tempfile.gettempdir(), "ulpp.log")
        stream = open(path, "a", encoding="utf-8", buffering=1)
    except Exception:  # pragma: no cover
        import io

        stream = io.StringIO()
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def _language_from_argv():
    for i, arg in enumerate(sys.argv):
        if arg == "--lang" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if arg.startswith("--lang="):
            return arg.split("=", 1)[1]
    return None


def _show_error(err: str) -> None:
    try:
        from ulpp.i18n import set_language, tr

        set_language(_language_from_argv())
        title = tr("entry.error_title")
        message = tr("entry.error_body", error=err)
    except Exception:  # pragma: no cover - 包都坏了就退回双语提示
        title = "通用标签打印平台 / Universal Label Printing Platform"
        message = f"程序出错了 / Something went wrong:\n\n{err}\n\n详细日志 / Details: ulpp.log"
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:  # pragma: no cover
        pass


def main() -> int:
    _redirect_streams()
    if not getattr(sys, "frozen", False):
        # 直接跑源码时，把 src 加进搜索路径
        here = os.path.dirname(os.path.abspath(__file__))
        src = os.path.join(os.path.dirname(here), "src")
        if src not in sys.path:
            sys.path.insert(0, src)
    try:
        from ulpp.__main__ import main as app_main

        return app_main()
    except SystemExit:
        raise
    except Exception:
        tb = traceback.format_exc()
        try:
            with open(_log_path(), "a", encoding="utf-8") as fh:
                fh.write(tb + "\n")
        except Exception:
            pass
        _show_error(tb.strip().splitlines()[-1])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
