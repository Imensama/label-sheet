# -*- coding: utf-8 -*-
"""解析 PDF：找出每一页里的“卡片”（名称/编号/尺寸/序号/数量/颜色 + 图）。

坐标约定
--------
pdfplumber 用「左上角原点、y 向下」；PDF 用户坐标用「左下角原点、y 向上」。
本模块内部先按 pdfplumber 坐标算，最后统一换算成 PDF 坐标存进 Card.clip_pdf。
"""

from __future__ import annotations

import os
import re
import statistics
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

import pdfplumber

# ---------------------------------------------------------------- 文本规则

NAME_RE = re.compile(r"文件名称\s*[：:]?\s*([^\n]+)")
SIZE_RE = re.compile(r"(?:包络)?尺寸\s*[：:]?\s*([^\n]+)")
SEQ_RE = re.compile(r"序号\s*[：:]?\s*(\d+)")
QTY_RE = re.compile(r"数量\s*[：:]?\s*(\d+)")
COLOR_RE = re.compile(r"颜色\s*[：:]?\s*([^\n]+)")
DWG_NO_RE = re.compile(r"图号\s*[：:]?\s*([^\n]*)")

ANCHOR = "文件名称"

# 卡片内容距离格线的裁剪余量（pt）：避免把表格线条一起缩进标签
EDGE_PAD_PT = 1.2
# 聚类容差（pt）
CLUSTER_TOL = 6.0
# 判断“表格线”的最大粗细（pt）
RULE_THICKNESS = 1.6


@dataclass
class Card:
    """一张标签的数据。"""

    name: str = ""
    seq: Optional[int] = None
    qty: int = 1
    size: str = ""
    color: str = ""
    dwg_no: str = ""
    col: int = 0
    row: int = 0
    # PDF 用户坐标（左下原点）
    cell_pdf: Tuple[float, float, float, float] = (0, 0, 0, 0)
    clip_pdf: Tuple[float, float, float, float] = (0, 0, 0, 0)

    @property
    def label(self) -> str:
        return self.name or "?"


@dataclass
class PageCards:
    page_no: int                      # 1 起的物理页号
    cards: List[Card] = field(default_factory=list)
    cols: int = 0
    rows: int = 0
    warnings: List[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.cards)


@dataclass
class PdfCards:
    path: str
    n_pages: int
    pages: List[PageCards] = field(default_factory=list)

    @property
    def cards(self) -> List[Card]:
        return [c for p in self.pages for c in p.cards]

    @property
    def stickers(self) -> int:
        return sum(c.qty for c in self.cards)


# ---------------------------------------------------------------- 工具函数

def _cluster(values: Iterable[float], tol: float = CLUSTER_TOL) -> List[float]:
    groups: List[List[float]] = []
    for v in sorted(values):
        if groups and v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def _pitch(starts: Sequence[float], fallback: float) -> float:
    """由相邻起点估计节距。"""
    if len(starts) >= 2:
        diffs = [b - a for a, b in zip(starts, starts[1:]) if b - a > 1]
        if diffs:
            return statistics.median(diffs)
    return fallback


def _bbox_union(boxes: Iterable[Tuple[float, float, float, float]]):
    boxes = list(boxes)
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _grid_positions(drawings: Sequence[Tuple[float, float, float, float]], page_w: float, page_h: float):
    """找出贯通整页的表格线位置（列线 x、行线 y），用来识别“格线”。"""
    vgrid, hgrid = [], []
    for x0, y0, x1, y1 in drawings:
        if (x1 - x0) <= 2.0 and (y1 - y0) > 0.3 * page_h:
            vgrid.append((x0 + x1) / 2)
        if (y1 - y0) <= 2.0 and (x1 - x0) > 0.3 * page_w:
            hgrid.append((y0 + y1) / 2)
    return sorted(vgrid), sorted(hgrid)


def _is_rule(
    box: Tuple[float, float, float, float],
    cell: Sequence[float],
    vgrid: Sequence[float] = (),
    hgrid: Sequence[float] = (),
) -> bool:
    """细长的水平/垂直表格线（含贴格边的格线），不应该算进卡片内容。"""
    cw, ch = cell[2] - cell[0], cell[3] - cell[1]
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if h <= RULE_THICKNESS and w >= 0.9 * cw:
        return True
    if w <= RULE_THICKNESS and h >= 0.9 * ch:
        return True
    if h <= 2.0 and w >= 0.5 * cw and any(abs(y0 - g) < 2.0 or abs(y1 - g) < 2.0 for g in hgrid):
        return True
    if w <= 2.0 and h >= 0.5 * ch and any(abs(x0 - g) < 2.0 or abs(x1 - g) < 2.0 for g in vgrid):
        return True
    return False


def _is_frame(box: Tuple[float, float, float, float], cw: float, ch: float) -> bool:
    """几乎占满整格的边框/外框（3 列 1 行这类大格子常见），不算卡片内容。"""
    w, h = box[2] - box[0], box[3] - box[1]
    return w >= 0.9 * cw and h >= 0.9 * ch


FIELD_LABELS = ("文件名称", "图号", "包络尺寸", "尺寸", "序号", "数量", "颜色")


def _group_lines(words: Sequence[dict], tol: float = 2.5) -> List[dict]:
    """把词按 top 聚成文本行。"""
    lines: List[dict] = []
    for w in sorted(words, key=lambda x: (x["top"], x["x0"])):
        if lines and abs(w["top"] - lines[-1]["top"]) <= tol:
            lines[-1]["words"].append(w)
        else:
            lines.append({"top": w["top"], "words": [w]})
    for ln in lines:
        ln["words"].sort(key=lambda x: x["x0"])
        ln["text"] = "".join(w["text"] for w in ln["words"])
        ln["x0"] = min(w["x0"] for w in ln["words"])
        ln["x1"] = max(w["x1"] for w in ln["words"])
        ln["bottom"] = max(w["bottom"] for w in ln["words"])
    return lines


def _card_lines(lines: Sequence[dict], anchor_word: dict) -> List[Tuple[str, Tuple[float, float, float, float]]]:
    """从“文件名称”所在行开始，把这张卡片的字段行捡出来。

    - 行首可能残留左边格溢出的字（如“支架（改）文件名称:…”），从字段标签处截断
    - “颜色”值太长换行的，紧跟着的一行也算进来
    """
    ai = next((i for i, ln in enumerate(lines) if any(w is anchor_word for w in ln["words"])), None)
    if ai is None:
        return []

    picked: List[Tuple[str, Tuple[float, float, float, float]]] = []
    prev_label = ""
    prev_bottom = None
    for k, ln in enumerate(lines[ai:]):
        j = next((i for i, w in enumerate(ln["words"]) if w["text"].startswith(FIELD_LABELS)), None)
        if j is not None:
            ws = ln["words"][j:]
            text = "".join(w["text"] for w in ws)
            if k > 0 and text.startswith(ANCHOR):
                break                      # 撞到下一张卡片的开头，收工
            label = next(l for l in FIELD_LABELS if text.startswith(l))
            box = (min(w["x0"] for w in ws), ln["top"], max(w["x1"] for w in ws), ln["bottom"])
            picked.append((text, box))
            prev_label, prev_bottom = label, ln["bottom"]
            continue
        if picked and prev_label == "颜色" and prev_bottom is not None and ln["top"] - prev_bottom < 8:
            picked.append((ln["text"], (ln["x0"], ln["top"], ln["x1"], ln["bottom"])))
            prev_bottom = ln["bottom"]
            continue
        break
    return picked


def parse_card_text(text: str) -> dict:
    """从卡片区域文本里抠字段。"""
    out = {"name": "", "seq": None, "qty": None, "size": "", "color": "", "dwg_no": ""}
    m = NAME_RE.search(text)
    if m:
        out["name"] = m.group(1).strip()
    m = SIZE_RE.search(text)
    if m:
        out["size"] = m.group(1).strip()
    m = SEQ_RE.search(text)
    if m:
        out["seq"] = int(m.group(1))
    m = QTY_RE.search(text)
    if m:
        out["qty"] = int(m.group(1))
    m = COLOR_RE.search(text)
    if m:
        out["color"] = m.group(1).strip()
    m = DWG_NO_RE.search(text)
    if m:
        out["dwg_no"] = m.group(1).strip()
    return out


# ---------------------------------------------------------------- 解析一页

def _page_drawings(page) -> List[Tuple[float, float, float, float]]:
    boxes = []
    for coll in (page.rects, page.lines, page.curves):
        for o in coll:
            boxes.append((o["x0"], o["top"], o["x1"], o["bottom"]))
    return boxes


def parse_page(page, page_no: int, page_h_pt: float) -> PageCards:
    """解析 pdfplumber 的一页。page_h_pt = 该页 PDF 坐标下的高度。"""
    res = PageCards(page_no=page_no)
    words = page.extract_words(x_tolerance=2, y_tolerance=3)
    anchors = [w for w in words if w["text"].startswith(ANCHOR)]
    if not anchors:
        res.warnings.append(f"第 {page_no} 页没有找到“文件名称”卡片，已跳过")
        return res

    xs = _cluster([a["x0"] for a in anchors])
    ys = _cluster([a["top"] for a in anchors])
    res.cols, res.rows = len(xs), len(ys)

    fallback_w = page.width / max(1, len(xs))
    fallback_h = page.height / max(1, len(ys))
    pitch_x = _pitch(xs, fallback_w)
    pitch_y = _pitch(ys, fallback_h)

    drawings = _page_drawings(page)
    vgrid, hgrid = _grid_positions(drawings, page.width, page.height)

    for a in anchors:
        ci = min(range(len(xs)), key=lambda i: abs(a["x0"] - xs[i]))
        ri = min(range(len(ys)), key=lambda i: abs(a["top"] - ys[i]))
        cx0, cy0 = xs[ci], ys[ri]
        cell = (cx0, cy0, min(cx0 + pitch_x, page.width), min(cy0 + pitch_y, page.height))
        cw, ch = cell[2] - cell[0], cell[3] - cell[1]

        # 卡片字段行：词按“最近的列起点”归属，避免把隔壁格的字吸进来；
        # 行的下界用锚点自身的位置（同一行不同卡片 top 会有 1~2pt 抖动）
        lo = a["top"] - 2.5
        hi = cell[3] - 0.5
        cell_words = [w for w in words
                      if min(range(len(xs)), key=lambda i: abs(w["x0"] - xs[i])) == ci
                      and lo <= w["top"] <= hi]
        cell_lines = _group_lines(cell_words)
        picked = _card_lines(cell_lines, a)
        if not picked:
            res.warnings.append(f"第 {page_no} 页第 {ri + 1} 行第 {ci + 1} 列疑似卡片，但定位不到字段行，已跳过")
            continue
        text = "\n".join(t for t, _ in picked)
        fields = parse_card_text(text)
        if not fields["name"]:
            res.warnings.append(f"第 {page_no} 页第 {ri + 1} 行第 {ci + 1} 列疑似卡片，但取不到名称，已跳过")
            continue

        # 内容包围盒：卡片字段文字 + 格内图形（排除表格线/外框）
        boxes = [box for _, box in picked]
        for d in drawings:
            if d[0] >= cell[0] - 0.3 and d[1] >= cell[1] - 0.3 and d[2] <= cell[2] + 0.3 and d[3] <= cell[3] + 0.3:
                if _is_rule(d, cell, vgrid, hgrid) or _is_frame(d, cw, ch):
                    continue
                boxes.append(d)

        # 兜底：完全没有图形时只按文字框裁
        content = _bbox_union(boxes)
        if content is None:
            res.warnings.append(f"第 {page_no} 页 “{fields['name']}” 取不到内容区域，已跳过")
            continue

        # 贴边裁剪：把紧贴格线的部分让开
        x0, y0, x1, y1 = content
        if x0 < cell[0] + EDGE_PAD_PT:
            x0 = cell[0] + EDGE_PAD_PT
        if y0 < cell[1] + EDGE_PAD_PT:
            y0 = cell[1] + EDGE_PAD_PT
        if x1 > cell[2] - EDGE_PAD_PT:
            x1 = cell[2] - EDGE_PAD_PT
        if y1 > cell[3] - EDGE_PAD_PT:
            y1 = cell[3] - EDGE_PAD_PT
        if x1 - x0 < 5 or y1 - y0 < 5:
            res.warnings.append(f"第 {page_no} 页 “{fields['name']}” 内容区域异常，已跳过")
            continue

        qty = fields["qty"] if fields["qty"] else 1
        res.cards.append(
            Card(
                name=fields["name"],
                seq=fields["seq"],
                qty=qty,
                size=fields["size"],
                color=fields["color"],
                dwg_no=fields["dwg_no"],
                col=ci,
                row=ri,
                cell_pdf=(cell[0], page_h_pt - cell[3], cell[2], page_h_pt - cell[1]),
                clip_pdf=(x0, page_h_pt - y1, x1, page_h_pt - y0),
            )
        )

    res.cards.sort(key=lambda c: (c.row, c.col))
    return res


# ---------------------------------------------------------------- 解析一份 PDF

def parse_pdf(path: str, first_page_only: bool = False, progress=None) -> PdfCards:
    """解析一份 PDF，返回每页的卡片。"""
    from pypdf import PdfReader

    reader = PdfReader(path)
    n_pages = len(reader.pages)
    result = PdfCards(path=path, n_pages=n_pages)

    with pdfplumber.open(path) as pdf:
        pages = pdf.pages[:1] if first_page_only else pdf.pages
        for idx, page in enumerate(pages):
            try:
                page_h = float(reader.pages[idx].mediabox.height)
            except Exception:                                 # pragma: no cover
                page_h = float(page.height)
            try:
                info = parse_page(page, idx + 1, page_h)
            except Exception as exc:                          # pragma: no cover
                info = PageCards(page_no=idx + 1, warnings=[f"第 {idx + 1} 页解析失败：{exc}"])
            result.pages.append(info)
            if progress:
                progress(idx + 1, len(pages))
    return result


def parse_many(paths: Iterable[str], first_page_only: bool = False, progress=None) -> List[PdfCards]:
    out = []
    for p in paths:
        out.append(parse_pdf(p, first_page_only=first_page_only, progress=progress))
    return out
