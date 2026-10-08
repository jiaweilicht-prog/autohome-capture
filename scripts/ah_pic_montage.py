#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成已收集副驾侧图样的样张拼图，并按品牌输出覆盖缺口报告。"""
import os, csv, json
from PIL import Image, ImageDraw, ImageFont

ROOT = 'output/collection_us/verified'
OUT_SHEET = 'output/collection_us/contact_sheet.png'
META = 'output/clip_rank5/clip_ranked_filtered.csv'

US_BRANDS = {'福特','别克','林肯','凯迪拉克','雪佛兰','Jeep','特斯拉','克莱斯勒','GMC','道奇'}

# 1) 收集已收集图片
items = []  # (brand, series, path)
for brand in sorted(os.listdir(ROOT)):
    bd = os.path.join(ROOT, brand)
    if not os.path.isdir(bd):
        continue
    for series in sorted(os.listdir(bd)):
        sd = os.path.join(bd, series)
        if not os.path.isdir(sd):
            continue
        for fn in sorted(os.listdir(sd)):
            if fn.endswith('.jpg'):
                items.append((brand, series, os.path.join(sd, fn)))

print(f"已收集图片: {len(items)} 张")

# 2) 生成拼图 (6 列)
THUMB = 320
COLS = 6
PAD = 6
LABEL_H = 22
rows = (len(items) + COLS - 1) // COLS
sheet_w = COLS * (THUMB + PAD) + PAD
sheet_h = rows * (THUMB + LABEL_H + PAD) + PAD
sheet = Image.new('RGB', (sheet_w, sheet_h), (20, 20, 24))
draw = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype('/System/Library/Fonts/PingFang.ttc', 16)
except Exception:
    font = ImageFont.load_default()

for i, (brand, series, path) in enumerate(items):
    r, c = divmod(i, COLS)
    x = PAD + c * (THUMB + PAD)
    y = PAD + r * (THUMB + LABEL_H + PAD)
    try:
        im = Image.open(path).convert('RGB')
        im.thumbnail((THUMB, THUMB))
        sheet.paste(im, (x, y))
    except Exception:
        pass
    draw.rectangle([x, y + THUMB, x + THUMB, y + THUMB + LABEL_H], fill=(35, 35, 40))
    label = f"{brand} {series}"[:22]
    draw.text((x + 4, y + THUMB + 3), label, fill=(220, 220, 220), font=font)

sheet.save(OUT_SHEET)
print(f"拼图已保存: {OUT_SHEET} ({sheet_w}x{sheet_h})")

# 3) 覆盖缺口报告
models = {}
with open(META, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['brand'] in US_BRANDS:
            models[r['sid']] = (r['brand'], r['series'])
collected_sids = set()
for brand, series, path in items:
    # 从 sidecar 取 sid/gid
    jp = path + '.json'
    if os.path.exists(jp):
        with open(jp, encoding='utf-8') as f:
            d = json.load(f)
        collected_sids.add(d['sid'])

gap = {sid: v for sid, v in models.items() if sid not in collected_sids}
gap_by_brand = {}
for sid, (b, s) in gap.items():
    gap_by_brand.setdefault(b, []).append(s)

print(f"\n=== 覆盖报告 ===")
print(f"原始美系车型(去重): {len(models)}")
print(f"已有确认图车型: {len(collected_sids & set(models.keys()))}")
print(f"缺口车型: {len(gap)}")
for b in sorted(gap_by_brand, key=lambda x: -len(gap_by_brand[x])):
    print(f"  {b}: 缺 {len(gap_by_brand[b])} 款 -> " + ", ".join(sorted(gap_by_brand[b])[:12]) + (" ..." if len(gap_by_brand[b])>12 else ""))

# 写缺口 CSV
with open('output/collection_us/coverage_gap.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['brand','series','sid'])
    for sid, (b, s) in sorted(gap.items(), key=lambda x: (x[1][0], x[1][1])):
        w.writerow([b, s, sid])
print("\n缺口清单: output/collection_us/coverage_gap.csv")
