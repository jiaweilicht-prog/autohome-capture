#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成一张合并全部图片的联络图（verified 在前，review 在后）。

用法:
  python3 scripts/ah_pic_montage_all.py --root output/collection_us
"""
import argparse, csv, os
from PIL import Image, ImageDraw, ImageFont

THUMB = 300
COLS = 8
PAD = 6
LABEL_H = 22
C_VER = (34, 139, 34)
C_REV = (200, 120, 0)
BG = (245, 245, 245)

FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def load_font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, 16)
            except Exception:
                pass
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='output/collection_us', help='收集根目录')
    ap.add_argument('--dest', default='', help='扁平化目录，默认 <root>/all')
    ap.add_argument('--out', default='', help='输出图，默认 <root>/contact_sheet_all.png')
    a = ap.parse_args()

    root = a.root
    dest = a.dest or os.path.join(root, "all")
    out = a.out or os.path.join(root, "contact_sheet_all.png")

    idx = os.path.join(dest, "index.csv")
    if not os.path.exists(idx):
        print(f"找不到 {idx}（先跑 ah_pic_flatten.py）")
        return
    with open(idx, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rank = {"verified": 0, "review": 1}
    rows.sort(key=lambda r: (rank.get(r["status"], 2), r["brand"], r["series"], r["gid"]))

    font = load_font()
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
        fn = os.path.join(dest, r["filename"])
        try:
            im = Image.open(fn).convert("RGB")
            im.thumbnail((THUMB, THUMB), Image.LANCZOS)
            cell = Image.new("RGB", (THUMB, THUMB), (255, 255, 255))
            cell.paste(im, ((THUMB - im.width) // 2, (THUMB - im.height) // 2))
            sheet.paste(cell, (x, y))
        except Exception:
            draw.rectangle([x, y, x + THUMB, y + THUMB], fill=(220, 220, 220))
            draw.text((x + 4, y + THUMB // 2), f"ERR {r['filename']}", fill=(180, 0, 0), font=font)
        c = C_VER if r["status"] == "verified" else C_REV
        label = f"{r['brand']}{r['series']} g{r['gid']} {r['score']}"
        draw.rectangle([x, y + THUMB, x + THUMB, y + THUMB + LABEL_H], fill=c)
        draw.text((x + 4, y + THUMB + 2), label, fill=(255, 255, 255), font=font)

    sheet.save(out, quality=88)
    ver_n = sum(1 for r in rows if r["status"] == "verified")
    rev_n = sum(1 for r in rows if r["status"] == "review")
    print(f"生成: {out}  尺寸 {W}x{H}  共 {n} 张 (verified {ver_n} / review {rev_n})")


if __name__ == '__main__':
    main()
