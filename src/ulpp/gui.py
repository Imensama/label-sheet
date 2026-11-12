# -*- coding: utf-8 -*-
"""图形界面：拖入/选入 PDF 或粘贴一段文字，一键排成 A4 不干胶标签。"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from . import __version__
from .builder import build_all
from .cli import expand_inputs
from .config import GridSpec
from .i18n import (
    available_languages,
    current_language,
    language_name,
    set_language,
    tr,
)
from .parser import parse_many
from .presets import DEFAULT_PRESET_KEY, PRESETS, by_key
from .textlabel import parse_text_block

try:  # 可选：装了 tkinterdnd2 就能拖拽
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore

    _HAS_DND = True
except Exception:  # pragma: no cover
    _HAS_DND = False
    DND_FILES = None
    TkinterDnD = None


class App:
    def __init__(self, root: tk.Tk, lang: Optional[str] = None) -> None:
        self.root = root
        if lang:
            set_language(lang)
        self.files: List[str] = []
        self.out_dir = tk.StringVar()
        self.first_page_only = tk.BooleanVar(value=False)
        self.make_proof = tk.BooleanVar(value=True)
        self.make_csv = tk.BooleanVar(value=True)
        self.base_name = tk.StringVar(value=tr("out.default_base"))
        self.status = tk.StringVar(value=tr("gui.status.ready"))
        self.preset_key = tk.StringVar(value=DEFAULT_PRESET_KEY)
        self.preset_display = tk.StringVar(value=by_key(DEFAULT_PRESET_KEY).title)
        self.lang_display = tk.StringVar(value=language_name(current_language()))
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
        self.partial_window = None
        self._loading_preset = False

        root.title(f"{tr('app.name')} v{__version__}")
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
        files_frame = ttk.LabelFrame(self.root, text=tr("gui.file_frame"))
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
        ttk.Button(btns, text=tr("gui.btn.add_pdf"), command=self.add_pdfs).pack(side="left")
        ttk.Button(btns, text=tr("gui.btn.add_folder"), command=self.add_folder).pack(side="left", padx=6)
        ttk.Button(btns, text=tr("gui.btn.add_zip"), command=self.add_zip).pack(side="left")
        ttk.Button(btns, text=tr("gui.btn.clear"), command=self.clear_files).pack(side="right")
        ttk.Button(btns, text=tr("gui.btn.remove"), command=self.remove_selected).pack(side="right", padx=6)

        # 文字标签
        text_frame = ttk.LabelFrame(self.root, text=tr("gui.text_frame"))
        text_frame.pack(fill="both", expand=True, **pad)
        self.text_box = tk.Text(text_frame, height=6, wrap="word", undo=True)
        self.text_box.pack(fill="both", expand=True, padx=8, pady=(6, 2))
        ttk.Label(text_frame, text=tr("gui.hint.text"), foreground="#666",
                  wraplength=940, justify="left").pack(anchor="w", padx=10, pady=(0, 6))
        trow = ttk.Frame(text_frame)
        trow.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(trow, text=tr("gui.align.label")).pack(side="left")
        for label, val in ((tr("gui.align.center"), "center"),
                           (tr("gui.align.left"), "left"),
                           (tr("gui.align.right"), "right")):
            ttk.Radiobutton(trow, text=label, variable=self.text_align, value=val).pack(side="left")
        ttk.Checkbutton(trow, text=tr("gui.text_uniform"),
                        variable=self.text_uniform).pack(side="left", padx=16)

        # 选项
        opt = ttk.LabelFrame(self.root, text=tr("gui.options_frame"))
        opt.pack(fill="x", **pad)

        row1 = ttk.Frame(opt)
        row1.pack(fill="x", padx=8, pady=(6, 2))
        ttk.Label(row1, text=tr("gui.pdf_pages")).pack(side="left")
        ttk.Radiobutton(row1, text=tr("gui.pages.all"), variable=self.first_page_only,
                        value=False).pack(side="left")
        ttk.Radiobutton(row1, text=tr("gui.pages.first_only"), variable=self.first_page_only,
                        value=True).pack(side="left", padx=(6, 16))
        ttk.Checkbutton(row1, text=tr("gui.make_proof"), variable=self.make_proof).pack(side="left")
        ttk.Checkbutton(row1, text=tr("gui.make_csv"), variable=self.make_csv).pack(side="left", padx=12)

        row2 = ttk.Frame(opt)
        row2.pack(fill="x", padx=8, pady=2)
        ttk.Label(row2, text=tr("gui.out_dir")).pack(side="left")
        ttk.Entry(row2, textvariable=self.out_dir).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(row2, text=tr("gui.btn.browse"), command=self.choose_out_dir).pack(side="left")

        row3 = ttk.Frame(opt)
        row3.pack(fill="x", padx=8, pady=2)
        ttk.Label(row3, text=tr("gui.base_name")).pack(side="left")
        ttk.Entry(row3, textvariable=self.base_name, width=20).pack(side="left", padx=(4, 16))
        ttk.Label(row3, text=tr("gui.base_name_hint"), foreground="#666").pack(side="left")

        # 版式参数
        adv = ttk.LabelFrame(self.root, text=tr("gui.advanced_frame"))
        adv.pack(fill="x", **pad)
        prow = ttk.Frame(adv)
        prow.pack(fill="x", padx=8, pady=(6, 2))
        ttk.Label(prow, text=tr("gui.preset.label")).pack(side="left")
        self.preset_cb = ttk.Combobox(prow, textvariable=self.preset_display, state="readonly",
                                      values=[p.title for p in PRESETS], width=30)
        self.preset_cb.pack(side="left", padx=4)
        self.preset_cb.bind("<<ComboboxSelected>>", self._on_preset_selected)
        ttk.Label(prow, text=tr("gui.preset.hint"),
                  foreground="#666").pack(side="left")

        grid = ttk.Frame(adv)
        grid.pack(fill="x", padx=8, pady=6)
        specs = [
            (tr("gui.grid.cols"), "cols", 4), (tr("gui.grid.rows"), "rows", 4),
            (tr("gui.grid.cell_w"), "cell_w", 6), (tr("gui.grid.cell_h"), "cell_h", 6),
            (tr("gui.grid.pitch_x"), "pitch_x", 6), (tr("gui.grid.pitch_y"), "pitch_y", 6),
            (tr("gui.grid.margin_top"), "margin_top", 6), (tr("gui.grid.inset"), "inset", 6),
        ]
        for i, (label, key, width) in enumerate(specs):
            ttk.Label(grid, text=label).grid(row=0, column=i * 2, sticky="e", padx=(6, 2))
            ttk.Entry(grid, textvariable=self.grid_vars[key], width=width).grid(row=0, column=i * 2 + 1, sticky="w")

        # 日志
        logf = ttk.LabelFrame(self.root, text=tr("gui.log_frame"))
        logf.pack(fill="both", expand=True, **pad)
        self.log_text = tk.Text(logf, height=6, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=8, pady=6)

        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", padx=8, pady=(0, 10))
        ttk.Label(bottom, textvariable=self.status, foreground="#333").pack(side="left")
        self.lang_cb = ttk.Combobox(
            bottom, textvariable=self.lang_display, state="readonly", width=8,
            values=[language_name(code) for code in available_languages()],
        )
        self.lang_cb.pack(side="right", padx=(8, 0))
        self.lang_cb.bind("<<ComboboxSelected>>", self._on_lang_selected)
        ttk.Label(bottom, text=tr("gui.lang.label")).pack(side="right")
        self.partial_btn = ttk.Button(bottom, text=tr("gui.btn.continue"), command=self.open_partial)
        self.partial_btn.pack(side="right", padx=(8, 0))
        self.open_btn = ttk.Button(bottom, text=tr("gui.btn.open_out"),
                                   command=self.open_out_dir, state="disabled")
        self.open_btn.pack(side="right", padx=(8, 0))
        self.start_btn = ttk.Button(bottom, text=tr("gui.btn.start"), command=self.start)
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

    # ---------------- 语言 ----------------
    def _on_lang_selected(self, _event=None) -> None:
        wanted = self.lang_display.get()
        code = next((c for c in available_languages() if language_name(c) == wanted), None)
        if not code or code == current_language():
            self.lang_display.set(language_name(current_language()))
            return
        self._switch_language(code)

    def _switch_language(self, code: str) -> None:
        """即时重绘界面：保留文件列表、文字框和参数。"""
        text = self.text_box.get("1.0", "end-1c")
        open_state = str(self.open_btn.cget("state"))
        old_base = tr("out.default_base")
        old_dir = tr("out.default_dir")
        set_language(code)
        for child in self.root.winfo_children():
            child.destroy()
        self._build_ui()
        self.root.title(f"{tr('app.name')} v{__version__}")
        self.lang_display.set(language_name(current_language()))
        self.preset_display.set(by_key(self.preset_key.get()).title)
        if self.base_name.get().strip() == old_base:
            self.base_name.set(tr("out.default_base"))
        out_dir = self.out_dir.get().strip()
        if out_dir and os.path.basename(os.path.normpath(out_dir)) == old_dir:
            self.out_dir.set(os.path.join(os.path.dirname(out_dir), tr("out.default_dir")))
        self.listbox.delete(0, "end")
        for path in self.files:
            self.listbox.insert("end", os.path.basename(path))
        if text:
            self.text_box.insert("1.0", text)
        if open_state == "normal":
            self.open_btn.configure(state="normal")
        self.progress.configure(value=0, maximum=100)
        self.status.set(tr("gui.status.ready"))
        self._log(tr("gui.log.lang_switched", lang=language_name(code)))
        self._setup_dnd()

    # ---------------- 规格 ----------------
    def _on_preset_selected(self, _event=None) -> None:
        idx = self.preset_cb.current()
        if idx >= 0:
            self._apply_preset(PRESETS[idx].key)

    def _apply_preset(self, key: str, log: bool = True) -> None:
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
        self.preset_key.set(preset.key)
        self.preset_display.set(preset.title)
        if log:
            self._log(tr("gui.log.preset", title=preset.title))

    # ---------------- 文件管理 ----------------
    def _add_paths(self, paths: List[str]) -> None:
        found = expand_inputs(paths)
        if not found:
            messagebox.showwarning(tr("app.name"), tr("gui.warn.no_pdf"))
            return
        for f in found:
            if f not in self.files:
                self.files.append(f)
                self.listbox.insert("end", os.path.basename(f))
        if not self.out_dir.get() and self.files:
            self.out_dir.set(os.path.join(os.path.dirname(self.files[0]), tr("out.default_dir")))
        self._log(tr("gui.log.added", added=len(found), total=len(self.files)))

    def add_pdfs(self) -> None:
        paths = filedialog.askopenfilenames(title=tr("gui.dialog.choose_pdf"),
                                            filetypes=[(tr("gui.filetype.pdf"), "*.pdf")])
        if paths:
            self._add_paths(list(paths))

    def add_folder(self) -> None:
        path = filedialog.askdirectory(title=tr("gui.dialog.choose_folder"))
        if path:
            self._add_paths([path])

    def add_zip(self) -> None:
        path = filedialog.askopenfilename(title=tr("gui.dialog.choose_zip"),
                                          filetypes=[(tr("gui.filetype.zip"), "*.zip")])
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
        path = filedialog.askdirectory(title=tr("gui.dialog.choose_out"))
        if path:
            self.out_dir.set(path)

    def open_out_dir(self) -> None:
        path = self.out_dir.get().strip()
        if path and os.path.isdir(path):
            try:
                os.startfile(path)  # type: ignore[attr-defined]
            except Exception:
                messagebox.showinfo(tr("app.name"), tr("gui.info.out_dir", path=path))

    def open_partial(self) -> None:
        from .partial_gui import PartialWindow

        win = self.partial_window
        if win is not None and win.winfo_exists():
            win.lift()
            win.focus_force()
            return
        self.partial_window = PartialWindow(self.root)

    # ---------------- 运行 ----------------
    def _grid(self) -> GridSpec:
        data = GridSpec().to_dict()
        try:
            for key, var in self.grid_vars.items():
                data[key] = float(var.get())
            data["cols"] = int(data["cols"])
            data["rows"] = int(data["rows"])
        except ValueError as exc:
            raise ValueError(tr("gui.err.grid_number", error=exc)) from exc
        spec = GridSpec.from_dict(data)
        if spec.cols <= 0 or spec.rows <= 0:
            raise ValueError(tr("gui.err.grid_positive"))
        return spec

    def start(self) -> None:
        text = self.text_box.get("1.0", "end")
        items = parse_text_block(text)
        if not self.files and not items:
            messagebox.showwarning(tr("app.name"), tr("gui.warn.no_content"))
            return
        out_dir = self.out_dir.get().strip()
        if not out_dir:
            base = os.path.dirname(self.files[0]) if self.files else os.getcwd()
            out_dir = os.path.join(base, tr("out.default_dir"))
            self.out_dir.set(out_dir)
        try:
            grid = self._grid()
        except ValueError as exc:
            messagebox.showerror(tr("app.name"), str(exc))
            return

        self.start_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self.lang_cb.configure(state="disabled")
        self.progress.configure(value=0, maximum=100)
        self.status.set(tr("gui.status.parsing"))
        files = list(self.files)
        first_only = self.first_page_only.get()
        proof = self.make_proof.get()
        csv_on = self.make_csv.get()
        name = self.base_name.get().strip() or tr("out.default_base")
        align = self.text_align.get()
        uniform = self.text_uniform.get()

        def work():
            try:
                pdfs = []
                for i, f in enumerate(files, 1):
                    self.q.put(("log", tr("log.parsing", i=i, n=len(files),
                                          name=os.path.basename(f))))
                    info = parse_many([f], first_page_only=first_only)[0]
                    for page in info.pages:
                        for w in page.warnings:
                            self.q.put(("log", f"    ! {w}"))
                    pdfs.append(info)
                    self.q.put(("progress", i, max(1, len(files))))
                n_pdf = sum(p.stickers for p in pdfs)
                n_txt = sum(i.copies for i in items)
                self.q.put(("log", tr("gui.log.counts", pdf=n_pdf, text=n_txt)))
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
                    self.status.set(tr("gui.status.processing", done=done, total=total))
                elif kind == "done":
                    outs = item[1]
                    self.status.set(tr("gui.status.done"))
                    self.open_btn.configure(state="normal")
                    self.start_btn.configure(state="normal")
                    self.lang_cb.configure(state="readonly")
                    self._log(tr("gui.log.done"))
                    for k, v in outs.items():
                        self._log(f"  {k}: {v}")
                    messagebox.showinfo(
                        tr("app.name"),
                        tr("gui.msg.done", files="\n".join(os.path.basename(v) for v in outs.values())),
                    )
                elif kind == "error":
                    self.status.set(tr("gui.status.error"))
                    self.start_btn.configure(state="normal")
                    self.lang_cb.configure(state="readonly")
                    self._log(item[1])
                    messagebox.showerror(tr("app.name"), str(item[1]).splitlines()[0])
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    def _log(self, msg: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


def main(lang: Optional[str] = None) -> None:
    if lang:
        set_language(lang)
    root = TkinterDnD.Tk() if _HAS_DND else tk.Tk()  # type: ignore[misc]
    App(root)
    root.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
