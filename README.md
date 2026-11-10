# A4 标签排版（label-sheet）

把 **PDF 页面里的若干小块**按份数排进 A4 预切不干胶的格子里，输出可直接打印的 PDF。

适用情形：PDF 页面本身是“一格一条记录”的表格（一页排了十几二十条信息）。
工具按文字锚点找出每一格，把这一格的内容原样抠出来、等比缩放进标签格，内容保持矢量（不是截图）。

默认版式是 5 列 × 9 行、单格 40×30mm（节距 41.5×32、上边距 6mm、内容距刀线内缩 2mm），
列数/行数/格宽/节距/边距都可以改。

> 最初是为了摆脱琐碎手工排版的“案牍之劳形”。

![效果](docs/example.png)

## 功能

- **自动识别卡片**：按“文件名称”这类字段当锚点找每一格，份数读“数量”字段，不依赖固定表格行数
- **按份数复制**：`数量 2` 出 2 张，`数量 10` 出 10 张；同一卡片的多张连排，方便分发
- **矢量裁剪**：整格内容按矢量缩放入格，放大不糊
- **一次出三个文件**：生产版（无刀线）、刀线校样版（浅灰刀线，试打对位）、标签清单 CSV
- **多份一起排**：一次排几十上百张，按 45 格一版自动分页
- **输入支持 PDF / 文件夹 / ZIP**（中文文件名的 ZIP 会自动纠正编码）
- **参数可调**：列数、行数、格宽高、节距、边距、安全边

## 卡片是怎么认的

- 字段名写在 `src/label_sheet/parser.py` 顶部（`FIELD_LABELS` 和几个正则里），
  换一套模板时改这几个常量即可，不用动排版逻辑
- 一页有几列几行**不写死**，按锚点位置聚类推断
- 表格线会被识别并剔除，不会跟着缩进标签
- 一格里没有锚点时，这张卡片会跳过并在日志里提示

## 三种用法

### 1. 免安装：下载 exe

去 [Releases](../../releases) 下载 `标签排版.exe`，双击运行，不用装 Python。

> 未签名的 exe 可能被 Windows Defender / SmartScreen 拦一下：点“更多信息 → 仍要运行”。

### 2. 源码运行

```bash
git clone https://github.com/<your-name>/label-sheet.git
cd label-sheet
pip install -r requirements.txt
python run_gui.pyw          # Windows 图形界面
python -m label_sheet     # 各平台通用（无参数即开界面）
```

### 3. 命令行

```bash
python -m label_sheet 输入.zip -o 输出目录
python -m label_sheet 某个目录 --first-page-only --no-proof
python -m label_sheet 表单.pdf --cols 5 --rows 9 --cell 40x30 --pitch 41.5x32
python -m label_sheet 表单.pdf --save-config g.json   # 存一套参数，下次 --config g.json
```

`python -m label_sheet -h` 看全部参数。

## 输出

| 文件 | 用途 |
| --- | --- |
| `*_生产版.pdf` | 直接上不干胶纸打印（无色标线） |
| `*_刀线校样版.pdf` | 普通纸试打，和不干胶纸透光叠对，检查刀线对位 |
| `*_标签清单.csv` | 每张标签在第几版第几格、来源、名称、数量、第几份 |

## 目录结构

```
label-sheet/
├─ src/label_sheet/
│  ├─ config.py      # 版式参数（GridSpec）
│  ├─ parser.py      # 解析 PDF：找卡片、读字段、算内容框
│  ├─ builder.py     # 拼版输出：Form XObject + 裁剪 + 缩放
│  ├─ cli.py         # 命令行
│  ├─ gui.py         # 图形界面（tkinter）
│  └─ __main__.py    # 有参数走 CLI，无参数开界面
├─ packaging/        # PyInstaller 打包配置与脚本
├─ tests/            # 单元测试
└─ .github/workflows/build-windows.yml   # 打 tag 自动打包并发 Release
```

## 技术要点

- 解析用 **pdfplumber**（拿文字和线条坐标）：以字段名所在的词当锚点，按最近的列起点归格，
  同一格的词按 top 聚成行，从锚点行开始按字段名收行；遇到下一个“文件名称”就停。
- 输出用 **pypdf**：源页做成 **Form XObject**（整页只内嵌一份），用「裁剪路径 + 缩放矩阵 + `Do`」
  画进小格。**裁剪框必须用内容区而不是整格**，否则安全边里会漏出相邻内容。
- 表格线识别：细长且贯通整页的线判为格线剔除，避免把表格边框缩进标签。

## 开发与打包

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -t .
```

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
# 产物：dist\标签排版.exe（单文件，约 36MB）
```

或者用 GitHub Actions：打 tag 后自动构建并上传 Release 附件。

## 平台支持

| 平台 | 状态 | 需要额外装 |
| --- | --- | --- |
| Windows 10/11 | 主要支持，有 exe | 无 |
| macOS | 源码可跑 | Python 3.9+（官网安装包自带 tkinter） |
| Linux | 源码可跑 | `python3-tk` |

exe 是 Windows 专用；mac/Linux 用 `python -m label_sheet`。

## 常见问题

**Q：识别不到卡片？**
A：这个模式针对“每格一条记录”的表格型 PDF。扫描件（整页图片）或没有这些字段名的 PDF 取不到，
可以改 `parser.py` 顶部的字段名。

**Q：某个格子的标签空白 / 只有一小条？**
A：多半是那一格的表格线被判成了内容。把 PDF 发个 issue，或先用 `--inset 1` 试试。

**Q：刀线对不上？**
A：先打校样版，量出 X/Y 偏移，改“上边距”和“行节距”。

## 许可

[MIT](LICENSE)。第三方组件均为宽松协议（MIT / BSD / PSF / MIT-CMU），可以随 exe 分发到 Releases。
详见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
