# -*- coding: utf-8 -*-
"""“接着打”功能的本地数据：没用完的胶纸记录 + 位置校准配置。

数据默认存 ``%APPDATA%/ulpp/sheets.json``（Windows）或
``~/.config/ulpp/sheets.json``（macOS/Linux）。没有数据库，纯 JSON，
写入时先写临时文件再 ``os.replace``，避免写到一半损坏。

旧版本（叫 label-sheet 的时候）存在 ``label-sheet/`` 目录下；首次运行时
会自动复制过来，老用户不用重新配置。
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from .config import GridSpec

SCHEMA_VERSION = 1
FEED_ORIENTATIONS = ("face_up_short", "face_up_long", "face_down_short", "face_down_long")
DEFAULT_FEED = "face_up_short"


class SheetStoreError(ValueError):
    """纸张记录文件损坏或格式不认识。"""


def default_sheets_path() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if base:
            new = Path(base) / "ulpp" / "sheets.json"
            return _migrate_legacy(new)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    root = Path(xdg) if xdg else Path.home() / ".config"
    return _migrate_legacy(root / "ulpp" / "sheets.json")


def _migrate_legacy(new: Path) -> Path:
    """老版本（label-sheet）的配置还在、新位置没有 → 复制过来。"""
    if new.exists():
        return new
    old = new.parent.parent / "label-sheet" / "sheets.json"
    try:
        if old.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old, new)
    except OSError:
        return old          # 拷不过去就直接继续用老文件
    return new


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class PrinterProfile:
    """一台打印机的位置校准配置；offset 是“补偿量”，正数表示把内容往右/往下移。"""

    id: str = "default"
    name: str = "default"
    offset_x_mm: float = 0.0
    offset_y_mm: float = 0.0
    feed: str = DEFAULT_FEED
    tray: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "offset_x_mm": round(float(self.offset_x_mm), 3),
            "offset_y_mm": round(float(self.offset_y_mm), 3),
            "feed": self.feed if self.feed in FEED_ORIENTATIONS else DEFAULT_FEED,
            "tray": self.tray,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PrinterProfile":
        feed = str(data.get("feed") or DEFAULT_FEED)
        if feed not in FEED_ORIENTATIONS:
            feed = DEFAULT_FEED
        return cls(
            id=str(data.get("id") or _new_id()),
            name=str(data.get("name") or "default"),
            offset_x_mm=float(data.get("offset_x_mm") or 0.0),
            offset_y_mm=float(data.get("offset_y_mm") or 0.0),
            feed=feed,
            tray=str(data.get("tray") or ""),
            note=str(data.get("note") or ""),
        )


@dataclass
class SheetRecord:
    """一张半张纸。``used`` 是已经用掉/撕掉的格子（0 起、行优先）。"""

    id: str
    name: str
    grid: Dict[str, float]
    used: List[int] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    note: str = ""

    @property
    def grid_spec(self) -> GridSpec:
        return GridSpec.from_dict(self.grid)

    @property
    def per_sheet(self) -> int:
        return self.grid_spec.per_sheet

    @property
    def used_cells(self) -> set:
        return set(self.used)

    @property
    def free_cells(self) -> List[int]:
        used = self.used_cells
        return [i for i in range(self.per_sheet) if i not in used]

    @property
    def free_count(self) -> int:
        return max(0, self.per_sheet - len(self.used_cells))

    def is_free(self, slot: int) -> bool:
        return 0 <= slot < self.per_sheet and slot not in self.used_cells

    def mark_used(self, slots: Iterable[int]) -> List[int]:
        before = self.used_cells
        changed = []
        for slot in slots:
            slot = int(slot)
            if 0 <= slot < self.per_sheet and slot not in before:
                before.add(slot)
                changed.append(slot)
        self.used = sorted(before)
        return changed

    def mark_free(self, slots: Iterable[int]) -> List[int]:
        before = self.used_cells
        changed = []
        for slot in slots:
            slot = int(slot)
            if slot in before:
                before.remove(slot)
                changed.append(slot)
        self.used = sorted(before)
        return changed

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "grid": dict(self.grid),
            "used": sorted(self.used_cells),
            "created_at": self.created_at,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SheetRecord":
        grid = data.get("grid")
        if not isinstance(grid, dict):
            raise SheetStoreError("sheet.grid 不是对象")
        spec = GridSpec.from_dict(grid)
        if spec.cols <= 0 or spec.rows <= 0:
            raise SheetStoreError("sheet.grid 的列数/行数必须大于 0")
        used = []
        for slot in data.get("used") or []:
            try:
                value = int(slot)
            except (TypeError, ValueError):
                continue
            if 0 <= value < spec.per_sheet and value not in used:
                used.append(value)
        sheet_id = str(data.get("id") or _new_id())
        name = str(data.get("name") or f"sheet-{sheet_id}")
        return cls(
            id=sheet_id,
            name=name,
            grid=spec.to_dict(),
            used=sorted(used),
            created_at=str(data.get("created_at") or _now()),
            note=str(data.get("note") or ""),
        )


@dataclass
class SheetStore:
    path: Optional[Path] = None
    sheets: List[SheetRecord] = field(default_factory=list)
    printers: List[PrinterProfile] = field(default_factory=list)
    default_printer: str = "default"

    def __post_init__(self) -> None:
        if self.path is not None and not isinstance(self.path, Path):
            self.path = Path(self.path)
        if self.path is None:
            self.path = default_sheets_path()
        self._ensure_printer()

    # ---------------- 打印机 ----------------
    def _ensure_printer(self) -> None:
        if not self.printers:
            self.printers = [PrinterProfile()]
            self.default_printer = self.printers[0].id
        if not any(p.id == self.default_printer for p in self.printers):
            self.default_printer = self.printers[0].id

    def get_printer(self, printer_id: Optional[str] = None) -> PrinterProfile:
        wanted = printer_id or self.default_printer
        for profile in self.printers:
            if profile.id == wanted:
                return profile
        self._ensure_printer()
        return self.printers[0]

    def save_printer(self, profile: PrinterProfile) -> None:
        for i, old in enumerate(self.printers):
            if old.id == profile.id:
                self.printers[i] = profile
                break
        else:
            self.printers.append(profile)
        if not self.default_printer:
            self.default_printer = profile.id

    # ---------------- 纸张 ----------------
    def _unique_name(self, name: str) -> str:
        base = name.strip() or "sheet"
        existing = {s.name for s in self.sheets}
        if base not in existing:
            return base
        n = 2
        while f"{base} #{n}" in existing:
            n += 1
        return f"{base} #{n}"

    def add_sheet(self, name: str, grid: GridSpec, used: Sequence[int] = (), note: str = "") -> SheetRecord:
        spec = GridSpec.from_dict(grid.to_dict())
        sheet = SheetRecord(
            id=_new_id(),
            name=self._unique_name(name),
            grid=spec.to_dict(),
            used=[],
            note=note,
        )
        sheet.mark_used(used)
        self.sheets.append(sheet)
        return sheet

    def remove_sheet(self, sheet_id: str) -> bool:
        before = len(self.sheets)
        self.sheets = [s for s in self.sheets if s.id != sheet_id]
        return len(self.sheets) != before

    def get_sheet(self, sheet_id: str) -> Optional[SheetRecord]:
        for sheet in self.sheets:
            if sheet.id == sheet_id:
                return sheet
        return None

    def mark_used(self, sheet_id: str, slots: Iterable[int]) -> List[int]:
        sheet = self.get_sheet(sheet_id)
        if sheet is None:
            return []
        return sheet.mark_used(slots)

    def mark_free(self, sheet_id: str, slots: Iterable[int]) -> List[int]:
        sheet = self.get_sheet(sheet_id)
        if sheet is None:
            return []
        return sheet.mark_free(slots)

    def free_cells(self, sheet_id: str) -> List[int]:
        sheet = self.get_sheet(sheet_id)
        return sheet.free_cells if sheet else []

    def free_total(self) -> int:
        return sum(s.free_count for s in self.sheets)

    # ---------------- 持久化 ----------------
    def to_dict(self) -> dict:
        return {
            "version": SCHEMA_VERSION,
            "sheets": [s.to_dict() for s in self.sheets],
            "printers": [p.to_dict() for p in self.printers],
            "default_printer": self.default_printer,
        }

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "SheetStore":
        target = Path(path) if path is not None else default_sheets_path()
        source = target
        if not target.exists():
            # v1.3 预览版曾用过 inventory.json；读到就迁移到 sheets.json
            legacy = target.with_name("inventory.json")
            if legacy.exists():
                source = legacy
        if not source.exists():
            return cls(path=target)
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except Exception as exc:
            raise SheetStoreError(f"纸张记录文件读取失败：{source}（{exc}）") from exc
        if not isinstance(data, dict):
            raise SheetStoreError("纸张记录文件顶层必须是 JSON 对象")
        try:
            version = int(data.get("version") or SCHEMA_VERSION)
        except (TypeError, ValueError) as exc:
            raise SheetStoreError("纸张记录文件 version 字段不是整数") from exc
        if version > SCHEMA_VERSION:
            raise SheetStoreError(f"纸张记录文件版本 {version} 太新，当前只支持 {SCHEMA_VERSION}")
        sheets = []
        seen = set()
        for item in data.get("sheets") or []:
            if not isinstance(item, dict):
                continue
            try:
                sheet = SheetRecord.from_dict(item)
            except Exception as exc:
                raise SheetStoreError(f"记录里的纸张记录损坏：{exc}") from exc
            if sheet.id in seen:
                sheet.id = _new_id()
            seen.add(sheet.id)
            sheets.append(sheet)
        printers = []
        for item in data.get("printers") or []:
            if isinstance(item, dict):
                try:
                    printers.append(PrinterProfile.from_dict(item))
                except Exception as exc:
                    raise SheetStoreError(f"记录里的打印机配置损坏：{exc}") from exc
        store = cls(
            path=target,
            sheets=sheets,
            printers=printers,
            default_printer=str(data.get("default_printer") or "default"),
        )
        return store

    def save(self, path: Optional[Path] = None) -> Path:
        target = Path(path) if path is not None else (self.path or default_sheets_path())
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        text = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, target)
        self.path = target
        return target
