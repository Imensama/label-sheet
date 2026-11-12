# -*- coding: utf-8 -*-
"""命令行入口。

用法示例：
    python -m ulpp 输入.zip -o 输出目录
    python -m ulpp 表单.pdf --preset 24
    python -m ulpp --text-file 清单.txt -o 输出目录
    python -m ulpp 表单.pdf --text "急件 |2" --text "返修件"
    python -m ulpp --list-presets
    python -m ulpp --lang en --list-presets
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import sys
import tempfile
import zipfile
from typing import List, Optional, Sequence

from . import __version__
from .builder import build_all
from .config import GridSpec
from .i18n import set_language, tr
from .parser import parse_many
from .presets import DEFAULT_PRESET_KEY, PRESETS, by_key
from .textlabel import parse_text_block


def _prescan_lang(argv: Sequence[str]) -> Optional[str]:
    """在 argparse 建好之前先找出 ``--lang``，这样 --help / 错误提示也能用对语言。"""
    for i, arg in enumerate(argv):
        if arg == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--lang="):
            return arg.split("=", 1)[1]
    return None


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
            tmp = tempfile.mkdtemp(prefix="ulpp_zip_")
            try:
                out.extend(_safe_extract_zip(p, tmp))
            except Exception as exc:  # pragma: no cover
                print(tr("cli.err.unzip", path=p, error=exc), file=sys.stderr)
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
    app_name = tr("app.name")
    sep = tr("cli.preset_sep")
    preset_text = sep.join(p.title for p in PRESETS)
    ap = argparse.ArgumentParser(
        prog="ulpp",
        description=tr("cli.description", app=app_name, version=__version__),
        epilog=tr("cli.epilog", presets=preset_text),
    )
    ap.add_argument("inputs", nargs="*", help=tr("cli.help.inputs"))
    ap.add_argument("-o", "--out", default=None, help=tr("cli.help.out"))
    ap.add_argument("--name", default=None, help=tr("cli.help.name"))

    # 版式
    ap.add_argument("--preset", default=None,
                    help=tr("cli.help.preset", default=by_key(DEFAULT_PRESET_KEY).title))
    ap.add_argument("--list-presets", action="store_true", help=tr("cli.help.list_presets"))
    ap.add_argument("--config", default=None, help=tr("cli.help.config"))
    ap.add_argument("--save-config", default=None, help=tr("cli.help.save_config"))
    ap.add_argument("--cols", type=int, default=None, help=tr("cli.help.cols"))
    ap.add_argument("--rows", type=int, default=None, help=tr("cli.help.rows"))
    ap.add_argument("--cell", default=None, help=tr("cli.help.cell"))
    ap.add_argument("--pitch", default=None, help=tr("cli.help.pitch"))
    ap.add_argument("--margin-top", type=float, default=None, help=tr("cli.help.margin_top"))
    ap.add_argument("--inset", type=float, default=None, help=tr("cli.help.inset"))

    # 内容
    ap.add_argument("--first-page-only", action="store_true", help=tr("cli.help.first_page_only"))
    ap.add_argument("--text", action="append", default=[], metavar="TEXT", help=tr("cli.help.text"))
    ap.add_argument("--text-file", default=None, help=tr("cli.help.text_file"))
    ap.add_argument("--text-align", choices=["center", "left", "right"], default="center",
                    help=tr("cli.help.text_align"))
    ap.add_argument("--text-uniform", action="store_true", help=tr("cli.help.text_uniform"))
    ap.add_argument("--text-max-pt", type=float, default=48.0, help=tr("cli.help.text_max_pt"))

    ap.add_argument("--no-proof", action="store_true", help=tr("cli.help.no_proof"))
    ap.add_argument("--no-csv", action="store_true", help=tr("cli.help.no_csv"))
    ap.add_argument("-q", "--quiet", action="store_true", help=tr("cli.help.quiet"))
    ap.add_argument("--lang", default=None, metavar="zh|en", help=tr("cli.help.lang"))
    ap.add_argument("-V", "--version", action="version",
                    version=f"{app_name} {__version__}")
    return ap


def grid_from_args(args) -> GridSpec:
    if args.config:
        grid = GridSpec.load(args.config)
    elif args.preset:
        try:
            grid = by_key(args.preset).to_grid()
        except KeyError:
            raise SystemExit(tr("cli.err.no_preset", key=args.preset,
                                available=", ".join(p.title for p in PRESETS)))
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
    argv = list(sys.argv[1:] if argv is None else argv)
    set_language(_prescan_lang(argv))
    args = build_arg_parser().parse_args(argv)

    app_name = tr("app.name")

    if args.list_presets:
        print(tr("cli.list.header", app=app_name, version=__version__) + "\n")
        for p in PRESETS:
            g = p.to_grid()
            print(tr("cli.list.line", title=p.title, pitch_x=g.pitch_x,
                     pitch_y=g.pitch_y, margin_top=g.margin_top))
        return 0

    files = expand_inputs(args.inputs)
    text_items = collect_text_items(args)
    if not files and not text_items:
        print(tr("cli.err.no_input"), file=sys.stderr)
        return 2

    grid = grid_from_args(args)
    if args.save_config:
        grid.save(args.save_config)
        print(tr("cli.msg.saved", path=args.save_config))

    base_dir = os.path.dirname(files[0]) if files else os.getcwd()
    out_dir = args.out or os.path.join(base_dir, tr("out.default_dir"))
    log = (lambda *a, **k: None) if args.quiet else (lambda msg: print(msg))

    log(f"{app_name} {__version__}")
    log(tr("cli.log.spec", cols=grid.cols, rows=grid.rows, per=grid.cols * grid.rows,
           w=f"{grid.cell_w:g}", h=f"{grid.cell_h:g}"))
    if files:
        log(tr("cli.log.pdf_count", n=len(files), out=out_dir))

    pdfs = []
    for i, f in enumerate(files, 1):
        log(tr("log.parsing", i=i, n=len(files), name=os.path.basename(f)))
        info = parse_many([f], first_page_only=args.first_page_only)[0]
        pdfs.append(info)
        for page in info.pages:
            for w in page.warnings:
                print(f"    ! {w}", file=sys.stderr)
        log(tr("cli.log.page_summary", pages=len(info.pages), cards=len(info.cards),
               stickers=info.stickers))

    if text_items:
        n = sum(i.copies for i in text_items)
        log(tr("cli.log.text_count", items=len(text_items), copies=n))

    total = sum(p.stickers for p in pdfs) + sum(i.copies for i in text_items)
    if total == 0:
        print(tr("cli.err.no_content"), file=sys.stderr)
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
        print(tr("cli.err.build_failed", error=exc), file=sys.stderr)
        return 4

    log(tr("cli.log.done"))
    for key, path in outputs.items():
        log(f"  {key:10s} {path}")
    if not args.quiet:
        print(tr("cli.log.total", total=total, out=out_dir))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
