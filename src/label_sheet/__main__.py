# -*- coding: utf-8 -*-
"""python -m label_sheet：无参数（或只给 --lang）时开图形界面，其余参数走命令行。"""

import sys
from typing import Optional, Tuple


def _parse_gui_args(argv) -> Tuple[bool, Optional[str]]:
    """判断参数是否“只指定了语言”。是则返回 (True, lang)，否则 (False, None)。"""
    lang: Optional[str] = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--lang":
            if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
                return False, None
            lang = argv[i + 1]
            i += 2
        elif arg.startswith("--lang="):
            lang = arg.split("=", 1)[1]
            i += 1
        else:
            return False, None
    return True, lang


def main() -> int:
    from .i18n import set_language

    argv = sys.argv[1:]
    if not argv:
        set_language(None)
        from .gui import main as gui_main

        gui_main()
        return 0

    gui_only, lang = _parse_gui_args(argv)
    if gui_only:
        set_language(lang)
        from .gui import main as gui_main

        gui_main()
        return 0

    from .cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
