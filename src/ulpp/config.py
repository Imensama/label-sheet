# -*- coding: utf-8 -*-
"""版式参数：A4 不干胶 5×9 网格。单位统一用毫米(mm)，内部换算成 PDF 点(pt)。"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, fields
from typing import Tuple

MM_TO_PT = 72.0 / 25.4


@dataclass(frozen=True)
class GridSpec:
    """一版 A4 不干胶的几何参数。默认值按《A4不干胶批量打印-AI提示词》里的实测值。"""

    page_w: float = 210.0        # 纸张宽 mm
    page_h: float = 297.0        # 纸张高 mm
    cols: int = 5                # 列数
    rows: int = 9                # 行数
    cell_w: float = 40.0         # 单格宽 mm（标签内）
    cell_h: float = 30.0         # 单格高 mm
    pitch_x: float = 41.5        # 列节距 mm
    pitch_y: float = 32.0        # 行节距 mm
    margin_top: float = 6.0      # 上边距 mm
    margin_left: float | None = None   # 左右边距；None = 自动居中
    inset: float = 2.0           # 内容距标签边缘内缩 mm
    knife_width: float = 0.3     # 参考版网格线粗细 pt
    knife_gray: float = 0.72     # 参考版网格线灰度 0~1

    # ---------- 派生量 ----------
    @property
    def margin_x(self) -> float:
        if self.margin_left is not None:
            return float(self.margin_left)
        return (self.page_w - ((self.cols - 1) * self.pitch_x + self.cell_w)) / 2.0

    @property
    def per_sheet(self) -> int:
        return self.cols * self.rows

    def cell_mm(self, index: int) -> Tuple[float, float, float, float]:
        """第 index 格（0 起，按行优先）的 mm 坐标 (x0, y0, x1, y1)，原点在左下角。"""
        col, row = index % self.cols, index // self.cols
        x0 = self.margin_x + col * self.pitch_x
        top = self.margin_top + row * self.pitch_y
        # PDF 原点在左下：把"从上往下数的 top"换成 y
        y1 = self.page_h - top
        y0 = y1 - self.cell_h
        return x0, y0, x0 + self.cell_w, y1

    def cell_pt(self, index: int) -> Tuple[float, float, float, float]:
        return tuple(v * MM_TO_PT for v in self.cell_mm(index))  # type: ignore[return-value]

    def frame_pt(self) -> Tuple[float, float]:
        return self.page_w * MM_TO_PT, self.page_h * MM_TO_PT

    # ---------- 存取 ----------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GridSpec":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def load(cls, path: str) -> "GridSpec":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)
