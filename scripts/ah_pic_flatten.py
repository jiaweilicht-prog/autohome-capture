#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把美系所有图片(verified + review)扁平化到一个不分品牌的目录，并合并 index.csv。
用法: python ah_pic_flatten.py
"""
import os, shutil, csv, json

ROOT = "/Users/licht/WorkBuddy/数据抓取/output/collection_us"
VER = os.path.join(ROOT, "verified")
REV = os.path.join(ROOT, "review")
DEST = os.path.join(ROOT, "all")
os.makedirs(DEST, exist_ok=True)

# 1) 复制所有 jpg + json，处理碰撞
def collect(src_root):
    rows = []
    for dp, _, fns in os.walk(src_root):
        for fn in fns:
            if fn.lower().endswith((".jpg", ".jpeg", ".png", ".json")):
                rows.append(os.path.join(dp, fn))
    return rows

copied = 0
for label in ("verified", "review"):
    src = VER if label == "verified" else REV
    for fp in sorted(collect(src)):
        base = os.path.basename(fp)
        dest_fp = os.path.join(DEST, base)
        # 碰撞处理：追加 _2/_3
        k = 1
        stem, ext = os.path.splitext(dest_fp)
        while os.path.exists(dest_fp):
            k += 1
            dest_fp = f"{stem}_{k}{ext}"
        shutil.copy2(fp, dest_fp)
        copied += 1

# 2) 合并两个 manifest 成 index.csv
index_cols = ["filename", "brand", "series", "sid", "gid", "view", "score", "source_url", "status"]
index_rows = []
for mf, st in ((os.path.join(ROOT, "manifest.csv"), "verified"),
               (os.path.join(ROOT, "review_manifest.csv"), "review")):
    if not os.path.exists(mf):
        continue
    with open(mf, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            raw = row.get("filename", "")
            base = os.path.basename(raw)  # 扁平化后只保留文件名
            index_rows.append({
                "filename": base,
                "brand": row.get("brand", ""),
                "series": row.get("series", ""),
                "sid": row.get("sid", ""),
                "gid": row.get("gid", ""),
                "view": row.get("view", ""),
                "score": row.get("score", ""),
                "source_url": row.get("source_url", ""),
                "status": st,
            })

with open(os.path.join(DEST, "index.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=index_cols)
    w.writeheader()
    w.writerows(index_rows)

# 3) 统计
n_jpg = len([f for f in os.listdir(DEST) if f.lower().endswith((".jpg", ".jpeg", ".png"))])
n_json = len([f for f in os.listdir(DEST) if f.lower().endswith(".json")])
ver = sum(1 for r in index_rows if r["status"] == "verified")
rev = sum(1 for r in index_rows if r["status"] == "review")
print(f"复制文件总数: {copied}")
print(f"all/ 内 图片: {n_jpg}  侧车json: {n_json}")
print(f"index.csv 行数: {len(index_rows)}  (verified {ver} / review {rev})")
