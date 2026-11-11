# A4 Label Sheet (label-sheet)

[简体中文](README.md) | English

Turn **small regions of a PDF page** or **a block of plain text** into A4 pre-cut label sheets, with one copy per quantity, and get a print-ready PDF.

Two kinds of input:

1. **Table-style PDF** — each cell of the page is one record. The tool finds every cell by a text anchor,
   clips the cell content as vectors (not a screenshot), scales it into the label cell and keeps it sharp.
2. **Plain text** — one line per label, wrapped and auto-sized, rendered as a 600 dpi bitmap.

14 common A4 label presets are built in, and you can also set columns, cell size, pitch and margins yourself.
On Windows, just double-click the exe; the command line is available for batch work.
The UI defaults to the system language, and falls back to English when the system locale is neither Chinese nor English.

> Originally built to escape the tedious hand-layout grind.
> Text mode and label-size presets came later.

![Table-style PDF example](docs/example.png)
![Text label example](docs/example-text.png)

## Features

- **Copies by quantity**: a cell with “数量 2” produces 2 stickers, “数量 10” produces 10; copies of the same card are laid out together
- **Vector clipping**: cell content is scaled as vectors, so it stays sharp; text labels are 600 dpi bitmaps without embedded fonts, so a PDF stays small
- **Automatic text layout**: wraps lines and picks the font size automatically; alignment can be center / left / right; “uniform font size” uses one size for the whole batch.
  End a line with `|2` or ` ×2` to print that label twice (`120×80×6`-style dimensions are not mistaken for a copy count)
- **Mix PDF cards and text labels**: PDF cards come first, text labels follow, filling the same sheet
- **Three outputs per run**: production PDF (no knife lines), knife-line proof PDF (light gray lines for alignment checks), and a label list CSV
- **Built-in presets**: pick one and the columns / cell size / pitch / margins are filled in; fine-tune them for your actual stock
- **Inputs**: PDF, folder or ZIP (file names in Chinese ZIPs are decoded automatically)
- **Bilingual UI (v1.2+)**: Chinese and English, switchable in the GUI or with `--lang zh|en`; the default follows the system language, and English is used when the system locale is neither Chinese nor English

## How PDF card detection works

- Field labels such as “文件名称” (file name) are used as **anchors**; the quantity comes from “数量” (quantity)
- The field names live at the top of `src/label_sheet/parser.py` (`FIELD_LABELS` and the regular expressions).
  For a different template, change those constants; the layout code does not need to change
- The number of columns and rows is **not hard-coded**; it is inferred from anchor positions. Table rules are detected and removed so they do not get scaled into labels
- A cell without an anchor is skipped, with a warning in the log

> The anchor field names are Chinese because the original template is Chinese. English PDF templates are not
> detected out of the box; change `FIELD_LABELS` for your own template.

## Built-in label presets

| Preset | Columns × rows | Cell |
| --- | --- | --- |
| 45 labels (measured stock) | 5×9 | 40 × 30 mm, pitch 41.5×32 |
| 24 labels | 3×8 | 70 × 37 mm |
| 21 labels | 3×7 | 70 × 42.3 mm |
| 30 labels | 3×10 | 70 × 29.7 mm |
| 12 labels | 2×6 | 99 × 49.5 mm |
| 10 labels | 2×5 | 99 × 59.4 mm |
| 8 labels | 2×4 | 99 × 74.25 mm |
| 6 labels | 2×3 | 99 × 99 mm |
| 4 labels | 2×2 | 105 × 148.5 mm |
| 2 labels | 1×2 | 210 × 148.5 mm |
| 40 labels | 4×10 | 48 × 25 mm |
| 72 labels | 6×12 | 33 × 23 mm |
| 65 labels | 5×13 | 38 × 22 mm |
| 44 labels | 4×11 | 46 × 25 mm |

> Die-cut lines differ by 0.5–1 mm between batches. After choosing a preset, print one “knife-line proof”,
> overlay it on the real label stock against a light, and adjust “pitch Y / top margin / inset” if needed.

## Three ways to use it

### 1. No install: download the exe

Get `标签排版.exe` from [Releases](../../releases), double-click it, and no Python is needed.

> The unsigned exe may be blocked once by Windows Defender / SmartScreen: choose “More info → Run anyway”.
> If that is a problem, run from source; the result is identical.

### 2. Run from source

```bash
git clone https://github.com/<your-name>/label-sheet.git
cd label-sheet
pip install -r requirements.txt
pip install -e .            # makes `python -m label_sheet` find the package in src/
python run_gui.pyw          # Windows GUI
python -m label_sheet       # any platform (no arguments opens the GUI)
```

> If you prefer not to install the package, set `PYTHONPATH=src` before running `python -m label_sheet`.

### 3. Command line (batch / scheduled jobs)

> Run these from the repository root; for a source checkout, run `pip install -e .` first
> (or set `PYTHONPATH=src`).

```bash
# Table-style PDF
python -m label_sheet input.zip -o output
python -m label_sheet some-folder --first-page-only --no-proof
python -m label_sheet form.pdf --preset 24

# Text labels only (one line per label; |2 = print two)
python -m label_sheet --lang en --text "URGENT A-01 |2" --text "REWORK" -o output
python -m label_sheet --lang en --text-file list.txt --text-uniform

# Mixed
python -m label_sheet form.pdf --text "Rush |2" --preset 45

# English UI for one command
python -m label_sheet --lang en --list-presets

python -m label_sheet --list-presets        # list all presets
python -m label_sheet --save-config g.json  # save a grid, reuse with --config g.json
```

`python -m label_sheet -h` lists every option. `--preset` accepts the stable id (`45`, `24`, …),
the English name, or the old Chinese name, so existing scripts keep working.

## Using the GUI

1. **1  PDF files** (optional): use “Add PDF / Add folder / Add ZIP”. With `tkinterdnd2` installed, you can also drop files onto the list
2. **2  Text labels** (optional): one line per label, `|2` at the end prints two; choose alignment and “uniform font size”
3. **3  Output options**: all pages / first page only; whether to generate the knife-line proof and CSV; output folder
4. **4  Label preset & grid**: choose a preset to fill in the dimensions, then fine-tune for the actual die-cut lines
5. Click **Generate**, then “Open output folder”

The language selector at the bottom right switches between **中文** and **English** immediately; files, text and
grid settings are kept. Without a choice, the language follows `--lang` (if given), then `LC_ALL` / `LANG`,
then the system locale; when the system locale is neither Chinese nor English, it uses English.

## Output

| File | Purpose |
| --- | --- |
| `*_production.pdf` | Print directly on label stock (no registration lines) |
| `*_knife-proof.pdf` | Print on plain paper, overlay on the label stock, check die-cut alignment |
| `*_manifest.csv` | For every sticker: sheet, cell, source (PDF/text), name, quantity, copy number |

> File names are localized too: a Chinese UI writes `*_生产版.pdf`, `*_刀线校样版.pdf` and `*_标签清单.csv`;
> an English UI writes the English names above. The default prefix is `标签` / `label`, and the default
> output folder is `标签输出` / `label-output`.

## Project layout

```
label-sheet/
├─ src/label_sheet/
│  ├─ config.py      # grid parameters (GridSpec)
│  ├─ presets.py     # common A4 label presets (stable ids + localized names)
│  ├─ parser.py      # PDF parsing: find cards, read fields, compute content boxes
│  ├─ textlabel.py   # text layout: tokenize, wrap, auto-size, render bitmap
│  ├─ imagex.py      # write bitmaps as PDF image XObjects (1-bit + Flate)
│  ├─ builder.py     # layout output: Form XObject / image + clip + scale
│  ├─ i18n.py        # runtime i18n: JSON packs, system language, tr()
│  ├─ locales/       # zh_CN.json / en_US.json
│  ├─ cli.py         # command line
│  ├─ gui.py         # tkinter GUI
│  └─ __main__.py    # arguments → CLI; no arguments → GUI
├─ packaging/        # PyInstaller specs and scripts
├─ tests/            # unit and end-to-end tests
└─ .github/workflows/build-windows.yml   # build and publish a Release on tag
```

## Technical notes

- Parsing uses **pdfplumber** (text and line coordinates): the word containing a field label is the anchor,
  words are assigned to the nearest column start, grouped into lines by `top`, and collected from the anchor
  line until the next “文件名称”.
- PDF output uses **pypdf**: each source page becomes a **Form XObject** (embedded once), then drawn into a
  cell with “clip path + scale matrix + `Do`”. **The clip box must be the content box, not the whole cell**,
  otherwise neighbouring content leaks into the inset.
- Text output uses **Pillow** to render a 600 dpi 1-bit image, written as an `/Image` XObject (Flate).
  No Chinese font is embedded: labels are small, a bitmap is visually indistinguishable from vectors when
  printed, and the PDF does not grow by ten megabytes.
- Table-line detection: thin lines spanning a large part of the page are treated as rules and removed, so
  table borders do not get scaled into labels.
- i18n: two JSON packs; a test asserts that their key sets are identical, that placeholders match, and that
  every `tr()` key used in the source exists. Missing packs or keys fall back to Chinese with a warning.

## Development and packaging

```bash
pip install -r requirements.txt
pip install -e .
python -m unittest discover -s tests -t .
```

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
# artifact: dist\标签排版.exe (single file, about 36 MB)
```

For local testing, a `--onedir` build avoids the single-file extraction problem in sandboxed environments:

```powershell
python -m PyInstaller packaging\label_sheet_onedir.spec --noconfirm
# artifact: dist\标签排版\标签排版.exe
```

Or use GitHub Actions: push a tag such as `v1.2.1` and the workflow builds and attaches the exe to the Release.

## Platform support

| Platform | Status | Extra requirements |
| --- | --- | --- |
| Windows 10/11 | main target, exe provided | none |
| macOS | source works | Python 3.9+ (python.org builds include tkinter; Homebrew needs `brew install python-tk`) |
| Linux | source works | `python3-tk`; text mode needs a font (DejaVu Sans for English, `fonts-wqy-microhei` for Chinese) |

The exe is Windows-only; on macOS/Linux use `python -m label_sheet`.
The “Open output folder” button only shows the path on macOS/Linux.

## FAQ

**Q: No cards detected?**
A: This mode is for table-style PDFs where each cell is a record. Scanned pages (one big image) or PDFs
without the expected field names cannot be parsed. Use text mode instead, or edit the field names at the
top of `parser.py`.

**Q: Text labels vary in size?**
A: By default each label uses the largest size that fits. Tick “Uniform font size” to use one size for the
whole batch (the smallest size that fits every label).

**Q: One character is pushed onto the next line?**
A: There is a “widow pull-back” step, but very narrow cells can still do this. Shorten the text or reduce
the content inset.

**Q: A cell is blank or only a thin strip?**
A: Most often a table rule in that cell was treated as content. Open an issue with the PDF, or try
`--inset 1`.

**Q: The die-cut lines do not line up?**
A: Print the proof first, measure the X/Y offset, then adjust “top margin” and “pitch Y”, or pick a closer
preset.

**Q: Can it generate barcodes / QR codes?**
A: Not currently; existing ones in the source PDF are clipped as-is. Generation could be added on top of
`textlabel.py`.

## License

[MIT](LICENSE). Runtime dependencies use permissive licenses (MIT / BSD / PSF / MIT-CMU) and can be
redistributed with the exe on Releases.
See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
PyMuPDF is AGPL-3.0: bundling it into an exe would require publishing the source under AGPL, so this
project stays MIT and uses pdfplumber + pypdf instead.
