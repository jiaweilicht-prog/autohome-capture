#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
判定节点 · 准备（A 方案）

把候选图切成「判定批次」，并生成给视觉判定方（视觉大模型 / 能看图的工作代理）
的标准提示词 judge_prompt.md 与待填结果表 judge_results.csv。

这样「看图判定」这一步从原来靠人工的临时动作，变成一个可复现、可交接的标准节点：
    抓取 → CLIP 粗筛 → 【judge_prep → 视觉判定 → judge_apply】 → 收集

用法：
  python3 scripts/ah_pic_judge_prep.py --cand output/pull/cand --outdir output/judge --batch 20
  python3 scripts/ah_pic_judge_prep.py --cand output/clip_rank6/clip_ranked.csv --outdir output/judge
"""
import argparse, csv, os, shutil, sys, glob

JUDGE_PROMPT = """# 副驾侧视角判定任务（judge）

你的任务：判定每一张汽车内饰图是否为目标视角。

## 目标视角定义
左舵车（LHD）**副驾侧车外 3/4 内饰**拍摄。相机在车辆副驾侧车门外，向车内斜上方拍。

## 唯一决定性判据：A 柱位置
不看 A 柱倾斜角度大小，只看 A 柱斜线在画面中的**左右位置**：

| 判定 | A 柱位置 | 旋转方向 | 车头方向 | 结论 |
|------|---------|---------|---------|------|
| POS  | **画面右侧** | 从上边界**顺时针**转下 | 朝右 | 命中 |
| NEG  | **画面左侧** | 从上边界**逆时针**转下 | 朝左 | 负面 |

无框车门（如 Tesla）用挡风玻璃侧边缘代替 A 柱，同样适用位置判据。

## 辅助验证：空间纵深三层次（从近到远）
   前景（画面下方）→ 副驾座椅 / 车门内侧板
   中景（画面中央）→ 中控台 console + IP 交界
   远景（画面上方）→ 方向盘 / 驾驶员区域 / A 柱根部
方向盘的远近是关键：**方向盘在远端 = 副驾侧（POS）；方向盘在近景/中心 = 主驾侧（NEG）**。

## 硬排除（任一触即 NEG）
1. 方向盘在近景/中心/前景，或方向盘特写
2. 看不到 A 柱/挡风侧边框，或 A 柱在画面左侧
3. 单座椅特写、车外外观图、门板特写、车顶/天窗特写、后排视角、正对 IP 直拍
4. 门框在画面右侧前景（主驾侧特征）

## 校准参照
先看 seed_pool/pos/（10 张标准 POS）与 seed_pool/neg/（10 张标准 NEG），
每对都是「同款车、对的角度 vs 错的角度」，用来对齐你的判定标准。校准是必须步骤。

## 输出格式
对每张图输出一行：`sid,gid,verdict,reason`
  - verdict 只能是 POS 或 NEG
  - reason 一句话，指出依据（如「A柱在右、方向盘远端」或「方向盘近景、A柱在左」）
把结果写入 judge_results.csv（表头已给）。

## 自检
合理批次 POS 率约 55~85%。若某批 >95% 或 <40%，说明标准漂移，必须复核。
"""


def collect_candidates(cand, maxpx=None):
    """返回 [(sid, gid, path), ...]"""
    items = []
    if os.path.isdir(cand):
        for p in sorted(glob.glob(os.path.join(cand, '*.jpg'))):
            base = os.path.basename(p)[:-4]
            parts = base.split('_')
            sid = parts[0] if parts else ''
            gid = parts[1] if len(parts) > 1 else ''
            if sid.isdigit():
                sid = str(int(sid))
            if gid.isdigit():          # 文件名里是零填充 gid(0108) → 还原成 108
                gid = str(int(gid))
            items.append((sid, gid, p))
        return items
    # CSV 输入
    with open(cand, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            p = r.get('cand') or r.get('local') or ''
            if not p or not os.path.exists(p):
                continue
            items.append((str(r.get('sid', '')), str(r.get('gid', '')), p))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cand', required=True, help='候选图目录，或含 local/cand 列的 CSV')
    ap.add_argument('--outdir', default='output/judge')
    ap.add_argument('--batch', type=int, default=20, help='每批图数')
    ap.add_argument('--maxpx', type=int, default=640, help='批内缩略图最长边，0=不缩')
    a = ap.parse_args()

    items = collect_candidates(a.cand)
    if not items:
        print('没有找到候选图（检查 --cand 路径与文件名 {sid}_{gid}.jpg 格式）')
        sys.exit(1)

    batch_root = os.path.join(a.outdir, 'batches')
    os.makedirs(batch_root, exist_ok=True)

    # 逐批落盘
    n_batch = 0
    for bi in range(0, len(items), a.batch):
        chunk = items[bi:bi + a.batch]
        bdir = os.path.join(batch_root, f'batch_{n_batch:03d}')
        os.makedirs(bdir, exist_ok=True)
        with open(os.path.join(bdir, 'list.csv'), 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['no', 'sid', 'gid', 'file'])
            for j, (sid, gid, p) in enumerate(chunk):
                dst = os.path.join(bdir, f'{j:02d}_{sid}_{gid}.jpg')
                if a.maxpx and a.maxpx > 0:
                    try:
                        from PIL import Image
                        im = Image.open(p).convert('RGB')
                        im.thumbnail((a.maxpx, a.maxpx))
                        im.save(dst, 'JPEG', quality=85)
                    except Exception:
                        shutil.copy(p, dst)
                else:
                    shutil.copy(p, dst)
                w.writerow([j, sid, gid, os.path.basename(dst)])
        n_batch += 1

    # 提示词 + 结果表模板
    with open(os.path.join(a.outdir, 'judge_prompt.md'), 'w', encoding='utf-8') as f:
        f.write(JUDGE_PROMPT)
    res_path = os.path.join(a.outdir, 'judge_results.csv')
    if not os.path.exists(res_path):
        with open(res_path, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(['sid', 'gid', 'verdict', 'reason'])

    print(f'候选 {len(items)} 张 → {n_batch} 批（每批 {a.batch}）')
    print(f'  提示词 : {a.outdir}/judge_prompt.md')
    print(f'  批次   : {batch_root}/batch_XXX/  （含 list.csv）')
    print(f'  结果表 : {res_path}  ← 视觉判定方按 judge_prompt.md 填写')
    print('\n下一步：把 judge_prompt.md + 各批次交给视觉判定（视觉大模型 / 工作代理），')
    print('        结果写入 judge_results.csv 后跑 ah_pic_judge_apply.py 回灌样本池。')


if __name__ == '__main__':
    main()
