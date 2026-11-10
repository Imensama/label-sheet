# -*- coding: utf-8 -*-
"""python -m label_sheet：无参数时开图形界面，有参数时走命令行。"""

import sys


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        from .gui import main as gui_main

        gui_main()
        return 0
    from .cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
