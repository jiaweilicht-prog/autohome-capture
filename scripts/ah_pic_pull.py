#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
汽车之家 · 座椅分类 轻量抓取（供 CLIP 语义精排）
============================================================================
设计要点（吸取上一版教训）：
  - 只抓每车系「最近 N 页」（默认 6 页=216 张），不扫全量，控制带宽/时间。
  - 下载后统一缩放到 maxpx 并重编码为小 JPEG 存盘 —— 无论 CDN 是否忽略尺寸前缀，落盘都极小(~5KB)。
  - **不做 pHash 预筛**：实测该判据在跨车型上近乎随机(50% 通过)，无区分度；改由 CLIP 精排全量候选。
  - 每车系处理完立即写 {outdir}/parts/{sid}.csv，可断点续跑（重跑自动跳过已完成车系）。
  - 结束时合并所有 parts → {outdir}/items.csv。

依赖：Pillow（默认 venv 或 /tmp/clipvenv 均可）。
用法：
  python3 probe/ah_pic_pull.py --targets /tmp/us_part_0.json --classid 3 --pages 6 \
      --prefix 240x0_ --maxpx 160 --threads 6 --outdir output/pull_part0
"""
import argparse, csv, io, json, os, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 '
      '(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1')

FIELDS = ['brand', 'series', 'sid', 'gid', 'imgid', 'specname', 'width', 'height', 'imgurl', 'cand']


def fetch(url, ref, retries=3, timeout=30):
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': ref})
            return urllib.request.urlopen(req, timeout=timeout).read()
        except Exception:
            time.sleep(0.8)
    return b''


def sized(url, prefix):
    if url.startswith('//'):
        url = 'https:' + url
    head, base = url.rsplit('/', 1)
    return f'{head}/{prefix}{base}'


def run_model(t, a, parts_dir, cand_dir):
    sid = t['seriesId']
    brand = t.get('brandCn', '')
    name = t.get('seriesName', str(sid))
    pf = f'{parts_dir}/{sid}.csv'
    if os.path.exists(pf) and not a.force:
        return 'skip'
    ref = f'https://car.m.autohome.com.cn/pic/series/{sid}.html'
    items, p = [], 1
    while p <= a.pages:
        try:
            d = json.loads(fetch(
                f'https://car.m.autohome.com.cn/pic/getpiclist?seriesid={sid}&specid=0'
                f'&classid={a.classid}&pageindex={p}&pagesize=36', ref).decode('utf-8', 'ignore'))
            r = d['result']
        except Exception:
            break
        pl = r.get('piclist', [])
        if not pl:
            break
        items += pl
        if p >= r.get('pagecount', 1):
            break
        p += 1

    def work(kv):
        idx, it = kv
        cp = f'{cand_dir}/{sid}_{idx:04d}.jpg'
        try:
            raw = fetch(sized(it['imgurl'], a.prefix), ref)
            if not raw or len(raw) < 300:
                return None
            im = Image.open(io.BytesIO(raw)).convert('RGB')
            if a.maxpx:
                im.thumbnail((a.maxpx, a.maxpx))
            im.save(cp, 'JPEG', quality=a.quality)
            return {'brand': brand, 'series': name, 'sid': sid, 'gid': idx, 'imgid': it.get('id'),
                    'specname': it.get('specname', ''), 'width': it.get('width', ''),
                    'height': it.get('height', ''), 'imgurl': it['imgurl'], 'cand': cp}
        except Exception:
            return None

    rows = []
    with ThreadPoolExecutor(a.threads) as ex:
        for res in ex.map(work, list(enumerate(items))):
            if res:
                rows.append(res)
    with open(pf, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return f'{len(items)}图/{len(rows)}存'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--targets', required=True)
    ap.add_argument('--classid', default='3')
    ap.add_argument('--pages', type=int, default=6)
    ap.add_argument('--prefix', default='240x0_')
    ap.add_argument('--maxpx', type=int, default=160)
    ap.add_argument('--quality', type=int, default=72)
    ap.add_argument('--threads', type=int, default=6)
    ap.add_argument('--outdir', required=True)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()

    targets = json.load(open(a.targets))
    if a.limit:
        targets = targets[:a.limit]
    parts_dir = f'{a.outdir}/parts'
    cand_dir = f'{a.outdir}/cand'
    os.makedirs(parts_dir, exist_ok=True)
    os.makedirs(cand_dir, exist_ok=True)

    for i, t in enumerate(targets):
        try:
            r = run_model(t, a, parts_dir, cand_dir)
        except Exception as e:
            r = f'ERR {e}'
        print(f'[{i+1}/{len(targets)}] {t.get("brandCn","")} {t.get("seriesName","")} '
              f'({t.get("seriesId")}) {r}', flush=True)

    out = f'{a.outdir}/items.csv'
    n = 0
    with open(out, 'w', newline='', encoding='utf-8') as fo:
        w = csv.DictWriter(fo, fieldnames=FIELDS)
        w.writeheader()
        for fn in sorted(os.listdir(parts_dir)):
            if not fn.endswith('.csv'):
                continue
            for row in csv.DictReader(open(f'{parts_dir}/{fn}', encoding='utf-8')):
                w.writerow(row)
                n += 1
    print(f'merged {n} rows -> {out}', flush=True)


if __name__ == '__main__':
    main()
