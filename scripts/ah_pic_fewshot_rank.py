#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Few-shot 对比重排：正样本锚点(用户打星115张+原2参考)做吸引项，易混负面样本(325张)做排斥项。
  pos_score = Σ w_k · max_<P> cos(cand_k, p_k)      (k = 整图/近/中/远 四视图)
  neg_score = Σ w_k · max_<N> cos(cand_k, n_k)
  score = pos_score − λ·neg_score ；neg_score > pos_score → review=1（疑似混淆，剔除出候选墙）
复用缓存：output/clip_rank3/emb_cache.npz(整图) + output/clip_rank5/reg_depth.npz(三带)，候选零重嵌。
输出：output/clip_rank6/clip_ranked_fewshot.csv + top_per_car.json
"""
import argparse, csv, json, os
import numpy as np
import torch
import open_clip
from PIL import Image

REF_EXTRA = ['output/ah_pic_ref/ref_target.jpg', 'output/ah_pic_ref/jeep_4072_gid57.jpg']
BANDS = {'far': (0.00, 0.45), 'mid': (0.30, 0.72), 'near': (0.55, 1.00)}
W = {'img': 0.20, 'near': 0.27, 'mid': 0.27, 'far': 0.26}
CH = 64


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--outdir', default='output/clip_rank6')
    ap.add_argument('--topk', type=int, default=3)
    ap.add_argument('--lam', type=float, default=0.6)
    ap.add_argument('--pos', default='output/fewshot/positives.csv', help='正样本池')
    ap.add_argument('--neg', default='output/fewshot/negatives.csv', help='负样本池')
    ap.add_argument('--cache-img', default='output/clip_rank3/emb_cache.npz', help='整图嵌入缓存')
    ap.add_argument('--cache-depth', default='output/clip_rank5/reg_depth.npz', help='三带嵌入缓存')
    ap.add_argument('--cands', default='output/clip_rank5/clip_ranked_filtered.csv', help='候选主表')
    ap.add_argument('--extra', default='output/clip_rank5/extra_rows.csv', help='补抓候选（可选）')
    ap.add_argument('--refs', default=','.join(REF_EXTRA), help='额外参考图，逗号分隔')
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
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
        W_, H_ = im.size
        return im.crop((0, int(band[0] * H_), W_, int(band[1] * H_)))

    def embed_set(paths):
        out = {k: [] for k in W}
        for i in range(0, len(paths), CH):
            ims = []
            for p in paths[i:i + CH]:
                try:
                    ims.append(Image.open(p).convert('RGB'))
                except Exception:
                    ims.append(Image.new('RGB', (224, 224)))
            out['img'].append(emb_imgs(ims))
            for b in BANDS:
                out[b].append(emb_imgs([crop_band(im, BANDS[b]) for im in ims]))
        return {k: np.concatenate(v) for k, v in out.items()}

    pos_rows = list(csv.DictReader(open(a.pos, encoding='utf-8')))
    neg_rows = list(csv.DictReader(open(a.neg, encoding='utf-8')))
    refs = [p for p in a.refs.split(',') if p.strip()]
    pos_paths = [r['local'] for r in pos_rows if r.get('local')] + refs
    neg_paths = [r['local'] for r in neg_rows if r.get('local')]
    print(f'正样本 {len(pos_paths)} | 负样本 {len(neg_paths)}，嵌入中…', flush=True)
    P = embed_set(pos_paths)
    N = embed_set(neg_paths)
    print('标注图嵌入完成', flush=True)

    # 候选缓存（两个缓存路径顺序不同，用字典映射）
    z = np.load(a.cache_img, allow_pickle=True)
    c_paths = list(z['paths'].tolist())
    C_img = np.stack(z['embs'])
    z2 = np.load(a.cache_depth, allow_pickle=True)
    d_paths = list(z2['paths'].tolist())
    C_band = {b: np.stack(z2[b]) for b in BANDS}
    assert set(c_paths) == set(d_paths), '两个缓存候选集合不一致'
    idx_of = {p: i for i, p in enumerate(d_paths)}
    order = [idx_of[p] for p in c_paths]        # c_paths 顺序 → depth 带行号
    C_band = {b: C_band[b][order] for b in BANDS}

    # 矩阵化相似度
    Sp = {'img': (C_img @ P['img'].T).max(axis=1)}
    Sn = {'img': (C_img @ N['img'].T).max(axis=1)}
    for b in BANDS:
        Sp[b] = (C_band[b] @ P[b].T).max(axis=1)
        Sn[b] = (C_band[b] @ N[b].T).max(axis=1)
    pos_score = sum(W[k] * Sp[k] for k in W)
    neg_score = sum(W[k] * Sn[k] for k in W)

    rows = list(csv.DictReader(open(a.cands, encoding='utf-8')))
    extra_p = a.extra
    if os.path.exists(extra_p):
        ex = list(csv.DictReader(open(extra_p, encoding='utf-8')))
        have = {r['cand'] for r in rows}
        add = [r for r in ex if r['cand'] not in have]
        rows = rows + add
        print(f'并入补抓候选 {len(add)} 行（总 {len(rows)}）', flush=True)
    pos_keys = {(str(r['sid']), str(r['gid'])) for r in pos_rows}   # 用户确认过的图永久豁免硬闸
    cache_idx = {p: i for i, p in enumerate(c_paths)}
    finals = []
    for r in rows:
        j = cache_idx.get(r['cand'])
        if j is None:      # 未成功嵌入的图跳过
            continue
        ps, ns = float(pos_score[j]), float(neg_score[j])
        r['pos_score'] = round(ps, 4)
        r['neg_score'] = round(ns, 4)
        r['score'] = round(ps - a.lam * ns, 4)
        r['review'] = 1 if (ns > ps and (str(r['sid']), str(r['gid'])) not in pos_keys) else 0
        finals.append(r)

    live = [r for r in finals if not r['review']]
    live.sort(key=lambda r: -r['score'])
    bycar = {}
    for r in live:
        bycar.setdefault(r['sid'], []).append(r)
    top = []
    for sid, rs in bycar.items():
        rs.sort(key=lambda r: -r['score'])
        top += rs[:a.topk]
    top.sort(key=lambda r: -r['score'])
    print(f'硬闸通过 {len(live)}/{len(finals)} | 覆盖车系 {len(bycar)} | top{a.topk} 合计 {len(top)}', flush=True)
    print('Top12:')
    for r in live[:12]:
        print(f"  {r['brand']}{r['series']} gid{r['gid']} pos={r['pos_score']} "
              f"neg={r['neg_score']} score={r['score']}", flush=True)

    cols = ['brand', 'series', 'sid', 'gid', 'imgid', 'specname', 'imgurl', 'cand',
            'pos_score', 'neg_score', 'review', 'score']
    with open(f'{a.outdir}/clip_ranked_fewshot.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(live)   # 只写硬闸通过行，防止 finalize 把 review=1 的图排进候选墙
    json.dump(top, open(f'{a.outdir}/top_per_car.json', 'w'), ensure_ascii=False, indent=1)
    print('done ->', a.outdir, flush=True)


if __name__ == '__main__':
    main()
