#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
缺口补全：为美系名单中「尚无确认图」的车型，各取 few-shot 得分最高的 1 张作为「待复核」候选。
复用 ah_pic_fewshot_rank.py 的评分逻辑（全缓存，零重嵌），仅改变输出：
  - 不送候选墙，而是按 sid 分组取 top1（忽略硬闸 review，因为本来就是待人工复核）
  - 下载到 output/collection_us/review/{品牌}/{车型}/
  - 生成 output/collection_us/contact_sheet_review.png 样张
"""
import argparse, csv, json, os, sys
import numpy as np
import torch
import open_clip
from PIL import Image

REF_EXTRA = ['output/ah_pic_ref/ref_target.jpg', 'output/ah_pic_ref/jeep_4072_gid57.jpg']
BANDS = {'far': (0.00, 0.45), 'mid': (0.30, 0.72), 'near': (0.55, 1.00)}
W = {'img': 0.20, 'near': 0.27, 'mid': 0.27, 'far': 0.26}
CH = 64

US_BRANDS = {'福特','别克','林肯','凯迪拉克','雪佛兰','Jeep','特斯拉','克莱斯勒','GMC','道奇',
             '福特(进口)','别克(进口)','雪佛兰(进口)','凯迪拉克(进口)','林肯(进口)',
             '道奇(进口)','克莱斯勒(进口)','Jeep(进口)','特斯拉(进口)'}

OUT = 'output/collection_us'


def norm_url(u):
    u = (u or '').strip()
    if not u:
        return ''
    if u.startswith('//'):
        return 'https:' + u
    if u.startswith('http'):
        return u
    return 'https://' + u


def download(url, dst, timeout=40):
    import urllib.request
    url = norm_url(url)
    if not url:
        return False
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://car.m.autohome.com.cn/'})
    try:
        data = urllib.request.urlopen(req, timeout=timeout).read()
        if len(data) < 2000:
            return False
        with open(dst, 'wb') as f:
            f.write(data)
        return True
    except Exception:
        return False


def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument('--lam', type=float, default=0.6)
    ap.add_argument('--limit', type=int, default=1, help='每款缺口车型取 top N')
    ap.add_argument('--out', default=OUT, help='输出根目录')
    ap.add_argument('--cands', default='output/clip_rank5/clip_ranked_filtered.csv', help='候选主表')
    ap.add_argument('--pos', default='output/fewshot/positives.csv', help='正样本池')
    ap.add_argument('--neg', default='output/fewshot/negatives.csv', help='负样本池')
    ap.add_argument('--cache-img', default='output/clip_rank3/emb_cache.npz', help='整图嵌入缓存')
    ap.add_argument('--cache-depth', default='output/clip_rank5/reg_depth.npz', help='三带嵌入缓存')
    ap.add_argument('--extra', default='output/clip_rank5/extra_rows.csv', help='补抓候选（可选）')
    ap.add_argument('--refs', default=','.join(REF_EXTRA), help='额外参考图，逗号分隔')
    a = ap.parse_args()
    OUT = a.out

    # ---- 1. 美系车型清单（sid -> 品牌/车型）----
    rows_all = list(csv.DictReader(open(a.cands, encoding='utf-8')))
    sid_meta = {}
    for r in rows_all:
        if r['brand'] in US_BRANDS:
            sid_meta[r['sid']] = (r['brand'], r['series'])

    # ---- 2. 已确认车型（manifest 的去重 sid）----
    confirmed_sid = set()
    if os.path.exists(f'{OUT}/manifest.csv'):
        with open(f'{OUT}/manifest.csv', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                confirmed_sid.add(r['sid'])

    gap_sids = [s for s in sid_meta if s not in confirmed_sid]
    print(f'美系车型总数: {len(sid_meta)} | 已确认: {len(confirmed_sid & set(sid_meta))} '
          f'| 缺口: {len(gap_sids)}', flush=True)

    # ---- 3. 评分（与 fewshot_rank 一致，全缓存）----
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

    z = np.load(a.cache_img, allow_pickle=True)
    c_paths = list(z['paths'].tolist())
    C_img = np.stack(z['embs'])
    z2 = np.load(a.cache_depth, allow_pickle=True)
    d_paths = list(z2['paths'].tolist())
    C_band = {b: np.stack(z2[b]) for b in BANDS}
    assert set(c_paths) == set(d_paths), '两个缓存候选集合不一致'
    idx_of = {p: i for i, p in enumerate(d_paths)}
    order = [idx_of[p] for p in c_paths]
    C_band = {b: C_band[b][order] for b in BANDS}

    Sp = {'img': (C_img @ P['img'].T).max(axis=1)}
    Sn = {'img': (C_img @ N['img'].T).max(axis=1)}
    for b in BANDS:
        Sp[b] = (C_band[b] @ P[b].T).max(axis=1)
        Sn[b] = (C_band[b] @ N[b].T).max(axis=1)
    pos_score = sum(W[k] * Sp[k] for k in W)
    neg_score = sum(W[k] * Sn[k] for k in W)

    extra_p = a.extra
    rows = rows_all
    if os.path.exists(extra_p):
        ex = list(csv.DictReader(open(extra_p, encoding='utf-8')))
        have = {r['cand'] for r in rows}
        add = [r for r in ex if r['cand'] not in have]
        rows = rows + add
    cache_idx = {p: i for i, p in enumerate(c_paths)}

    # ---- 4. 为每款缺口车型取 top N ----
    bycar = {}
    for r in rows:
        if r['sid'] not in gap_sids:
            continue
        j = cache_idx.get(r['cand'])
        if j is None:
            continue
        ps, ns = float(pos_score[j]), float(neg_score[j])
        r['score'] = round(ps - a.lam * ns, 4)
        r['pos_score'] = round(ps, 4)
        r['neg_score'] = round(ns, 4)
        bycar.setdefault(r['sid'], []).append(r)

    picks = []
    for sid, rs in bycar.items():
        rs.sort(key=lambda r: -r['score'])
        brand, series = sid_meta[sid]
        for r in rs[:a.limit]:
            picks.append({
                'sid': sid, 'gid': r['gid'], 'brand': brand, 'series': series,
                'imgurl': r.get('imgurl', ''), 'score': r['score'],
                'pos_score': r['pos_score'], 'neg_score': r['neg_score'],
            })
    picks.sort(key=lambda r: (r['brand'], r['series']))
    print(f'缺口候选待下载: {len(picks)} 张（{len(bycar)} 款车型）', flush=True)

    # ---- 5. 下载 ----
    os.makedirs(f'{OUT}/review', exist_ok=True)
    manifest_rows = []
    dl = 0
    for p in picks:
        brand_dir = f'{OUT}/review/{p["brand"]}'
        series_dir = f'{brand_dir}/{p["series"]}'
        os.makedirs(series_dir, exist_ok=True)
        fname = f'IMG_{p["brand"]}_{p["series"]}_PSV_REVIEW_01.jpg'
        dst = f'{series_dir}/{fname}'
        if os.path.exists(dst):
            ok = True
        else:
            ok = download(p['imgurl'], dst)
        if ok:
            dl += 1
        manifest_rows.append({
            'brand': p['brand'], 'series': p['series'], 'sid': p['sid'], 'gid': p['gid'],
            'filename': f'{p["brand"]}/{p["series"]}/{fname}', 'view': 'LHD副驾侧车外3/4内饰(待复核)',
            'score': p['score'], 'source_url': norm_url(p['imgurl']),
            'status': 'ok' if ok else 'fail',
        })
    with open(f'{OUT}/review_manifest.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['brand','series','sid','gid','filename','view','score','source_url','status'])
        w.writeheader()
        w.writerows(manifest_rows)
    print(f'下载完成: {dl}/{len(picks)} | review_manifest.csv 已写', flush=True)

    # ---- 6. 样张拼图 ----
    try:
        from PIL import ImageDraw
        build_montage(f'{OUT}/review', f'{OUT}/contact_sheet_review.png', manifest_rows)
    except Exception as e:
        print('拼图失败(不影响下载):', e, flush=True)


def build_montage(root, out_path, manifest_rows):
    files = []
    for r in manifest_rows:
        if r['status'] != 'ok':
            continue
        fp = os.path.join(root, r['filename'])
        if os.path.exists(fp):
            files.append((fp, r))
    if not files:
        return
    cols = 8
    thumb = 256
    rows_n = (len(files) + cols - 1) // cols
    pad = 6
    label_h = 18
    W_ = cols * thumb + (cols + 1) * pad
    H_ = rows_n * (thumb + label_h) + (rows_n + 1) * pad
    sheet = Image.new('RGB', (W_, H_), (20, 20, 24))
    d = ImageDraw.Draw(sheet)
    try:
        from PIL import ImageFont
        font = ImageFont.load_default()
    except Exception:
        font = None
    for i, (fp, r) in enumerate(files):
        c = i % cols
        rw = i // cols
        x = pad + c * (thumb + pad)
        y = pad + rw * (thumb + label_h + pad)
        try:
            im = Image.open(fp).convert('RGB')
            im = im.resize((thumb, thumb))
            sheet.paste(im, (x, y))
        except Exception:
            pass
        label = f'{r["brand"]} {r["series"]} {r["score"]}'
        if font:
            d.text((x, y + thumb + 2), label[:24], fill=(180, 220, 255), font=font)
    sheet.save(out_path)
    print(f'样张已生成: {out_path} ({len(files)} 张)', flush=True)


if __name__ == '__main__':
    main()
