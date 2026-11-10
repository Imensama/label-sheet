# -*- coding: utf-8 -*-
"""排版与输出：把每张卡片按“数量”复制，等比塞进 A4 不干胶的 5×9 小格。

实现要点
--------
用 pypdf 把源 PDF 的每一页做成一个 Form XObject（BBox = 整页），
再在 A4 目标页上用「裁剪路径 + 变换矩阵 + Do」把需要的区域画到指定小格里。
这样同一个源页只内嵌一份数据，输出体积小、内容仍是矢量。
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    ContentStream,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
)

from .config import GridSpec, MM_TO_PT
from .parser import Card, PdfCards


@dataclass
class Sticker:
    """一张贴纸：某份 PDF 的某页上的某张卡片，第 copy_no 份。"""

    pdf_path: str
    page_index: int          # 0 起
    page_no: int             # 1 起，仅用于清单
    card: Card
    copy_no: int             # 1 起

    @property
    def total_copies(self) -> int:
        return self.card.qty


def collect_stickers(pdfs: Sequence[PdfCards]) -> List[Sticker]:
    """按“文件 → 页 → 行 → 列”顺序展开，数量 N 就连排 N 张。"""
    out: List[Sticker] = []
    for pdf in pdfs:
        for page in pdf.pages:
            for card in page.cards:
                for k in range(max(1, card.qty)):
                    out.append(
                        Sticker(
                            pdf_path=pdf.path,
                            page_index=page.page_no - 1,
                            page_no=page.page_no,
                            card=card,
                            copy_no=k + 1,
                        )
                    )
    return out


class _FormCache:
    """把源 PDF 的每一页转成 Form XObject，同一页只做一次。"""

    def __init__(self, writer: PdfWriter) -> None:
        self.writer = writer
        self._readers: Dict[str, PdfReader] = {}
        self._forms: Dict[Tuple[str, int], Tuple[str, object]] = {}

    def _reader(self, path: str) -> PdfReader:
        if path not in self._readers:
            self._readers[path] = PdfReader(path)
        return self._readers[path]

    def get(self, path: str, page_index: int) -> Tuple[str, object]:
        key = (path, page_index)
        if key in self._forms:
            return self._forms[key]

        src = self._reader(path).pages[page_index]
        if int(src.rotation or 0) % 360:
            src.transfer_rotation_to_content()  # 让页面内容“躺正”

        mb = src.mediabox
        try:
            data = src._get_contents_as_bytes() or b""
        except Exception:  # pragma: no cover - 极少数 PDF 走这里
            stream = src.get_contents()
            data = stream.get_data() if stream is not None else b""

        resources = src.get("/Resources")
        resources = resources.clone(self.writer) if resources is not None else DictionaryObject()

        form = DecodedStreamObject()
        form.set_data(data)
        form[NameObject("/Type")] = NameObject("/XObject")
        form[NameObject("/Subtype")] = NameObject("/Form")
        form[NameObject("/FormType")] = NumberObject(1)
        form[NameObject("/BBox")] = ArrayObject(
            [
                FloatObject(float(mb.left)),
                FloatObject(float(mb.bottom)),
                FloatObject(float(mb.right)),
                FloatObject(float(mb.top)),
            ]
        )
        form[NameObject("/Resources")] = resources

        ref = self.writer._add_object(form)
        name = f"/Xf{len(self._forms)}"
        self._forms[key] = (name, ref)
        return self._forms[key]


def _placement(clip: Sequence[float], cell: Sequence[float], inset_mm: float):
    """算出「源区域 → 目标小格」的缩放和位移（含安全边、居中）。

    返回 (scale, tx, ty, 目标矩形)。tx/ty 是页面原点的平移量：
    源坐标 (x, y) 会被画到 (x*scale + tx, y*scale + ty)。
    """
    inset = inset_mm * MM_TO_PT
    cx0, cy0, cx1, cy1 = cell
    avail_x0, avail_y0 = cx0 + inset, cy0 + inset
    avail_x1, avail_y1 = cx1 - inset, cy1 - inset
    sw, sh = clip[2] - clip[0], clip[3] - clip[1]
    aw, ah = avail_x1 - avail_x0, avail_y1 - avail_y0
    if sw <= 0 or sh <= 0:
        return None
    scale = min(aw / sw, ah / sh)
    tw, th = sw * scale, sh * scale
    tx0 = avail_x0 + (aw - tw) / 2.0
    ty0 = avail_y0 + (ah - th) / 2.0
    tx = tx0 - clip[0] * scale
    ty = ty0 - clip[1] * scale
    return scale, tx, ty, (tx0, ty0, tx0 + tw, ty0 + th)


def _num(v: float) -> FloatObject:
    return FloatObject(round(float(v), 4))


def build_pdf(
    stickers: Sequence[Sticker],
    grid: GridSpec,
    output_path: str,
    knife_lines: bool = False,
    progress=None,
) -> List[dict]:
    """生成一个 A4 标签 PDF，返回逐张标签的清单行。"""
    writer = PdfWriter()
    cache = _FormCache(writer)
    page_w, page_h = grid.frame_pt()
    per_sheet = grid.per_sheet
    n_sheets = max(1, (len(stickers) + per_sheet - 1) // per_sheet)
    manifest: List[dict] = []

    for sheet in range(n_sheets):
        page = writer.add_blank_page(width=page_w, height=page_h)
        xobjects = DictionaryObject()
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/ProcSet"): ArrayObject([NameObject("/PDF")]),
                NameObject("/XObject"): xobjects,
            }
        )

        ops = []
        if knife_lines:
            gray = FloatObject(round(grid.knife_gray, 3))
            for i in range(per_sheet):
                x0, y0, x1, y1 = grid.cell_pt(i)
                ops += [
                    ([], b"q"),
                    ([gray], b"G"),          # DeviceGray 描边色：浅灰
                    ([FloatObject(round(grid.knife_width, 3))], b"w"),
                    ([_num(x0), _num(y0), _num(x1 - x0), _num(y1 - y0)], b"re"),
                    ([], b"S"),
                    ([], b"Q"),
                ]

        for slot in range(per_sheet):
            idx = sheet * per_sheet + slot
            if idx >= len(stickers):
                break
            st = stickers[idx]
            cell = grid.cell_pt(slot)
            placed = _placement(st.card.clip_pdf, cell, grid.inset)
            if placed is None:
                continue
            scale, tx, ty, target = placed
            name, ref = cache.get(st.pdf_path, st.page_index)
            xobjects[NameObject(name)] = ref

            # 裁剪框必须用「内容区」而不是整格，否则安全边里会漏出相邻内容
            ops += [
                ([], b"q"),
                ([_num(target[0]), _num(target[1]), _num(target[2] - target[0]), _num(target[3] - target[1])], b"re"),
                ([], b"W"),
                ([], b"n"),
                ([_num(scale), FloatObject(0), FloatObject(0), _num(scale), _num(tx), _num(ty)], b"cm"),
                ([NameObject(name)], b"Do"),
                ([], b"Q"),
            ]
            manifest.append(
                {
                    "sheet": sheet + 1,
                    "cell": slot + 1,
                    "row": slot // grid.cols + 1,
                    "col": slot % grid.cols + 1,
                    "file": os.path.basename(st.pdf_path),
                    "pdf_page": st.page_no,
                    "seq": st.card.seq if st.card.seq is not None else "",
                    "name": st.card.name,
                    "qty": st.card.qty,
                    "copy": st.copy_no,
                    "scale_pct": round(scale * 100, 1),
                }
            )

        content = ContentStream(None, writer)
        content.operations.extend(ops)
        page.replace_contents(content)

        if progress:
            progress(sheet + 1, n_sheets)

    writer.add_metadata(
        {
            "/Title": "A4 不干胶 PDF标签" + ("（刀线校样版）" if knife_lines else "（生产版）"),
            "/Creator": "label-sheet",
            "/Producer": "label-sheet (pypdf)",
        }
    )
    with open(output_path, "wb") as fh:
        writer.write(fh)
    writer.close()
    return manifest


def write_manifest(manifest: Sequence[dict], csv_path: str) -> None:
    fields = ["sheet", "cell", "row", "col", "file", "pdf_page", "seq", "name", "qty", "copy", "scale_pct"]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest)


def build_all(
    pdfs: Sequence[PdfCards],
    grid: GridSpec,
    out_dir: str,
    base_name: str = "PDF标签",
    make_proof: bool = True,
    make_csv: bool = True,
    progress=None,
    log=None,
) -> Dict[str, str]:
    """一次性生成生产版 / 校样版 / 清单，返回各文件路径。"""
    os.makedirs(out_dir, exist_ok=True)
    stickers = collect_stickers(pdfs)
    if not stickers:
        raise ValueError("没有解析到任何卡片，请检查 PDF 是否是“PDF 卡片”格式")

    outputs: Dict[str, str] = {}
    total_sheets = max(1, (len(stickers) + grid.per_sheet - 1) // grid.per_sheet)

    def _p(prefix):
        return (lambda done, total: progress(prefix, done, total)) if progress else None

    prod = os.path.join(out_dir, f"{base_name}_生产版.pdf")
    if log:
        log(f"排 {len(stickers)} 张贴纸，共 {total_sheets} 版 → {os.path.basename(prod)}")
    manifest = build_pdf(stickers, grid, prod, knife_lines=False, progress=_p("生产版"))
    outputs["production"] = prod

    if make_proof:
        proof = os.path.join(out_dir, f"{base_name}_刀线校样版.pdf")
        if log:
            log(f"生成刀线校样版 → {os.path.basename(proof)}")
        build_pdf(stickers, grid, proof, knife_lines=True, progress=_p("校样版"))
        outputs["proof"] = proof

    if make_csv:
        csv_path = os.path.join(out_dir, f"{base_name}_标签清单.csv")
        write_manifest(manifest, csv_path)
        outputs["manifest"] = csv_path
        if log:
            log(f"标签清单 → {os.path.basename(csv_path)}")

    return outputs
