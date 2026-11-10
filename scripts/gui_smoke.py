# -*- coding: utf-8 -*-
"""GUI 冒烟测试：建窗口 → 检查控件 → 销毁（不进 mainloop）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))


def main() -> int:
    try:
        from label_sheet.gui import App, _HAS_DND, TkinterDnD
        import tkinter as tk
    except Exception as exc:  # pragma: no cover
        print("IMPORT FAIL:", exc)
        return 1
    try:
        root = TkinterDnD.Tk() if _HAS_DND else tk.Tk()
    except Exception as exc:  # pragma: no cover
        print("NO DISPLAY:", exc)
        return 2
    app = App(root)
    root.update_idletasks()
    root.update()
    print("title:", root.title())
    print("files:", len(app.files))
    print("grid vars:", {k: v.get() for k, v in app.grid_vars.items()})
    spec = app._grid()
    print("grid ok:", spec.cols, spec.rows, spec.cell_w, spec.cell_h, spec.pitch_x, spec.pitch_y)
    root.destroy()
    print("GUI SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
