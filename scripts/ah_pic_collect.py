#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ah_pic_collect.py — 副驾侧车外3/4内饰图 正式收集脚本

读取人工确认的 positive 池，下载全分辨率原图，按「品牌/车型」归档，
套 DDGS 命名 IMG_{品牌}_{车型}_PSV_{序号}.jpg，并为每张图写 sidecar JSON，
最后生成总清单 manifest.csv。
"""
import os, sys, csv, json, time, argparse, threading
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
REF = "https://car.m.autohome.com.cn/"

VIEW_CODE = "PSV"
VIEW_LABEL = "LHD副驾侧车外3/4内饰"

US_BRANDS = {'福特','别克','林肯','凯迪拉克','雪佛兰','Jeep','特斯拉','克莱斯勒',
             'GMC','道奇','福特(进口)','别克(进口)','雪佛兰(进口)','凯迪拉克(进口)','林肯(进口)'}

def safe_name(s):
    return "".join(c for c in s if c not in '/\\:*?"<>|').strip()

def norm_url(u):
    u = (u or '').strip()
    if u.startswith('//'):
        return 'https:' + u
    return u

def fetch(url, timeout=45):
    req = Request(url, headers={'User-Agent': UA, 'Referer': REF})
    return urlopen(req, timeout=timeout).read()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pos', default='output/fewshot/positives.csv')
    ap.add_argument('--meta', default='output/clip_rank5/clip_ranked_filtered.csv')
    ap.add_argument('--out', default='output/collection_us/verified')
    ap.add_argument('--manifest', default='output/collection_us/manifest.csv')
    ap.add_argument('--threads', type=int, default=8)
    args = ap.parse_args()

    # 反向元数据：补全品牌/车型 + 找回源 URL
    meta = {}
    src_map = {}
    with open(args.meta, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            meta[(r['sid'], r['gid'])] = (r['brand'], r['series'])
            u = (r.get('imgurl') or '').strip()
            if u:
                src_map[(r['sid'], r['gid'])] = u

    rows = []
    seen = set()
    skipped = []
    with open(args.pos, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            sid, gid = r['sid'], r['gid']
            key = (sid, gid)
            if key in seen:
                continue
            brand = (r.get('brand') or '').strip()
            series = (r.get('series') or '').strip()
            if (not brand or not series) and key in meta:
                brand, series = meta[key]
            if not brand:
                brand = '未知'
            if not series:
                series = f'gid{gid}'
            fullurl = norm_url(r.get('fullurl'))
            local = (r.get('local') or '').strip()
            # 缺 fullurl/local 时，从 clip_rank5 找回源 URL
            if not fullurl and key in src_map:
                fullurl = norm_url(src_map[key])
            if brand not in US_BRANDS and brand != '未知':
                skipped.append((key, '非美系', brand))
                continue
            if not fullurl and not local:
                skipped.append((key, '无来源', brand))
                continue
            seen.add(key)
            rows.append({'sid': sid, 'gid': gid, 'brand': brand, 'series': series,
                         'fullurl': fullurl, 'local': local, 'score': r.get('score', '')})

    print(f"[collect] 待收集美系确认图: {len(rows)} 张  (跳过 {len(skipped)} 条)", flush=True)
    for k, reason, br in skipped:
        print(f"   跳过 {reason}: sid={k[0]} gid={k[1]} brand={br}", flush=True)

    os.makedirs(args.out, exist_ok=True)
    seq_map = {}
    lock = threading.Lock()
    manifest = []
    stats = {'ok': 0, 'fail': 0, 'fallback': 0}
    by_brand = {}

    def worker(item):
        sid, gid, brand, series = item['sid'], item['gid'], item['brand'], item['series']
        fullurl, local, score = item['fullurl'], item['local'], item['score']
        d = os.path.join(args.out, safe_name(brand), safe_name(series))
        os.makedirs(d, exist_ok=True)
        with lock:
            k = (brand, series)
            seq_map[k] = seq_map.get(k, 0) + 1
            seq = seq_map[k]
        fname = f"IMG_{safe_name(brand)}_{safe_name(series)}_{VIEW_CODE}_{seq:02d}.jpg"
        fpath = os.path.join(d, fname)
        status = 'ok'
        data = None
        src = 'fullurl'
        if fullurl:
            try:
                data = fetch(fullurl)
            except Exception:
                data = None
        if not data and local and os.path.exists(local):
            try:
                with open(local, 'rb') as fh:
                    data = fh.read()
                status = 'fallback'
                src = 'local'
            except Exception:
                data = None
        if not data:
            with lock:
                stats['fail'] += 1
            print(f"  ✗ 下载失败 sid={sid} gid={gid} ({brand} {series})", flush=True)
            return
        with open(fpath, 'wb') as fh:
            fh.write(data)
        sc = {'brand': brand, 'series': series, 'sid': sid, 'gid': gid,
              'view': VIEW_LABEL, 'view_code': VIEW_CODE, 'filename': fname,
              'source_url': fullurl, 'source_thumb': local, 'fewshot_score': score,
              'confidence': 'verified', 'src': src, 'collected_at': time.strftime('%Y-%m-%d')}
        with open(fpath + '.json', 'w', encoding='utf-8') as fh:
            json.dump(sc, fh, ensure_ascii=False, indent=2)
        with lock:
            stats['ok' if status == 'ok' else 'fallback'] += 1
            by_brand.setdefault(brand, 0)
            by_brand[brand] += 1
            manifest.append({'brand': brand, 'series': series, 'sid': sid, 'gid': gid,
                             'filename': os.path.relpath(fpath, args.out), 'view': VIEW_LABEL,
                             'score': score, 'source_url': fullurl, 'status': status})
        print(f"  ✓ {fname} ({len(data)//1024}KB, {status})", flush=True)

    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        list(ex.map(worker, rows))

    os.makedirs(os.path.dirname(args.manifest) or '.', exist_ok=True)
    with open(args.manifest, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['brand','series','sid','gid','filename','view','score','source_url','status'])
        w.writeheader()
        for m in manifest:
            w.writerow(m)

    print(f"\n[collect] 完成: 成功 {stats['ok']} / fallback {stats['fallback']} / 失败 {stats['fail']}", flush=True)
    print(f"[collect] 按品牌:", flush=True)
    for b, c in sorted(by_brand.items(), key=lambda x: -x[1]):
        print(f"    {b}: {c}", flush=True)
    print(f"[collect] 清单: {args.manifest}", flush=True)

if __name__ == '__main__':
    main()
