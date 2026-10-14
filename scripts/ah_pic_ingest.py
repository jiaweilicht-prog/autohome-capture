#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把补抓的新候选（pull_deep5 等）嵌入(整图+三段深度带)并入缓存与排名体系。
- 读取 parts/*.csv，剔除已在 rank5 主表的候选，按 cand 路径去重
- 嵌入并追加到 output/clip_rank3/emb_cache.npz 与 output/clip_rank5/reg_depth.npz
  （两个缓存保持同一键集合，fewshot_rank 的断言才不会炸）
- 输出增量行 output/clip_rank5/extra_rows.csv（与 rank5 主表同字段），供 fewshot_rank --extra 读取
"""
import argparse, csv, os
import numpy as np
import torch
import open_clip
from PIL import Image

BANDS = {'far': (0.00, 0.45), 'mid': (0.30, 0.72), 'near': (0.55, 1.00)}
CH = 16
EMB_DIM = 512


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--parts', nargs='+', required=True, help='pull 输出的 parts csv')
    ap.add_argument('--outdir', default='output/clip_rank5')
    ap.add_argument('--cache3', default='output/clip_rank3/emb_cache.npz')
    a = ap.parse_args()

    model, _, pre = open_clip.create_model_and_transforms(
        'ViT-B-32', pretrained='laion2b_s34b_b79k', device='cpu')
    model.eval()

    def emb_imgs(ims):
        with torch.no_grad():
            t = torch.stack([pre(im) for im in ims])
            e = model.encode_image(t)
            e = e / e.norm(dim=-1, keepdim=True)
        return e.cpu().numpy().astype(np.float32)

    def crop_band(im, band):
        W, H = im.size
        return im.crop((0, int(band[0] * H), W, int(band[1] * H)))

    # 主表已有 cand
    base = list(csv.DictReader(open(f'{a.outdir}/clip_ranked_filtered.csv', encoding='utf-8')))
    base_cands = {r['cand'] for r in base}
    new = []
    seen = set()
    for pf in a.parts:
        for r in csv.DictReader(open(pf, encoding='utf-8')):
            c = r.get('cand')
            if not c or c in base_cands or c in seen:
                continue
            if not os.path.exists(c):
                continue
            seen.add(c)
            new.append(r)
    print(f'新候选 {len(new)} 张（主表 {len(base_cands)}）', flush=True)
    if not new:
        print('无新增，退出'); return

    FIELDS = ['brand', 'series', 'sid', 'gid', 'imgid', 'specname', 'width', 'height', 'imgurl', 'cand']
    embs_img, embs_b = [], {b: [] for b in BANDS}
    for i in range(0, len(new), CH):
        chunk = new[i:i + CH]
        ims = []
        for r in chunk:
            try:
                ims.append(Image.open(r['cand']).convert('RGB'))
            except Exception:
                ims.append(Image.new('RGB', (224, 224)))
        embs_img.append(emb_imgs(ims))
        for b in BANDS:
            embs_b[b].append(emb_imgs([crop_band(im, BANDS[b]) for im in ims]))
        print(f'  嵌入 {min(i + CH, len(new))}/{len(new)}', flush=True)
    E_img = np.concatenate(embs_img)
    E_band = {b: np.concatenate(embs_b[b]) for b in BANDS}

    # 追加整图缓存
    z = np.load(a.cache3, allow_pickle=True)
    paths = list(z['paths'].tolist()) + [r['cand'] for r in new]
    embs = np.concatenate([z['embs'], E_img])
    np.savez_compressed(a.cache3, paths=np.array(paths, dtype=object), embs=embs)
    # 追加深度带缓存
    z2 = np.load(f'{a.outdir}/reg_depth.npz', allow_pickle=True)
    data = {'paths': np.array(list(z2['paths'].tolist()) + [r['cand'] for r in new], dtype=object)}
    for b in BANDS:
        data[b] = np.concatenate([z2[b], E_band[b]])
    np.savez_compressed(f'{a.outdir}/reg_depth.npz', **data)
    print('缓存已追加', flush=True)

    # 增量行（与旧 extra 合并去重）
    exp = f'{a.outdir}/extra_rows.csv'
    old = []
    if os.path.exists(exp):
        old = [r for r in csv.DictReader(open(exp, encoding='utf-8')) if r['cand'] not in seen]
    with open(exp, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction='ignore')
        w.writeheader()
        w.writerows(old + new)
    print(f'extra_rows.csv 共 {len(old) + len(new)} 行 -> {exp}', flush=True)


if __name__ == '__main__':
    main()
