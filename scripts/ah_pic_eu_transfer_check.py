#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 美系 few-shot 池能否迁移到欧系：在 EU pilot 候选上跑同一套 对比打分，输出 top 供肉眼核验。"""
import csv, glob, os
import numpy as np
import torch
import open_clip
from PIL import Image

BANDS = {'far': (0.00, 0.45), 'mid': (0.30, 0.72), 'near': (0.55, 1.00)}
W = {'img': 0.20, 'near': 0.27, 'mid': 0.27, 'far': 0.26}
CH = 64
REF_EXTRA = ['output/ah_pic_ref/ref_target.jpg', 'output/ah_pic_ref/jeep_4072_gid57.jpg']

model, _, pre = open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k', device='cpu')
model.eval()

def emb_imgs(ims):
    with torch.no_grad():
        t = torch.stack([pre(im) for im in ims])
        e = model.encode_image(t); e = e / e.norm(dim=-1, keepdim=True)
    return e.cpu().numpy().astype(np.float32)

def crop_band(im, band):
    W_, H_ = im.size
    return im.crop((0, int(band[0]*H_), W_, int(band[1]*H_)))

def embed_set(paths):
    out = {k: [] for k in W}
    miss = 0
    for i in range(0, len(paths), CH):
        ims = []
        for p in paths[i:i+CH]:
            try:
                ims.append(Image.open(p).convert('RGB'))
            except Exception:
                ims.append(Image.new('RGB', (224, 224))); miss += 1
        out['img'].append(emb_imgs(ims))
        for b in BANDS:
            out[b].append(emb_imgs([crop_band(im, BANDS[b]) for im in ims]))
    print(f'  嵌入 {len(paths)} 张 (缺失 {miss})', flush=True)
    return {k: np.concatenate(v) for k, v in out.items()}

# 1) 美系池
pos_rows = list(csv.DictReader(open('output/fewshot/positives.csv', encoding='utf-8')))
neg_rows = list(csv.DictReader(open('output/fewshot/negatives.csv', encoding='utf-8')))
pos_paths = [r['local'] for r in pos_rows if r.get('local')] + REF_EXTRA
neg_paths = [r['local'] for r in neg_rows if r.get('local')]
print(f'正样本 {len(pos_paths)} | 负样本 {len(neg_paths)}', flush=True)
P = embed_set(pos_paths)
N = embed_set(neg_paths)

# 2) EU pilot 候选（parts/*.csv -> cand 路径）
eu_cands = []
for fn in sorted(glob.glob('output/pull_eu_pilot/parts/*.csv')):
    for r in csv.DictReader(open(fn, encoding='utf-8')):
        if r.get('cand') and os.path.exists(r['cand']):
            eu_cands.append(r)
print(f'EU pilot 候选 {len(eu_cands)}', flush=True)
eu_paths = [r['cand'] for r in eu_cands]
E = embed_set(eu_paths)

# 3) 对比打分
Sp = {k: (E[k] @ P[k].T).max(axis=1) for k in W}
Sn = {k: (E[k] @ N[k].T).max(axis=1) for k in W}
pos_score = sum(W[k]*Sp[k] for k in W)
neg_score = sum(W[k]*Sn[k] for k in W)
lam = 0.6
score = pos_score - lam*neg_score

order = np.argsort(-score)
print('\n=== EU pilot top 24 (按 score 降序) ===')
for i in order[:24]:
    r = eu_cands[i]
    print(f"  {r['brand']}{r['series']} sid{r['sid']} gid{r['gid']} "
          f"pos={pos_score[i]:.3f} neg={neg_score[i]:.3f} score={score[i]:.3f} -> {r['cand']}")
