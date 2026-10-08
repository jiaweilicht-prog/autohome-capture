#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为待复核缺口候选生成样张拼图（读 review_manifest.csv，不重跑评分）。"""
import csv, os
from PIL import Image, ImageDraw, ImageFont

OUT = 'output/collection_us'

def main():
    rows = list(csv.DictReader(open(f'{OUT}/review_manifest.csv', encoding='utf-8')))
    files = []
    for r in rows:
        if r['status'] != 'ok':
            continue
        fp = os.path.join(OUT, 'review', r['filename'])
        if os.path.exists(fp):
            files.append((fp, r))
    if not files:
        print('无可用文件')
        return
    cols = 8
    thumb = 256
    pad = 6
    label_h = 20
    rows_n = (len(files) + cols - 1) // cols
    W_ = cols * thumb + (cols + 1) * pad
    H_ = rows_n * (thumb + label_h) + (rows_n + 1) * pad
    sheet = Image.new('RGB', (W_, H_), (20, 20, 24))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    for i, (fp, r) in enumerate(files):
        c = i % cols
        rw = i // cols
        x = pad + c * (thumb + pad)
        y = pad + rw * (thumb + label_h + pad)
        try:
            im = Image.open(fp).convert('RGB').resize((thumb, thumb))
            sheet.paste(im, (x, y))
        except Exception:
            pass
        label = f'{r["brand"]} {r["series"]} {r["score"]}'
        if font:
            d.text((x, y + thumb + 2), label[:26], fill=(180, 220, 255), font=font)
    sheet.save(f'{OUT}/contact_sheet_review.png')
    print(f'样张已生成: {OUT}/contact_sheet_review.png ({len(files)} 张)')

if __name__ == '__main__':
    main()
