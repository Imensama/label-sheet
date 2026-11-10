# -*- coding: utf-8 -*-
"""命令行入口。

用法示例：
    python -m label_sheet 输入.zip -o 输出目录
    python -m label_sheet 表单.pdf --preset "24格 70×37（3×8）"
    python -m label_sheet --text-file 清单.txt -o 输出目录
    python -m label_sheet 表单.pdf --text "急件 |2" --text "返修件"
    python -m label_sheet --list-presets
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import sys
import tempfile
import zipfile
from typing import List, Sequence

from . import __version__, APP_NAME
from .builder import build_all
from .config import GridSpec
from .parser import parse_many
from .presets import DEFAULT_PRESET_KEY, PRESETS, by_key, keys
from .textlabel import parse_text_block


def _safe_extract_zip(zip_path: str, dest: str) -> List[str]:
    """把 zip 里的 PDF 平铺解到 dest（不建子目录），返回解出来的文件列表。

    中文 Windows 打的包文件名常是 GBK 编码，这里自动纠正；只取 PDF，避免解出乱七八糟的目录。
    """
    os.makedirs(dest, exist_ok=True)
    extracted: List[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        for idx, info in enumerate(zf.infolist()):
            if info.is_dir():
                continue
            name = info.filename
            if not (info.flag_bits & 0x800):  # 没有 UTF-8 标记
                try:
                    name = name.encode("cp437").decode("gbk")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    try:
                        name = name.encode("cp437").decode("utf-8")
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        pass
            base = os.path.basename(name.replace("\\", "/"))
            if not base.lower().endswith(".pdf"):
                continue
            target = os.path.join(dest, f"{idx:03d}_{base}")
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            extracted.append(target)
    return extracted


def expand_inputs(paths: Sequence[str]) -> List[str]:
    """把文件 / 文件夹 / zip 统一展开成 PDF 路径列表。"""
    out: List[str] = []
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                out.extend(sorted(os.path.join(root, f) for f in files if f.lower().endswith(".pdf")))
        elif p.lower().endswith(".zip"):
            tmp = tempfile.mkdtemp(prefix="label_sheet_zip_")
            try:
                out.extend(_safe_extract_zip(p, tmp))
            except Exception as exc:  # pragma: no cover
                print(f"解压失败：{p}（{exc}）", file=sys.stderr)
                continue
        elif p.lower().endswith(".pdf"):
            out.append(os.path.abspath(p))
        else:
            for hit in glob.glob(p):
                if hit.lower().endswith(".pdf"):
                    out.append(os.path.abspath(hit))
    # 去重且保序
    seen = set()
    uniq = []
    for p in out:
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="label-sheet",
        description=f"{APP_NAME} {__version__} —— 把 PDF 版面或一段文字自动排成 A4 不干胶标签",
        epilog="规格预设：" + "；".join(keys()),
    )
    ap.add_argument("inputs", nargs="*", help="PDF、文件夹或 zip（可多个；只用文字标签时可省略）")
    ap.add_argument("-o", "--out", default=None, help="输出目录（默认：第一个 PDF 旁的“标签输出”）")
    ap.add_argument("--name", default="标签", help="输出文件名前缀（默认：标签）")

    # 版式
    ap.add_argument("--preset", default=None,
                    help=f'胶贴规格预设名（默认 “{DEFAULT_PRESET_KEY}”，用 --list-presets 看全部）')
    ap.add_argument("--list-presets", action="store_true", help="列出所有胶贴规格后退出")
    ap.add_argument("--config", default=None, help="读取网格参数 JSON（优先于 --preset）")
    ap.add_argument("--save-config", default=None, help="把当前网格参数另存为 JSON")
    ap.add_argument("--cols", type=int, default=None, help="列数")
    ap.add_argument("--rows", type=int, default=None, help="行数")
    ap.add_argument("--cell", default=None, help="单格宽x高 mm，如 40x30")
    ap.add_argument("--pitch", default=None, help="节距 宽x高 mm，如 41.5x32")
    ap.add_argument("--margin-top", type=float, default=None, help="上边距 mm")
    ap.add_argument("--inset", type=float, default=None, help="内容安全边 mm（默认 2）")

    # 内容
    ap.add_argument("--first-page-only", action="store_true", help="每份 PDF 只取第 1 页")
    ap.add_argument("--text", action="append", default=[], metavar="TEXT",
                    help="直接给一行文字标签（可重复）；行尾写 |2 表示印 2 张")
    ap.add_argument("--text-file", default=None, help="从文本文件读文字标签（一行一张）")
    ap.add_argument("--text-align", choices=["center", "left", "right"], default="center",
                    help="文字对齐方式（默认居中）")
    ap.add_argument("--text-uniform", action="store_true",
                    help="所有文字标签用同一字号（取放得下的最小那档），排版更整齐")
    ap.add_argument("--text-max-pt", type=float, default=48.0, help="文字最大字号（pt，默认 48）")

    ap.add_argument("--no-proof", action="store_true", help="不生成刀线校样版")
    ap.add_argument("--no-csv", action="store_true", help="不生成标签清单 CSV")
    ap.add_argument("-q", "--quiet", action="store_true", help="少打印日志")
    ap.add_argument("-V", "--version", action="version", version=f"{APP_NAME} {__version__}")
    return ap


def grid_from_args(args) -> GridSpec:
    if args.config:
        grid = GridSpec.load(args.config)
    elif args.preset:
        try:
            grid = by_key(args.preset).to_grid()
        except KeyError:
            raise SystemExit(f"没有这个规格：{args.preset}\n可用：{', '.join(keys())}")
    else:
        grid = by_key(DEFAULT_PRESET_KEY).to_grid()

    data = grid.to_dict()
    if args.cols:
        data["cols"] = args.cols
    if args.rows:
        data["rows"] = args.rows
    if args.cell:
        w, h = (float(x) for x in args.cell.lower().split("x"))
        data["cell_w"], data["cell_h"] = w, h
    if args.pitch:
        w, h = (float(x) for x in args.pitch.lower().split("x"))
        data["pitch_x"], data["pitch_y"] = w, h
    if args.margin_top is not None:
        data["margin_top"] = args.margin_top
    if args.inset is not None:
        data["inset"] = args.inset
    return GridSpec.from_dict(data)


def collect_text_items(args) -> list:
    block = "\n".join(args.text or [])
    if args.text_file:
        with open(args.text_file, "r", encoding="utf-8-sig") as fh:
            block = (block + "\n" + fh.read()) if block else fh.read()
    return parse_text_block(block)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.list_presets:
        print(f"{APP_NAME} {__version__} 支持的胶贴规格：\n")
        for p in PRESETS:
            g = p.to_grid()
            print(f"  {p.key:<26s} 节距 {g.pitch_x:g}×{g.pitch_y:g}  上边距 {g.margin_top:.1f}")
        return 0

    files = expand_inputs(args.inputs)
    text_items = collect_text_items(args)
    if not files and not text_items:
        print("没有输入内容：给几个 PDF / 文件夹 / zip，或用 --text / --text-file 给文字。", file=sys.stderr)
        return 2

    grid = grid_from_args(args)
    if args.save_config:
        grid.save(args.save_config)
        print(f"网格参数已保存：{args.save_config}")

    base_dir = os.path.dirname(files[0]) if files else os.getcwd()
    out_dir = args.out or os.path.join(base_dir, "标签输出")
    log = (lambda *a, **k: None) if args.quiet else (lambda msg: print(msg))

    log(f"{APP_NAME} {__version__}")
    log(f"规格 {grid.cols}×{grid.rows}（{grid.cols * grid.rows} 格，{grid.cell_w:g}×{grid.cell_h:g}mm）")
    if files:
        log(f"共 {len(files)} 份 PDF → {out_dir}")

    pdfs = []
    for i, f in enumerate(files, 1):
        log(f"[{i}/{len(files)}] 解析 {os.path.basename(f)}")
        info = parse_many([f], first_page_only=args.first_page_only)[0]
        pdfs.append(info)
        for page in info.pages:
            for w in page.warnings:
                print(f"    ! {w}", file=sys.stderr)
        log(f"    {len(info.pages)} 页：{len(info.cards)} 个卡片 / {info.stickers} 张贴纸")

    if text_items:
        n = sum(i.copies for i in text_items)
        log(f"文字标签：{len(text_items)} 条 / {n} 张")

    total = sum(p.stickers for p in pdfs) + sum(i.copies for i in text_items)
    if total == 0:
        print("没有可排的内容。", file=sys.stderr)
        return 3

    try:
        outputs = build_all(
            pdfs, grid, out_dir, base_name=args.name,
            make_proof=not args.no_proof, make_csv=not args.no_csv,
            text_items=text_items, log=log,
            text_align=args.text_align, text_uniform=args.text_uniform,
            text_max_pt=args.text_max_pt,
        )
    except Exception as exc:  # pragma: no cover
        print(f"生成失败：{exc}", file=sys.stderr)
        return 4

    log("完成：")
    for key, path in outputs.items():
        log(f"  {key:10s} {path}")
    if not args.quiet:
        print(f"\n共 {total} 张贴纸，已生成到：{out_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
