# -*- coding: utf-8 -*-
"""普通纸校准页：把当前格子在 A4 上的理论位置印出来，方便和实际标签纸比对。

标签纸本身的边距往往只有 2mm，普通打印机打不到那么靠边，所以校准标记不能印在
标签纸上。这里生成一张**普通纸**参考页，用户在普通纸上打印后，和标签纸对比格子位置，
量出 X/Y 补偿，再回填到打印机配置里。
"""

from __future__ import annotations

import os
from typing import Optional, Sequence

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    ContentStream,
    DictionaryObject,
    FloatObject,
    NameObject,
)

from .config import GridSpec, MM_TO_PT
from .i18n import tr
from .imagex import add_image
from .sheets import DEFAULT_FEED, FEED_ORIENTATIONS
from .textlabel import find_cjk_font

CALIBRATION_DPI = 300
_PX_PER_MM = CALIBRATION_DPI / 25.4


def _px(mm: float) -> int:
    return int(round(float(mm) * _PX_PER_MM))


def _font(size_pt: float) -> ImageFont.FreeTypeFont:
    px = max(8, int(round(size_pt * CALIBRATION_DPI / 72.0)))
    path = find_cjk_font()
    if path:
        try:
            return ImageFont.truetype(path, px)
        except Exception:  # pragma: no cover
            pass
    try:
        return ImageFont.load_default(size=px)  # Pillow 9+ 可选 size
    except Exception:  # pragma: no cover
        return ImageFont.load_default()


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, font, y: int, width: int,
                   fill: int = 0) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) / 2.0, y), text, font=font, fill=fill)


def _feed_text(feed: str, lang: Optional[str]) -> str:
    code = feed if feed in FEED_ORIENTATIONS else DEFAULT_FEED
    return tr(f"calibration.feed.{code}", language=lang)


def _render_page(grid: GridSpec, feed: str, lang: Optional[str]) -> Image.Image:
    width = _px(grid.page_w)
    height = _px(grid.page_h)
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)

    # 1) 格子轮廓：按理论位置画，不加偏移（偏移由用户量出来再填）
    for slot in range(grid.per_sheet):
        x0, y0, x1, y1 = grid.cell_mm(slot)
        left, right = _px(x0), _px(x1)
        top, bottom = _px(grid.page_h - y1), _px(grid.page_h - y0)
        draw.rectangle([left, top, right, bottom], outline=0, width=2)

    # 2) 顶部 100mm 刻度尺，帮用户确认打印没有被缩放
    ruler_y = _px(4.8)
    draw.line([_px(10), ruler_y, _px(200), ruler_y], fill=0, width=1)
    for mm in range(10, 201, 10):
        tick = 4.0 if mm % 50 == 0 else 2.0
        draw.line([_px(mm), ruler_y, _px(mm), ruler_y + _px(tick)], fill=0, width=1)

    # 3) 页面中心的十字，方便目测
    cx, cy = _px(grid.page_w / 2.0), _px(grid.page_h / 2.0)
    arm = _px(6.0)
    draw.line([cx - arm, cy, cx + arm, cy], fill=0, width=1)
    draw.line([cx, cy - arm, cx, cy + arm], fill=0, width=1)

    # 4) 顶部进纸方向 + 顶部箭头
    top_font = _font(7)
    top_text = tr("calibration.top", language=lang) + "   " + _feed_text(feed, lang)
    _draw_centered(draw, top_text, top_font, _px(0.3), width)

    arrow_x = _px(grid.page_w - 16)
    draw.line([arrow_x, _px(5.2), arrow_x, _px(2.0)], fill=0, width=2)
    draw.line([arrow_x - _px(1.5), _px(3.5), arrow_x, _px(2.0)], fill=0, width=2)
    draw.line([arrow_x + _px(1.5), _px(3.5), arrow_x, _px(2.0)], fill=0, width=2)

    # 5) 底部提示：必须 100%
    bottom_font = _font(6)
    _draw_centered(draw, tr("calibration.100", language=lang), bottom_font,
                   height - _px(4.5), width)

    return img


def _render_orientation_page(feed: str, lang: Optional[str]) -> Image.Image:
    """方向测试页：大字 A + 顶部 TOP 箭头 + 粗黑条，用来判断哪面着墨、哪条边朝里。"""
    width, height = _px(210), _px(297)
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)

    # 1) 四角角标：顺便检查打印有没有被缩放
    m = _px(6)
    for x, y, sx, sy in ((m, m, 1, 1), (width - m, m, -1, 1),
                         (m, height - m, 1, -1), (width - m, height - m, -1, -1)):
        draw.line([(x, y), (x + sx * _px(12), y)], fill=0, width=max(1, _px(0.8)))
        draw.line([(x, y), (x, y + sy * _px(12))], fill=0, width=max(1, _px(0.8)))

    # 2) 顶部箭头 + TOP
    cx = width // 2
    top = _px(18)
    draw.polygon([(cx, top), (cx - _px(16), top + _px(22)), (cx + _px(16), top + _px(22))],
                 fill=0)
    draw.rectangle([cx - _px(6), top + _px(22), cx + _px(6), top + _px(34)], fill=0)
    _draw_centered(draw, "TOP", _font(45), top + _px(38), width)

    # 3) 大 A：哪面着墨，一眼能看出
    _draw_centered(draw, "A", _font(340), _px(76), width)

    # 4) 粗黑条：翻到背面也能看出哪面有墨
    draw.rectangle([_px(30), _px(215), width - _px(30), _px(230)], fill=0)

    # 5) 底部说明 + 当前放纸方向
    _draw_centered(draw, tr("calibration.orientation.hint", language=lang), _font(9),
                   height - _px(26), width)
    _draw_centered(draw, _feed_text(feed, lang), _font(10), height - _px(20), width)
    _draw_centered(draw, tr("calibration.100", language=lang), _font(7),
                   height - _px(10), width)
    return img


def _write_image_pdf(img: Image.Image, output_path: str, page_w: float, page_h: float,
                     title: str) -> str:
    """把一张灰度高整页塞进单页 PDF。"""
    writer = PdfWriter()
    page = writer.add_blank_page(width=page_w, height=page_h)
    xobjects = DictionaryObject()
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/ProcSet"): ArrayObject([NameObject("/PDF"), NameObject("/ImageB")]),
            NameObject("/XObject"): xobjects,
        }
    )
    ref, _w, _h = add_image(writer, img)
    name = "/Cal"
    xobjects[NameObject(name)] = ref

    ops = ContentStream(None, writer)
    ops.operations.extend(
        [
            ([], b"q"),
            ([FloatObject(page_w), FloatObject(0), FloatObject(0),
              FloatObject(page_h), FloatObject(0), FloatObject(0)], b"cm"),
            ([NameObject(name)], b"Do"),
            ([], b"Q"),
        ]
    )
    page.replace_contents(ops)

    writer.add_metadata(
        {
            "/Title": title,
            "/Creator": "ulpp",
            "/Producer": "ulpp (pypdf)",
        }
    )
    parent = os.path.dirname(os.path.abspath(output_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(output_path, "wb") as fh:
        writer.write(fh)
    writer.close()
    return output_path


def make_orientation_pdf(
    output_path: str,
    feed: str = DEFAULT_FEED,
    lang: Optional[str] = None,
) -> str:
    """生成一页"方向测试页"PDF：判断打印机往哪面印、纸哪条边朝里。"""
    feed = feed if feed in FEED_ORIENTATIONS else DEFAULT_FEED
    img = _render_orientation_page(feed, lang)
    grid = GridSpec()
    page_w, page_h = grid.frame_pt()
    return _write_image_pdf(img, output_path, page_w, page_h,
                            tr("calibration.orientation.title", language=lang))


def make_calibration_pdf(
    grid: GridSpec,
    output_path: str,
    feed: str = DEFAULT_FEED,
    lang: Optional[str] = None,
) -> str:
    """生成一页普通纸校准页 PDF，返回路径。"""
    feed = feed if feed in FEED_ORIENTATIONS else DEFAULT_FEED
    img = _render_page(grid, feed, lang)
    page_w, page_h = grid.frame_pt()
    return _write_image_pdf(img, output_path, page_w, page_h,
                            tr("calibration.title", language=lang))


