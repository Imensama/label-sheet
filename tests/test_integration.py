# -*- coding: utf-8 -*-
"""端到端测试：用 examples/sample.pdf 跑一遍解析 + 生成（stdlib unittest）。

sample.pdf 是 scripts/make_sample.py 生成的小样张：6 张卡片，数量 1/4/2/1/1/1 = 10 张贴纸。
"""

import csv
import os
import shutil
import uuid
import unittest

from pypdf import PdfReader

from label_sheet.builder import build_all, collect_entries, collect_stickers
from label_sheet.i18n import set_language
from label_sheet.presets import by_key
from label_sheet.textlabel import parse_text_block
from label_sheet.config import GridSpec
from label_sheet.parser import parse_pdf

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(os.path.dirname(HERE), "examples", "sample.pdf")


@unittest.skipUnless(os.path.exists(SAMPLE), "缺少 examples/sample.pdf")
class TestIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        set_language("zh_CN")   # 断言里的 CSV kind 是中文，固定语言避免受系统语言影响
        cls.parsed = parse_pdf(SAMPLE)

    def test_cards(self):
        self.assertEqual(len(self.parsed.pages), 1)
        cards = self.parsed.cards
        self.assertEqual(len(cards), 6)
        self.assertEqual([c.qty for c in cards], [1, 4, 2, 1, 1, 1])
        self.assertTrue(cards[0].name.startswith("DEMO-1001"))
        self.assertEqual(cards[1].seq, 2)

    def test_content_box_valid(self):
        for c in self.parsed.cards:
            x0, y0, x1, y1 = c.clip_pdf
            self.assertGreater(x1, x0)
            self.assertGreater(y1, y0)
            self.assertGreaterEqual(x0, 0)
            self.assertGreaterEqual(y0, 0)

    def test_sticker_expansion(self):
        self.assertEqual(len(collect_stickers([self.parsed])), 10)

    def test_build(self):
        grid = GridSpec()
        tmp = os.path.join(os.path.dirname(HERE), f"label_sheet_test_{uuid.uuid4().hex[:8]}")
        os.makedirs(tmp, exist_ok=True)
        self.addCleanup(shutil.rmtree, tmp, True)   # ignore_errors=True
        outs = build_all([self.parsed], grid, tmp, base_name="t")
        for key in ("production", "proof", "manifest"):
            self.assertTrue(os.path.exists(outs[key]), key)

        prod = PdfReader(outs["production"])
        self.assertEqual(len(prod.pages), 1)          # 10 张 → 1 版
        w = float(prod.pages[0].mediabox.width)
        h = float(prod.pages[0].mediabox.height)
        self.assertAlmostEqual(w, 595.28, delta=1)    # A4
        self.assertAlmostEqual(h, 841.89, delta=1)

        with open(outs["manifest"], encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 10)
        self.assertTrue(all(1 <= int(r["cell"]) <= 45 for r in rows))
        self.assertEqual(sum(1 for r in rows if int(r["qty"]) == 4), 4)


    def test_build_text_labels(self):
        """纯文字标签：一行一张，|2 出两张，按预设尺寸排。"""
        items = parse_text_block("急件 A-01 |2\n返修件\n2026-11-09 出货")
        self.assertEqual(len(items), 3)
        grid = by_key("24格 70×37（3×8）").to_grid()
        tmp = os.path.join(os.path.dirname(HERE), "label_sheet_test_text")
        os.makedirs(tmp, exist_ok=True)
        self.addCleanup(shutil.rmtree, tmp, True)
        outs = build_all([], grid, tmp, base_name="t", text_items=items)
        prod = PdfReader(outs["production"])
        self.assertEqual(len(prod.pages), 1)          # 4 张 → 1 版（24 格）
        with open(outs["manifest"], encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(r["kind"] == "文字" for r in rows))

    def test_mixed_entries_order(self):
        items = parse_text_block("A\nB")
        entries = collect_entries([self.parsed], items)
        self.assertEqual(len(entries), 10 + 2)
        self.assertTrue(entries[-1].__class__.__name__ == "TextSticker")


if __name__ == "__main__":
    unittest.main()
