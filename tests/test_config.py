# -*- coding: utf-8 -*-
"""网格几何的单元测试（stdlib unittest，不依赖 pytest）。"""

import unittest

from label_sheet.config import GridSpec, MM_TO_PT


class TestGridSpec(unittest.TestCase):
    def test_default_grid_is_45_cells(self):
        g = GridSpec()
        self.assertEqual(g.per_sheet, 45)
        self.assertEqual((g.cols, g.rows), (5, 9))

    def test_margins_are_centered(self):
        g = GridSpec()
        # 5 列、节距 41.5、格宽 40 → 左右各留 (210-206)/2 = 2mm
        self.assertAlmostEqual(g.margin_x, 2.0, places=6)

    def test_first_cell_position(self):
        g = GridSpec()
        x0, y0, x1, y1 = g.cell_mm(0)
        self.assertAlmostEqual(x0, 2.0, places=6)
        self.assertAlmostEqual(x1, 42.0, places=6)
        # 原点在左下：第一行顶边距页面顶部 6mm
        self.assertAlmostEqual(y1, 297 - 6, places=6)
        self.assertAlmostEqual(y0, 297 - 6 - 30, places=6)

    def test_last_cell_fits_page(self):
        g = GridSpec()
        x0, y0, x1, y1 = g.cell_mm(g.per_sheet - 1)
        self.assertLessEqual(x1, g.page_w + 1e-6)
        self.assertGreaterEqual(y0, -1e-6)
        self.assertGreater(x1, g.page_w - 3)   # 右边距不超过 3mm

    def test_pt_conversion(self):
        g = GridSpec()
        x0, y0, x1, y1 = g.cell_pt(0)
        self.assertAlmostEqual(x1 - x0, 40 * MM_TO_PT, places=6)

    def test_roundtrip_dict(self):
        g = GridSpec(cols=4, rows=8, cell_w=45, cell_h=28)
        self.assertEqual(GridSpec.from_dict(g.to_dict()), g)

    def test_unknown_keys_ignored(self):
        g = GridSpec.from_dict({"cols": 3, "行数": 99})
        self.assertEqual(g.cols, 3)
        self.assertEqual(g.rows, 9)


if __name__ == "__main__":
    unittest.main()
