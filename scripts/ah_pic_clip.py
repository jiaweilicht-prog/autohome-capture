#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
汽车之家 · CLIP 语义精排（在 ah_pic_pull.py 的候选上运行）
============================================================================
- OpenCLIP ViT-B-32：对「参考图」与「文本提示」分别编码，与候选缩略图算余弦相似度。
- 综合分 score = (img_sim + txt_sim)/2；img_sim 抓「同款构图」，txt_sim 抓「语义场景」。
- 每组车系取 topK → 逐车给出最像「副驾开门看 IP+console」的几张。
- 输出 clip_ranked.csv / top_per_car.json / top_sheet_*.jpg / global_sheet_*.jpg。
- 嵌入结果缓存到 {outdir}/emb_cache.npz，可被 SIGKILL 后断点续跑。

依赖：torch + open_clip + numpy + Pillow（/tmp/clipvenv）。
用法：
  /tmp/clipvenv/bin/python probe/ah_pic_clip.py \
    --cands output/pull_part0/items.csv ... \
    --refs output/ah_pic_ref/ref_target.jpg output/ah_pic_ref/jeep_4072_gid57.jpg \
    --outdir output/clip_rank --topk 6
"""
import argparse, csv, json, math, os
import numpy as np
import torch
import open_clip
from PIL import Image, ImageDraw

DEFAULT_TEXT = ('a car interior photographed through the open front passenger door, '
                'clearly showing the center console and the dashboard')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cands', nargs='+', required=True)
    ap.add_argument('--refs', nargs='+', required=True)
    ap.add_argument('--outdir', required=True)
    ap.add_argument('--topk', type=int, default=6)
    ap.add_argument('--text', default=DEFAULT_TEXT)
    ap.add_argument('--model', default='ViT-B-32')
    ap.add_argument('--pretrained', default='laion2b_s34b_b79k')
    a = ap.parse_args()

    os.makedirs(a.outdir, exist_ok=True)
    model, _, pre = open_clip.create_model_and_transforms(a.model, pretrained=a.pretrained, device='cpu')
    model.eval()

    def emb_img(path):
        im = Image.open(path).convert('RGB')
        with torch.no_grad():
            t = pre(im).unsqueeze(0)
            e = model.encode_image(t)
            e = e / e.norm(dim=-1, keepdim=True)
        return e[0].numpy().astype(np.float32)

    def emb_txt(s):
        with torch.no_grad():
            t = open_clip.tokenize([s])
            e = model.encode_text(t)
            e = e / e.norm(dim=-1, keepdim=True)
        return e[0].numpy().astype(np.float32)

    refes = [emb_img(p) for p in a.refs]
    te = emb_txt(a.text) if a.text else None

    rows = []
    for cf in a.cands:
        if not os.path.exists(cf):
            print('  [warn] 缺文件', cf)
            continue
        rows += list(csv.DictReader(open(cf, encoding='utf-8')))
    print('候选总数', len(rows), flush=True)

    cache_path = f'{a.outdir}/emb_cache.npz'
    cache = {}
    if os.path.exists(cache_path):
        try:
            z = np.load(cache_path, allow_pickle=True)
            for k, v in zip(z['paths'].tolist(), z['embs']):
                cache[k] = v
            print('缓存命中', len(cache), flush=True)
        except Exception as e:
            print('缓存读取失败', e)

    def save_cache():
        paths = list(cache.keys())
        np.savez_compressed(cache_path, paths=np.array(paths, dtype=object),
                            embs=np.stack([cache[p] for p in paths]))

    new = 0
    for i, r in enumerate(rows):
        p = r['cand']
        if p in cache:
            continue
        try:
            cache[p] = emb_img(p)
            new += 1
        except Exception:
            continue
        if new % 500 == 0:
            save_cache()
            print(f'  嵌入 {len(cache)}/{len(rows)}', flush=True)
    save_cache()
    print('嵌入完成 新增', new, '缓存', len(cache), flush=True)

    ok = []
    for r in rows:
        e = cache.get(r['cand'])
        if e is None:
            continue
        imgs = max(float(np.dot(e, re)) for re in refes)
        r['img_sim'] = round(imgs, 4)
        if te is not None:
            ts = float(np.dot(e, te))
            r['txt_sim'] = round(ts, 4)
            r['score'] = round((imgs + ts) / 2, 4)
        else:
            r['txt_sim'] = ''
            r['score'] = round(imgs, 4)
        ok.append(r)

    ok.sort(key=lambda r: -float(r['score']))
    with open(f'{a.outdir}/clip_ranked.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(ok[0].keys()))
        w.writeheader()
        w.writerows(ok)
    print('top10:')
    for r in ok[:10]:
        print('  ', r['brand'], r['series'], 'gid', r['gid'], 'score', r['score'],
              'img', r['img_sim'], 'txt', r['txt_sim'], flush=True)

    bycar = {}
    for r in ok:
        bycar.setdefault(r['sid'], []).append(r)
    top = []
    for sid, rs in bycar.items():
        rs.sort(key=lambda r: -float(r['score']))
        top += rs[:a.topk]
    top.sort(key=lambda r: -float(r['score']))
    json.dump(top, open(f'{a.outdir}/top_per_car.json', 'w'), ensure_ascii=False, indent=1)
    print(f'覆盖车系 {len(bycar)} | per-car top{a.topk} 合计 {len(top)}', flush=True)

    build_sheets(top, f'{a.outdir}/percar', cols=6, cell=300)
    build_sheets(ok[:120], f'{a.outdir}/global', cols=6, cell=300)


def build_sheets(items, outdir, cols=6, cell=300):
    os.makedirs(outdir, exist_ok=True)
    per = cols * 4
    for blk in range(math.ceil(len(items) / per)):
        sub = items[blk * per:(blk + 1) * per]
        rn = math.ceil(len(sub) / cols)
        cv = Image.new('RGB', (cols * (cell + 6) + 6, rn * (cell + 24) + 6), (22, 22, 25))
        dr = ImageDraw.Draw(cv)
        for k, m in enumerate(sub):
            try:
                im = Image.open(m['cand']).convert('RGB')
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
