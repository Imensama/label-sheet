# -*- coding: utf-8 -*-
"""多语言语言包与 ``tr()`` 的单元测试（stdlib unittest）。"""

import io
import os
import re
import sys
import unittest
from contextlib import redirect_stdout
from string import Formatter

from label_sheet import cli
from label_sheet.i18n import (
    available_languages,
    current_language,
    load_pack,
    normalize_language,
    set_language,
    tr,
)
from label_sheet.presets import PRESETS, by_key

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
TR_CALL_RE = re.compile(r"""\btr\(\s*['"]([A-Za-z0-9_.]+)['"]""")


class TestLanguagePacks(unittest.TestCase):
    def setUp(self):
        self._previous = current_language()
        set_language("zh_CN")

    def tearDown(self):
        set_language(self._previous)

    def test_key_sets_are_identical(self):
        zh = load_pack("zh_CN")
        en = load_pack("en_US")
        self.assertTrue(zh)
        self.assertTrue(en)
        self.assertEqual(set(zh), set(en), "中英语言包的 key 必须完全一致")
        self.assertEqual([], [k for k, v in zh.items() if not v.strip()])
        self.assertEqual([], [k for k, v in en.items() if not v.strip()])

    def test_placeholders_match(self):
        formatter = Formatter()
        zh = load_pack("zh_CN")
        en = load_pack("en_US")

        def fields(text):
            return {name for _, name, _, _ in formatter.parse(text) if name}

        for key in sorted(zh):
            self.assertEqual(fields(zh[key]), fields(en[key]), f"占位符不一致：{key}")

    def test_every_tr_key_exists(self):
        packs = load_pack("zh_CN")
        sources = [os.path.join(SRC, "label_sheet", name)
                   for name in os.listdir(os.path.join(SRC, "label_sheet"))
                   if name.endswith(".py")]
        sources.append(os.path.join(ROOT, "packaging", "entry.py"))
        used = set()
        for path in sources:
            with open(path, "r", encoding="utf-8") as fh:
                used.update(TR_CALL_RE.findall(fh.read()))
        missing = sorted(used - set(packs))
        self.assertEqual([], missing, "代码里用了语言包没有的 key")

    def test_missing_key_returns_key(self):
        self.assertEqual(tr("this.key.does.not.exist"), "this.key.does.not.exist")

    def test_unknown_language_falls_back(self):
        code = set_language("xx_YY")
        self.assertIn(code, available_languages())
        self.assertTrue(load_pack(code))

    def test_aliases(self):
        self.assertEqual(normalize_language("zh"), "zh_CN")
        self.assertEqual(normalize_language("zh-Hans-CN"), "zh_CN")
        self.assertEqual(normalize_language("en"), "en_US")
        self.assertEqual(normalize_language("en-GB"), "en_US")
        self.assertIsNone(normalize_language("fr_FR"))

    def test_formatting(self):
        set_language("en_US")
        self.assertEqual(tr("gui.status.processing", done=2, total=9), "Working… 2/9")
        self.assertEqual(tr("gui.log.lang_switched", lang="English"),
                         "UI language switched to English.")
        set_language("zh_CN")
        self.assertEqual(tr("gui.status.processing", done=2, total=9), "处理中… 2/9")

    def test_preset_titles_are_localized(self):
        set_language("en_US")
        self.assertEqual(by_key("45").title, "45 labels 40×30 (5×9, common)")
        self.assertEqual(by_key("24 labels 70×37 (3×8)").key, "24")
        set_language("zh_CN")
        self.assertEqual(by_key("45").title, "45格 40×30（5×9，常用）")
        self.assertEqual(by_key("24格 70×37（3×8）").key, "24")

    def test_presets_have_titles_in_every_language(self):
        for lang in available_languages():
            for preset in PRESETS:
                title = preset.title_in(lang)
                self.assertTrue(title.strip(), f"{preset.key} 缺少 {lang} 名称")
                if lang == "en_US":
                    self.assertFalse(CJK_RE.search(title), title)

    def test_cli_list_presets_english_only(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["--lang", "en", "--list-presets"])
        out = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("supported label presets", out)
        self.assertIn("45 labels", out)
        self.assertIsNone(CJK_RE.search(out), "英文模式不应出现中文")

    def test_cli_list_presets_chinese(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["--lang", "zh", "--list-presets"])
        out = buf.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("45格", out)
        self.assertIsNotNone(CJK_RE.search(out))

    def test_cli_help_english(self):
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit) as ctx:
            cli.main(["--lang", "en", "--help"])
        self.assertEqual(ctx.exception.code, 0)
        out = buf.getvalue()
        self.assertIn("Output folder", out)
        self.assertIsNone(CJK_RE.search(out), "英文 --help 不应出现中文")

    def test_lang_only_opens_gui(self):
        import label_sheet.__main__ as app_main
        import label_sheet.gui as gui

        calls = []
        original = gui.main
        gui.main = lambda: calls.append(current_language())
        original_argv = sys.argv
        try:
            sys.argv = ["label-sheet", "--lang", "en"]
            app_main.main()
        finally:
            gui.main = original
            sys.argv = original_argv
        self.assertEqual(["en_US"], calls)


if __name__ == "__main__":
    unittest.main()
