# -*- coding: utf-8 -*-
"""极简运行时多语言：JSON 语言包 + 系统语言识别 + ``tr()``。

语言解析优先级：显式参数（``--lang`` / GUI 下拉）> 环境变量 ``LC_ALL`` / ``LANG`` /
``LANGUAGE`` > 系统区域设置 > ``zh_CN``。

语言包缺失或某个 key 没翻译时，回退到 ``zh_CN`` 并往 stderr 打一条警告，不抛异常；
这样即使打包时漏了 ``locales/*.json``，程序仍然能用，只是界面回到中文。
"""

from __future__ import annotations

import json
import locale
import os
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple

DEFAULT_LANGUAGE = "zh_CN"
SUPPORTED_LANGUAGES: Tuple[str, ...] = ("zh_CN", "en_US")
LANGUAGE_NAMES: Dict[str, str] = {"zh_CN": "中文", "en_US": "English"}

_PACKS: Dict[str, Dict[str, str]] = {}
_CURRENT = DEFAULT_LANGUAGE
_INITIALIZED = False
_WARNED: set = set()


def _warn(message: str) -> None:
    stream = sys.stderr
    if stream is None:
        return
    try:
        print(f"[label-sheet] {message}", file=stream)
    except Exception:  # pragma: no cover - 极端情况下 stderr 不可写
        pass


def _warn_once(key: str, message: str) -> None:
    if key in _WARNED:
        return
    _WARNED.add(key)
    _warn(message)


def normalize_language(value: Optional[str]) -> Optional[str]:
    """把 ``zh`` / ``zh-CN`` / ``en`` / ``en_US`` 等写法归一成受支持的语言代码。"""
    if not value:
        return None
    text = str(value).strip().lower().replace("-", "_")
    if not text:
        return None
    if text.startswith("zh"):
        return "zh_CN"
    if text.startswith("en"):
        return "en_US"
    if "chinese" in text:
        return "zh_CN"
    if "english" in text:
        return "en_US"
    return None


def _locale_dir() -> Path:
    """语言包目录：源码运行在包内，PyInstaller 打包后在 ``_MEIPASS`` 下。"""
    here = Path(__file__).resolve().parent
    candidates = [here / "locales"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "label_sheet" / "locales")
    for path in candidates:
        if path.is_dir():
            return path
    return candidates[0]


def _load(lang: str) -> Dict[str, str]:
    if lang in _PACKS:
        return _PACKS[lang]
    path = _locale_dir() / f"{lang}.json"
    data: Dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
        if not isinstance(loaded, dict):
            raise ValueError("语言包顶层必须是 JSON 对象")
        data = {str(k): str(v) for k, v in loaded.items()}
    except FileNotFoundError:
        _warn_once(f"missing:{lang}", f"语言包不存在：{path}，回退 {DEFAULT_LANGUAGE}")
    except Exception as exc:  # pragma: no cover - 损坏的语言包
        _warn_once(f"broken:{lang}", f"语言包读取失败：{path}（{exc}），回退 {DEFAULT_LANGUAGE}")
    _PACKS[lang] = data
    return data


def load_pack(lang: str) -> Dict[str, str]:
    """返回某个语言的完整语言包（给测试 / 文档脚本用）。"""
    code = normalize_language(lang) or DEFAULT_LANGUAGE
    return dict(_load(code))


def available_languages() -> Tuple[str, ...]:
    return SUPPORTED_LANGUAGES


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code)


def _env_language() -> Optional[str]:
    for name in ("LC_ALL", "LANG", "LANGUAGE"):
        value = os.environ.get(name)
        if not value:
            continue
        # LANG 可能是 zh_CN.UTF-8 或 "en_US:fr_FR"
        first = value.split(":")[0].split(".")[0]
        code = normalize_language(first)
        if code:
            return code
    return None


def _system_language() -> Optional[str]:
    try:
        value = locale.getlocale()[0]
    except Exception:  # pragma: no cover - 极少数平台
        value = None
    return normalize_language(value)


def resolve_language(explicit: Optional[str] = None) -> str:
    """按“显式 > 环境变量 > 系统 > 默认”解析语言代码，并保证语言包存在。"""
    if explicit is not None and normalize_language(explicit) is None:
        _warn_once(f"unsupported:{explicit}", f"不支持的语言：{explicit!r}，改用系统语言")
    code = normalize_language(explicit) or _env_language() or _system_language() or DEFAULT_LANGUAGE
    pack = _load(code)
    if not pack and code != DEFAULT_LANGUAGE:
        _warn_once(f"empty:{code}", f"语言包 {code} 为空，回退 {DEFAULT_LANGUAGE}")
        code = DEFAULT_LANGUAGE
    return code


def set_language(lang: Optional[str] = None) -> str:
    """设置当前语言；``None`` 表示按环境变量 / 系统语言自动判断。"""
    global _CURRENT, _INITIALIZED
    _CURRENT = resolve_language(lang)
    _INITIALIZED = True
    return _CURRENT


def ensure_language() -> str:
    """首次取翻译时按环境 / 系统语言初始化（显式设置过就不再改）。"""
    if not _INITIALIZED:
        set_language(None)
    return _CURRENT


def current_language() -> str:
    return ensure_language()


def tr(message_key: str, language: Optional[str] = None, **fmt) -> str:
    """取一条翻译；当前语言缺这条时回退 ``zh_CN``，再缺就返回 key 本身。

    第二个参数叫 ``language`` 而不是 ``lang``，这样 ``tr(..., lang=...)``
    里的 ``lang`` 才能作为普通占位符使用。
    """
    ensure_language()
    code = normalize_language(language) or _CURRENT
    pack = _load(code)
    template = pack.get(message_key)
    if template is None:
        template = _load(DEFAULT_LANGUAGE).get(message_key)
    if template is None:
        _warn_once(f"key:{message_key}", f"缺少翻译 key：{message_key}")
        template = message_key
    if fmt:
        try:
            return template.format(**fmt)
        except (KeyError, IndexError, ValueError):  # pragma: no cover - 语言包写错时的兜底
            _warn_once(f"fmt:{message_key}", f"翻译占位符不匹配：{message_key}")
            return template
    return template
