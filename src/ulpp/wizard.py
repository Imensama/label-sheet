# -*- coding: utf-8 -*-
"""位置校准向导（9 步）：看图问答，推出这台机器该怎么放纸。

设计取舍：
- 只解决**方向**（哪面朝上、哪条边朝里），不碰标签尺寸 —— 尺寸要靠扫描量，另做。
- 结论直接写回 ``PrinterProfile.feed`` + 偏移，不新增字段。
- 图和程序解耦：只读 ``assets/<皮肤>/<560|980>/*.png``，将来换渲染器重出 PNG 即可。
- 文案集中在本文件顶部的 ``TEXTS``（中英各一份），方便双语一起校对。
"""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk
from typing import Callable, Dict, Optional

from .calibration import make_orientation_pdf
from .i18n import current_language
from .sheets import PrinterProfile

TOTAL = 9
BASE_SCALING = 1.3345      # 设计稿按这个 Tk scaling 画的

TEXTS: Dict[str, Dict[str, str]] = {
    "zh_CN": {
        "title": "位置校准",
        "app": "通用标签打印平台",
        "theme": "外观：{name}",
        "light": "浅色",
        "mono": "黑白",
        "step_of": "{title}  ·  第 {n} 步 / 共 {total} 步",
        "cancel": "取消",
        "proto_note": "不写你的配置，随便点",
        "prev": "←  上一步",
        "next": "下一步  →",
        "next_print": "打好了，下一步  →",
        "next_fine": "微调一下  →",
        "save": "保存",
        "eyebrow": "{title} · 第 {n} 步",
        # 1
        "s1.title": "先告诉我是哪台机器",
        "s1.body": "校准结果按“打印机 + 纸盘”存一份。以后选这台机器，放纸方向会自动带出来。",
        "s1.tip": "不用真连打印机；型号随便填，能区分就行。",
        "s1.printer": "打印机型号",
        "s1.tray": "纸盘",
        # 2
        "s2.title": "在普通纸上写一个大大的 A",
        "s2.body": "拿一张普通 A4 纸，用笔在正面写一个大 A。\n\n写好后按“下一步”。",
        "s2.tip": "为什么用普通纸？为了不浪费胶纸。",
        "s2.cap": "一张普通纸（不要用胶纸）",
        # 3
        "s3.title": "确认 A 面朝上",
        "s3.body": "写着 A 的那一面就是正面。\n\n等一下放纸，这一面要朝上。",
        "s3.tip": "如果 A 写反了或者看不清，换一张重写更省事。",
        "s3.cap": "写着 A 的那面 = 正面",
        # 4
        "s4.title": "把纸平放在手送盘上",
        "s4.i1": "把手送盘翻下来（有的机器还要拉出延长板）。",
        "s4.i2": "纸平放上去，写着 A 的那面朝上。",
        "s4.i3": "蓝色那条边先伸进去，然后把盘推回去。",
        "s4.tip": "找不到手送盘？看打印机正面，能一张一张放纸的那个口；不要塞进下面的普通纸盒。",
        # 5
        "s5.title": "打一张方向测试页",
        "s5.body": "上面有一支很粗的 TOP 箭头、一个大 A、一条粗黑条，方便你看哪一面着了墨。",
        "s5.tip": "必须用普通纸、按 100% 实际大小打印；不要选“适应页面”。",
        "s5.cap": "方向测试页（普通纸）",
        "s5.btn": "生成测试页 PDF 并打开",
        "s5.again": "重新生成",
        "s5.done": "已生成：{path}\n用你的 PDF 阅读器打印这张（普通纸、100%），打完点“下一步”。",
        "s5.fail": "生成失败：{err}",
        # 6
        "s6.hint": "点一下你看到的那张",
        "s6.title": "再看一眼测试页",
        "s6.body": "把测试页拿在手上，看有字的这一面。\n\n字是打在你写了 A 的那一面，还是另一面？",
        "s6.tip": "A 面 = 你刚才放纸时朝上的那一面。",
        "s6.a": "字在写了 A 的那面",
        "s6.b": "字在另一面（翻过来才看到）",
        # 7
        "s7.hint": "点一下 TOP 箭头在的那条边",
        "s7.title": "TOP 箭头在哪条边？",
        "s7.body": "把测试页按你刚才放纸的方向摆好，看 TOP 箭头靠近哪条边。",
        "s7.tip": "不要转纸去凑答案 —— 按它现在躺着的样子看。",
        "s7.top": "上边", "s7.right": "右边", "s7.left": "左边", "s7.bottom": "下边",
        # 8
        "s8.title": "以后这台机器就这样放",
        "s8.tip": "换胶纸品牌、换纸盘，都要重新对一次；同一台机器不用再对。",
        "s8.again": "重新校准",
        "s8.note_down": "胶面朝下的机器（比如施乐 C8055 打标签），按上面这句话放就对了。",
        "s8.note_up": "胶面朝上的机器，按上面这句话放就对了。",
        # 9
        "s9.title": "最后：左右 / 上下微调",
        "s9.body": "打出来的标签如果整体偏了一点，在这里挪；不用再去改纸。",
        "s9.tip": "先打一张试，偏多少就填多少。负数往左/往上。",
        "s9.x": "左右 (mm)",
        "s9.y": "上下 (mm)",
        "s9.now": "当前：左右 {x:+.1f} mm，上下 {y:+.1f} mm",
        # 词表
        "feed.up": "正面朝上", "feed.down": "正面朝下",
        "edge.short": "短边朝前", "edge.long": "长边朝前",
    },
    "en_US": {
        "title": "Calibration",
        "app": "Universal Label Printing Platform",
        "theme": "Theme: {name}",
        "light": "Light", "mono": "Mono",
        "step_of": "{title}  ·  Step {n} of {total}",
        "cancel": "Cancel",
        "proto_note": "Your settings are not written yet — click freely",
        "prev": "←  Back",
        "next": "Next  →",
        "next_print": "Printed, next  →",
        "next_fine": "Fine-tune  →",
        "save": "Save",
        "eyebrow": "{title} · Step {n}",
        "s1.title": "Which printer is it?",
        "s1.body": "The result is saved per printer + tray. Next time you pick this printer, the feed direction comes back automatically.",
        "s1.tip": "No need for a real printer; any name that tells them apart works.",
        "s1.printer": "Printer", "s1.tray": "Tray",
        "s2.title": "Write a big A on plain paper",
        "s2.body": "Take a plain A4 sheet and write a big A on the front with a pen.\n\nPress Next when done.",
        "s2.tip": "Plain paper on purpose — no label stock wasted.",
        "s2.cap": "One plain sheet (not a label sheet)",
        "s3.title": "Confirm the A side faces up",
        "s3.body": "The side with the A is the front.\n\nWhen you load the sheet, this side faces up.",
        "s3.tip": "If the A looks wrong, just write a new sheet.",
        "s3.cap": "The side with the A = front",
        "s4.title": "Lay the sheet on the bypass tray",
        "s4.i1": "Fold the bypass tray down (some printers need the extension pulled out).",
        "s4.i2": "Lay the sheet on it, the A side facing up.",
        "s4.i3": "The blue edge goes in first, then push the tray back.",
        "s4.tip": "Can't find the tray? Look at the front of the printer for the slot that takes one sheet at a time — not the paper cassette below.",
        "s5.title": "Print an orientation test page",
        "s5.body": "It has a big TOP arrow, a big A, and a thick black bar, so you can tell which side got the ink.",
        "s5.tip": "Plain paper, 100% actual size — never “fit to page”.",
        "s5.cap": "Orientation test page (plain paper)",
        "s5.btn": "Generate test page PDF and open",
        "s5.again": "Generate again",
        "s5.done": "Saved: {path}\nPrint it from your PDF reader (plain paper, 100%), then press Next.",
        "s5.fail": "Failed: {err}",
        "s6.hint": "Tap the one you see",
        "s6.title": "Look at the test page",
        "s6.body": "Hold the test page, look at the printed side.\n\nIs the ink on the side where you wrote the A, or the other side?",
        "s6.tip": "A side = the side that faced up when you loaded it.",
        "s6.a": "Ink on the A side",
        "s6.b": "Ink on the other side (visible when flipped)",
        "s7.hint": "Tap the edge the TOP arrow is on",
        "s7.title": "Which edge is the TOP arrow on?",
        "s7.body": "Hold the test page the way you loaded it, and see which edge the TOP arrow is near.",
        "s7.tip": "Don't rotate the sheet to make the answer fit — look at it as it lies.",
        "s7.top": "Top", "s7.right": "Right", "s7.left": "Left", "s7.bottom": "Bottom",
        "s8.title": "Load it this way from now on",
        "s8.tip": "New label brand or new tray needs a new calibration; the same printer does not.",
        "s8.again": "Calibrate again",
        "s8.note_down": "For face-down printers (Xerox C8055 with labels), this is the way.",
        "s8.note_up": "For face-up printers, this is the way.",
        "s9.title": "Last step: left/right, up/down",
        "s9.body": "If the print sits a bit off, nudge it here instead of changing the sheet.",
        "s9.tip": "Print one, measure the offset, type it in. Negative moves left/up.",
        "s9.x": "Left/right (mm)", "s9.y": "Up/down (mm)",
        "s9.now": "Now: left/right {x:+.1f} mm, up/down {y:+.1f} mm",
        "feed.up": "front side up", "feed.down": "front side down",
        "edge.short": "short edge first", "edge.long": "long edge first",
    },
}

LIGHT = dict(
    name="light", bg="#F3F5F9", card="#FFFFFF", border="#E2E8F0", text="#1F2937",
    muted="#5B6574", accent="#2563EB", accent_text="#FFFFFF", soft="#EFF6FF",
    soft_text="#1E3A8A", paper="#FFFFFF", paper_line="#94A3B8", ink="#111827",
    chip="#E8EEF7", dot_off="#D3DBE6", dot_done="#9DB7E8", green="#16A34A",
    btn2="#FFFFFF",
)
MONO = dict(
    name="mono", bg="#FFFFFF", card="#FFFFFF", border="#111111", text="#000000",
    muted="#444444", accent="#000000", accent_text="#FFFFFF", soft="#F1F1F1",
    soft_text="#000000", paper="#FFFFFF", paper_line="#000000", ink="#000000",
    chip="#E9E9E9", dot_off="#CCCCCC", dot_done="#666666", green="#000000",
    btn2="#FFFFFF",
)


def _resources() -> Path:
    base = os.environ.get("_MEIPASS") or getattr(__import__("sys"), "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parent


def feed_from_answers(face: Optional[str], edge: Optional[str], fallback: str) -> str:
    """两个问题的答案 → PrinterProfile.feed 的四个值之一。

    face: ``"up"``（字打在写了 A 的那面）/ ``"down"``（打在另一面）
    edge: ``"short"``（TOP 箭头在上/下边）/ ``"long"``（在左/右边）
    """
    if face not in ("up", "down") or edge not in ("short", "long"):
        return fallback
    return "face_%s_%s" % (face, edge)


def feed_label(face: Optional[str], edge: Optional[str], lang: str) -> str:
    """结论页那句人话，例如“正面朝下 · 短边朝前”。"""
    tx = TEXTS.get(lang) or TEXTS["zh_CN"]
    face_key = "feed.up" if face == "up" else "feed.down"
    edge_key = "edge.long" if edge == "long" else "edge.short"
    return "%s · %s" % (tx[face_key], tx[edge_key])


class CalibrationWizard(tk.Toplevel):
    """9 步向导。保存时回调 on_save(feed, offset_x_mm, offset_y_mm)。"""

    def __init__(self, master, profile: PrinterProfile,
                 on_save: Optional[Callable[[str, float, float], None]] = None,
                 output_dir: Optional[str] = None):
        super().__init__(master)
        self.profile = profile
        self.on_save = on_save
        self.output_dir = output_dir or os.getcwd()
        self.lang = current_language() if current_language() in TEXTS else "zh_CN"
        self.TX = TEXTS[self.lang]
        self.z = max(1.0, round(float(self.tk.call("tk", "scaling")) / BASE_SCALING, 3))
        self.img_px = 980 if self.z >= 1.4 else 560
        self.theme_key = "light"
        self.step = 1
        self.face = None            # "up" / "down"
        self.edge = None            # "short" / "long"
        self.edge_pos = None
        self.images = {}
        self.anim = []
        self.anim_i = 0
        self.anim_job = None
        self.off_x = float(profile.offset_x_mm)
        self.off_y = float(profile.offset_y_mm)

        self.title(self.T("app"))
        self.configure(bg=LIGHT["bg"])
        self.geometry("%dx%d" % (self.S(1180), self.S(780)))
        self.transient(master)
        self.resizable(False, False)
        self.fam = ("Microsoft YaHei UI"
                    if "Microsoft YaHei UI" in tkfont.families() else "Segoe UI")
        self._build()
        self.grab_set()

    # ------------------------------------------------------------ 基础
    def T(self, key, **kw):
        s = self.TX.get(key, key)
        return s.format(**kw) if kw else s

    def S(self, v):
        return int(round(v * self.z))

    def f(self, size, bold=False):
        return (self.fam, size, "bold") if bold else (self.fam, size)

    def fp(self, px):
        return self.f(max(8, int(round(px / (BASE_SCALING * self.z)))))

    @property
    def TH(self):
        return LIGHT if self.theme_key == "light" else MONO

    def img(self, name):
        key = (self.theme_key, name)
        if key not in self.images:
            path = _resources() / "assets" / self.theme_key / str(self.img_px) / name
            self.images[key] = tk.PhotoImage(file=str(path))
        return self.images[key]

    def clear(self):
        if self.anim_job:
            self.after_cancel(self.anim_job)
            self.anim_job = None
        self.anim = []
        for w in self.winfo_children():
            w.destroy()

    def go(self, step):
        self.step = max(1, min(TOTAL, step))
        self.clear()
        self._build()

    def _build(self):
        T, S = self.TH, self.S
        self.configure(bg=T["bg"])
        head = tk.Frame(self, bg=T["bg"])
        head.pack(fill="x", padx=S(30), pady=(S(16), 0))
        tk.Label(head, text=self.T("app"), font=self.f(14, True), fg=T["text"],
                 bg=T["bg"]).pack(side="left")
        tk.Label(head, text=self.T("step_of", title=self.T("title"), n=self.step,
                                   total=TOTAL), font=self.f(10), fg=T["muted"],
                 bg=T["bg"]).pack(side="right")
        tk.Button(head, text=self.T("theme", name=self.T(T["name"])), font=self.f(9),
                  fg=T["text"], bg=T["btn2"], relief="flat", bd=0, padx=S(10), pady=S(4),
                  highlightthickness=1, highlightbackground=T["border"],
                  command=self.toggle_theme).pack(side="right", padx=(0, S(12)))

        dots = tk.Frame(self, bg=T["bg"])
        dots.pack(fill="x", padx=S(30), pady=(S(8), 0))
        for i in range(1, TOTAL + 1):
            fg = T["accent"] if i == self.step else (
                T["dot_done"] if i < self.step else T["dot_off"])
            tk.Label(dots, text="●", font=self.f(10), fg=fg, bg=T["bg"]).pack(side="left",
                                                                             padx=S(2))

        body = tk.Frame(self, bg=T["bg"])
        body.pack(fill="both", expand=True, padx=S(30), pady=(S(10), 0))
        self.left = tk.Frame(body, bg=T["card"], highlightthickness=1,
                             highlightbackground=T["border"],
                             width=self.img_px + S(24), height=self.img_px + S(28))
        self.left.pack(side="left", fill="y")
        self.left.pack_propagate(False)
        self.right = tk.Frame(body, bg=T["bg"])
        self.right.pack(side="left", fill="both", expand=True, padx=(S(34), 0))

        foot = tk.Frame(self, bg=T["bg"])
        foot.pack(fill="x", padx=S(30), pady=(S(12), S(16)))
        tk.Button(foot, text=self.T("cancel"), font=self.f(10), fg=T["muted"], bg=T["bg"],
                  relief="flat", bd=0, command=self.destroy).pack(side="left")
        tk.Label(foot, text=self.T("proto_note"), font=self.f(9), fg=T["muted"],
                 bg=T["bg"]).pack(side="left", padx=S(14))
        nxt = tk.Button(foot, text=self._next_label(), font=self.f(12, True),
                        fg=T["accent_text"], bg=T["accent"], relief="flat", bd=0,
                        padx=S(24), pady=S(10),
                        command=self.finish if self.step == TOTAL else self.next)
        nxt.pack(side="right")
        prev = tk.Button(foot, text=self.T("prev"), font=self.f(10), fg=T["text"],
                         bg=T["card"], relief="flat", bd=0, padx=S(16), pady=S(10),
                         highlightthickness=1, highlightbackground=T["border"],
                         command=lambda: self.go(self.step - 1))
        prev.pack(side="right", padx=(0, S(10)))
        if self.step == 1:
            prev.configure(state="disabled", fg=T["muted"])
        getattr(self, "step%d" % self.step)()

    def toggle_theme(self):
        self.theme_key = "mono" if self.theme_key == "light" else "light"
        self.go(self.step)

    def next(self):
        if self.step == 6 and not self.face:
            return
        if self.step == 7 and not self.edge:
            return
        self.go(self.step + 1)

    def _next_label(self):
        return {5: self.T("next_print"), 8: self.T("next_fine"),
                TOTAL: self.T("save")}.get(self.step, self.T("next"))

    # ------------------------------------------------------------ 右栏
    def textcol(self, title, body=None, tip=None):
        T, S = self.TH, self.S
        tk.Label(self.right, text=self.T("eyebrow", title=self.T("title"), n=self.step),
                 font=self.f(10, True), fg=T["accent"], bg=T["bg"]).pack(anchor="w")
        tk.Label(self.right, text=title, font=self.f(22, True), fg=T["text"], bg=T["bg"],
                 justify="left", wraplength=S(430)).pack(anchor="w", pady=(S(8), S(12)))
        if body:
            tk.Label(self.right, text=body, font=self.f(12), fg=T["text"], bg=T["bg"],
                     justify="left", wraplength=S(430), anchor="nw").pack(anchor="w", fill="x")
        if tip:
            self.tipbox(tip)

    def tipbox(self, text):
        T, S = self.TH, self.S
        box = tk.Frame(self.right, bg=T["soft"])
        box.pack(fill="x", pady=(S(16), 0))
        tk.Label(box, text=text, font=self.f(10), fg=T["soft_text"], bg=T["soft"],
                 justify="left", wraplength=S(400), anchor="w", padx=S(14),
                 pady=S(10)).pack(fill="x")

    def checklist(self, items):
        T, S = self.TH, self.S
        box = tk.Frame(self.right, bg=T["bg"])
        box.pack(anchor="w", fill="x", pady=(S(4), 0))
        for i, s in enumerate(items, start=1):
            row = tk.Frame(box, bg=T["bg"])
            row.pack(anchor="w", fill="x", pady=S(4))
            d = S(26)
            c = tk.Canvas(row, width=d, height=d, bg=T["bg"], highlightthickness=0)
            c.pack(side="left")
            c.create_oval(1, 1, d - 1, d - 1, fill=T["accent"], outline="")
            c.create_text(d / 2, d / 2, text=str(i), fill=T["accent_text"],
                          font=self.f(10, True))
            tk.Label(row, text=s, font=self.f(12), fg=T["text"], bg=T["bg"], justify="left",
                     wraplength=S(370), anchor="w").pack(side="left", padx=S(9))

    # ------------------------------------------------------------ 画纸
    def draw_sheet(self, canvas, x, y, w, h, mode="plain", label=None):
        T, S = self.TH, self.S
        canvas.create_rectangle(x + S(5), y + S(5), x + w + S(5), y + h + S(5),
                                fill=T["chip"], outline="")
        canvas.create_rectangle(x, y, x + w, y + h, fill=T["paper"],
                                outline=T["paper_line"], width=S(2))
        cx, cy = x + w / 2, y + h / 2
        col = T["chip"] if mode == "test_back" else T["ink"]
        canvas.create_text(cx, cy + h * 0.02, text="A", font=self.fp(int(h * 0.52)), fill=col)
        if mode.startswith("edge_"):
            self.draw_arrow(canvas, x, y, w, h, mode.split("_")[1], T)
        if mode == "faceup":
            cx2, cy2 = x + w * 0.74, y + h * 0.72
            r = min(w, h) * 0.09
            canvas.create_oval(cx2 - r, cy2 - r, cx2 + r, cy2 + r, fill=T["green"],
                               outline="")
            canvas.create_line(cx2 - r * 0.45, cy2, cx2 - r * 0.05, cy2 + r * 0.4,
                               cx2 + r * 0.5, cy2 - r * 0.42, fill="#FFFFFF", width=S(3))
        if label:
            canvas.create_text(cx, y + h + S(14), text=label, font=self.f(10), fill=T["muted"])

    def draw_arrow(self, canvas, x, y, w, h, pos, T):
        S = self.S
        cx, cy = x + w / 2, y + h / 2
        if pos == "top":
            canvas.create_text(cx, y + S(22), text="▲ TOP", font=self.f(11, True),
                               fill=T["ink"])
        elif pos == "bottom":
            canvas.create_text(cx, y + h - S(22), text="▼ TOP", font=self.f(11, True),
                               fill=T["ink"])
        elif pos == "left":
            canvas.create_text(x + S(10), cy, text="◀\nTOP", font=self.f(10, True),
                               fill=T["ink"], anchor="w", justify="left")
        else:
            canvas.create_text(x + w - S(10), cy, text="TOP\n▶", font=self.f(10, True),
                               fill=T["ink"], anchor="e", justify="right")

    def page_canvas(self, w, h, mode, label=None):
        c = tk.Canvas(self.left, width=self.S(w), height=self.S(h), bg=self.TH["card"],
                      highlightthickness=0)
        c.pack(pady=(self.S(6), 0))
        self.draw_sheet(c, self.S(26), self.S(18), self.S(w) - self.S(52),
                        self.S(h) - self.S(62), mode, label)
        return c

    def iso_view(self, name):
        im = self.img(name)
        lab = tk.Label(self.left, image=im, bg=self.TH["card"], bd=0)
        lab.image = im
        lab.pack(pady=(self.S(10), 0))
        return lab

    def bind_all(self, widget, fn):
        widget.bind("<Button-1>", fn)
        for c in widget.winfo_children():
            self.bind_all(c, fn)

    # ------------------------------------------------------------ 第 1 步
    def step1(self):
        T, S = self.TH, self.S
        self.iso_view("tray_plain.png")
        self.textcol(self.T("s1.title"), self.T("s1.body"), self.T("s1.tip"))
        form = tk.Frame(self.right, bg=T["bg"])
        form.pack(fill="x", pady=(S(16), 0), anchor="w")
        tk.Label(form, text=self.T("s1.printer"), font=self.f(10), fg=T["muted"],
                 bg=T["bg"]).pack(anchor="w")
        self.printer_var = tk.StringVar(value=self.profile.name or "Xerox C8055")
        tk.Entry(form, textvariable=self.printer_var, font=self.f(12), width=32,
                 relief="flat", highlightthickness=1,
                 highlightbackground=T["border"]).pack(anchor="w", pady=(S(4), S(12)),
                                                       ipady=S(5))
        tk.Label(form, text=self.T("s1.tray"), font=self.f(10), fg=T["muted"],
                 bg=T["bg"]).pack(anchor="w")
        self.tray_var = tk.StringVar(value=self.profile.tray or self.T("s1.tray"))
        ttk.Combobox(form, textvariable=self.tray_var, font=self.f(11), width=30,
                     values=["手送盘（Tray 5）", "Bypass tray", "Tray 1"],
                     state="readonly").pack(anchor="w", pady=(S(4), 0), ipady=S(3))

    # ------------------------------------------------------------ 第 2/3 步
    def step2(self):
        self.page_canvas(430, 420, "plain", self.T("s2.cap"))
        self.textcol(self.T("s2.title"), self.T("s2.body"), self.T("s2.tip"))

    def step3(self):
        self.page_canvas(430, 420, "faceup", self.T("s3.cap"))
        self.textcol(self.T("s3.title"), self.T("s3.body"), self.T("s3.tip"))

    # ------------------------------------------------------------ 第 4 步
    def step4(self):
        self.anim = [self.img("tray_f%02d.png" % i) for i in range(12)]
        lab = tk.Label(self.left, image=self.anim[0], bg=self.TH["card"], bd=0)
        lab.image = self.anim[0]
        lab.pack(pady=(self.S(10), 0))
        self.anim_lab = lab
        self.anim_i = 0
        self._tick_anim()
        self.textcol(self.T("s4.title"), None, None)
        self.checklist([self.T("s4.i1"), self.T("s4.i2"), self.T("s4.i3")])
        self.tipbox(self.T("s4.tip"))

    def _tick_anim(self):
        if not self.anim:
            return
        self.anim_i = (self.anim_i + 1) % len(self.anim)
        self.anim_lab.configure(image=self.anim[self.anim_i])
        self.anim_lab.image = self.anim[self.anim_i]
        self.anim_job = self.after(140, self._tick_anim)

    # ------------------------------------------------------------ 第 5 步
    def step5(self):
        T, S = self.TH, self.S
        self.page_canvas(430, 420, "plain", self.T("s5.cap"))
        self.textcol(self.T("s5.title"), self.T("s5.body"), self.T("s5.tip"))
        row = tk.Frame(self.right, bg=T["bg"])
        row.pack(anchor="w", pady=(S(16), 0), fill="x")
        self.print_btn = tk.Button(row, text=self.T("s5.btn"), font=self.f(11, True),
                                   fg=T["accent_text"], bg=T["accent"], relief="flat",
                                   bd=0, padx=S(18), pady=S(9), command=self.make_test_pdf)
        self.print_btn.pack(anchor="w")
        self.print_lbl = tk.Label(row, text="", font=self.f(9), fg=T["muted"], bg=T["bg"],
                                  justify="left", wraplength=S(420))
        self.print_lbl.pack(anchor="w", pady=(S(8), 0))

    def make_test_pdf(self):
        out = os.path.join(self.output_dir, "方向测试页.pdf")
        try:
            make_orientation_pdf(out, feed=self.profile.feed, lang=self.lang)
        except Exception as exc:                                    # noqa: BLE001
            self.print_lbl.configure(text=self.T("s5.fail", err=exc))
            return
        self.print_btn.configure(text=self.T("s5.again"))
        self.print_lbl.configure(text=self.T("s5.done", path=out))
        try:
            if os.name == "nt":
                os.startfile(out)                                   # type: ignore[attr-defined]
        except Exception:                                           # noqa: BLE001
            pass

    # ------------------------------------------------------------ 第 6 步
    def step6(self):
        T, S = self.TH, self.S
        tk.Label(self.left, text=self.T("s6.hint"), font=self.f(11), fg=T["muted"],
                 bg=T["card"]).pack(pady=(S(14), S(8)))
        wrap = tk.Frame(self.left, bg=T["card"])
        wrap.pack()
        self.cards6 = {}
        for i, (key, cap, mode) in enumerate((("up", self.T("s6.a"), "plain"),
                                              ("down", self.T("s6.b"), "test_back"))):
            w = tk.Frame(wrap, bg=T["card"], highlightthickness=2,
                         highlightbackground=T["border"], padx=S(7), pady=S(7))
            w.grid(row=0, column=i, padx=S(8))
            c = tk.Canvas(w, width=S(170), height=S(240), bg=T["card"], highlightthickness=0)
            c.pack()
            self.draw_sheet(c, S(16), S(12), S(138), S(190), mode)
            tk.Label(w, text=cap, font=self.f(10), fg=T["text"], bg=T["card"],
                     wraplength=S(150), justify="center").pack(pady=(S(5), S(2)))
            self.bind_all(w, lambda e, k=key: self.pick_face(k))
            self.cards6[key] = w
        self.textcol(self.T("s6.title"), self.T("s6.body"), self.T("s6.tip"))

    def pick_face(self, key):
        T = self.TH
        self.face = key
        for k, w in self.cards6.items():
            w.configure(highlightbackground=T["accent"] if k == key else T["border"],
                        highlightthickness=3 if k == key else 2)

    # ------------------------------------------------------------ 第 7 步
    def step7(self):
        T, S = self.TH, self.S
        tk.Label(self.left, text=self.T("s7.hint"), font=self.f(11), fg=T["muted"],
                 bg=T["card"]).pack(pady=(S(10), S(6)))
        grid = tk.Frame(self.left, bg=T["card"])
        grid.pack()
        self.cards7 = {}
        spots = [("top", 0, 0, self.T("s7.top")), ("right", 0, 1, self.T("s7.right")),
                 ("left", 1, 0, self.T("s7.left")), ("bottom", 1, 1, self.T("s7.bottom"))]
        for key, r, c_, cap in spots:
            w = tk.Frame(grid, bg=T["card"], highlightthickness=2,
                         highlightbackground=T["border"], padx=S(7), pady=S(7))
            w.grid(row=r, column=c_, padx=S(6), pady=S(6))
            c = tk.Canvas(w, width=S(140), height=S(190), bg=T["card"], highlightthickness=0)
            c.pack()
            self.draw_sheet(c, S(14), S(10), S(112), S(155), "edge_" + key)
            tk.Label(w, text=cap, font=self.f(10), fg=T["text"], bg=T["card"]).pack(
                pady=(S(3), 0))
            self.bind_all(w, lambda e, k=key: self.pick_edge(k))
            self.cards7[key] = w
        self.textcol(self.T("s7.title"), self.T("s7.body"), self.T("s7.tip"))

    def pick_edge(self, key):
        T = self.TH
        self.edge_pos = key
        self.edge = "short" if key in ("top", "bottom") else "long"
        for k, w in self.cards7.items():
            w.configure(highlightbackground=T["accent"] if k == key else T["border"],
                        highlightthickness=3 if k == key else 2)

    # ------------------------------------------------------------ 结论
    def feed_text(self):
        return feed_label(self.face, self.edge, self.lang)

    def feed_key(self):
        return feed_from_answers(self.face, self.edge, self.profile.feed)

    def step8(self):
        T, S = self.TH, self.S
        self.iso_view("tray_plain.png")
        self.textcol(self.T("s8.title"), None, self.T("s8.tip"))
        big = tk.Frame(self.right, bg=T["soft"])
        big.pack(fill="x", pady=(S(16), 0))
        tk.Label(big, text=self.printer_var.get(), font=self.f(9), fg=T["muted"],
                 bg=T["soft"]).pack(anchor="w", padx=S(16), pady=(S(10), 0))
        tk.Label(big, text=self.feed_text(), font=self.f(20, True), fg=T["soft_text"],
                 bg=T["soft"]).pack(anchor="w", padx=S(16), pady=(S(2), S(10)))
        note = self.T("s8.note_down" if self.face == "down" else "s8.note_up")
        tk.Label(self.right, text=note, font=self.f(10), fg=T["muted"], bg=T["bg"],
                 wraplength=S(420), justify="left").pack(anchor="w", pady=(S(8), 0))
        tk.Button(self.right, text=self.T("s8.again"), font=self.f(10), fg=T["text"],
                  bg=T["card"], relief="flat", bd=0, padx=S(14), pady=S(7),
                  highlightthickness=1, highlightbackground=T["border"],
                  command=lambda: self.go(1)).pack(anchor="w", pady=(S(14), 0))

    # ------------------------------------------------------------ 第 9 步
    def step9(self):
        T, S = self.TH, self.S
        self.iso_view("tray_plain.png")
        self.textcol(self.T("s9.title"), self.T("s9.body"), self.T("s9.tip"))
        box = tk.Frame(self.right, bg=T["bg"])
        box.pack(anchor="w", pady=(S(16), 0))
        self.off_x_var = tk.DoubleVar(value=self.off_x)
        self.off_y_var = tk.DoubleVar(value=self.off_y)
        for i, (lbl, var) in enumerate(((self.T("s9.x"), self.off_x_var),
                                        (self.T("s9.y"), self.off_y_var))):
            tk.Label(box, text=lbl, font=self.f(10), fg=T["muted"], bg=T["bg"]).grid(
                row=i, column=0, sticky="w", pady=S(5))
            tk.Spinbox(box, from_=-5.0, to=5.0, increment=0.5, textvariable=var, width=7,
                       font=self.f(12), relief="flat", highlightthickness=1,
                       highlightbackground=T["border"]).grid(row=i, column=1, padx=S(10),
                                                             pady=S(5), ipady=S(3))
        tk.Label(self.right, text=self.T("s9.now", x=self.off_x, y=self.off_y),
                 font=self.f(10), fg=T["muted"], bg=T["bg"]).pack(anchor="w", pady=(S(10), 0))

    def finish(self):
        feed = self.feed_key()
        try:
            ox, oy = float(self.off_x_var.get()), float(self.off_y_var.get())
        except (tk.TclError, ValueError):
            ox, oy = self.off_x, self.off_y
        if self.printer_var.get().strip():
            self.profile.name = self.printer_var.get().strip()
        if self.on_save:
            try:
                self.on_save(feed, ox, oy)
            except Exception:                                       # noqa: BLE001
                pass
        self.grab_release()
        self.destroy()
