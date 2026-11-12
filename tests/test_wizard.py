# -*- coding: utf-8 -*-
"""位置校准向导的推理逻辑测试（不建窗口）。"""

import unittest

from ulpp.sheets import DEFAULT_FEED, FEED_ORIENTATIONS
from ulpp.wizard import feed_from_answers, feed_label


class TestFeedInference(unittest.TestCase):
    def test_four_combinations(self):
        """两个问题 → 四个合法值，且都能落进 FEED_ORIENTATIONS。"""
        cases = {
            ("up", "short"): "face_up_short",
            ("up", "long"): "face_up_long",
            ("down", "short"): "face_down_short",
            ("down", "long"): "face_down_long",
        }
        for (face, edge), want in cases.items():
            got = feed_from_answers(face, edge, "unused")
            self.assertEqual(got, want)
            self.assertIn(got, FEED_ORIENTATIONS)

    def test_c8055_case(self):
        """施乐 C8055 打标签：胶面朝下 + A4 横放 = face_down_short。"""
        self.assertEqual(feed_from_answers("down", "short", DEFAULT_FEED),
                         "face_down_short")

    def test_missing_answer_falls_back(self):
        self.assertEqual(feed_from_answers(None, "short", "face_up_long"), "face_up_long")
        self.assertEqual(feed_from_answers("up", None, "face_down_short"), "face_down_short")
        self.assertEqual(feed_from_answers("nonsense", "nonsense", DEFAULT_FEED),
                         DEFAULT_FEED)

    def test_label_both_languages(self):
        self.assertEqual(feed_label("down", "short", "zh_CN"), "正面朝下 · 短边朝前")
        self.assertEqual(feed_label("up", "long", "zh_CN"), "正面朝上 · 长边朝前")
        en = feed_label("down", "short", "en_US")
        self.assertIn("down", en)
        self.assertIn("short", en)

    def test_unknown_language_uses_chinese(self):
        self.assertEqual(feed_label("down", "short", "fr_FR"), "正面朝下 · 短边朝前")


if __name__ == "__main__":
    unittest.main()
