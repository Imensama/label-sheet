# -*- coding: utf-8 -*-
"""图形界面：拖入/选入 PDF 或粘贴一段文字，一键排成 A4 不干胶标签。"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from . import __version__, APP_NAME
from .builder import build_all
from .cli import expand_inputs
from .config import GridSpec
from .parser import parse_many
from .presets import DEFAULT_PRESET_KEY, PRESETS, by_key, match_grid
from .textlabel import find_cjk_font, parse_text_block

try:  # 可选：装了 tkinterdnd2 就能拖拽
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore

    _HAS_DND = True
except Exception:  # pragma: no cover
    _HAS_DND = False
    DND_FILES = None
    TkinterDnD = None


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.files: List[str] = []
        self.out_dir = tk.StringVar()
        self.first_page_only = tk.BooleanVar(value=False)
        self.make_proof = tk.BooleanVar(value=True)
        self.make_csv = tk.BooleanVar(value=True)
        self.base_name = tk.StringVar(value="标签")
        self.status = tk.StringVar(value="就绪：添加 PDF 或在下面粘贴文字，然后点“开始生成”")
        self.preset_key = tk.StringVar(value=DEFAULT_PRESET_KEY)
        self.text_align = tk.StringVar(value="center")
        self.text_uniform = tk.BooleanVar(value=False)
        self.grid_vars = {
            "cols": tk.StringVar(value="5"),
            "rows": tk.StringVar(value="9"),
            "cell_w": tk.StringVar(value="40"),
            "cell_h": tk.StringVar(value="30"),
            "pitch_x": tk.StringVar(value="41.5"),
            "pitch_y": tk.StringVar(value="32"),
            "margin_top": tk.StringVar(value="6"),
            "inset": tk.StringVar(value="2"),
        }
        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self._loading_preset = False

        root.title(f"{APP_NAME} v{__version__}")
        root.geometry("1020x900")
        root.minsize(900, 760)
        self._build_ui()
        self._setup_dnd()
        self._apply_preset(DEFAULT_PRESET_KEY)
        root.after(120, self._poll_queue)

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}

        # 顶部：文件列表
        files_frame = ttk.LabelFrame(self.root, text="① PDF 文件（可选）")
        files_frame.pack(fill="both", expand=False, **pad)

        list_wrap = ttk.Frame(files_frame)
        list_wrap.pack(fill="both", expand=True, padx=8, pady=6)
        self.listbox = tk.Listbox(list_wrap, height=4, selectmode="extended", activestyle="none")
        sb = ttk.Scrollbar(list_wrap, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        btns = ttk.Frame(files_frame)
        btns.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(btns, text="添加 PDF…", command=self.add_pdfs).pack(side="left")
        ttk.Button(btns, text="添加文件夹…", command=self.add_folder).pack(side="left", padx=6)
        ttk.Button(btns, text="添加压缩包…", command=self.add_zip).pack(side="left")
        ttk.Button(btns, text="清空", command=self.clear_files).pack(side="right")
        ttk.Button(btns, text="移除选中", command=self.remove_selected).pack(side="right", padx=6)

        # 文字标签
        text_frame = ttk.LabelFrame(self.root, text="② 文字标签（一行一张，会自动换行/自动选字号）")
        text_frame.pack(fill="both", expand=True, **pad)
        self.text_box = tk.Text(text_frame, height=6, wrap="word", undo=True)
        self.text_box.pack(fill="both", expand=True, padx=8, pady=(6, 2))
        hint = ("提示：一行 = 一张标签；行尾写 |2 或 ×2 表示这张印 2 份（例：急件 A-01 |2）。"
                "留空就只排 PDF 里的卡片。")
        ttk.Label(text_frame, text=hint, foreground="#666").pack(anchor="w", padx=10, pady=(0, 6))
        trow = ttk.Frame(text_frame)
        trow.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(trow, text="对齐：").pack(side="left")
        for label, val in (("居中", "center"), ("左对齐", "left"), ("右对齐", "right")):
            ttk.Radiobutton(trow, text=label, variable=self.text_align, value=val).pack(side="left")
        ttk.Checkbutton(trow, text="统一字号（整批取最小那档，看起来更整齐）",
                        variable=self.text_uniform).pack(side="left", padx=16)

        # 选项
        opt = ttk.LabelFrame(self.root, text="③ 生成选项")
        opt.pack(fill="x", **pad)

        row1 = ttk.Frame(opt)
        row1.pack(fill="x", padx=8, pady=(6, 2))
        ttk.Label(row1, text="PDF 页码：").pack(side="left")
        ttk.Radiobutton(row1, text="全部页", variable=self.first_page_only, value=False).pack(side="left")
        ttk.Radiobutton(row1, text="仅第 1 页", variable=self.first_page_only, value=True).pack(side="left", padx=(6, 16))
        ttk.Checkbutton(row1, text="同时生成刀线校样版", variable=self.make_proof).pack(side="left")
        ttk.Checkbutton(row1, text="生成标签清单 CSV", variable=self.make_csv).pack(side="left", padx=12)

        row2 = ttk.Frame(opt)
        row2.pack(fill="x", padx=8, pady=2)
        ttk.Label(row2, text="输出目录：").pack(side="left")
        ttk.Entry(row2, textvariable=self.out_dir).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row2, text="浏览…", command=self.choose_out_dir).pack(side="left")

        row3 = ttk.Frame(opt)
        row3.pack(fill="x", padx=8, pady=2)
        ttk.Label(row3, text="文件名前缀：").pack(side="left")
        ttk.Entry(row3, textvariable=self.base_name, width=20).pack(side="left", padx=(4, 16))
        ttk.Label(row3, text="（输出“前缀_生产版.pdf”）", foreground="#666").pack(side="left")

        # 版式参数
        adv = ttk.LabelFrame(self.root, text="④ 胶贴规格与版式参数（换胶纸批次时才需要调）")
        adv.pack(fill="x", **pad)
        prow = ttk.Frame(adv)
        prow.pack(fill="x", padx=8, pady=(6, 2))
        ttk.Label(prow, text="规格预设：").pack(side="left")
        self.preset_cb = ttk.Combobox(prow, textvariable=self.preset_key, state="readonly",
                                      values=[p.key for p in PRESETS], width=30)
        self.preset_cb.pack(side="left", padx=4)
        self.preset_cb.bind("<<ComboboxSelected>>", lambda e: self._apply_preset(self.preset_key.get()))
        ttk.Label(prow, text="（选中后下面的格子尺寸会自动填好，也可以再手动改）",
                  foreground="#666").pack(side="left")

        grid = ttk.Frame(adv)
        grid.pack(fill="x", padx=8, pady=6)
        specs = [
            ("列数", "cols", 4), ("行数", "rows", 4), ("格宽", "cell_w", 6),
            ("格高", "cell_h", 6), ("列节距", "pitch_x", 6), ("行节距", "pitch_y", 6),
            ("上边距", "margin_top", 6), ("安全边", "inset", 6),
        ]
        for i, (label, key, width) in enumerate(specs):
            ttk.Label(grid, text=label).grid(row=0, column=i * 2, sticky="e", padx=(6, 2))
            ttk.Entry(grid, textvariable=self.grid_vars[key], width=width).grid(row=0, column=i * 2 + 1, sticky="w")

        # 日志
        logf = ttk.LabelFrame(self.root, text="⑤ 运行日志")
        logf.pack(fill="both", expand=True, **pad)
        self.log_text = tk.Text(logf, height=6, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=8, pady=6)

        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", padx=8, pady=(0, 10))
        ttk.Label(bottom, textvariable=self.status, foreground="#333").pack(side="left")
        self.open_btn = ttk.Button(bottom, text="打开输出文件夹", command=self.open_out_dir, state="disabled")
        self.open_btn.pack(side="right")
        self.start_btn = ttk.Button(bottom, text="开始生成", command=self.start)
        self.start_btn.pack(side="right", padx=8)
        self.progress = ttk.Progressbar(bottom, mode="determinate", length=200)
        self.progress.pack(side="right", padx=8)

    def _setup_dnd(self) -> None:
        if not _HAS_DND:
            return
        try:
            self.listbox.drop_target_register(DND_FILES)  # type: ignore[attr-defined]
            self.listbox.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            pass

    def _on_drop(self, event) -> None:  # pragma: no cover - 需要 GUI 交互
        paths = self.root.tk.splitlist(event.data)
        self._add_paths(list(paths))

    # ---------------- 规格 ----------------
    def _apply_preset(self, key: str) -> None:
        try:
            preset = by_key(key)
        except KeyError:
            return
        grid = preset.to_grid()
        self._loading_preset = True
        for k in ("cols", "rows"):
            self.grid_vars[k].set(str(getattr(grid, k)))
        for k in ("cell_w", "cell_h", "pitch_x", "pitch_y", "margin_top", "inset"):
            self.grid_vars[k].set(f"{getattr(grid, k):g}")
        self._loading_preset = False
        self._log(f"规格：{preset.title}")

    # ---------------- 文件管理 ----------------
    def _add_paths(self, paths: List[str]) -> None:
        found = expand_inputs(paths)
        if not found:
            messagebox.showwarning(APP_NAME, "这些路径里没找到 PDF。")
            return
        for f in found:
            if f not in self.files:
                self.files.append(f)
                self.listbox.insert("end", os.path.basename(f))
        if not self.out_dir.get() and self.files:
            self.out_dir.set(os.path.join(os.path.dirname(self.files[0]), "标签输出"))
        self._log(f"已添加 {len(found)} 份 PDF，共 {len(self.files)} 份。")

    def add_pdfs(self) -> None:
        paths = filedialog.askopenfilenames(title="选择 PDF 文件", filetypes=[("PDF 文件", "*.pdf")])
        if paths:
            self._add_paths(list(paths))

    def add_folder(self) -> None:
        path = filedialog.askdirectory(title="选择包含 PDF 的文件夹")
        if path:
            self._add_paths([path])

    def add_zip(self) -> None:
        path = filedialog.askopenfilename(title="选择压缩包", filetypes=[("ZIP 压缩包", "*.zip")])
        if path:
            self._add_paths([path])

    def remove_selected(self) -> None:
        for idx in reversed(self.listbox.curselection()):
            self.listbox.delete(idx)
            del self.files[idx]

    def clear_files(self) -> None:
        self.listbox.delete(0, "end")
        self.files.clear()

    def choose_out_dir(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.out_dir.set(path)

    def open_out_dir(self) -> None:
        path = self.out_dir.get().strip()
        if path and os.path.isdir(path):
            try:
                os.startfile(path)  # type: ignore[attr-defined]
            except Exception:
                messagebox.showinfo(APP_NAME, f"输出目录：{path}")

    # ---------------- 运行 ----------------
    def _grid(self) -> GridSpec:
        data = GridSpec().to_dict()
        try:
            for key, var in self.grid_vars.items():
                data[key] = float(var.get())
            data["cols"] = int(data["cols"])
            data["rows"] = int(data["rows"])
        except ValueError as exc:
            raise ValueError(f"版式参数里有个不是数字：{exc}") from exc
        spec = GridSpec.from_dict(data)
        if spec.cols <= 0 or spec.rows <= 0:
            raise ValueError("列数/行数必须大于 0")
        return spec

    def start(self) -> None:
        text = self.text_box.get("1.0", "end")
        items = parse_text_block(text)
        if not self.files and not items:
            messagebox.showwarning(APP_NAME, "没有内容：请添加 PDF，或在文字框里粘贴几行文字。")
            return
        out_dir = self.out_dir.get().strip()
        if not out_dir:
            base = os.path.dirname(self.files[0]) if self.files else os.getcwd()
            out_dir = os.path.join(base, "标签输出")
            self.out_dir.set(out_dir)
        try:
            grid = self._grid()
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return

        self.start_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self.progress.configure(value=0, maximum=100)
        self.status.set("正在解析…")
        files = list(self.files)
        first_only = self.first_page_only.get()
        proof = self.make_proof.get()
        csv_on = self.make_csv.get()
        name = self.base_name.get().strip() or "标签"
        align = self.text_align.get()
        uniform = self.text_uniform.get()

        def work():
            try:
                pdfs = []
                for i, f in enumerate(files, 1):
                    self.q.put(("log", f"[{i}/{len(files)}] 解析 {os.path.basename(f)}"))
                    info = parse_many([f], first_page_only=first_only)[0]
                    for page in info.pages:
                        for w in page.warnings:
                            self.q.put(("log", f"    ! {w}"))
                    pdfs.append(info)
                    self.q.put(("progress", i, max(1, len(files))))
                n_pdf = sum(p.stickers for p in pdfs)
                n_txt = sum(i.copies for i in items)
                self.q.put(("log", f"内容：PDF {n_pdf} 张 + 文字 {n_txt} 张"))
                outputs = build_all(
                    pdfs, grid, out_dir, base_name=name,
                    make_proof=proof, make_csv=csv_on,
                    text_items=items,
                    progress=lambda stage, done, tot: self.q.put(("progress", done, max(1, tot))),
                    log=lambda msg: self.q.put(("log", msg)),
                    text_align=align, text_uniform=uniform,
                )
                self.q.put(("done", outputs))
            except Exception as exc:  # pragma: no cover
                import traceback
                self.q.put(("error", f"{exc}\n{traceback.format_exc()}"))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._log(item[1])
                elif kind == "progress":
                    done, total = item[1], item[2]
                    self.progress.configure(maximum=max(1, total), value=done)
                    self.status.set(f"处理中… {done}/{total}")
                elif kind == "done":
                    outs = item[1]
                    self.status.set("完成")
                    self.open_btn.configure(state="normal")
                    self.start_btn.configure(state="normal")
                    self._log("完成，输出：")
                    for k, v in outs.items():
                        self._log(f"  {k}: {v}")
                    messagebox.showinfo(APP_NAME, "生成完成！\n\n" + "\n".join(os.path.basename(v) for v in outs.values()))
                elif kind == "error":
                    self.status.set("出错")
                    self.start_btn.configure(state="normal")
                    self._log(item[1])
                    messagebox.showerror(APP_NAME, str(item[1]).splitlines()[0])
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    def _log(self, msg: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


def main() -> None:
    root = TkinterDnD.Tk() if _HAS_DND else tk.Tk()  # type: ignore[misc]
    App(root)
    root.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
