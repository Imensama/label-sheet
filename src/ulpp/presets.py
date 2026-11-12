# -*- coding: utf-8 -*-
"""常见 A4 不干胶（预切）规格预设。

每家标签纸的裁切线都会差一点点，这里给的是**按 A4 满版/居中**算出来的几何尺寸，
选中后仍可在界面上微调节距、边距和安全边。

- ``key`` 是稳定的 id（``45``、``24`` ……），显示名走语言包 ``presets.<key>``；
- ``by_key`` 同时接受 id、旧版中文名和英文名，老命令行脚本不用改；
- 45 格那套是之前实测量过的规格，节距 41.5×32、上边距 6mm，保持原样；
- 其余规格多为“满版裁切”（格子紧挨着，没有刀缝），seam=0。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .config import GridSpec
from .i18n import available_languages, tr


@dataclass(frozen=True)
class Preset:
    key: str            # 稳定 id，语言无关；显示名见 title
    cols: int
    rows: int
    cell_w: float
    cell_h: float
    seam_x: float = 0.0
    seam_y: float = 0.0
    margin_top: Optional[float] = None   # None = 垂直居中
    inset: float = 2.0

    @property
    def count(self) -> int:
        return self.cols * self.rows

    @property
    def title(self) -> str:
        return tr(f"presets.{self.key}")

    def title_in(self, lang: str) -> str:
        return tr(f"presets.{self.key}", language=lang)

    def to_grid(self, page_w: float = 210.0, page_h: float = 297.0) -> GridSpec:
        pitch_x = self.cell_w + self.seam_x
        pitch_y = self.cell_h + self.seam_y
        block_h = (self.rows - 1) * pitch_y + self.cell_h
        margin_top = self.margin_top if self.margin_top is not None else (page_h - block_h) / 2.0
        return GridSpec(
            page_w=page_w,
            page_h=page_h,
            cols=self.cols,
            rows=self.rows,
            cell_w=self.cell_w,
            cell_h=self.cell_h,
            pitch_x=pitch_x,
            pitch_y=pitch_y,
            margin_top=margin_top,
            margin_left=None,
            inset=self.inset,
        )


PRESETS: List[Preset] = [
    # 45 格这套就是原先校验过的规格
    Preset("45", 5, 9, 40.0, 30.0, seam_x=1.5, seam_y=2.0, margin_top=6.0),
    Preset("24", 3, 8, 70.0, 37.0),
    Preset("21", 3, 7, 70.0, 42.3),
    Preset("30", 3, 10, 70.0, 29.7),
    Preset("12", 2, 6, 99.0, 49.5),
    Preset("10", 2, 5, 99.0, 59.4),
    Preset("8", 2, 4, 99.0, 74.25),
    Preset("6", 2, 3, 99.0, 99.0),
    Preset("4", 2, 2, 105.0, 148.5),
    Preset("2", 1, 2, 210.0, 148.5),
    Preset("40", 4, 10, 48.0, 25.0, seam_x=1.5, seam_y=2.0),
    Preset("72", 6, 12, 33.0, 23.0, seam_x=1.0, seam_y=1.0),
    Preset("65", 5, 13, 38.0, 22.0, seam_x=1.5, seam_y=0.0),
    Preset("44", 4, 11, 46.0, 25.0, seam_x=1.5, seam_y=1.5),
]

DEFAULT_PRESET_KEY = PRESETS[0].key


def _matches_title(preset: Preset, text: str) -> bool:
    wanted = text.strip()
    if not wanted:
        return False
    for lang in available_languages():
        try:
            if preset.title_in(lang).strip() == wanted:
                return True
        except Exception:  # pragma: no cover - 语言包损坏时不影响 id 查找
            continue
    return False


def by_key(key: str) -> Preset:
    """按 id、旧版中文名或英文名找预设。"""
    for p in PRESETS:
        if p.key == key:
            return p
    for p in PRESETS:
        if _matches_title(p, key):
            return p
    raise KeyError(tr("presets.error.unknown", key=key))


def keys() -> List[str]:
    return [p.key for p in PRESETS]


def match_grid(grid: GridSpec) -> Optional[str]:
    """反查当前参数最接近的预设（用于界面回显），返回稳定 id。"""
    for p in PRESETS:
        g = p.to_grid(grid.page_w, grid.page_h)
        if (g.cols, g.rows) != (grid.cols, grid.rows):
            continue
        if abs(g.cell_w - grid.cell_w) < 0.3 and abs(g.cell_h - grid.cell_h) < 0.3:
            return p.key
    return None
