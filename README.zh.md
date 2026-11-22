# 鹈鹕骑单车数据库（`Folkbench/pelican-database`）

[English](README.md) | 简体中文

[![Auto Sync](https://github.com/Folkbench/pelican-database/actions/workflows/auto-sync.yml/badge.svg)](https://github.com/Folkbench/pelican-database/actions/workflows/auto-sync.yml)
[![Model IDs: models.dev](https://img.shields.io/badge/model%20IDs-models.dev-blue)](https://models.dev)
[![License: MIT](https://img.shields.io/badge/code%20%26%20schema-MIT-green.svg)](LICENSE)

一个持续自动更新、严格对齐 [`models.dev`](https://models.dev) 模型 ID 规范的大语言模型 **「鹈鹕骑单车（Pelican Riding a Bicycle）」SVG 与 PNG 参考数据库**。

每个模型均按标准的 `provider/model_id` 格式归档，保留 1 份代表性的原始 `.svg`（若公开可得）及统一的高清 `.png` 渲染图，并提供结构化的 [`catalog.json`](catalog.json) 与可查询的 SQLite 数据库（[`pelicans.sqlite`](pelicans.sqlite)）。

---

## 数据库统计

<!-- STATS:START -->
| 指标 | 数值 |
|---|---:|
| **最后更新（UTC）** | `2026-11-22T05:50:22Z` |
| **唯一模型数（`provider/model_id`）** | **507** |
| **覆盖 Provider 数** | **68** |
| **含原始 `.svg` + 渲染 `.png`** | **454** (89.5%) |
| **仅截图样本（`has_svg: false`，已统一转 `.png`）** | **53** |
| **精确命中活跃 `models.dev/api.json`** | **378** (74.6%) |
| **含 Simon Willison 实测记录** | **177** |
<!-- STATS:END -->

---

## 仓库目录结构

```text
pelican-database/
├── catalog.json                    # 全量 JSON 索引（含 models.dev 元数据、文件路径、来源与别名）
├── pelicans.sqlite                 # SQLite 数据库（含 models / providers / model_aliases / model_sources 表与视图）
├── models/
│   └── <provider>/                 # 对齐 models.dev 的 Provider ID（如 openai、anthropic、google、alibaba、zai 等）
│       ├── <model_id>.svg          # 原始 SVG 源码（has_svg = true 时存在）
│       └── <model_id>.png          # 无头浏览器高清渲染 PNG（1024px 宽白底）或标准化后的 PNG
├── scripts/
│   ├── sync.py                     # 一键增量同步主入口
│   ├── 01_fetch_all.py             # 抓取 Simon Willison pelican-riding-a-bicycle 全量文章与静态对比网格
│   ├── 02_harvest_sources.py       # 融合 UncleK/pelicanmap 与 Simon Willison 直链 SVG/对比网格
│   ├── 03_map_models_dev.py        # 对齐 models.dev 规范 provider/model_id
│   ├── 04_select_and_download.py   # 确定性筛选代表样本并校验下载
│   ├── 05_render_pngs.mjs          # 跨平台无头 Chromium/Edge CDP 增量 PNG 渲染器
│   └── 06_build_database.py        # 完整性校验并生成 catalog.json / pelicans.sqlite / README
├── .github/workflows/auto-sync.yml # 每日自动增量更新 GitHub Actions 工作流
├── LICENSE                         # MIT 许可证（适用于脚本、数据库结构与原创文档）
├── NOTICE.md                       # 上游版权、溯源与归属说明
├── README.md                       # 英文文档
└── README.zh.md                    # 中文文档
```

---

## `models.dev` ID 对齐与样本筛选规则

1. **统一 `provider/model_id` 命名规范**：全部模型对齐 [`models.dev`](https://models.dev) 格式（`{provider}/{model_id}`），例如：
   - `openai/gpt-6.2-astra`、`openai/gpt-5.4`、`openai/o1-preview`
   - `anthropic/claude-fable-5-2`、`anthropic/claude-opus-5-5`、`anthropic/claude-3-7-sonnet`
   - `google/gemini-4-neon`、`google/gemini-2.5-pro`、`google/gemma-4-31b-it`
   - `alibaba/qwen3.6-27b`、`deepseek/deepseek-v4-pro`、`zai/glm-5.2`、`moonshotai/kimi-k3.1-pro`
2. **强制按原生厂商归属**：自动识别并纠正经由第三方聚合路由/云平台转售的模型，避免同一模型分散到多个 Provider 下。
3. **完整溯源字段**：每条记录同时保存 `model_id`（规范 ID）与 `models_dev_id`（活跃 `models.dev/api.json` 中精确命中的原始 key；历史下线模型为 `null`），以及 `models_dev_exact`、`models_dev_first_party`、`raw_model_aliases` 和 `all_source_urls`。
4. **单模型确定性去重优先级**（每个 `model_id` 保留 1 个代表样本）：
   - **真实 `.svg` 源码优先**于纯截图（仅在全网无 `.svg` 时保留截图样本并标记 `has_svg: false`，统一转为 `.png`）
   - 同条件下优先选用 **Simon Willison** 原测样本
   - 优先标准 classic *"pelican riding a bicycle"* 提示词（自动过滤非鹈鹕衍生题与多模型拼图）
   - 优先默认 / `high` 推理档位，避免优先选中 `minimal` / `none` 降档输出

---

## 主要 Provider 分布

<!-- PROVIDERS:START -->
| Provider（`models.dev`） | 模型数 | 含 SVG | 仅截图 | 精确命中 `models.dev` | Simon 实测 |
|---|---:|---:|---:|---:|---:|
| `openai` | 72 | 61 | 11 | 63 | 39 |
| `google` | 64 | 52 | 12 | 35 | 35 |
| `alibaba` | 63 | 54 | 9 | 50 | 19 |
| `anthropic` | 30 | 30 | 0 | 23 | 22 |
| `meta` | 21 | 18 | 3 | 18 | 12 |
| `mistral` | 21 | 18 | 3 | 19 | 7 |
| `openrouter` | 21 | 20 | 1 | 0 | 0 |
| `deepseek` | 19 | 17 | 2 | 18 | 9 |
| `zai` | 19 | 18 | 1 | 17 | 7 |
| `xai` | 16 | 16 | 0 | 12 | 2 |
| `bailing` | 11 | 10 | 1 | 8 | 0 |
| `moonshotai` | 11 | 11 | 0 | 9 | 6 |
| `amazon-bedrock` | 9 | 9 | 0 | 9 | 6 |
| `minimax` | 9 | 8 | 1 | 8 | 1 |
| `nvidia` | 9 | 8 | 1 | 9 | 0 |
| `volcengine` | 9 | 8 | 1 | 9 | 0 |
| `xiaomi` | 7 | 7 | 0 | 6 | 0 |
| `community` | 5 | 2 | 3 | 0 | 1 |
| `inception` | 5 | 5 | 0 | 4 | 0 |
| `tencent-tokenhub` | 5 | 5 | 0 | 5 | 2 |
| `cohere` | 4 | 4 | 0 | 4 | 0 |
| `ibm` | 4 | 4 | 0 | 1 | 1 |
| `perplexity` | 4 | 4 | 0 | 4 | 0 |
| `aion-labs` | 3 | 3 | 0 | 2 | 0 |
| `arcee` | 3 | 3 | 0 | 3 | 0 |
| *（另有 43 个 Provider）* | — | — | — | — | — |
<!-- PROVIDERS:END -->

---

## 快速使用

### SQLite 查询示例

```sql
-- 查询所有含 Simon Willison 实测记录且带真实 SVG 源码的模型
SELECT model_id, models_dev_id, svg_path, png_path, date
FROM models
WHERE tested_by_simon = 1 AND has_svg = 1
ORDER BY provider, model_id;

-- 通过非规范别称反查标准 models.dev ID
SELECT a.raw_model, m.model_id, m.svg_path, m.png_path
FROM model_aliases a
JOIN models m ON m.model_id = a.model_id
WHERE a.raw_model LIKE '%Claude 3.7%';

-- 按 Provider 查看覆盖统计
SELECT * FROM providers ORDER BY model_count DESC;
```

### Python 读取示例

```python
import json
from pathlib import Path

catalog = json.loads(Path("catalog.json").read_text(encoding="utf-8"))
by_id = {m["model_id"]: m for m in catalog["models"]}

sample = by_id["google/gemini-4-neon"]
print(sample["svg_path"], sample["png_path"], sample["source_url"])
```

### 本地执行增量同步

环境要求：Python 3.10+、Node.js 22+、Chrome / Chromium / Edge：

```bash
pip install -r requirements.txt
python scripts/sync.py
```

本仓库已配置 GitHub Actions 工作流（`.github/workflows/auto-sync.yml`），每天 `09:00 UTC` 自动增量同步上游新增模型，并通过源文件 SHA-256 哈希比对仅对新增或变更的样本重新渲染 PNG。

---

## 致谢（Credits & Acknowledgements）

本数据库的建立离不开推动「鹈鹕骑单车」评测生态与模型标准化的各位原作者、归档维护者与社区贡献者：

- **[Simon Willison](https://simonwillison.net/)** — 创造了极具影响力的 *"Generate an SVG of a pelican riding a bicycle"* 大模型非正式基准测试。本库直接融合了 [simonwillison.net/tags/pelican-riding-a-bicycle](https://simonwillison.net/tags/pelican-riding-a-bicycle/) 下的全部评测文章、静态对比网格与 [simonw/pelican-bicycle](https://github.com/simonw/pelican-bicycle) 原始样本。
- **[UncleK / Pelican Map](https://github.com/UncleK/pelicanmap)**（[pelicanmap.aveniqa.com](https://pelicanmap.aveniqa.com)）— 长期每日持续维护最完整的多语言鹈鹕骑单车归档库，并严谨保留了每一份样本的来源链接、日期与原始媒体。
- **[models.dev](https://models.dev)**（[anomalyco/models.dev](https://github.com/anomalyco/models.dev)）— 提供开放、规范的 AI Provider 与模型 ID 元数据注册表（`api.json`），为本库提供了统一的标准化索引基准。
- **社区评测站点与测试者** — 感谢 **Tihu**（`tihu.app`）、**Pelican Zoo**（`pelicanzoo.ai`）、**Museum of Models**（`museumofmodels.com`）、**Pelicans.wtf**、**Pelican Benchmark** 以及活跃在 X、GitHub、Reddit、Hugging Face 等平台的每一位测试者与贡献者。所有样本的原作者、测试日期与原始链接均完整保留在 `catalog.json` 与 `pelicans.sqlite` 中。

---

## 开源协议与版权说明

- 本仓库的抓取/对齐/渲染脚本、数据库结构与原创文档采用 **[MIT License](LICENSE)** 开源。
- 收录的第三方模型 SVG/PNG 输出与上游评测元数据归原作者及原来源所有，不因归档而改变其原有授权。详情及署名修正/移除流程请参见 **[NOTICE.md](NOTICE.md)**。

---

## 关于 Folkbench

本仓库是 **[Folkbench](https://folkbench.com/)** 维护的官方鹈鹕参考数据库，用于**驱动 Folkbench 的模型真实性检测**——通过将待测 API / 中转站生成的鹈鹕骑单车输出与各模型的规范参考基线进行比对，辅助识别模型掺假、偷换及隐性降智等问题。
