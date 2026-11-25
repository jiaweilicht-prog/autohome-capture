# HANDOFF · 副驾侧内饰图采集线 · 工作交接

> **给接手 agent 的话**：读完这一页 + 仓库 README.md，你就能继续干活。
> **最后更新**：2026-11-25　|　**交接人**：Tom（WorkBuddy agent）｜ **Owner**：Licht

## 一、任务是什么

从汽车之家图片库（`classid=3` 内饰图）批量采集 **LHD 副驾侧车外 3/4 内饰视角** 图，供内饰 Benchmark 使用。

**目标视角判据（唯一决定性标准，不得更改）：**
- ✅ POS：**A 柱斜线在画面右侧** + 从画面上边界**顺时针**转下来 = 车头朝右 = 左舵副驾侧视角
- ❌ NEG：A 柱在画面左侧 + 逆时针 = 车头朝左（主驾侧视角）
- 空间纵深验证：副驾座椅（近）→ console（中）→ 方向盘/主驾（远）
- ⚠️ 禁止：用画面左右直接判断、镜像测试（CLIP 对镜像不变）、文本相似度（无区分度）

## 二、管线与工具

```
ah_pic_pull.py（抓取）→ ah_pic_clip.py（CLIP 初排）→ judge 判定节点 → ah_pic_fewshot_rank.py（重排）→ ah_pic_finalize.py（候选墙）→ ah_pic_collect.py / ah_pic_gap_fill.py（收集）
```

- **judge 判定节点**（换机冷启动的关键）：`scripts/ah_pic_judge_prep.py` 切批并生成判定提示词 → 视觉判定 → `scripts/ah_pic_judge_apply.py` 把 POS/NEG 结果回灌正负样本池
- **校准种子**：`seed_pool/` 20 张真实图（10 正 + 10 负，同车配对），`python scripts/fetch_seed_pool.py` 可重下
- **判据细节**：见本仓库 `SKILL.md` 与 `references/exclusion-rules.md`（14 条硬排除）
- **Python 环境**： ranking 需要 py3.12 + torch 2.2.2 + open_clip（原机用 `.clipvenv/`）；仅下载/拼图用标准库即可
- 身份键一律用 **(sid, gid)**，不用行号；正样本池豁免硬 gate（neg>pos 不剔除已确认正样本）

## 三、当前进度（2026-11-25 实测）

### 美系 — 采集完成 ✅（差最后人工复核）
- **147/147 款全覆盖**，10 品牌（福特 38 / 别克 27 / 雪佛兰 22 / 凯迪拉克 18 / 林肯 15 / Jeep 12 / 特斯拉 7 / GMC 3 / 道奇 3 / 克莱斯勒 2）
- 已收集 163 张平铺在（原工作机）`output/collection_us/all/` + `index.csv` 总索引
  - **verified 71 张**（55 款）：已确认，带 JSON sidecar
  - **review 92 张**（92 款）：各缺口车型 few-shot top1 兜底，**待 Licht 人工过筛**（样张 `contact_sheet_review.png`）——命中即移入 verified 并补 JSON

### 欧系 — 拉取完成，待精排 🔄
- `output/pull_eu/`：**478/478 车系全部抓完**，候选图 **62,738 张**，`items.csv` 已合并
- 下一步按管线执行：CLIP 初排 → judge 判定 → few-shot 重排 → 候选墙 → 收集

### 韩系 / 日系 — 未开始 ⏳
- 排在欧系之后，方法同美系（先拉取 → 判定迭代）

### 模型迭代里程碑
v7 → v8（A 柱判据确立）→ v9（Skill 化）→ v10/v11（池收敛：正 76 / 负 1028）→ A+C（judge 节点 + 种子池 + 参数化，换机可用）

## 四、接下来干什么（优先级）

1. **欧系精排**：对 62,738 张候选跑 CLIP 初排 + judge 判定，出候选墙给 Licht 过筛（后台长任务，可断点续跑）
2. **美系 92 张待复核收尾**：等 Licht 看样张报命中 → 移入 verified + 补 JSON → 刷新 index.csv
3. 欧系收尾后 → 韩系（35 款）→ 日系

## 五、硬规则（必须遵守）

- ⚠️ **修复/调参后不得擅自启动全量批次**——必须先出样张，等 Licht 确认后才继续
- 破坏性操作（删除/覆盖）必须先列清单、经确认
- PAT/令牌不进对话记录：让用户复制到剪贴板，用 `pbpaste` 读取；推送前先 API 验活
- 推送需代理：`git -c http.proxy=http://127.0.0.1:7890 push ...`
- 美系样本池数据（`positives.csv` / `negatives.csv`、嵌入缓存）在原工作机 `output/fewshot/` 与 `output/clip_rank3/`，不在本仓库——换机后用 judge 节点 + seed_pool 冷启动重建

## 六、相关文件地图（原工作机 `~/WorkBuddy/数据抓取/`）

| 路径 | 内容 |
|---|---|
| `output/fewshot/positives.csv` / `negatives.csv` | 正 76 / 负 1028 样本池 |
| `output/clip_rank3/emb_cache.npz`、`output/clip_rank5/reg_depth.npz` | 嵌入缓存（29,286 条候选） |
| `output/pull_eu/` | 欧系候选（478 车系 / 62,738 张） |
| `output/collection_us/` | 美系收集产物（verified + review + all 平铺） |
| `probe/ah_pic_*.py` | 全部脚本源（本仓库 scripts/ 为参数化发布版） |
| `.workbuddy/memory/MEMORY.md` | 项目长期记忆（含 360° 全景线，那是另一条线，勿混淆） |
