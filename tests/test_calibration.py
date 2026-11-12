# -*- coding: utf-8 -*-
"""普通纸校准页的单元测试。"""

import os
import shutil
import unittest
import uuid

from pypdf import PdfReader

from ulpp.calibration import make_calibration_pdf, make_orientation_pdf
from ulpp.config import GridSpec
from ulpp.i18n import set_language

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


class TestCalibrationPdf(unittest.TestCase):
    def setUp(self):
        set_language("zh_CN")
        self.dir = os.path.join(ROOT, f"ulpp_cal_test_{uuid.uuid4().hex[:8]}")
        os.makedirs(self.dir, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_default_page(self):
        out = os.path.join(self.dir, "cal.pdf")
        make_calibration_pdf(GridSpec(), out)
        self.assertTrue(os.path.exists(out))
        pdf = PdfReader(out)
        self.assertEqual(len(pdf.pages), 1)
        page = pdf.pages[0]
        self.assertAlmostEqual(float(page.mediabox.width), 595.28, delta=1)
        self.assertAlmostEqual(float(page.mediabox.height), 841.89, delta=1)
        self.assertEqual(len(page.images), 1, "校准页应是一张嵌入图")

    def test_custom_grid_and_feed(self):
        out = os.path.join(self.dir, "cal2.pdf")
        make_calibration_pdf(GridSpec(cols=2, rows=2, cell_w=99, cell_h=74.25),
                             out, feed="face_down_long", lang="en_US")
        pdf = PdfReader(out)
        self.assertEqual(len(pdf.pages), 1)

    def test_invalid_feed_falls_back(self):
        out = os.path.join(self.dir, "cal3.pdf")
        make_calibration_pdf(GridSpec(), out, feed="not-a-feed")
        self.assertTrue(os.path.exists(out))


class TestOrientationPdf(unittest.TestCase):
    """方向测试页：判断打印机哪面着墨 / 纸哪条边朝里。"""

    def setUp(self):
        set_language("zh_CN")
        self.dir = os.path.join(ROOT, f"ulpp_orient_test_{uuid.uuid4().hex[:8]}")
        os.makedirs(self.dir, exist_ok=True)
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_default_feed(self):
        out = os.path.join(self.dir, "orient.pdf")
        make_orientation_pdf(out)
        self.assertTrue(os.path.exists(out))
        pdf = PdfReader(out)
        self.assertEqual(len(pdf.pages), 1)
        page = pdf.pages[0]
        self.assertAlmostEqual(float(page.mediabox.width), 595.28, delta=1)
        self.assertAlmostEqual(float(page.mediabox.height), 841.89, delta=1)
        self.assertEqual(len(page.images), 1, "方向测试页应是一张嵌入图")

    def test_all_feeds_render(self):
        for feed in ("face_up_short", "face_up_long", "face_down_short", "face_down_long"):
            out = os.path.join(self.dir, f"orient_{feed}.pdf")
            make_orientation_pdf(out, feed=feed, lang="en_US")
            self.assertEqual(len(PdfReader(out).pages), 1, feed)

    def test_invalid_feed_falls_back(self):
        out = os.path.join(self.dir, "orient_bad.pdf")
        make_orientation_pdf(out, feed="nonsense")
        self.assertTrue(os.path.exists(out))

    def test_page_image_is_not_blank(self):
        """测试页上必须真有大 A / 黑条，不能是一张白纸。"""
        out = os.path.join(self.dir, "orient_ink.pdf")
        make_orientation_pdf(out)
        img = list(PdfReader(out).pages[0].images)[0].image.convert("L")
        dark = sum(1 for p in img.getdata() if p < 128)
        self.assertGreater(dark, img.width * img.height * 0.02, "测试页黑墨太少")


if __name__ == "__main__":
    unittest.main()

