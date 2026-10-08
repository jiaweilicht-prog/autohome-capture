#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
汽车之家 · 把 CLIP 排序结果落地成「每车系 topK 候选」交付物
============================================================================
输入 clip_ranked.csv（含 rank/brand/series/sid/gid/score/img_sim/txt_sim/imgurl），
- 每车系取 topK（默认 3），下载 400x0_ 中等清晰缩略图到 outdir/img/
- 生成 picklist.csv（品牌/车型/gid/分数/直链），供人工勾选
- 生成带标签的候选墙 outdir/sheets/s_*.jpg（8 列 x 5 行，单元 260px）

用法：
  python3 probe/ah_pic_finalize.py --rank output/clip_rank3/clip_ranked.csv \
      --topk 3 --outdir output/us_target_candidates
"""
import argparse, csv, json, math, os, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw

UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 '
      '(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1')


def fetch(url, ref, retries=3, timeout=30):
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': ref})
            return urllib.request.urlopen(req, timeout=timeout).read()
        except Exception:
            time.sleep(0.8)
    return b''


def sized(url, prefix='400x0_'):
    if url.startswith('//'):
        url = 'https:' + url
    head, base = url.rsplit('/', 1)
    return f'{head}/{prefix}{base}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rank', required=True)
    ap.add_argument('--topk', type=int, default=3)
    ap.add_argument('--prefix', default='400x0_')
    ap.add_argument('--outdir', required=True)
    ap.add_argument('--threads', type=int, default=8)
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.rank, encoding='utf-8')))
    bycar = {}
    for r in rows:
        bycar.setdefault(r['sid'], []).append(r)
    picks = []
    for sid, rs in bycar.items():
        rs.sort(key=lambda r: -float(r['score']))
        picks += rs[:a.topk]
    print(f'车系 {len(bycar)} | 取 top{a.topk} 共 {len(picks)} 张', flush=True)

    img_dir = f'{a.outdir}/img'
    os.makedirs(img_dir, exist_ok=True)

    def dl(m):
        ref = f'https://car.m.autohome.com.cn/pic/series/{m["sid"]}.html'
        fn = f'{img_dir}/{m["sid"]}_{int(m["gid"]):04d}.jpg'
        m['local'] = fn
        if os.path.exists(fn) and os.path.getsize(fn) > 3000:
            return m
        try:
            raw = fetch(sized(m['imgurl'], a.prefix), ref)
            if raw and len(raw) > 1000:
                open(fn, 'wb').write(raw)
        except Exception:
            pass
        return m

    with ThreadPoolExecutor(a.threads) as ex:
        picks = list(ex.map(dl, picks))
    ok = [m for m in picks if os.path.exists(m.get('local', '')) and os.path.getsize(m['local']) > 1000]
    print(f'下载成功 {len(ok)}/{len(picks)}', flush=True)

    with open(f'{a.outdir}/picklist.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['brand', 'series', 'sid', 'gid', 'score', 'img_sim', 'txt_sim', 'specname',
                    'thumb400', 'fullurl', 'local'])
        for m in ok:
            w.writerow([m['brand'], m['series'], m['sid'], m['gid'], m['score'],
                        float(m.get('img_sim', m.get('s_img', m.get('pos_score', 0)))),
                        m.get('txt_sim', m.get('s_mid', m.get('neg_score', ''))),
                        m.get('specname', ''),
                        sized(m['imgurl'], a.prefix),
                        m['imgurl'], m['local']])
    build_sheets(ok, f'{a.outdir}/sheets')


def build_sheets(items, outdir, cols=8, cell=260):
    os.makedirs(outdir, exist_ok=True)
    per = cols * 5
    for blk in range(math.ceil(len(items) / per)):
        sub = items[blk * per:(blk + 1) * per]
        rn = math.ceil(len(sub) / cols)
        cv = Image.new('RGB', (cols * (cell + 6) + 6, rn * (cell + 24) + 6), (22, 22, 25))
        dr = ImageDraw.Draw(cv)
        for k, m in enumerate(sub):
            try:
                im = Image.open(m['local']).convert('RGB')
            except Exception:
                continue
            im.thumbnail((cell, cell))
            r, c = divmod(k, cols)
            x, y = 6 + c * (cell + 6), 6 + r * (cell + 24)
            cv.paste(im, (x, y))
            dr.text((x + 2, y + cell + 6),
                    f"{m['brand']}{m['series']} gid{m['gid']} {m['score']}", fill=(150, 230, 255))
        out = f'{outdir}/s_{blk}.jpg'
        cv.save(out, quality=85)
        print('sheet', out, cv.size, flush=True)


if __name__ == '__main__':
    main()
