#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成一张合并所有 163 张美系图片的联络图(verified 在前, review 在后)。"""
import os, csv
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output', 'collection_us')
DEST = os.path.join(ROOT, "all")
OUT = os.path.join(ROOT, "contact_sheet_all.png")

# 读 index.csv 拿排序与标签
rows = []
with open(os.path.join(DEST, "index.csv"), encoding="utf-8") as f:
    for r in csv.DictReader(f):
        rows.append(r)
status_rank = {"verified": 0, "review": 1}
rows.sort(key=lambda r: (status_rank.get(r["status"], 2), r["brand"], r["series"], r["gid"]))

THUMB = 300
COLS = 8
PAD = 6
LABEL_H = 22
# 颜色
C_VER = (34, 139, 34)   # 绿: verified
C_REV = (200, 120, 0)   # 橙: review
BG = (245, 245, 245)

# 字体(系统默认)
try:
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 16)
except Exception:
    font = ImageFont.load_default()

n = len(rows)
rows_n = (n + COLS - 1) // COLS
W = COLS * THUMB + (COLS + 1) * PAD
H = rows_n * (THUMB + LABEL_H) + (rows_n + 1) * PAD
sheet = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(sheet)

for i, r in enumerate(rows):
    col = i % COLS
    rn = i // COLS
    x = PAD + col * (THUMB + PAD)
    y = PAD + rn * (THUMB + LABEL_H + PAD)
    fn = os.path.join(DEST, r["filename"])
    try:
        im = Image.open(fn).convert("RGB")
        im.thumbnail((THUMB, THUMB), Image.LANCZOS)
        # 居中贴到 THUMB×THUMB 画格
        cell = Image.new("RGB", (THUMB, THUMB), (255, 255, 255))
        cell.paste(im, ((THUMB - im.width) // 2, (THUMB - im.height) // 2))
        sheet.paste(cell, (x, y))
    except Exception as e:
        draw.rectangle([x, y, x + THUMB, y + THUMB], fill=(220, 220, 220))
        draw.text((x + 4, y + THUMB // 2), f"ERR {r['filename']}", fill=(180, 0, 0), font=font)
    # 标签
    c = C_VER if r["status"] == "verified" else C_REV
    label = f"{r['brand']}{r['series']} g{r['gid']} {r['score']}"
    draw.rectangle([x, y + THUMB, x + THUMB, y + THUMB + LABEL_H], fill=c)
    draw.text((x + 4, y + THUMB + 2), label, fill=(255, 255, 255), font=font)

sheet.save(OUT, quality=88)
print(f"生成: {OUT}  尺寸 {W}x{H}  共 {n} 张 (verified {sum(1 for r in rows if r['status']=='verified')} / review {sum(1 for r in rows if r['status']=='review')})")
