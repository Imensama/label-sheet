# -*- coding: utf-8 -*-
"""GUI 冒烟测试：建窗口 → 检查中文/英文静态文案 → 切换语言 → 截图 → 销毁。"""

import os
import re
import sys
import tempfile
import tkinter as tk
from tkinter import ttk

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _walk(widget):
    stack = [widget]
    while stack:
        current = stack.pop()
        stack.extend(current.winfo_children())
        yield current


def visible_texts(widget):
    """收集所有控件上会显示出来的文字（含 textvariable 和下拉选项）。"""
    texts = []
    for w in _walk(widget):
        try:
            text = w.cget("text")
        except Exception:
            text = ""
        if text:
            texts.append(str(text))
        try:
            var = w.cget("textvariable")
        except Exception:
            var = ""
        if var:
            try:
                value = w.getvar(str(var))
            except Exception:
                value = ""
            if value:
                texts.append(str(value))
        if isinstance(w, ttk.Combobox):
            try:
                texts.extend(str(v) for v in w.cget("values"))
            except Exception:
                pass
    return texts


def screenshot(root, path):
    try:
        from PIL import ImageGrab

        root.lift()
        root.attributes("-topmost", True)
        root.update()
        # 高 DPI 下 Tk 用逻辑坐标，ImageGrab 按物理像素抓图，这里换算一下
        shot = ImageGrab.grab()
        fx = shot.size[0] / root.winfo_screenwidth()
        fy = shot.size[1] / root.winfo_screenheight()
        x, y = root.winfo_rootx(), root.winfo_rooty()
        w, h = root.winfo_width(), root.winfo_height()
        box = (int(x * fx), int(y * fy), int((x + w) * fx), int((y + h) * fy))
        ImageGrab.grab(bbox=box).save(path)
        root.attributes("-topmost", False)
        print("screenshot:", path)
    except Exception as exc:  # pragma: no cover - 截图不是必须
        print("screenshot skipped:", exc)


def main() -> int:
    from label_sheet.gui import App, _HAS_DND, TkinterDnD
    from label_sheet.i18n import current_language, set_language

    set_language("zh_CN")
    root = TkinterDnD.Tk() if _HAS_DND else tk.Tk()
    app = App(root)
    root.update()
    print("zh title:", root.title())
    print("zh start:", app.start_btn.cget("text"))
    zh_texts = visible_texts(root)
    assert any(CJK_RE.search(t) for t in zh_texts), "中文界面应该有中文"
    shot_dir = os.environ.get("GUI_SMOKE_SHOT_DIR", tempfile.gettempdir())
    screenshot(root, os.path.join(shot_dir, "label_sheet_gui_zh.png"))

    app.text_box.insert("1.0", "TEST A-01 |2\nREWORK")
    app._switch_language("en_US")
    root.update()
    en_texts = visible_texts(root)
    # 语言下拉里的“中文”和“语言 / Language”是故意保留的：
    # 两个语言名用本语言写，标签固定中英双语，方便任何系统切回来
    allowed_cjk = {"中文", "语言 / Language"}
    leftovers = sorted({t for t in en_texts if CJK_RE.search(t)} - allowed_cjk)
    assert not leftovers, f"英文界面仍有中文：{leftovers}"
    assert "Generate" in en_texts, en_texts
    assert "English" in en_texts, "语言下拉里没有 English"
    assert "语言 / Language" in en_texts, "语言标签不是中英双语"
    assert "45 labels 40×30 (5×9, common)" in en_texts, "英文预设名没生效"
    assert app.text_box.get("1.0", "end-1c") == "TEST A-01 |2\nREWORK", "切换语言丢了文字"
    assert app.base_name.get() == "label", app.base_name.get()
    log_text = app.log_text.get("1.0", "end-1c")
    assert "{lang}" not in log_text, log_text
    assert "UI language switched to English." in log_text, log_text
    print("en title:", root.title())
    print("en start:", app.start_btn.cget("text"))
    print("en status:", app.status.get())
    print("en language:", current_language())
    screenshot(root, os.path.join(shot_dir, "label_sheet_gui_en.png"))

    app._switch_language("zh_CN")
    root.update()
    assert any(CJK_RE.search(t) for t in visible_texts(root)), "切回中文失败"
    assert app.text_box.get("1.0", "end-1c") == "TEST A-01 |2\nREWORK", "切回中文丢了文字"
    assert app.base_name.get() == "标签", app.base_name.get()
    print("back title:", root.title())
    print("GUI SMOKE OK")
    root.destroy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
