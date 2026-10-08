# autohome-passenger-view

汽车之家「左舵车（LHD）副驾侧车外 3/4 内饰视角」图片**批量采集 + 质检**工具链。

本仓库包含两部分：

1. **passenger-side-view 质检技能**（`SKILL.md` + `references/`）—— 用 A 柱位置判据 + 空间纵深 + 14 条硬排除规则，判定一张内饰图是否为目标视角。
2. **抓取 / 精排 / 收集脚本**（`scripts/`）—— 基于汽车之家移动端 `classid=3` 接口的轻量抓取、CLIP 语义精排、few-shot 对比重排、候选墙生成、正式收集下载。

## 目录结构

```
.
├── SKILL.md                    # 副驾侧视角质检技能（方法论 + 工作流）
├── references/
│   └── exclusion-rules.md      # 14 条硬排除规则
├── scripts/
│   ├── ah_pic_pull.py          # 按车型清单抓取 classid=3 候选图（断点续跑）
│   ├── ah_pic_clip.py          # CLIP 嵌入 + 文本/参考图相似度初排
│   ├── ah_pic_fewshot_rank.py  # few-shot 对比重排（score = pos − λ·neg）
│   ├── ah_pic_finalize.py      # 生成候选墙（联络图）+ picklist
│   ├── ah_pic_collect.py       # 正式收集：下载已确认图（DDGS 命名 + JSON sidecar）
│   ├── ah_pic_gap_fill.py      # 缺口兜底：每款缺口车型取 top1
│   ├── ah_pic_flatten.py       # 扁平化合并到单一目录 + 总索引
│   ├── ah_pic_montage.py       # 已确认图联络图
│   ├── ah_pic_montage_review.py# 待复核图联络图
│   ├── ah_pic_montage_all.py   # 合并联络图
│   └── ah_pic_eu_transfer_check.py # 区域迁移验证示例（美系池 → 欧系）
├── examples/
│   └── targets.example.json    # --targets 输入格式示例
├── requirements.txt
└── LICENSE
```

## 环境依赖

- Python 3.12+（本项目用 3.13 验证）
- 建议独立 venv，安装 `requirements.txt`
- 首次运行会下载 OpenCLIP 预训练权重（ViT-B-32 / `laion2b_s34b_b79k`，约 600MB）

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 构建抓取目标清单（`--targets`）

`ah_pic_pull.py` 需要一份车型清单 JSON，每条含 `seriesId`（汽车之家车型 ID）、`brandCn`、`seriesName`：

```json
[
  { "seriesId": "3170", "brandCn": "奥迪", "seriesName": "奥迪A3" },
  { "seriesId": "980",  "brandCn": "GMC",  "seriesName": "SAVANA" }
]
```

`seriesId` 可从汽车之家车型页 URL 取得，或参考本项目的 `config/` 下 discovery / catalog 列表批量生成。

## 完整流水线

```bash
# 1) 抓取候选（每车系最近 N 页；每车系落盘为 parts/{sid}.csv，可断点续跑）
python scripts/ah_pic_pull.py --targets examples/targets.example.json \
  --classid 3 --pages 4 --prefix 240x0_ --maxpx 160 --threads 8 --outdir output/pull

# 2) CLIP 嵌入 + 初排（文本提示或参考图）
python scripts/ah_pic_clip.py --cands output/pull/cand \
  --refs <参考图目录> --outdir output/clip_rank --topk 6

# 3) few-shot 对比重排（依赖正负样本池 output/fewshot/positives.csv + negatives.csv）
python scripts/ah_pic_fewshot_rank.py --outdir output/clip_rank6 --topk 3 --lam 0.6

# 4) 生成候选墙（联络图）+ picklist
python scripts/ah_pic_finalize.py --rank output/clip_rank6/ranked.csv \
  --topk 3 --outdir output/walls

# 5) 人工过筛候选墙 → 更新正负样本池（见 SKILL.md 场景 C / D），迭代收敛

# 6) 正式收集已确认图（DDGS 命名 + JSON 元数据）
python scripts/ah_pic_collect.py --pos output/fewshot/positives.csv \
  --out output/collection/verified --manifest output/collection/manifest.csv

# 7) 缺口兜底（每款缺口车型取 top1）
python scripts/ah_pic_gap_fill.py --lam 0.6

# 8) 扁平化合并 + 总索引 + 合并联络图
python scripts/ah_pic_flatten.py
python scripts/ah_pic_montage_all.py
```

## 核心方法论：副驾侧视角判据

详见 `SKILL.md`。一句话原则：

> **A 柱斜线在画面右侧、且从上边界顺时针转下 → 命中（车头朝右 = 左舵副驾侧视角）；在左侧 / 逆时针 → 负面。**

辅以空间纵深三层次（近：副驾座椅 → 中：中控台 → 远：方向盘/驾驶侧）与 14 条硬排除规则。

## 说明

- `ah_pic_fewshot_rank.py` 依赖一个预构建的候选嵌入缓存（本项目为约 2.9 万条）；首次使用需先跑 `ah_pic_clip.py` 生成缓存。
- `ah_pic_flatten.py` / `ah_pic_montage*.py` 路径按本项目 `output/collection_us/` 布局硬编码，迁移到新项目时需按实际目录修改。
- 本工具仅用于汽车内饰设计 Benchmark 的公开素材采集，请遵守汽车之家 robots 与版权政策。

## License

MIT
