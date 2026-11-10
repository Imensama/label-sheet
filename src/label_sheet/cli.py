# -*- coding: utf-8 -*-
"""命令行入口：python -m label_sheet [-o 输出目录] PDF1.pdf PDF2.pdf ..."""

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
        description=f"{APP_NAME} {__version__} —— 把PDF 自动排成 A4 不干胶标签",
    )
    ap.add_argument("inputs", nargs="+", help="PDF、文件夹或 zip（可多个）")
    ap.add_argument("-o", "--out", default=None, help="输出目录（默认：第一个 PDF 旁的“标签输出”文件夹）")
    ap.add_argument("--name", default="PDF标签", help="输出文件名前缀（默认：PDF标签）")
    ap.add_argument("--first-page-only", action="store_true", help="只取每份 PDF 的第 1 页")
    ap.add_argument("--no-proof", action="store_true", help="不生成刀线校样版")
    ap.add_argument("--no-csv", action="store_true", help="不生成标签清单 CSV")
    ap.add_argument("--config", default=None, help="读取网格参数 JSON")
    ap.add_argument("--save-config", default=None, help="把当前网格参数另存为 JSON")
    ap.add_argument("--cols", type=int, default=None, help="列数（默认 5）")
    ap.add_argument("--rows", type=int, default=None, help="行数（默认 9）")
    ap.add_argument("--cell", default=None, help="单格宽x高 mm，如 40x30")
    ap.add_argument("--pitch", default=None, help="节距 宽x高 mm，如 41.5x32")
    ap.add_argument("--margin-top", type=float, default=None, help="上边距 mm（默认 6）")
    ap.add_argument("--inset", type=float, default=None, help="内容安全边 mm（默认 2）")
    ap.add_argument("-q", "--quiet", action="store_true", help="少打印日志")
    ap.add_argument("-V", "--version", action="version", version=f"{APP_NAME} {__version__}")
    return ap


def grid_from_args(args) -> GridSpec:
    grid = GridSpec.load(args.config) if args.config else GridSpec()
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


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    files = expand_inputs(args.inputs)
    if not files:
        print("没找到任何 PDF。", file=sys.stderr)
        return 2

    grid = grid_from_args(args)
    if args.save_config:
        grid.save(args.save_config)
        print(f"网格参数已保存：{args.save_config}")

    out_dir = args.out or os.path.join(os.path.dirname(files[0]), "标签输出")
    log = (lambda *a, **k: None) if args.quiet else (lambda msg: print(msg))

    log(f"{APP_NAME} {__version__}")
    log(f"共 {len(files)} 份 PDF → {out_dir}")

    pdfs = []
    for i, f in enumerate(files, 1):
        log(f"[{i}/{len(files)}] 解析 {os.path.basename(f)}")
        info = parse_many([f], first_page_only=args.first_page_only)[0]
        pdfs.append(info)
        for page in info.pages:
            for w in page.warnings:
                print(f"    ! {w}", file=sys.stderr)
        if args.first_page_only:
            log(f"    第 1 页：{len(info.pages[0].cards) if info.pages else 0} 个卡片 / {info.pages[0].stickers if info.pages else 0} 张贴纸")
        else:
            log(f"    {len(info.pages)} 页：{len(info.cards)} 个卡片 / {info.stickers} 张贴纸")

    stickers = sum(p.stickers for p in pdfs)
    if stickers == 0:
        print("没有解析到任何卡片，请确认 PDF 是“PDF 卡片”格式。", file=sys.stderr)
        return 3

    try:
        outputs = build_all(
            pdfs, grid, out_dir, base_name=args.name,
            make_proof=not args.no_proof, make_csv=not args.no_csv, log=log,
        )
    except Exception as exc:  # pragma: no cover
        print(f"生成失败：{exc}", file=sys.stderr)
        return 4

    log("完成：")
    for key, path in outputs.items():
        log(f"  {key:10s} {path}")
    if not args.quiet:
        print(f"\n共 {stickers} 张贴纸，已生成到：{out_dir}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
