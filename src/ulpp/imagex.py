# -*- coding: utf-8 -*-
"""把一个 PIL 图像塞进 pypdf 生成的 PDF 里（1bit 灰度，Flate 压缩）。"""

from __future__ import annotations

import zlib
from typing import Tuple

from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    EncodedStreamObject,
    FloatObject,
    NameObject,
    NumberObject,
)


def _as_bilevel(img: Image.Image) -> Image.Image:
    if img.mode != "1":
        # 转成“黑/白”二值：阈值保证文字边缘不发灰
        img = img.convert("L").point(lambda v: 255 if v > 160 else 0, mode="1")
    return img


def add_image(writer: PdfWriter, img: Image.Image) -> Tuple[object, float, float]:
    """注册一张图到 writer，返回 (间接引用, 宽, 高)。

    用 EncodedStreamObject + /FlateDecode：pypdf 不会二次编码，
    1bit 的黑白图压缩后通常只剩几 KB，几十张标签也不会把 PDF 撑大。
    """
    gray = _as_bilevel(img)
    w, h = gray.size
    raw = gray.tobytes()
    packed = zlib.compress(raw, 9)

    stream = EncodedStreamObject()
    # 注意：pypdf 6 的 set_data() 不接受带 /Filter 的预压缩数据，这里直接写 _data
    stream._data = packed
    stream[NameObject("/Type")] = NameObject("/XObject")
    stream[NameObject("/Subtype")] = NameObject("/Image")
    stream[NameObject("/Width")] = NumberObject(w)
    stream[NameObject("/Height")] = NumberObject(h)
    stream[NameObject("/ColorSpace")] = NameObject("/DeviceGray")
    stream[NameObject("/BitsPerComponent")] = NumberObject(1)
    stream[NameObject("/Decode")] = ArrayObject([FloatObject(0), FloatObject(1)])
    stream[NameObject("/Filter")] = NameObject("/FlateDecode")

    ref = writer._add_object(stream)
    return ref, float(w), float(h)
