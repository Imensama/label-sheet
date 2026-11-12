# -*- coding: utf-8 -*-
"""排版与输出：把卡片 / 文字标签按“数量”复制，等比塞进 A4 不干胶的小格。

两种内容：
1) PDF 卡片（矢量）：把源 PDF 每页做成一个 Form XObject，用「裁剪路径 + 缩放矩阵 + Do」画进小格，
   同一个源页只内嵌一份数据，输出体积小、内容仍是矢量。
2) 文字标签（位图）：一段文字自动折行、自动选字号后渲染成 600dpi 位图再贴进小格，
   好处是不用内嵌中文字体（那会让 PDF 大十几 MB）。
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Union

from PIL import Image
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
from .imagex import add_image
from .i18n import tr
from .parser import Card, PdfCards
from .textlabel import TextItem, find_cjk_font, fit_size, render_text_label

TEXT_DPI = 600          # 文字标签的渲染分辨率


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


@dataclass
class TextSticker:
    """一张文字贴纸。"""

    item: TextItem
    copy_no: int = 1

    @property
    def total_copies(self) -> int:
        return self.item.copies


Entry = Union[Sticker, TextSticker]


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


def collect_text_stickers(items: Sequence[TextItem]) -> List[TextSticker]:
    out: List[TextSticker] = []
    for item in items:
        for k in range(max(1, item.copies)):
            out.append(TextSticker(item=item, copy_no=k + 1))
    return out


def collect_entries(pdfs: Sequence[PdfCards], items: Sequence[TextItem] = ()) -> List[Entry]:
    """PDF 卡片排前面，文字标签接在后面。"""
    return list(collect_stickers(pdfs)) + list(collect_text_stickers(items))


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


class _TextCache:
    """文字标签：每个 item 只渲染一次，按目标尺寸出图。"""

    def __init__(self, writer: PdfWriter, font_path: Optional[str] = None,
                 align: str = "center", max_pt: float = 48.0, dpi: int = TEXT_DPI,
                 uniform: bool = False) -> None:
        self.writer = writer
        self.font_path = font_path or find_cjk_font()
        self.align = align
        self.max_pt = max_pt
        self.dpi = dpi
        self.uniform = uniform
        self.fixed_pt: Optional[float] = None
        self._cache: Dict[Tuple[int, int, int], Tuple[str, object]] = {}

    def prepare(self, items: Sequence[TextItem], width_pt: float, height_pt: float) -> None:
        """统一字号模式：先算一遍每张能用的最大字号，取最小值，全批复用。"""
        if not self.uniform or not items:
            return
        w_px = max(16, int(round(width_pt / 72.0 * self.dpi)))
        h_px = max(16, int(round(height_pt / 72.0 * self.dpi)))
        sizes = [fit_size(i.text, w_px, h_px, font_path=self.font_path, max_pt=self.max_pt)
                 for i in items]
        self.fixed_pt = min(sizes) if sizes else None

    def get(self, item: TextItem, width_pt: float, height_pt: float) -> Tuple[str, object]:
        w_px = max(16, int(round(width_pt / 72.0 * self.dpi)))
        h_px = max(16, int(round(height_pt / 72.0 * self.dpi)))
        key = (item.index, w_px, h_px)
        if key in self._cache:
            return self._cache[key]
        img: Image.Image = render_text_label(
            item.text, w_px, h_px, font_path=self.font_path,
            align=self.align, max_pt=self.max_pt, fixed_pt=self.fixed_pt,
        )
        ref, _w, _h = add_image(self.writer, img)
        name = f"/Tx{len(self._cache)}"
        self._cache[key] = (name, ref)
        return self._cache[key]


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
    entries: Sequence[Entry],
    grid: GridSpec,
    output_path: str,
    knife_lines: bool = False,
    progress=None,
    text_font: Optional[str] = None,
    text_align: str = "center",
    text_max_pt: float = 48.0,
    text_uniform: bool = False,
) -> List[dict]:
    """生成一个 A4 标签 PDF，返回逐张标签的清单行。"""
    writer = PdfWriter()
    forms = _FormCache(writer)
    texts = _TextCache(writer, font_path=text_font, align=text_align,
                       max_pt=text_max_pt, uniform=text_uniform)
    page_w, page_h = grid.frame_pt()
    per_sheet = grid.per_sheet
    n_sheets = max(1, (len(entries) + per_sheet - 1) // per_sheet)
    manifest: List[dict] = []

    # 统一字号模式需要先知道每张的字号
    text_items = [e.item for e in entries if isinstance(e, TextSticker)]
    if text_items:
        first_avail_w = grid.cell_w * MM_TO_PT - 2 * grid.inset * MM_TO_PT
        first_avail_h = grid.cell_h * MM_TO_PT - 2 * grid.inset * MM_TO_PT
        texts.prepare(text_items, first_avail_w, first_avail_h)

    for sheet in range(n_sheets):
        page = writer.add_blank_page(width=page_w, height=page_h)
        xobjects = DictionaryObject()
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/ProcSet"): ArrayObject([NameObject("/PDF"), NameObject("/ImageB")]),
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

        inset = grid.inset * MM_TO_PT
        for slot in range(per_sheet):
            idx = sheet * per_sheet + slot
            if idx >= len(entries):
                break
            entry = entries[idx]
            cell = grid.cell_pt(slot)
            avail = (cell[0] + inset, cell[1] + inset, cell[2] - inset, cell[3] - inset)

            if isinstance(entry, Sticker):
                placed = _placement(entry.card.clip_pdf, cell, grid.inset)
                if placed is None:
                    continue
                scale, tx, ty, target = placed
                name, ref = forms.get(entry.pdf_path, entry.page_index)
                xobjects[NameObject(name)] = ref

                # 裁剪框必须用「内容区」而不是整格，否则安全边里会漏出相邻内容
                ops += [
                    ([], b"q"),
                    ([_num(target[0]), _num(target[1]), _num(target[2] - target[0]),
                      _num(target[3] - target[1])], b"re"),
                    ([], b"W"),
                    ([], b"n"),
                    ([_num(scale), FloatObject(0), FloatObject(0), _num(scale), _num(tx), _num(ty)], b"cm"),
                    ([NameObject(name)], b"Do"),
                    ([], b"Q"),
                ]
                manifest.append({
                    "sheet": sheet + 1, "cell": slot + 1,
                    "row": slot // grid.cols + 1, "col": slot % grid.cols + 1,
                    "kind": tr("builder.kind.pdf"),
                    "file": os.path.basename(entry.pdf_path), "pdf_page": entry.page_no,
                    "seq": entry.card.seq if entry.card.seq is not None else "",
                    "name": entry.card.name, "qty": entry.card.qty, "copy": entry.copy_no,
                    "scale_pct": round(scale * 100, 1),
                })
            else:  # TextSticker
                name, ref = texts.get(entry.item, avail[2] - avail[0], avail[3] - avail[1])
                xobjects[NameObject(name)] = ref
                ops += [
                    ([], b"q"),
                    ([_num(avail[2] - avail[0]), FloatObject(0), FloatObject(0),
                      _num(avail[3] - avail[1]), _num(avail[0]), _num(avail[1])], b"cm"),
                    ([NameObject(name)], b"Do"),
                    ([], b"Q"),
                ]
                manifest.append({
                    "sheet": sheet + 1, "cell": slot + 1,
                    "row": slot // grid.cols + 1, "col": slot % grid.cols + 1,
                    "kind": tr("builder.kind.text"),
                    "file": "", "pdf_page": "",
                    "seq": "", "name": entry.item.text.replace("\n", " "),
                    "qty": entry.item.copies, "copy": entry.copy_no, "scale_pct": "",
                })

        content = ContentStream(None, writer)
        content.operations.extend(ops)
        page.replace_contents(content)

        if progress:
            progress(sheet + 1, n_sheets)

    writer.add_metadata(
        {
            "/Title": tr("builder.title.proof" if knife_lines else "builder.title.production"),
            "/Creator": "ulpp",
            "/Producer": "ulpp (pypdf)",
        }
    )
    with open(output_path, "wb") as fh:
        writer.write(fh)
    writer.close()
    return manifest


def write_manifest(manifest: Sequence[dict], csv_path: str) -> None:
    fields = ["sheet", "cell", "row", "col", "kind", "file", "pdf_page",
              "seq", "name", "qty", "copy", "scale_pct"]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(manifest)


def build_all(
    pdfs: Sequence[PdfCards],
    grid: GridSpec,
    out_dir: str,
    base_name: Optional[str] = None,
    make_proof: bool = True,
    make_csv: bool = True,
    text_items: Sequence[TextItem] = (),
    progress=None,
    log=None,
    text_font: Optional[str] = None,
    text_align: str = "center",
    text_max_pt: float = 48.0,
    text_uniform: bool = False,
) -> Dict[str, str]:
    """一次性生成打印版 / 网格参考版 / 清单，返回各文件路径。"""
    os.makedirs(out_dir, exist_ok=True)
    entries = collect_entries(pdfs, text_items)
    if not entries:
        raise ValueError(tr("builder.err.empty"))
    base_name = base_name or tr("out.default_base")

    outputs: Dict[str, str] = {}
    total_sheets = max(1, (len(entries) + grid.per_sheet - 1) // grid.per_sheet)

    def _p(prefix):
        return (lambda done, total: progress(prefix, done, total)) if progress else None

    prod = os.path.join(out_dir, tr("out.production", base=base_name))
    if log:
        n_pdf = sum(1 for e in entries if isinstance(e, Sticker))
        n_txt = len(entries) - n_pdf
        log(tr("builder.log.place", total=len(entries), pdf=n_pdf, text=n_txt,
               sheets=total_sheets, file=os.path.basename(prod)))
    manifest = build_pdf(entries, grid, prod, knife_lines=False, progress=_p("production"),
                         text_font=text_font, text_align=text_align,
                         text_max_pt=text_max_pt, text_uniform=text_uniform)
    outputs["production"] = prod

    if make_proof:
        proof = os.path.join(out_dir, tr("out.proof", base=base_name))
        if log:
            log(tr("builder.log.proof", file=os.path.basename(proof)))
        build_pdf(entries, grid, proof, knife_lines=True, progress=_p("proof"),
                  text_font=text_font, text_align=text_align,
                  text_max_pt=text_max_pt, text_uniform=text_uniform)
        outputs["proof"] = proof

    if make_csv:
        csv_path = os.path.join(out_dir, tr("out.manifest", base=base_name))
        write_manifest(manifest, csv_path)
        outputs["manifest"] = csv_path
        if log:
            log(tr("builder.log.manifest", file=os.path.basename(csv_path)))

    return outputs


def _offset_cell(cell: Sequence[float], offset_mm: Sequence[float]):
    """把格子按补偿量平移：x 正数向右，y 正数向下（PDF 里 y 向下要取负）。"""
    dx = float(offset_mm[0]) * MM_TO_PT
    dy = -float(offset_mm[1]) * MM_TO_PT
    return cell[0] + dx, cell[1] + dy, cell[2] + dx, cell[3] + dy


def build_partial_pdf(
    placements: Dict[int, Entry],
    grid: GridSpec,
    output_path: str,
    offset_mm: Sequence[float] = (0.0, 0.0),
    progress=None,
    text_font: Optional[str] = None,
    text_align: str = "center",
    text_max_pt: float = 48.0,
    text_uniform: bool = False,
) -> List[dict]:
    """只把指定格子画到一页 A4 上；``placements`` 是 {格号(0起): Entry}。"""
    if not placements:
        raise ValueError(tr("builder.err.no_partial"))
    try:
        placements = {int(slot): entry for slot, entry in placements.items()}
    except (TypeError, ValueError) as exc:
        raise ValueError(tr("builder.err.bad_slot", slot=0, per=grid.per_sheet)) from exc
    try:
        offset_mm = (float(offset_mm[0]), float(offset_mm[1]))
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError(tr("builder.err.bad_offset")) from exc

    slots = sorted(placements)
    for slot in slots:
        if slot < 0 or slot >= grid.per_sheet:
            raise ValueError(tr("builder.err.bad_slot", slot=slot + 1, per=grid.per_sheet))
    entries = [placements[slot] for slot in slots]

    writer = PdfWriter()
    forms = _FormCache(writer)
    texts = _TextCache(writer, font_path=text_font, align=text_align,
                       max_pt=text_max_pt, uniform=text_uniform)
    page_w, page_h = grid.frame_pt()

    text_items = [e.item for e in entries if isinstance(e, TextSticker)]
    if text_items:
        first_avail_w = grid.cell_w * MM_TO_PT - 2 * grid.inset * MM_TO_PT
        first_avail_h = grid.cell_h * MM_TO_PT - 2 * grid.inset * MM_TO_PT
        texts.prepare(text_items, first_avail_w, first_avail_h)

    page = writer.add_blank_page(width=page_w, height=page_h)
    xobjects = DictionaryObject()
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/ProcSet"): ArrayObject([NameObject("/PDF"), NameObject("/ImageB")]),
            NameObject("/XObject"): xobjects,
        }
    )
    ops = []
    inset = grid.inset * MM_TO_PT
    manifest: List[dict] = []

    for slot, entry in zip(slots, entries):
        cell = _offset_cell(grid.cell_pt(slot), offset_mm)
        avail = (cell[0] + inset, cell[1] + inset, cell[2] - inset, cell[3] - inset)

        if isinstance(entry, Sticker):
            placed = _placement(entry.card.clip_pdf, cell, grid.inset)
            if placed is None:
                continue
            scale, tx, ty, target = placed
            name, ref = forms.get(entry.pdf_path, entry.page_index)
            xobjects[NameObject(name)] = ref
            ops += [
                ([], b"q"),
                ([_num(target[0]), _num(target[1]), _num(target[2] - target[0]),
                  _num(target[3] - target[1])], b"re"),
                ([], b"W"),
                ([], b"n"),
                ([_num(scale), FloatObject(0), FloatObject(0), _num(scale), _num(tx), _num(ty)], b"cm"),
                ([NameObject(name)], b"Do"),
                ([], b"Q"),
            ]
            manifest.append({
                "sheet": 1, "cell": slot + 1,
                "row": slot // grid.cols + 1, "col": slot % grid.cols + 1,
                "kind": tr("builder.kind.pdf"),
                "file": os.path.basename(entry.pdf_path), "pdf_page": entry.page_no,
                "seq": entry.card.seq if entry.card.seq is not None else "",
                "name": entry.card.name, "qty": entry.card.qty, "copy": entry.copy_no,
                "scale_pct": round(scale * 100, 1),
            })
        else:
            name, ref = texts.get(entry.item, avail[2] - avail[0], avail[3] - avail[1])
            xobjects[NameObject(name)] = ref
            ops += [
                ([], b"q"),
                ([_num(avail[2] - avail[0]), FloatObject(0), FloatObject(0),
                  _num(avail[3] - avail[1]), _num(avail[0]), _num(avail[1])], b"cm"),
                ([NameObject(name)], b"Do"),
                ([], b"Q"),
            ]
            manifest.append({
                "sheet": 1, "cell": slot + 1,
                "row": slot // grid.cols + 1, "col": slot % grid.cols + 1,
                "kind": tr("builder.kind.text"),
                "file": "", "pdf_page": "",
                "seq": "", "name": entry.item.text.replace("\n", " "),
                "qty": entry.item.copies, "copy": entry.copy_no, "scale_pct": "",
            })

    content = ContentStream(None, writer)
    content.operations.extend(ops)
    page.replace_contents(content)

    writer.add_metadata(
        {
            "/Title": tr("builder.title.partial"),
            "/Creator": "ulpp",
            "/Producer": "ulpp (pypdf)",
        }
    )
    with open(output_path, "wb") as fh:
        writer.write(fh)
    writer.close()
    if progress:
        progress(1, 1)
    return manifest


def build_partial_all(
    placements: Dict[int, Entry],
    grid: GridSpec,
    out_dir: str,
    base_name: Optional[str] = None,
    make_csv: bool = True,
    offset_mm: Sequence[float] = (0.0, 0.0),
    log=None,
    text_font: Optional[str] = None,
    text_align: str = "center",
    text_max_pt: float = 48.0,
    text_uniform: bool = False,
) -> Dict[str, str]:
    """生成接着打的一页 PDF（可选清单 CSV），返回各文件路径。"""
    if not placements:
        raise ValueError(tr("builder.err.no_partial"))
    os.makedirs(out_dir, exist_ok=True)
    base_name = base_name or tr("out.default_base")

    prod = os.path.join(out_dir, tr("out.partial_production", base=base_name))
    if log:
        log(tr("builder.log.partial", n=len(placements), file=os.path.basename(prod)))
    manifest = build_partial_pdf(
        placements, grid, prod, offset_mm=offset_mm,
        text_font=text_font, text_align=text_align,
        text_max_pt=text_max_pt, text_uniform=text_uniform,
    )
    outputs: Dict[str, str] = {"production": prod}

    if make_csv:
        csv_path = os.path.join(out_dir, tr("out.partial_manifest", base=base_name))
        write_manifest(manifest, csv_path)
        outputs["manifest"] = csv_path
        if log:
            log(tr("builder.log.partial_manifest", file=os.path.basename(csv_path)))

    return outputs
