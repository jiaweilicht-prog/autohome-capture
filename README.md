# autohome-passenger-view

汽车之家「左舵车（LHD）副驾侧车外 3/4 内饰视角」图片**批量采集 + 判定**工具链。

本仓库包含三层：

1. **判定技能**（`SKILL.md` + `references/`）—— A 柱位置判据 + 空间纵深 + 14 条硬排除规则。
2. **抓取 / 精排 / 收集脚本**（`scripts/`）—— classid=3 接口轻量抓取、CLIP 语义精排、few-shot 对比重排、候选墙、正式收集。
3. **种子校准池 + 判定节点**（`seed_pool/` + judge 脚本）—— 让「看图判定」变成本仓库自带、可执行的步骤。

---

## ⚠️ 冷启动必读（否则抓不准）

**本工具链的判别力不在算法里，而在「正负样本池」里。**

副驾侧视角 vs 主驾侧视角，对 CLIP 而言几乎相同（都是「开门拍内饰」的图），单独用 CLIP 打分的区分度极低
（实测正负得分常都在 0.29~0.31 之间）。真正把精度做上去的，是不断累积的正负样本。

所以：**样本池为空时，本仓库只能做「抓取 + 通用粗排」，精度不可用。**

正确做法是用自带的 20 张种子 + judge 判定节点，先把样本池建起来（见下「快速开始」）。

---

## 目录结构

```
.
├── SKILL.md                       # 副驾侧视角判定技能（方法论 + 工作流）
├── references/
│   └── exclusion-rules.md         # 14 条硬排除规则
├── seed_pool/                     # 自带 20 张校准样本（10 正 + 10 负，同车配对）
│   ├── manifest.csv
│   ├── pos/                       # 10 张标准命中
│   └── neg/                       # 10 张标准负面
├── scripts/
│   ├── fetch_seed_pool.py         # 下载 / 修复种子池（URL 失效时重跑）
│   ├── ah_pic_pull.py             # 抓取 classid=3 候选图（断点续跑）
│   ├── ah_pic_clip.py             # CLIP 嵌入 + 初排
│   ├── ah_pic_judge_prep.py       # 判定节点·切批 + 生成判定提示词
│   ├── ah_pic_judge_apply.py      # 判定节点·结果回灌样本池
│   ├── ah_pic_fewshot_rank.py     # few-shot 对比重排（score = pos − λ·neg）
│   ├── ah_pic_finalize.py         # 生成候选墙（联络图）+ picklist
│   ├── ah_pic_collect.py          # 正式收集（DDGS 命名 + JSON sidecar）
│   ├── ah_pic_gap_fill.py         # 缺口兜底：每款缺口车型取 top1
│   ├── ah_pic_ingest.py           # 增量入缓存（抓了新批次后补齐嵌入）
│   ├── ah_pic_flatten.py          # 扁平化合并 + 总索引
│   ├── ah_pic_montage*.py         # 各类联络图
│   └── ah_pic_eu_transfer_check.py# 区域迁移验证示例（美系池 → 欧系）
├── examples/targets.example.json  # --targets 输入格式示例
├── requirements.txt
└── LICENSE
```

## 环境依赖

- Python 3.12+（本项目用 3.13 验证）
- 建议独立 venv；首次运行会下载 OpenCLIP 权重（ViT-B-32 / `laion2b_s34b_b79k`，约 600MB）

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/fetch_seed_pool.py      # 下载 20 张校准样本（约 9MB）
```

## 快速开始（冷启动）

```bash
# 0) 种子池（判定标准的锚点）
python scripts/fetch_seed_pool.py

# 1) 抓取候选
python scripts/ah_pic_pull.py --targets examples/targets.example.json \
  --classid 3 --pages 4 --prefix 240x0_ --maxpx 160 --threads 8 --outdir output/pull

# 2) CLIP 嵌入 + 初排（生成嵌入缓存）
python scripts/ah_pic_clip.py --cands output/pull/cand --refs seed_pool/pos \
  --outdir output/clip_rank --topk 6

# 3) 判定节点：切批 → 视觉判定 → 回灌
python scripts/ah_pic_judge_prep.py --cand output/pull/cand --outdir output/judge --batch 20
#   把 output/judge/judge_prompt.md + batches/ 交给视觉判定方（视觉大模型 / 工作代理），
#   逐张判 POS/NEG 写入 output/judge/judge_results.csv（判定前先看 seed_pool/ 20 张校准）
python scripts/ah_pic_judge_apply.py \
  --results output/judge/judge_results.csv \
  --pos output/fewshot/positives.csv --neg output/fewshot/negatives.csv

# 4) 有了样本池，few-shot 重排才准
python scripts/ah_pic_fewshot_rank.py --pos output/fewshot/positives.csv \
  --neg output/fewshot/negatives.csv --outdir output/clip_rank6

# 5) 候选墙 → 人工/视觉复核 → 收集
python scripts/ah_pic_finalize.py --rank output/clip_rank6/clip_ranked_fewshot.csv \
  --topk 3 --outdir output/walls
python scripts/ah_pic_collect.py --pos output/fewshot/positives.csv \
  --out output/collection/verified --manifest output/collection/manifest.csv
```

## 完整流水线

```
抓取(pull) → 嵌入初排(clip) → ┌ 判定节点 (judge_prep → 视觉判定 → judge_apply) ┐ → few-shot 重排 → 候选墙 → 收集
                              └────────── 回灌正负样本池，闭环收敛 ───────────┘
```

- **判定节点**是精度来源：它把「看图判定」固化成可复现步骤（提示词由 `judge_prep` 自动生成，标准 = SKILL.md 的判据）。
- 每回灌一次，样本池增长，下一轮 `few-shot` 分数就更准。美系项目正是靠这个循环迭代了 11 轮。

## 种子校准池（seed_pool/）

10 正 + 10 负，**每对都是「同款车、对的角度 vs 错的角度」**（难点就是同车分辨对错角度）：

| # | 车型 | POS gid | NEG gid | 类型 |
|---|------|---------|---------|------|
| 1 | 福特 探险者 (5556) | 211 | 174 | 大型SUV |
| 2 | 别克 别克E5 (7043) | 31 | 81 | 纯电SUV |
| 3 | 林肯 冒险家新能源 (5386) | 93 | 39 | 插混SUV |
| 4 | 福特 F-150猛禽 (2353) | 160 | 135 | 皮卡 |
| 5 | 福特 福睿斯 (3347) | 24 | 113 | 轿车 |
| 6 | 凯迪拉克 IQ锐歌 (6404) | 39 | 20 | 纯电SUV |
| 7 | 雪佛兰 科鲁兹 (657) | 135 | 166 | 轿车 |
| 8 | Jeep 指南者 (3845) | 123 | 67 | SUV |
| 9 | 克莱斯勒 大捷龙 (2207) | 50 | 3 | MPV |
| 10 | 道奇 Charger SRT (3049) | 52 | 22 | 性能轿车 |

## 核心方法论：副驾侧视角判据

详见 `SKILL.md`。一句话原则：

> **A 柱斜线在画面右侧、且从上边界顺时针转下 → 命中（车头朝右 = 左舵副驾侧视角）；在左侧 / 逆时针 → 负面。**

辅以空间纵深三层次（近：副驾座椅 → 中：中控台 → 远：方向盘/驾驶侧）与 14 条硬排除规则。

## 说明

- 所有脚本路径均可用命令行参数覆盖（默认相对 `./output/`），不再写死绝对路径。
- `ah_pic_fewshot_rank.py` 依赖候选嵌入缓存（`ah_pic_clip.py` 生成）；抓了新批次后可用 `ah_pic_ingest.py` 增量补嵌入。
- 本工具仅用于汽车内饰设计 Benchmark 的公开素材采集，请遵守汽车之家 robots 与版权政策。

## License

MIT
