# 第三方组件与许可

本项目（label-sheet）以 **MIT** 协议发布。运行期只依赖下面两个库，均为宽松协议，
可以随本项目一起打包、商用、二次分发。

| 组件 | 版本要求 | 协议 | 用途 | 是否随 exe 分发 |
| --- | --- | --- | --- | --- |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | >=0.11,<1.0 | MIT | 读取 PDF 文字/线条坐标，定位卡片 | 是 |
| [pdfminer.six](https://github.com/pdfminer/pdfminer.six) | 由 pdfplumber 引入 | MIT | pdfplumber 的底层解析引擎 | 是 |
| [pypdf](https://github.com/py-pdf/pypdf) | >=4.0 | BSD-3-Clause | 把源页做成 Form XObject、裁剪缩放、拼 A4 | 是 |
| [Pillow](https://python-pillow.org/) | 由 pdfplumber 间接引入 | MIT-CMU | 图像处理（本工具不直接调用） | 视打包结果 |
| [tkinter / Tcl-Tk](https://docs.python.org/3/library/tkinter.html) | Python 自带 | PSF / BSD 类 | 图形界面 | 是 |
| [PyInstaller](https://pyinstaller.org/) | >=6 | GPL-2.0-or-later **+ 打包例外** | 仅构建期把 Python 打成 exe | 引导器随 exe |

## 关于 PyInstaller 的 GPL

PyInstaller 的 GPL 附带明确的“打包例外（bootloader exception）”：
用它打包出来的程序**不必**以 GPL 开源，可以保持 MIT / 闭源。因此把本项目的 exe
发到 GitHub Releases 是合规的，只需保留本文件的第三方声明。

## 为什么选 pdfplumber + pypdf

PyMuPDF 功能更全，采用 **AGPL-3.0** 许可（另提供商业授权）。按 AGPL 条款，把该组件
打包进 exe 分发时需要以 AGPL 公开源码；本项目希望保持 MIT 许可，便于分发与二次修改，
因此选用 `pdfplumber`（MIT）+ `pypdf`（BSD-3-Clause）：输出同样是**矢量**（不是截图）。

## 保留声明

如果你修改并再分发本项目，请：

1. 保留仓库根目录的 `LICENSE`（MIT）；
2. 保留本文件，或在你自己的 NOTICE 里列出上表组件及其协议；
3. 若把 exe 放到 GitHub Releases，建议同时附上源码链接（本仓库即可）。
