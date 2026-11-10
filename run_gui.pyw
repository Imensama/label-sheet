# -*- coding: utf-8 -*-
"""双击即可运行（源码方式）：pythonw run_gui.pyw"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from label_sheet.gui import main  # noqa: E402

if __name__ == "__main__":
    main()
