# -*- coding: utf-8 -*-
"""文字标签排版 + 标签纸规格预设的单元测试。"""

import unittest

from ulpp.config import GridSpec
from ulpp.presets import PRESETS, by_key, keys, match_grid
from ulpp.textlabel import fit_size, parse_text_block, render_text_label


class TestParseTextBlock(unittest.TestCase):
    def test_one_line_one_label(self):
        items = parse_text_block("A-01\nB-02\n\n  C-03  \n")
        self.assertEqual([i.text for i in items], ["A-01", "B-02", "C-03"])
        self.assertTrue(all(i.copies == 1 for i in items))

    def test_pipe_copies(self):
        items = parse_text_block("急件 A-01 |2\n返修件|3")
        self.assertEqual(items[0].text, "急件 A-01")
        self.assertEqual(items[0].copies, 2)
        self.assertEqual(items[1].copies, 3)

    def test_time_x_copies(self):
        items = parse_text_block("支架 ×2\n压板 x4")
        self.assertEqual(items[0].copies, 2)
        self.assertEqual(items[1].copies, 4)
        self.assertEqual(items[0].text, "支架")

    def test_dimension_not_treated_as_copies(self):
        """“120×80×6” 里的 ×35 不能当份数。"""
        items = parse_text_block("压板 120×80×6")
        self.assertEqual(items[0].copies, 1)
        self.assertEqual(items[0].text, "压板 120×80×6")

    def test_default_copies(self):
        items = parse_text_block("A\nB", default_copies=5)
        self.assertTrue(all(i.copies == 5 for i in items))

    def test_empty_block(self):
        self.assertEqual(parse_text_block("   \n\n  "), [])


class TestTextRender(unittest.TestCase):
    def test_fit_size_within_range(self):
        pt = fit_size("A-01", 850, 614)
        self.assertGreater(pt, 4)
        self.assertLessEqual(pt, 48)

    def test_longer_text_gets_smaller_font(self):
        short = fit_size("A", 850, 614)
        long = fit_size("这是一段很长很长的说明文字，需要换行", 850, 614)
        self.assertLess(long, short)

    def test_render_size_and_mode(self):
        img = render_text_label("测试", 400, 300)
        self.assertEqual(img.size, (400, 300))
        self.assertEqual(img.mode, "1")

    def test_fixed_pt(self):
        img = render_text_label("A-01", 400, 300, fixed_pt=10)
        self.assertEqual(img.size, (400, 300))


class TestPresets(unittest.TestCase):
    def test_all_presets_fit_page(self):
        for p in PRESETS:
            g = p.to_grid()
            self.assertGreaterEqual(g.margin_top, -0.01, p.key)
            self.assertGreaterEqual(g.margin_x, -0.01, p.key)
            x0, y0, x1, y1 = g.cell_mm(g.per_sheet - 1)
            self.assertLessEqual(x1, g.page_w + 0.01, p.key)
            self.assertGreaterEqual(y0, -0.01, p.key)

    def test_count_matches_grid(self):
        for p in PRESETS:
            self.assertEqual(p.count, p.cols * p.rows)

    def test_default_is_45(self):
        g = by_key(keys()[0]).to_grid()
        self.assertEqual(g.per_sheet, 45)
        self.assertAlmostEqual(g.cell_w, 40.0)
        self.assertAlmostEqual(g.margin_top, 6.0)

    def test_match_grid_roundtrip(self):
        p = by_key("24格 70×37（3×8）")
        g = p.to_grid()
        self.assertEqual(match_grid(g), p.key)

    def test_unknown_key(self):
        with self.assertRaises(KeyError):
            by_key("不存在的规格")


if __name__ == "__main__":
    unittest.main()
