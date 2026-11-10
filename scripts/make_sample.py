# -*- coding: utf-8 -*-
"""生成 examples/sample.pdf（示例样张）与 docs/example.png（README 配图）。

只用开发环境里的 PyMuPDF 造样例，程序本身不依赖它。
"""

import os

import pymupdf as fitz

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "examples")
DOCS = os.path.join(ROOT, "docs")
os.makedirs(EX, exist_ok=True)
os.makedirs(DOCS, exist_ok=True)

MM = 72 / 25.4
W, H = 297 * MM, 210 * MM          # A4 横
COLS, ROWS = 3, 2

CARDS = [
    ("DEMO-1001 支架（示例）", "120*80*6", 1, 1, "灰色喷涂", "rail"),
    ("DEMO-1002 盖板", "60*40*2", 2, 4, "白色喷涂", "plate"),
    ("DEMO-1003 垫片", "80*20*3", 3, 2, "1Cr13", "shim"),
    ("DEMO-1004 压板", "90*35*12", 4, 1, "灰色喷涂", "clamp"),
    ("DEMO-1005 隔块", "40*30*25", 5, 1, "铝合金", "block"),
    ("DEMO-1006 长条", "68*40*1200", 6, 1, "铝合金", "bar"),
]

doc = fitz.open()
page = doc.new_page(width=W, height=H)

title = "示例表格（DEMO-001）"
page.insert_text((W / 2 - 120, 26), title, fontname="china-s", fontsize=15)

cell_w = (W - 40) / COLS
cell_h = (H - 70) / ROWS * 0.72
top0 = 40

for i, (name, size, seq, qty, color, shape) in enumerate(CARDS):
    col, row = i % COLS, i // COLS
    x0 = 20 + col * cell_w
    y0 = top0 + row * cell_h
    rect = fitz.Rect(x0, y0, x0 + cell_w, y0 + cell_h)
    page.draw_rect(rect, color=(0, 0, 0), width=0.6)

    ty = y0 + 10
    for line in [f"文件名称:{name}", f"包络尺寸:{size}", f"序号:{seq}", f"数量:{qty}", f"颜色:{color}"]:
        page.insert_text((x0 + 5, ty), line, fontname="china-s", fontsize=8)
        ty += 12

    # 简单图（示意）
    cx, cy = x0 + cell_w * 0.60, y0 + 108
    if shape == "rail":
        page.draw_rect(fitz.Rect(cx - 55, cy - 10, cx + 55, cy + 8), color=(0, 0, 0), width=1)
        page.draw_line((cx - 55, cy + 8), (cx - 45, cy + 20))
        page.draw_line((cx + 55, cy + 8), (cx + 45, cy + 20))
        page.draw_line((cx - 45, cy + 20), (cx + 45, cy + 20))
    elif shape == "plate":
        page.draw_rect(fitz.Rect(cx - 20, cy - 25, cx + 20, cy + 25), color=(0, 0, 0), width=1)
        page.draw_circle((cx - 12, cy - 17), 2)
        page.draw_circle((cx + 12, cy + 17), 2)
    elif shape == "shim":
        page.draw_rect(fitz.Rect(cx - 60, cy - 4, cx + 60, cy + 4), color=(0, 0, 0), width=1)
    elif shape == "clamp":
        page.draw_rect(fitz.Rect(cx - 35, cy - 12, cx + 35, cy + 12), color=(0, 0, 0), width=1)
        page.draw_line((cx - 35, cy - 12), (cx - 20, cy - 26))
        page.draw_line((cx + 35, cy - 12), (cx + 20, cy - 26))
        page.draw_line((cx - 20, cy - 26), (cx + 20, cy - 26))
    elif shape == "block":
        page.draw_rect(fitz.Rect(cx - 22, cy - 18, cx + 22, cy + 18), color=(0, 0, 0), width=1)
        page.draw_line((cx - 22, cy - 18), (cx - 8, cy - 28))
        page.draw_line((cx + 22, cy - 18), (cx + 8, cy - 28))
        page.draw_line((cx - 8, cy - 28), (cx + 8, cy - 28))
    else:
        page.draw_rect(fitz.Rect(cx - 70, cy - 3, cx + 70, cy + 3), color=(0, 0, 0), width=1)

page.insert_text((22, H - 20), "第（1）页", fontname="china-s", fontsize=8)

sample = os.path.join(EX, "sample.pdf")
doc.save(sample, deflate=True, garbage=4)
doc.close()
print("saved", sample, os.path.getsize(sample))
