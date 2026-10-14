#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
判定节点 · 回灌（A 方案）

把视觉判定的结果 judge_results.csv 合并回「正负样本池」，形成自动收敛循环：
    判定结果 POS → 进 positives.csv（若原在 negatives 则提升）
    判定结果 NEG → 进 negatives.csv（若原在 positives 则降级）
跨版本合并唯一键 = (sid, gid)，禁用行号。

用法：
  python3 scripts/ah_pic_judge_apply.py \
      --results output/judge/judge_results.csv \
      --pos output/fewshot/positives.csv \
      --neg output/fewshot/negatives.csv \
      --meta output/clip_rank6/clip_ranked.csv
"""
import argparse, csv, os, shutil, sys, time

FIELDS = ['shot', 'blk', 'row', 'col', 'idx', 'brand', 'series', 'sid', 'gid',
          'score', 'local', 'fullurl']


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [dict(r) for r in csv.DictReader(f)]


def load_meta(path):
    """可选：从候选表补齐 brand/series/score/local/fullurl"""
    m = {}
    if not path or not os.path.exists(path):
        return m
    with open(path, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            m[(str(r.get('sid', '')), str(r.get('gid', '')))] = r
    return m


def key(r):
    return (str(r.get('sid', '')), str(r.get('gid', '')))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--results', default='output/judge/judge_results.csv')
    ap.add_argument('--pos', default='output/fewshot/positives.csv')
    ap.add_argument('--neg', default='output/fewshot/negatives.csv')
    ap.add_argument('--meta', default='', help='可选：候选表，用于补齐字段')
    ap.add_argument('--backup-dir', default='output/fewshot')
    ap.add_argument('--no-backup', action='store_true')
    a = ap.parse_args()

    if not os.path.exists(a.results):
        print(f'找不到判定结果表 {a.results}'); sys.exit(1)

    pos = load(a.pos)
    neg = load(a.neg)
    meta = load_meta(a.meta)
    pos_keys = {key(r) for r in pos}
    neg_keys = {key(r) for r in neg}

    rows = list(csv.DictReader(open(a.results, encoding='utf-8')))
    n_pos_add = n_neg_add = n_promote = n_demote = n_skip = 0

    for r in rows:
        k = (str(r.get('sid', '')), str(r.get('gid', '')))
        v = (r.get('verdict') or '').strip().upper()
        if not k[0] or not k[1] or v not in ('POS', 'NEG'):
            n_skip += 1; continue
        mr = meta.get(k, {})
        base = {f: mr.get(f, '') for f in FIELDS}
        base.update({'sid': k[0], 'gid': k[1],
                     'shot': 'judge', 'idx': mr.get('idx', '')})
        if v == 'POS':
            if k in neg_keys:
                neg = [x for x in neg if key(x) != k]; neg_keys.discard(k); n_promote += 1
            if k not in pos_keys:
                pos.append(base); pos_keys.add(k); n_pos_add += 1
        else:
            if k in pos_keys:
                pos = [x for x in pos if key(x) != k]; pos_keys.discard(k); n_demote += 1
            if k not in neg_keys:
                neg.append(base); neg_keys.add(k); n_neg_add += 1

    if not a.no_backup:
        ts = time.strftime('%Y%m%d_%H%M%S')
        bk = os.path.join(a.backup_dir, f'backup_judge_{ts}')
        os.makedirs(bk, exist_ok=True)
        for name, p in (('positives.csv', a.pos), ('negatives.csv', a.neg)):
            if os.path.exists(p):
                shutil.copy(p, os.path.join(bk, name))
        print(f'已备份原池 → {bk}')

    def dump(path, data):
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            for r in data:
                w.writerow({k2: r.get(k2, '') for k2 in FIELDS})

    dump(a.pos, pos)
    dump(a.neg, neg)

    print(f'判定输入 {len(rows)} 行：新增正 {n_pos_add} / 新增负 {n_neg_add} '
          f'/ 提升 {n_promote} / 降级 {n_demote} / 忽略 {n_skip}')
    print(f'合并后样本池：正 {len(pos)} / 负 {len(neg)}')


if __name__ == '__main__':
    main()
