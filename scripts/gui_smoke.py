# -*- coding: utf-8 -*-
"""GUI 冒烟测试：建窗口 → 检查控件 → 切换规格 → 销毁。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))


def main() -> int:
    from label_sheet.gui import App, _HAS_DND, TkinterDnD
    import tkinter as tk

    root = TkinterDnD.Tk() if _HAS_DND else tk.Tk()
    app = App(root)
    root.update_idletasks()
    print("title:", root.title())
    print("preset:", app.preset_key.get())
    print("grid:", {k: v.get() for k, v in app.grid_vars.items()})
    # 切一个预设
    app.preset_key.set("24格 70×37（3×8）")
    app._apply_preset(app.preset_key.get())
    root.update()
    print("after switch:", {k: v.get() for k, v in app.grid_vars.items()})
    spec = app._grid()
    print("spec:", spec.cols, spec.rows, spec.cell_w, spec.cell_h, spec.pitch_x, spec.pitch_y)
    app.text_box.insert("1.0", "急件 A-01 |2\n返修件")
    root.destroy()
    print("GUI SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
