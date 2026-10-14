#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把收集到的图片（verified + review）扁平化到一个不分品牌的目录，并合并 index.csv。

用法:
  python3 scripts/ah_pic_flatten.py --root output/collection_us
  python3 scripts/ah_pic_flatten.py --root output/collection_us --dest output/collection_us/all
"""
import argparse, csv, os, shutil

INDEX_COLS = ["filename", "brand", "series", "sid", "gid", "view", "score", "source_url", "status"]


def collect(src_root):
    rows = []
    for dp, _, fns in os.walk(src_root):
        for fn in fns:
            if fn.lower().endswith((".jpg", ".jpeg", ".png", ".json")):
                rows.append(os.path.join(dp, fn))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='output/collection_us', help='收集根目录（含 verified/ 与 review/）')
    ap.add_argument('--dest', default='', help='扁平化输出目录，默认 <root>/all')
    ap.add_argument('--clean', action='store_true', help='先清空 dest 再复制（避免 _2 重名副本）')
    a = ap.parse_args()

    root = a.root
    ver = os.path.join(root, "verified")
    rev = os.path.join(root, "review")
    dest = a.dest or os.path.join(root, "all")

    if a.clean and os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)

    copied = 0
    for label, src in (("verified", ver), ("review", rev)):
        if not os.path.isdir(src):
            continue
        for fp in sorted(collect(src)):
            dest_fp = os.path.join(dest, os.path.basename(fp))
            stem, ext = os.path.splitext(dest_fp)
            k = 1
            while os.path.exists(dest_fp):
                k += 1
                dest_fp = f"{stem}_{k}{ext}"
            shutil.copy2(fp, dest_fp)
            copied += 1

    index_rows = []
    for mf, st in ((os.path.join(root, "manifest.csv"), "verified"),
                   (os.path.join(root, "review_manifest.csv"), "review")):
        if not os.path.exists(mf):
            continue
        with open(mf, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                index_rows.append({
                    "filename": os.path.basename(row.get("filename", "")),
                    "brand": row.get("brand", ""), "series": row.get("series", ""),
                    "sid": row.get("sid", ""), "gid": row.get("gid", ""),
                    "view": row.get("view", ""), "score": row.get("score", ""),
                    "source_url": row.get("source_url", ""), "status": st,
                })

    with open(os.path.join(dest, "index.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_COLS)
        w.writeheader()
        w.writerows(index_rows)

    n_jpg = len([f for f in os.listdir(dest) if f.lower().endswith((".jpg", ".jpeg", ".png"))])
    n_json = len([f for f in os.listdir(dest) if f.lower().endswith(".json")])
    ver_n = sum(1 for r in index_rows if r["status"] == "verified")
    rev_n = sum(1 for r in index_rows if r["status"] == "review")
    print(f"复制文件总数: {copied}")
    print(f"图片: {n_jpg}  sidecar json: {n_json}")
    print(f"index.csv 行数: {len(index_rows)}  (verified {ver_n} / review {rev_n})")


if __name__ == '__main__':
    main()
