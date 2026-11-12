# -*- coding: utf-8 -*-
"""接着打窗口：选一张没用完的胶纸、在网格上放内容、生成单页 PDF、打印后标记已用。"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Tuple

from . import __version__
from .builder import Entry, Sticker, TextSticker, build_partial_all, collect_stickers, collect_text_stickers
from .calibration import make_calibration_pdf
from .cli import expand_inputs
from .config import GridSpec
from .i18n import current_language, tr
from .sheets import (
    FEED_ORIENTATIONS,
    SheetStore,
    SheetStoreError,
    default_sheets_path,
)
from .parser import parse_many
from .presets import PRESETS
from .textlabel import parse_text_block


def _short(text: str, limit: int = 34) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _safe_name(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", (name or "").strip()).strip(" .")
    return cleaned or "partial"


def _default_out_dir() -> str:
    home = os.path.expanduser("~")
    documents = os.path.join(home, "Documents")
    base = documents if os.path.isdir(documents) else home
    return os.path.join(base, tr("out.default_dir"))


class PartialWindow(tk.Toplevel):
    def __init__(self, master: tk.Misc, store: Optional[SheetStore] = None) -> None:
        super().__init__(master)
        self.title(f"{tr('partial.window_title')} — {tr('app.name')} v{__version__}")
        self.geometry("1280x900")
        self.minsize(1050, 760)
        self.transient(master)

        self.store = store or self._load_store()
        self.queue: List[Entry] = []
        self.placements: Dict[int, Entry] = {}
        self.selected_sheet_id: Optional[str] = None
        self.selected_queue_index: Optional[int] = None
        self.pending_job: Optional[dict] = None
        self.last_job: Optional[dict] = None
        self._cell_rects: Dict[int, Tuple[float, float, float, float]] = {}
        self._feed_display_to_key: Dict[str, str] = {}
        self._after_id: Optional[str] = None

        self._build()
        self._refresh_feed_values()
        self._refresh_sheet_list()
        self._load_printer()
        self._refresh_queue()
        self._after_id = self.after(80, self._refresh_canvas)
        self.bind("<Destroy>", self._on_destroy)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- 初始化 ----------------
    def _load_store(self) -> SheetStore:
        try:
            return SheetStore.load()
        except SheetStoreError as exc:
            path = default_sheets_path()
            messagebox.showerror(tr("partial.title"), str(exc), parent=self)
            if path.exists():
                backup = path.with_name(path.name + ".broken")
                try:
                    os.replace(path, backup)
                except Exception:
                    pass
            return SheetStore(path=path)

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=8)
        outer.pack(fill="both", expand=True)

        # 顶部纸张选择
        top = ttk.Frame(outer)
        top.pack(fill="x")
        ttk.Label(top, text=tr("partial.sheet")).pack(side="left")
        self.sheet_var = tk.StringVar()
        self.sheet_cb = ttk.Combobox(top, textvariable=self.sheet_var, state="readonly", width=46)
        self.sheet_cb.pack(side="left", padx=4)
        self.sheet_cb.bind("<<ComboboxSelected>>", self._on_sheet_changed)
        ttk.Button(top, text=tr("partial.new_sheet"), command=self._new_sheet).pack(side="left", padx=(8, 2))
        ttk.Button(top, text=tr("partial.delete_sheet"), command=self._delete_sheet).pack(side="left", padx=2)
        self.count_var = tk.StringVar()
        ttk.Label(top, textvariable=self.count_var, foreground="#555").pack(side="right")

        main = ttk.Frame(outer)
        main.pack(fill="both", expand=True, pady=(8, 4))
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=1)

        # 左：内容队列
        left = ttk.LabelFrame(main, text=tr("partial.content"))
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.configure(width=330)
        left.grid_propagate(False)

        self.tree = ttk.Treeview(left, columns=("type", "text", "state"), show="headings", height=16)
        self.tree.heading("type", text=tr("partial.queue_type"))
        self.tree.heading("text", text=tr("partial.queue_text"))
        self.tree.heading("state", text=tr("partial.queue_state"))
        self.tree.column("type", width=48, anchor="center", stretch=False)
        self.tree.column("text", width=190, anchor="w")
        self.tree.column("state", width=62, anchor="center", stretch=False)
        self.tree.pack(fill="both", expand=True, padx=4, pady=4)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        qbtns = ttk.Frame(left)
        qbtns.pack(fill="x", padx=4, pady=(0, 4))
        ttk.Button(qbtns, text=tr("partial.add_pdf"), command=self._add_pdf).pack(fill="x", pady=2)
        ttk.Button(qbtns, text=tr("partial.add_text"), command=self._add_text).pack(fill="x", pady=2)
        row = ttk.Frame(qbtns)
        row.pack(fill="x", pady=2)
        ttk.Button(row, text=tr("partial.remove_item"), command=self._remove_item).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text=tr("partial.clear_queue"), command=self._clear_queue).pack(side="left", fill="x", expand=True, padx=(4, 0))
        ttk.Button(qbtns, text=tr("partial.auto_fill"), command=self._auto_fill).pack(fill="x", pady=(4, 2))

        # 中：网格
        center = ttk.LabelFrame(main, text=tr("partial.grid"))
        center.grid(row=0, column=1, sticky="nsew", padx=6)
        center.grid_rowconfigure(0, weight=1)
        center.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(center, bg="white", highlightthickness=1, highlightbackground="#999")
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.canvas.bind("<Configure>", lambda _e: self._refresh_canvas())
        self.canvas.bind("<Button-1>", self._on_left_click)
        self.canvas.bind("<Button-3>", self._on_right_click)
        legend = ttk.Frame(center)
        legend.grid(row=1, column=0, sticky="w", padx=8, pady=(0, 4))
        self._legend(legend, "#d9d9d9", tr("partial.legend.used"))
        self._legend(legend, "#ffffff", tr("partial.legend.free"))
        self._legend(legend, "#cfe8ff", tr("partial.legend.placed"))
        ttk.Label(center, text=tr("partial.grid_hint"), foreground="#666").grid(
            row=2, column=0, sticky="w", padx=8, pady=(0, 4))

        # 右：位置校准 + 打印
        right = ttk.Frame(main, width=340)
        right.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        right.grid_propagate(False)

        cal = ttk.LabelFrame(right, text=tr("partial.calibration"))
        cal.pack(fill="x", pady=(0, 6))
        feed_row = ttk.Frame(cal)
        feed_row.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Label(feed_row, text=tr("partial.feed")).pack(side="left")
        self.feed_var = tk.StringVar()
        self.feed_cb = ttk.Combobox(feed_row, textvariable=self.feed_var, state="readonly", width=26)
        self.feed_cb.pack(side="left", fill="x", expand=True, padx=4)
        # 不知道该怎么放的人走这里；懂的人照旧用上面的下拉框
        ttk.Button(cal, text=tr("partial.wizard"), command=self._open_wizard).pack(
            fill="x", padx=6, pady=(0, 4))

        off_row = ttk.Frame(cal)
        off_row.pack(fill="x", padx=6, pady=2)
        ttk.Label(off_row, text=tr("partial.offset_x")).pack(side="left")
        self.offset_x_var = tk.StringVar(value="0")
        ttk.Entry(off_row, textvariable=self.offset_x_var, width=7).pack(side="left", padx=(2, 10))
        ttk.Label(off_row, text=tr("partial.offset_y")).pack(side="left")
        self.offset_y_var = tk.StringVar(value="0")
        ttk.Entry(off_row, textvariable=self.offset_y_var, width=7).pack(side="left", padx=2)

        ttk.Label(cal, text=tr("partial.offset_hint"), foreground="#666",
                  wraplength=310, justify="left").pack(anchor="w", padx=6, pady=2)
        ttk.Button(cal, text=tr("partial.save_printer"), command=self._save_printer).pack(
            fill="x", padx=6, pady=2)
        ttk.Button(cal, text=tr("partial.calibration_page"), command=self._calibration_page).pack(
            fill="x", padx=6, pady=(2, 2))
        ttk.Label(cal, text=tr("partial.calibration_hint"), foreground="#666",
                  wraplength=310, justify="left").pack(anchor="w", padx=6, pady=(0, 6))

        prt = ttk.LabelFrame(right, text=tr("partial.print"))
        prt.pack(fill="x", pady=(0, 6))
        ttk.Label(prt, text=tr("partial.output_dir")).pack(anchor="w", padx=6, pady=(6, 0))
        out_row = ttk.Frame(prt)
        out_row.pack(fill="x", padx=6, pady=2)
        self.out_dir_var = tk.StringVar(value=_default_out_dir())
        ttk.Entry(out_row, textvariable=self.out_dir_var).pack(side="left", fill="x", expand=True)
        ttk.Button(out_row, text=tr("partial.browse"), command=self._choose_out_dir).pack(side="left", padx=(4, 0))
        ttk.Button(prt, text=tr("partial.generate"), command=self._generate_pdf).pack(fill="x", padx=6, pady=(4, 2))
        ttk.Button(prt, text=tr("partial.mark_printed"), command=self._mark_printed).pack(fill="x", padx=6, pady=2)
        ttk.Button(prt, text=tr("partial.undo"), command=self._undo).pack(fill="x", padx=6, pady=(2, 6))

        logf = ttk.LabelFrame(right, text=tr("partial.log"))
        logf.pack(fill="both", expand=True)
        self.log_text = tk.Text(logf, height=7, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

        self.status_var = tk.StringVar(value=tr("partial.status.ready"))
        ttk.Label(outer, textvariable=self.status_var, foreground="#333").pack(fill="x", pady=(4, 0))

    def _legend(self, parent: ttk.Frame, color: str, text: str) -> None:
        box = tk.Frame(parent, width=12, height=12, bg=color, highlightthickness=1,
                       highlightbackground="#999")
        box.pack(side="left", padx=(0, 2))
        box.pack_propagate(False)
        ttk.Label(parent, text=text, foreground="#555").pack(side="left", padx=(0, 10))

    # ---------------- 纸张 ----------------
    def _current_sheet(self):
        idx = self.sheet_cb.current()
        if 0 <= idx < len(self.store.sheets):
            return self.store.sheets[idx]
        if self.selected_sheet_id:
            return self.store.get_sheet(self.selected_sheet_id)
        return self.store.sheets[0] if self.store.sheets else None

    def _refresh_sheet_list(self, select_id: Optional[str] = None) -> None:
        target_id = select_id or self.selected_sheet_id
        values = [
            tr("partial.sheet_entry", name=s.name, free=s.free_count, per=s.per_sheet)
            for s in self.store.sheets
        ]
        self.sheet_cb["values"] = values
        if not self.store.sheets:
            self.sheet_var.set("")
            self.selected_sheet_id = None
            self.count_var.set(tr("partial.no_sheets"))
            self._refresh_canvas()
            self._refresh_queue()
            self.status_var.set(tr("partial.status.no_sheet"))
            return
        idx = 0
        for i, sheet in enumerate(self.store.sheets):
            if sheet.id == target_id:
                idx = i
                break
        self.sheet_cb.current(idx)
        self.selected_sheet_id = self.store.sheets[idx].id
        self.sheet_var.set(values[idx])
        self.count_var.set(tr("partial.counts", sheets=len(self.store.sheets),
                              free=self.store.free_total()))
        self._refresh_canvas()
        self._refresh_queue()

    def _on_sheet_changed(self, _event=None) -> None:
        sheet = self._current_sheet()
        if sheet is None:
            self.selected_sheet_id = None
            self.placements.clear()
        else:
            if sheet.id != self.selected_sheet_id:
                self.placements.clear()
                self._invalidate_pending()
            self.selected_sheet_id = sheet.id
        self._refresh_canvas()
        self._refresh_queue()
        if sheet is not None:
            self.status_var.set(tr("partial.status.ready"))

    def _invalidate_pending(self) -> None:
        if self.pending_job:
            self.pending_job = None
            self._log(tr("partial.msg.job_invalidated"))

    def _new_sheet(self) -> None:
        dialog = NewSheetDialog(self)
        self.wait_window(dialog)
        if not dialog.result:
            return
        name, grid = dialog.result
        sheet = self.store.add_sheet(name, grid)
        self._save_store()
        self.placements.clear()
        self._invalidate_pending()
        self.selected_sheet_id = sheet.id
        self._refresh_sheet_list(select_id=sheet.id)
        self._on_sheet_changed()
        self._log(tr("partial.msg.sheet_created", name=sheet.name))

    def _delete_sheet(self) -> None:
        sheet = self._current_sheet()
        if sheet is None:
            messagebox.showinfo(tr("partial.title"), tr("partial.msg.no_sheet"), parent=self)
            return
        if not messagebox.askyesno(tr("partial.title"),
                                   tr("partial.msg.confirm_delete", name=sheet.name), parent=self):
            return
        self.store.remove_sheet(sheet.id)
        self._save_store()
        self.placements.clear()
        self._invalidate_pending()
        self.selected_sheet_id = None
        self._refresh_sheet_list()
        self._on_sheet_changed()

    # ---------------- 内容队列 ----------------
    def _entry_label(self, entry: Entry) -> str:
        if isinstance(entry, Sticker):
            suffix = f" (#{entry.copy_no}/{entry.card.qty})" if entry.card.qty > 1 else ""
            return _short(entry.card.name or "?", 30) + suffix
        suffix = f" (#{entry.copy_no}/{entry.item.copies})" if entry.item.copies > 1 else ""
        return _short(entry.item.text, 30) + suffix

    def _entry_kind(self, entry: Entry) -> str:
        return tr("partial.item.pdf") if isinstance(entry, Sticker) else tr("partial.item.text")

    def _is_placed(self, entry: Entry) -> bool:
        return any(value is entry for value in self.placements.values())

    def _refresh_queue(self) -> None:
        selected = self.selected_queue_index
        self.tree.delete(*self.tree.get_children())
        for i, entry in enumerate(self.queue):
            state = tr("partial.item.placed") if self._is_placed(entry) else tr("partial.item.free")
            self.tree.insert("", "end", iid=str(i),
                             values=(self._entry_kind(entry), self._entry_label(entry), state))
        if selected is not None and 0 <= selected < len(self.queue):
            self.tree.selection_set(str(selected))
        else:
            self.selected_queue_index = None

    def _on_tree_select(self, _event=None) -> None:
        selection = self.tree.selection()
        if selection:
            self.selected_queue_index = int(selection[0])

    def _add_pdf(self) -> None:
        paths = filedialog.askopenfilenames(
            title=tr("gui.dialog.choose_pdf"),
            filetypes=[(tr("gui.filetype.pdf"), "*.pdf")], parent=self)
        if not paths:
            return
        self.status_var.set(tr("partial.status.parsing"))
        self.update_idletasks()
        try:
            files = expand_inputs(list(paths))
            if not files:
                messagebox.showwarning(tr("partial.title"), tr("partial.msg.no_pdf"), parent=self)
                return
            pdfs = parse_many(files)
            found = collect_stickers(pdfs)
            if not found:
                messagebox.showwarning(tr("partial.title"), tr("partial.msg.no_pdf"), parent=self)
                return
            self.queue.extend(found)
            self._refresh_queue()
            self.status_var.set(tr("partial.status.ready"))
        except Exception as exc:
            messagebox.showerror(tr("partial.title"), tr("partial.msg.error", error=exc), parent=self)

    def _add_text(self) -> None:
        dialog = TextDialog(self)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        items = parse_text_block(dialog.result)
        if not items:
            messagebox.showwarning(tr("partial.title"), tr("partial.msg.text_empty"), parent=self)
            return
        self.queue.extend(collect_text_stickers(items))
        self._refresh_queue()
        self.status_var.set(tr("partial.status.ready"))

    def _remove_item(self) -> None:
        idx = self.selected_queue_index
        if idx is None or not (0 <= idx < len(self.queue)):
            return
        entry = self.queue.pop(idx)
        for slot, placed in list(self.placements.items()):
            if placed is entry:
                del self.placements[slot]
        self._invalidate_pending()
        self.selected_queue_index = min(idx, len(self.queue) - 1) if self.queue else None
        self._refresh_queue()
        self._refresh_canvas()

    def _clear_queue(self) -> None:
        if not self.queue and not self.placements:
            return
        if not messagebox.askyesno(tr("partial.title"), tr("partial.msg.confirm_clear"), parent=self):
            return
        self.queue.clear()
        self.placements.clear()
        self.selected_queue_index = None
        self._invalidate_pending()
        self._refresh_queue()
        self._refresh_canvas()

    def _auto_fill(self) -> None:
        sheet = self._current_sheet()
        if sheet is None:
            messagebox.showinfo(tr("partial.title"), tr("partial.msg.no_sheet"), parent=self)
            return
        free = [slot for slot in sheet.free_cells if slot not in self.placements]
        pending = [entry for entry in self.queue if not self._is_placed(entry)]
        if not free:
            messagebox.showinfo(tr("partial.title"), tr("partial.msg.no_free"), parent=self)
            return
        count = 0
        for slot, entry in zip(free, pending):
            self.placements[slot] = entry
            count += 1
        if count:
            self._invalidate_pending()
        self._refresh_queue()
        self._refresh_canvas()
        self.status_var.set(tr("partial.status.auto_filled", n=count))

    # ---------------- 网格 ----------------
    def _refresh_canvas(self) -> None:
        if not self.winfo_exists():
            return
        canvas = self.canvas
        canvas.delete("all")
        self._cell_rects.clear()
        sheet = self._current_sheet()
        if sheet is None:
            canvas.create_text(max(canvas.winfo_width(), 300) / 2, max(canvas.winfo_height(), 300) / 2,
                               text=tr("partial.no_sheets"), fill="#888")
            return
        grid = sheet.grid_spec
        width = max(canvas.winfo_width(), 320)
        height = max(canvas.winfo_height(), 320)
        pad = 34
        cw = max(18, min(96, (width - 2 * pad) // max(1, grid.cols)))
        ch = max(16, min(64, (height - 2 * pad) // max(1, grid.rows)))
        gx = (width - cw * grid.cols) / 2.0
        gy = (height - ch * grid.rows) / 2.0
        used = sheet.used_cells

        for col in range(grid.cols):
            canvas.create_text(gx + col * cw + cw / 2, gy - 12, text=str(col + 1), fill="#666")
        for row in range(grid.rows):
            canvas.create_text(gx - 14, gy + row * ch + ch / 2, text=str(row + 1), fill="#666")

        for slot in range(grid.per_sheet):
            row, col = divmod(slot, grid.cols)
            x0, y0 = gx + col * cw, gy + row * ch
            x1, y1 = x0 + cw, y0 + ch
            self._cell_rects[slot] = (x0, y0, x1, y1)
            entry = self.placements.get(slot)
            if slot in used:
                fill = "#d9d9d9"
            elif entry is not None:
                fill = "#cfe8ff"
            else:
                fill = "#ffffff"
            canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline="#9a9a9a")
            if slot in used:
                canvas.create_line(x0 + 3, y0 + 3, x1 - 3, y1 - 3, fill="#888")
                canvas.create_line(x0 + 3, y1 - 3, x1 - 3, y0 + 3, fill="#888")
            elif entry is not None:
                canvas.create_text((x0 + x1) / 2, (y0 + y1) / 2,
                                   text=_short(self._entry_label(entry), 12),
                                   width=max(20, cw - 6), fill="#123", justify="center")

    def _slot_at(self, event) -> Optional[int]:
        for slot, (x0, y0, x1, y1) in self._cell_rects.items():
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                return slot
        return None

    def _on_left_click(self, event) -> None:
        slot = self._slot_at(event)
        if slot is None:
            return
        sheet = self._current_sheet()
        if sheet is None:
            return
        if slot in sheet.used_cells:
            messagebox.showinfo(tr("partial.title"), tr("partial.msg.cell_used"), parent=self)
            return
        if slot in self.placements:
            self.placements.pop(slot)
            self._invalidate_pending()
            self._refresh_queue()
            self._refresh_canvas()
            self.status_var.set(tr("partial.status.removed", cell=slot + 1))
            return
        idx = self.selected_queue_index
        if idx is None or not (0 <= idx < len(self.queue)):
            messagebox.showinfo(tr("partial.title"), tr("partial.msg.no_selection"), parent=self)
            return
        entry = self.queue[idx]
        for old_slot, placed in list(self.placements.items()):
            if placed is entry:
                del self.placements[old_slot]
        self.placements[slot] = entry
        self._invalidate_pending()
        self._refresh_queue()
        self._refresh_canvas()
        self.status_var.set(tr("partial.status.placed", cell=slot + 1))

    def _on_right_click(self, event) -> None:
        slot = self._slot_at(event)
        if slot is None:
            return
        sheet = self._current_sheet()
        if sheet is None:
            return
        self.placements.pop(slot, None)
        self._invalidate_pending()
        if slot in sheet.used_cells:
            sheet.mark_free([slot])
        else:
            sheet.mark_used([slot])
        self._save_store()
        self._refresh_sheet_list()
        self._refresh_queue()
        self._refresh_canvas()

    # ---------------- 打印/扣格 ----------------
    def _choose_out_dir(self) -> None:
        path = filedialog.askdirectory(title=tr("gui.dialog.choose_out"), parent=self)
        if path:
            self.out_dir_var.set(path)

    def _offset(self) -> Tuple[float, float]:
        try:
            return float(self.offset_x_var.get()), float(self.offset_y_var.get())
        except ValueError as exc:
            raise ValueError(tr("partial.msg.bad_offset")) from exc

    def _generate_pdf(self) -> None:
        sheet = self._current_sheet()
        if sheet is None:
            messagebox.showinfo(tr("partial.title"), tr("partial.msg.no_sheet"), parent=self)
            return
        if not self.placements:
            messagebox.showinfo(tr("partial.title"), tr("partial.msg.no_placements"), parent=self)
            return
        try:
            offset = self._offset()
        except ValueError as exc:
            messagebox.showerror(tr("partial.title"), str(exc), parent=self)
            return
        out_dir = self.out_dir_var.get().strip() or _default_out_dir()
        self.out_dir_var.set(out_dir)
        try:
            outs = build_partial_all(
                self.placements, sheet.grid_spec, out_dir,
                base_name=_safe_name(sheet.name),
                make_csv=True, offset_mm=offset, log=self._log,
            )
        except Exception as exc:
            messagebox.showerror(tr("partial.title"), tr("partial.msg.error", error=exc), parent=self)
            return
        self.pending_job = {
            "sheet_id": sheet.id,
            "slots": sorted(self.placements),
            "entries": [self.placements[slot] for slot in sorted(self.placements)],
        }
        path = outs["production"]
        self.status_var.set(tr("partial.status.generated", file=os.path.basename(path)))
        messagebox.showinfo(tr("partial.title"), tr("partial.msg.pdf_ready", path=path), parent=self)
        self._open_path(path)

    def _mark_printed(self) -> None:
        job = self.pending_job
        if not job:
            messagebox.showinfo(tr("partial.title"), tr("partial.msg.no_placements"), parent=self)
            return
        sheet = self.store.get_sheet(job["sheet_id"])
        if sheet is None:
            return
        if not messagebox.askyesno(tr("partial.title"),
                                   tr("partial.msg.confirm_mark", n=len(job["slots"])), parent=self):
            return
        changed = self.store.mark_used(sheet.id, job["slots"])
        self._save_store()
        for slot in job["slots"]:
            self.placements.pop(slot, None)
        for entry in job["entries"]:
            for i, queued in enumerate(list(self.queue)):
                if queued is entry:
                    self.queue.remove(entry)
                    break
        self.last_job = job
        self.pending_job = None
        self.selected_queue_index = None
        self._refresh_sheet_list()
        self._refresh_queue()
        self._refresh_canvas()
        self.status_var.set(tr("partial.status.marked", n=len(changed), free=sheet.free_count))

    def _undo(self) -> None:
        job = self.last_job
        if not job:
            messagebox.showinfo(tr("partial.title"), tr("partial.msg.undo_none"), parent=self)
            return
        sheet = self.store.get_sheet(job["sheet_id"])
        if sheet is not None:
            self.store.mark_free(sheet.id, job["slots"])
            self._save_store()
        for entry in job["entries"]:
            if not any(queued is entry for queued in self.queue):
                self.queue.append(entry)
        self.last_job = None
        self.selected_queue_index = None
        self._refresh_sheet_list()
        self._refresh_queue()
        self._refresh_canvas()
        self.status_var.set(tr("partial.status.undo"))

    # ---------------- 位置校准/打印机 ----------------
    def _refresh_feed_values(self) -> None:
        self._feed_display_to_key = {
            tr(f"calibration.feed.{feed}"): feed for feed in FEED_ORIENTATIONS
        }
        self.feed_cb["values"] = list(self._feed_display_to_key.keys())

    def _load_printer(self) -> None:
        profile = self.store.get_printer()
        self.offset_x_var.set(f"{profile.offset_x_mm:g}")
        self.offset_y_var.set(f"{profile.offset_y_mm:g}")
        self.feed_var.set(tr(f"calibration.feed.{profile.feed}"))

    def _save_printer(self) -> None:
        try:
            offset = self._offset()
        except ValueError as exc:
            messagebox.showerror(tr("partial.title"), str(exc), parent=self)
            return
        feed = self._feed_display_to_key.get(self.feed_var.get(), FEED_ORIENTATIONS[0])
        profile = self.store.get_printer()
        profile.offset_x_mm, profile.offset_y_mm = offset
        profile.feed = feed
        self.store.save_printer(profile)
        self._save_store()
        self.status_var.set(tr("partial.msg.printer_saved"))

    def _calibration_page(self) -> None:
        sheet = self._current_sheet()
        grid = sheet.grid_spec if sheet is not None else GridSpec()
        feed = self._feed_display_to_key.get(self.feed_var.get(), FEED_ORIENTATIONS[0])
        out_dir = self.out_dir_var.get().strip() or _default_out_dir()
        path = os.path.join(out_dir, tr("calibration.file"))
        try:
            make_calibration_pdf(grid, path, feed=feed, lang=current_language())
        except Exception as exc:
            messagebox.showerror(tr("partial.title"), tr("partial.msg.error", error=exc), parent=self)
            return
        messagebox.showinfo(tr("partial.title"), tr("partial.msg.calibration_ready", path=path), parent=self)
        self._open_path(path)

    # ---------------- 工具 ----------------
    def _open_path(self, path: str) -> None:
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            messagebox.showinfo(tr("partial.title"), tr("partial.msg.open_failed", path=path), parent=self)

    def _open_wizard(self) -> None:
        """打开 9 步校准向导；结果写回同一份 PrinterProfile。"""
        from .wizard import CalibrationWizard

        profile = self.store.get_printer()

        def on_save(feed: str, off_x: float, off_y: float) -> None:
            p = self.store.get_printer()
            p.feed, p.offset_x_mm, p.offset_y_mm = feed, off_x, off_y
            if profile.name:
                p.name = profile.name
            if profile.tray:
                p.tray = profile.tray
            self.store.save_printer(p)
            self._save_store()
            self._load_printer()
            self.status_var.set(tr("partial.msg.printer_saved"))

        out_dir = self.out_dir_var.get().strip() or _default_out_dir()
        CalibrationWizard(self, profile=profile, on_save=on_save, output_dir=out_dir)

    def _save_store(self) -> None:
        try:
            self.store.save()
        except Exception as exc:
            messagebox.showerror(tr("partial.title"), tr("partial.msg.save_failed", error=exc), parent=self)

    def _log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _on_close(self) -> None:
        self._cancel_after()
        try:
            self.store.save()
        except Exception:
            pass
        self.destroy()

    def _cancel_after(self) -> None:
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _on_destroy(self, event) -> None:
        if event.widget is self:
            self._cancel_after()


class NewSheetDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title(tr("partial.new.title"))
        self.transient(master)
        self.resizable(False, False)
        self.result: Optional[Tuple[str, GridSpec]] = None
        self.grab_set()

        pad = ttk.Frame(self, padding=10)
        pad.pack(fill="both", expand=True)

        ttk.Label(pad, text=tr("partial.new.name")).grid(row=0, column=0, sticky="e", pady=3)
        self.name_var = tk.StringVar()
        ttk.Entry(pad, textvariable=self.name_var, width=28).grid(row=0, column=1, columnspan=3, sticky="we", pady=3)

        ttk.Label(pad, text=tr("partial.new.preset")).grid(row=1, column=0, sticky="e", pady=3)
        self.preset_var = tk.StringVar()
        self.preset_cb = ttk.Combobox(pad, textvariable=self.preset_var, state="readonly", width=26)
        self.preset_cb["values"] = [p.title for p in PRESETS] + [tr("partial.new.custom")]
        self.preset_cb.grid(row=1, column=1, columnspan=3, sticky="we", pady=3)
        self.preset_cb.bind("<<ComboboxSelected>>", self._on_preset)

        self.vars: Dict[str, tk.StringVar] = {
            key: tk.StringVar(value="5") for key in
            ("cols", "rows", "cell_w", "cell_h", "pitch_x", "pitch_y", "margin_top", "inset")
        }
        specs = [
            (tr("gui.grid.cols"), "cols"), (tr("gui.grid.rows"), "rows"),
            (tr("gui.grid.cell_w"), "cell_w"), (tr("gui.grid.cell_h"), "cell_h"),
            (tr("gui.grid.pitch_x"), "pitch_x"), (tr("gui.grid.pitch_y"), "pitch_y"),
            (tr("gui.grid.margin_top"), "margin_top"), (tr("gui.grid.inset"), "inset"),
        ]
        for i, (label, key) in enumerate(specs):
            r, c = 2 + i // 2, (i % 2) * 2
            ttk.Label(pad, text=label).grid(row=r, column=c, sticky="e", pady=2)
            ttk.Entry(pad, textvariable=self.vars[key], width=10).grid(
                row=r, column=c + 1, sticky="w", padx=(2, 12), pady=2)
        ttk.Label(pad, text=tr("partial.new.unit"), foreground="#666").grid(
            row=6, column=0, columnspan=4, sticky="w", pady=(4, 2))

        btns = ttk.Frame(pad)
        btns.grid(row=7, column=0, columnspan=4, pady=(8, 0), sticky="e")
        ttk.Button(btns, text=tr("partial.new.cancel"), command=self.destroy).pack(side="right", padx=4)
        ttk.Button(btns, text=tr("partial.new.create"), command=self._create).pack(side="right")

        self.preset_cb.current(0)
        self._on_preset()

    def _on_preset(self, _event=None) -> None:
        idx = self.preset_cb.current()
        if 0 <= idx < len(PRESETS):
            preset = PRESETS[idx]
            grid = preset.to_grid()
            self._fill(grid)
            if not self.name_var.get().strip():
                self.name_var.set(preset.title)
        elif not self.name_var.get().strip():
            self.name_var.set(tr("partial.new.title"))

    def _fill(self, grid: GridSpec) -> None:
        self.vars["cols"].set(str(grid.cols))
        self.vars["rows"].set(str(grid.rows))
        for key in ("cell_w", "cell_h", "pitch_x", "pitch_y", "margin_top", "inset"):
            self.vars[key].set(f"{getattr(grid, key):g}")

    def _create(self) -> None:
        try:
            cols = int(self.vars["cols"].get())
            rows = int(self.vars["rows"].get())
            cell_w = float(self.vars["cell_w"].get())
            cell_h = float(self.vars["cell_h"].get())
            pitch_x = float(self.vars["pitch_x"].get())
            pitch_y = float(self.vars["pitch_y"].get())
            margin_top = float(self.vars["margin_top"].get())
            inset = float(self.vars["inset"].get())
            if cols <= 0 or rows <= 0:
                raise ValueError(tr("gui.err.grid_positive"))
            if cell_w <= 0 or cell_h <= 0 or pitch_x <= 0 or pitch_y <= 0 or inset < 0 or margin_top < 0:
                raise ValueError(tr("partial.new.invalid", error="mm"))
            block_w = (cols - 1) * pitch_x + cell_w
            block_h = margin_top + (rows - 1) * pitch_y + cell_h
            if block_w > 210.01 or block_h > 297.01:
                raise ValueError(tr("partial.new.too_big", w=block_w, h=block_h))
            grid = GridSpec(cols=cols, rows=rows, cell_w=cell_w, cell_h=cell_h,
                            pitch_x=pitch_x, pitch_y=pitch_y, margin_top=margin_top,
                            inset=inset, margin_left=None)
        except Exception as exc:
            messagebox.showerror(tr("partial.new.title"), tr("partial.new.invalid", error=exc), parent=self)
            return
        name = self.name_var.get().strip() or tr("partial.new.title")
        self.result = (name, grid)
        self.destroy()


class TextDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title(tr("partial.text.title"))
        self.transient(master)
        self.result: Optional[str] = None
        self.grab_set()
        pad = ttk.Frame(self, padding=10)
        pad.pack(fill="both", expand=True)
        ttk.Label(pad, text=tr("partial.text.hint"), foreground="#666").pack(anchor="w")
        self.text = tk.Text(pad, width=60, height=10, wrap="word")
        self.text.pack(fill="both", expand=True, pady=6)
        btns = ttk.Frame(pad)
        btns.pack(fill="x")
        ttk.Button(btns, text=tr("partial.text.cancel"), command=self.destroy).pack(side="right", padx=4)
        ttk.Button(btns, text=tr("partial.text.ok"), command=self._ok).pack(side="right")

    def _ok(self) -> None:
        self.result = self.text.get("1.0", "end-1c")
        self.destroy()
