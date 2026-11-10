# -*- coding: utf-8 -*-
"""文字标签：把一段文字自动换行、自动选字号，渲染成一张位图，再塞进小格。

为什么用位图而不是矢量文字：
    输出 PDF 要能显示中文，就得内嵌一套中文字体（动辄 10MB+）。
    标签本身很小，600dpi 的 1bit 位图打印出来和矢量字几乎看不出差别，
    而且不涉及字体授权问题，生成的 PDF 也小。图那部分仍然是矢量。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

# 常见中文字体，按优先级找
CJK_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",      # 微软雅黑
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",    # 黑体
    r"C:\Windows\Fonts\simsun.ttc",    # 宋体
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]

# 份数后缀：优先“|2”，其次“ ×2 / x2”（要求前面不是数字，避免把 “120×80×6” 当份数）
_COPY_SUFFIX = re.compile(r"(?:\|\s*(\d{1,3})|(?<!\d)\s+[×xX]\s*(\d{1,3}))\s*$")


@dataclass
class TextItem:
    text: str
    copies: int = 1
    index: int = 0

    @property
    def label(self) -> str:
        return self.text.replace("\n", " ")[:24]


def parse_text_block(block: str, default_copies: int = 1) -> List[TextItem]:
    """一行一张标签；行尾写 “|2” 或 “×2” 表示这一张印 2 份。"""
    items: List[TextItem] = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        copies = default_copies
        m = _COPY_SUFFIX.search(line)
        if m:
            copies = max(1, int(m.group(1) or m.group(2)))
            line = line[: m.start()].rstrip()
        if not line:
            continue
        items.append(TextItem(text=line, copies=max(1, copies), index=len(items)))
    return items


def find_cjk_font(explicit: Optional[str] = None) -> Optional[str]:
    if explicit and os.path.exists(explicit):
        return explicit
    for path in CJK_FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


# ---------------------------------------------------------------- 排版

def _tokenize(text: str) -> List[str]:
    """中文按字、英文按词切，方便折行。"""
    tokens: List[str] = []
    buf = ""
    for ch in text:
        if ch.isspace():
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(" ")
        elif ord(ch) > 0x2E7F:          # CJK 及全角标点：单字成 token
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
        else:
            buf += ch
    if buf:
        tokens.append(buf)
    return tokens


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: float, draw: ImageDraw.ImageDraw) -> List[str]:
    lines: List[str] = []
    for para in text.split("\n"):
        if not para.strip():
            lines.append("")
            continue
        cur = ""
        for tok in _tokenize(para):
            cand = cur + tok
            if cur and draw.textlength(cand, font=font) > max_w:
                lines.append(cur.rstrip())
                cur = tok.lstrip()
            else:
                cur = cand
        lines.append(cur.rstrip())
    # 避免最后一行只剩一个字（“孤字”），从上一行挪一个过来
    if len(lines) >= 2 and len(lines[-1]) == 1 and len(lines[-2]) > 2:
        moved = lines[-2][-1]
        cand_prev = lines[-2][:-1]
        cand_last = moved + lines[-1]
        if (draw.textlength(cand_prev, font=font) <= max_w
                and draw.textlength(cand_last, font=font) <= max_w):
            lines[-2], lines[-1] = cand_prev, cand_last
    return lines


def _fit(text: str, font_path: Optional[str], box_w: int, box_h: int,
         max_pt: float, min_pt: float = 4.0, line_gap: float = 1.15):
    """从大往小试字号，找到能把文字塞进框里且尽量大的那档。"""
    probe = Image.new("1", (8, 8), 1)
    draw = ImageDraw.Draw(probe)
    best = None
    pt = max_pt
    while pt >= min_pt:
        px = max(6, int(round(pt * 4.1667)))     # 600dpi: 1pt ≈ 4.1667px
        try:
            font = ImageFont.truetype(font_path, px) if font_path else ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()
        lines = _wrap(text, font, box_w, draw)
        line_h = px * line_gap
        widest = max((draw.textlength(l, font=font) for l in lines), default=0)
        total_h = line_h * len(lines)
        if widest <= box_w and total_h <= box_h:
            best = (font, lines, px, line_h, total_h)
            break
        pt -= 0.5 if pt > 12 else 0.25
    if best is None:
        px = max(6, int(round(min_pt * 4.1667)))
        font = ImageFont.truetype(font_path, px) if font_path else ImageFont.load_default()
        lines = _wrap(text, font, box_w, draw)
        best = (font, lines, px, px * line_gap, px * line_gap * len(lines))
    return best


def fit_size(text: str, width_px: int, height_px: int,
             font_path: Optional[str] = None,
             max_pt: float = 48.0, min_pt: float = 4.0,
             margin_ratio: float = 0.06) -> float:
    """这段文字在框里能用的最大字号（pt，按 600dpi 折算）。"""
    width_px = max(8, int(width_px))
    height_px = max(8, int(height_px))
    mx = int(width_px * margin_ratio)
    my = int(height_px * margin_ratio)
    box_w, box_h = max(4, width_px - 2 * mx), max(4, height_px - 2 * my)
    font_path = font_path or find_cjk_font()
    _font, _lines, px, _lh, _th = _fit(text, font_path, box_w, box_h, max_pt, min_pt)
    return px / 4.1667


def render_text_label(text: str, width_px: int, height_px: int,
                      font_path: Optional[str] = None,
                      align: str = "center",
                      max_pt: float = 48.0,
                      min_pt: float = 4.0,
                      margin_ratio: float = 0.06,
                      fixed_pt: Optional[float] = None) -> Image.Image:
    """把一段文字排进 width_px × height_px 的 1bit 图（白底黑字）。

    fixed_pt 给定时用固定字号（“统一字号”模式），否则自动取能容纳的最大字号。
    """
    width_px = max(8, int(width_px))
    height_px = max(8, int(height_px))
    mx = int(width_px * margin_ratio)
    my = int(height_px * margin_ratio)
    box_w, box_h = max(4, width_px - 2 * mx), max(4, height_px - 2 * my)

    font_path = font_path or find_cjk_font()
    if fixed_pt:
        px = max(6, int(round(fixed_pt * 4.1667)))
        try:
            font = ImageFont.truetype(font_path, px) if font_path else ImageFont.load_default()
        except Exception:                      # pragma: no cover
            font = ImageFont.load_default()
        lines = _wrap(text, font, box_w, ImageDraw.Draw(Image.new("1", (8, 8), 1)))
        line_h, total_h = px * 1.15, px * 1.15 * len(lines)
    else:
        font, lines, px, line_h, total_h = _fit(text, font_path, box_w, box_h, max_pt, min_pt)

    img = Image.new("1", (width_px, height_px), 1)   # 1 = 白
    draw = ImageDraw.Draw(img)
    y = my + (box_h - total_h) / 2.0
    for line in lines:
        w = draw.textlength(line, font=font)
        if align == "left":
            x = mx
        elif align == "right":
            x = width_px - mx - w
        else:
            x = (width_px - w) / 2.0
        draw.text((x, y), line, font=font, fill=0)   # 0 = 黑
        y += line_h
    return img


def render_items(items: Sequence[TextItem], width_px: int, height_px: int,
                 font_path: Optional[str] = None, align: str = "center",
                 max_pt: float = 48.0) -> List[Image.Image]:
    return [render_text_label(i.text, width_px, height_px, font_path, align, max_pt) for i in items]
