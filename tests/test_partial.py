# -*- coding: utf-8 -*-
"""接着打按格排版的单元测试。"""

import csv
import os
import shutil
import unittest
import uuid

from pypdf import PdfReader

from ulpp.builder import (
    _offset_cell,
    build_partial_all,
    build_partial_pdf,
    collect_stickers,
    collect_text_stickers,
)
from ulpp.config import GridSpec, MM_TO_PT
from ulpp.i18n import set_language
from ulpp.parser import parse_pdf
from ulpp.textlabel import parse_text_block

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SAMPLE = os.path.join(ROOT, "examples", "sample.pdf")


class TestPartialLayout(unittest.TestCase):
    def setUp(self):
        set_language("zh_CN")
        self.dir = os.path.join(ROOT, f"ulpp_partial_test_{uuid.uuid4().hex[:8]}")
        os.makedirs(self.dir, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.grid = GridSpec()
        self.entries = collect_text_stickers(parse_text_block("A |2\nB"))

    def test_three_slots_one_page(self):
        placements = {0: self.entries[0], 5: self.entries[1], 44: self.entries[2]}
        outs = build_partial_all(placements, self.grid, self.dir, base_name="t")
        self.assertTrue(os.path.exists(outs["production"]))
        self.assertTrue(os.path.exists(outs["manifest"]))

        pdf = PdfReader(outs["production"])
        self.assertEqual(len(pdf.pages), 1)
        w = float(pdf.pages[0].mediabox.width)
        h = float(pdf.pages[0].mediabox.height)
        self.assertAlmostEqual(w, 595.28, delta=1)
        self.assertAlmostEqual(h, 841.89, delta=1)
        data = pdf.pages[0].get_contents().get_data().decode("latin-1")
        self.assertEqual(data.count("Do"), 3, "只应该有 3 个格子有内容")

        with open(outs["manifest"], encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 3)
        self.assertEqual([int(r["cell"]) for r in rows], [1, 6, 45])
        self.assertTrue(all(r["kind"] == "文字" for r in rows))

    def test_pdf_card_entry(self):
        with self.assertRaises(ValueError):
            build_partial_pdf({}, self.grid, os.path.join(self.dir, "empty.pdf"))

    @unittest.skipUnless(os.path.exists(SAMPLE), "缺少 examples/sample.pdf")
    def test_pdf_card(self):
        parsed = parse_pdf(SAMPLE)
        stickers = collect_stickers([parsed])
        placements = {3: stickers[0], 7: stickers[1]}
        out = os.path.join(self.dir, "pdf_cards.pdf")
        manifest = build_partial_pdf(placements, self.grid, out)
        self.assertEqual(len(manifest), 2)
        self.assertTrue(all(row["kind"] == "PDF" for row in manifest))
        self.assertEqual([row["cell"] for row in manifest], [4, 8])

    def test_invalid_slot(self):
        with self.assertRaises(ValueError):
            build_partial_pdf({45: self.entries[0]}, self.grid,
                              os.path.join(self.dir, "bad.pdf"))
        with self.assertRaises(ValueError):
            build_partial_pdf({-1: self.entries[0]}, self.grid,
                              os.path.join(self.dir, "bad2.pdf"))

    def test_empty_placements(self):
        with self.assertRaises(ValueError):
            build_partial_pdf({}, self.grid, os.path.join(self.dir, "empty.pdf"))

    def test_offset_sign(self):
        cell = _offset_cell((0.0, 0.0, 100.0, 100.0), (1.0, -0.5))
        self.assertAlmostEqual(cell[0], MM_TO_PT, places=6)
        self.assertAlmostEqual(cell[1], 0.5 * MM_TO_PT, places=6)
        self.assertAlmostEqual(cell[2], 100.0 + MM_TO_PT, places=6)
        self.assertAlmostEqual(cell[3], 100.0 + 0.5 * MM_TO_PT, places=6)

    def test_custom_grid(self):
        grid = GridSpec(cols=2, rows=2)
        placements = {0: self.entries[0], 3: self.entries[1]}
        out = os.path.join(self.dir, "small.pdf")
        manifest = build_partial_pdf(placements, grid, out)
        self.assertEqual([row["cell"] for row in manifest], [1, 4])
        self.assertEqual([(row["row"], row["col"]) for row in manifest], [(1, 1), (2, 2)])


if __name__ == "__main__":
    unittest.main()
