#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
下载种子校准池（seed_pool/manifest.csv 里列出的 20 张图）。

用途：
  - 新机器冷启动时，先跑本脚本拿到 10 正 + 10 负校准样本，
    让「看图判定」节点有参照标准，不必从零攒样本。
  - 图片 URL 失效时，更新 manifest.csv 后重跑即可。

用法：
  python3 scripts/fetch_seed_pool.py --manifest seed_pool/manifest.csv
"""
import argparse, csv, os, sys, time, urllib.request

UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 '
      '(KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1')


def norm(url):
    if url.startswith('//'):
        return 'https:' + url
    return url


def fetch(url, ref, retries=3, timeout=30):
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': ref})
            return urllib.request.urlopen(req, timeout=timeout).read()
        except Exception:
            time.sleep(0.8)
    return b''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', default='seed_pool/manifest.csv')
    ap.add_argument('--root', default='seed_pool', help='输出根目录')
    ap.add_argument('--min-bytes', type=int, default=2000, help='小于此体积视为失败')
    a = ap.parse_args()

    rows = list(csv.DictReader(open(a.manifest, encoding='utf-8')))
    os.makedirs(os.path.join(a.root, 'pos'), exist_ok=True)
    os.makedirs(os.path.join(a.root, 'neg'), exist_ok=True)

    ok = fail = 0
    for r in rows:
        rel = r['file']
        out = os.path.join(a.root, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        url = norm(r['source_url'])
        if os.path.exists(out) and os.path.getsize(out) >= a.min_bytes:
            print(f'  跳过(已有) {rel}')
            ok += 1
            continue
        ref = f'https://car.m.autohome.com.cn/pic/series/{r["sid"]}.html'
        raw = fetch(url, ref)
        if len(raw) < a.min_bytes:
            print(f'  失败 {rel}  ({len(raw)} bytes)  {url}')
            fail += 1
            continue
        open(out, 'wb').write(raw)
        print(f'  下载 {rel}  {len(raw)//1024}KB')
        ok += 1

    print(f'\n完成: 成功 {ok} / 失败 {fail}')
    if fail:
        print('失败的图请在 manifest.csv 里换 URL 后重跑。')
        sys.exit(1)


if __name__ == '__main__':
    main()
