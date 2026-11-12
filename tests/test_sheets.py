# -*- coding: utf-8 -*-
"""胶纸记录与打印机配置的单元测试（stdlib unittest）。"""

import json
import os
import shutil
import unittest
import uuid
from pathlib import Path

from ulpp.config import GridSpec
from ulpp.sheets import (
    SheetStore,
    SheetStoreError,
    PrinterProfile,
    SheetRecord,
    default_sheets_path,
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


class TestSheetRecord(unittest.TestCase):
    def test_free_cells_and_used(self):
        sheet = SheetRecord(id="a", name="s", grid=GridSpec().to_dict(), used=[0, 2])
        self.assertEqual(sheet.per_sheet, 45)
        self.assertFalse(sheet.is_free(0))
        self.assertTrue(sheet.is_free(1))
        self.assertEqual(sheet.free_count, 43)
        self.assertEqual(sheet.free_cells[:3], [1, 3, 4])

    def test_mark_used_and_free_dedup(self):
        sheet = SheetRecord(id="a", name="s", grid=GridSpec().to_dict())
        self.assertEqual(sheet.mark_used([1, 1, 2]), [1, 2])
        self.assertEqual(sheet.mark_free([2, 2, 99]), [2])
        self.assertEqual(sheet.used, [1])

    def test_invalid_used_filtered_on_load(self):
        sheet = SheetRecord.from_dict(
            {"id": "x", "name": "n", "grid": GridSpec(cols=2, rows=2).to_dict(),
             "used": [-1, 0, 3, 99, "x"]}
        )
        self.assertEqual(sheet.used, [0, 3])

    def test_roundtrip_dict(self):
        sheet = SheetRecord(id="x", name="n", grid=GridSpec(cols=2, rows=2).to_dict(), used=[0])
        self.assertEqual(SheetRecord.from_dict(sheet.to_dict()), sheet)


class TestSheetStore(unittest.TestCase):
    def setUp(self):
        # 不用系统临时目录：沙箱/中文环境下清理会偶发 PermissionError
        self.dir = os.path.join(ROOT, f"ulpp_sheets_test_{uuid.uuid4().hex[:8]}")
        os.makedirs(self.dir, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = Path(self.dir) / "sheets.json"
        self.inv = SheetStore(path=self.path)

    def tearDown(self):
        pass

    def test_add_and_persist(self):
        sheet = self.inv.add_sheet("45格 #1", GridSpec(), used=[0, 1, 2])
        self.assertEqual(sheet.free_count, 42)
        self.assertEqual(self.inv.free_total(), 42)
        self.inv.save()
        loaded = SheetStore.load(self.path)
        self.assertEqual(len(loaded.sheets), 1)
        self.assertEqual(loaded.sheets[0].name, "45格 #1")
        self.assertEqual(loaded.sheets[0].free_count, 42)
        self.assertEqual(loaded.free_total(), 42)

    def test_unique_names(self):
        a = self.inv.add_sheet("paper", GridSpec())
        b = self.inv.add_sheet("paper", GridSpec())
        self.assertEqual(a.name, "paper")
        self.assertEqual(b.name, "paper #2")

    def test_remove_sheet(self):
        sheet = self.inv.add_sheet("p", GridSpec())
        self.assertTrue(self.inv.remove_sheet(sheet.id))
        self.assertFalse(self.inv.remove_sheet("nope"))
        self.assertEqual(self.inv.sheets, [])

    def test_mark_used_free(self):
        sheet = self.inv.add_sheet("p", GridSpec())
        self.assertEqual(self.inv.mark_used(sheet.id, [1, 2]), [1, 2])
        self.assertEqual(self.inv.mark_free(sheet.id, [2]), [2])
        self.assertEqual(self.inv.free_cells(sheet.id)[:2], [0, 2])

    def test_printer_roundtrip(self):
        p = PrinterProfile(id="p1", name="Laser", offset_x_mm=1.25,
                           offset_y_mm=-0.5, feed="face_down_long", note="hand feed")
        self.inv.save_printer(p)
        self.inv.default_printer = "p1"
        self.inv.save()
        loaded = SheetStore.load(self.path)
        got = loaded.get_printer("p1")
        self.assertEqual(got.name, "Laser")
        self.assertAlmostEqual(got.offset_x_mm, 1.25, places=3)
        self.assertAlmostEqual(got.offset_y_mm, -0.5, places=3)
        self.assertEqual(got.feed, "face_down_long")

    def test_missing_file_starts_empty(self):
        loaded = SheetStore.load(self.path)
        self.assertEqual(loaded.sheets, [])
        self.assertIsNotNone(loaded.get_printer())

    def test_legacy_inventory_migrates(self):
        legacy = Path(self.dir) / "inventory.json"
        payload = {"version": 1, "sheets": [{"id": "legacy", "name": "旧记录",
                   "grid": GridSpec().to_dict(), "used": [0]}],
                   "printers": [], "default_printer": "default"}
        legacy.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        loaded = SheetStore.load(self.path)
        self.assertEqual(len(loaded.sheets), 1)
        self.assertEqual(loaded.sheets[0].name, "旧记录")
        loaded.save()
        self.assertTrue(self.path.exists())

    def test_corrupt_file_raises(self):
        self.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(SheetStoreError):
            SheetStore.load(self.path)

    def test_default_path_has_json_name(self):
        self.assertEqual(default_sheets_path().name, "sheets.json")


if __name__ == "__main__":
    unittest.main()


