# -*- coding: utf-8 -*-
"""字段解析 / 排序复制的单元测试（stdlib unittest）。"""

import unittest

from label_sheet.builder import collect_stickers
from label_sheet.parser import Card, PageCards, PdfCards, parse_card_text


def _card(name: str, qty: int, row: int, col: int) -> Card:
    return Card(name=name, qty=qty, row=row, col=col, clip_pdf=(0, 0, 100, 50))


class TestParseCardText(unittest.TestCase):
    def test_standard_card(self):
        text = (
            "文件名称:DEMO-1001 支架（示例）\n"
            "尺寸:120*80*6\n"
            "序号:1\n"
            "数量:2\n"
            "颜色:灰色喷涂"
        )
        f = parse_card_text(text)
        self.assertEqual(f["name"], "DEMO-1001 支架（示例）")
        self.assertEqual(f["size"], "120*80*6")
        self.assertEqual(f["seq"], 1)
        self.assertEqual(f["qty"], 2)
        self.assertTrue(f["color"].startswith("灰色"))

    def test_value_before_colon(self):
        """有些PDF写成“数量 1:”“颜色 不锈钢:”。"""
        text = ("文件名称:DEMO-1002 盖板\n图号:\n尺寸:60*40*2\n"
                "颜色 白色喷涂:\n数量 10:")
        f = parse_card_text(text)
        self.assertEqual(f["name"], "DEMO-1002 盖板")
        self.assertEqual(f["qty"], 10)
        self.assertIsNone(f["seq"])
        self.assertEqual(f["size"], "60*40*2")

    def test_fullwidth_colon(self):
        f = parse_card_text("文件名称：DEMO-1\n数量：3\n序号：7")
        self.assertEqual(f["name"], "DEMO-1")
        self.assertEqual(f["qty"], 3)
        self.assertEqual(f["seq"], 7)

    def test_missing_qty_is_none(self):
        f = parse_card_text("文件名称:DEMO-2\n序号:5")
        self.assertIsNone(f["qty"])
        self.assertEqual(f["seq"], 5)


class TestCollectStickers(unittest.TestCase):
    def test_repeats_by_qty(self):
        page = PageCards(page_no=1, cards=[_card("A", 2, 0, 0), _card("B", 1, 0, 1)])
        pdf = PdfCards(path="x.pdf", n_pages=1, pages=[page])
        stickers = collect_stickers([pdf])
        self.assertEqual([s.card.name for s in stickers], ["A", "A", "B"])
        self.assertEqual([s.copy_no for s in stickers], [1, 2, 1])

    def test_keeps_file_order(self):
        p1 = PageCards(page_no=1, cards=[_card("A", 1, 0, 0)])
        p2 = PageCards(page_no=1, cards=[_card("B", 1, 0, 0)])
        pdfs = [PdfCards(path="1.pdf", n_pages=1, pages=[p1]),
                PdfCards(path="2.pdf", n_pages=1, pages=[p2])]
        self.assertEqual([s.card.name for s in collect_stickers(pdfs)], ["A", "B"])

    def test_records_source_page(self):
        p1 = PageCards(page_no=2, cards=[_card("A", 1, 0, 0)])
        pdf = PdfCards(path="x.pdf", n_pages=3, pages=[p1])
        st = collect_stickers([pdf])[0]
        self.assertEqual(st.page_no, 2)
        self.assertEqual(st.page_index, 1)


if __name__ == "__main__":
    unittest.main()
