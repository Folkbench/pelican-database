# Pelican Database (`Folkbench/pelican-database`)

English | [简体中文](README.zh.md)

[![Auto Sync](https://github.com/Folkbench/pelican-database/actions/workflows/auto-sync.yml/badge.svg)](https://github.com/Folkbench/pelican-database/actions/workflows/auto-sync.yml)
[![Model IDs: models.dev](https://img.shields.io/badge/model%20IDs-models.dev-blue)](https://models.dev)
[![License: MIT](https://img.shields.io/badge/code%20%26%20schema-MIT-green.svg)](LICENSE)

A continuously updated, [`models.dev`](https://models.dev)-aligned SVG and PNG reference database of LLM-generated **"a pelican riding a bicycle"** outputs across frontier and open-weight models.

Each model is indexed under a canonical `provider/model_id` identifier with one representative `.svg` source (when publicly available) and a standardized `.png` render, backed by both [`catalog.json`](catalog.json) and a queryable SQLite database ([`pelicans.sqlite`](pelicans.sqlite)).

---

## Database Statistics

<!-- STATS:START -->
| Metric | Value |
|---|---:|
| **Last Updated (UTC)** | `2026-11-26T18:47:32Z` |
| **Unique Models (`provider/model_id`)** | **507** |
| **Providers Covered** | **68** |
| **Original `.svg` + Rendered `.png`** | **454** (89.5%) |
| **Raster-only (`has_svg: false`, normalized `.png`)** | **53** |
| **Exact Match in Live `models.dev/api.json`** | **371** (73.2%) |
| **Tested by Simon Willison** | **179** |
<!-- STATS:END -->

---

## Repository Structure

```text
pelican-database/
├── catalog.json                    # Full JSON index with models.dev metadata, paths, sources & aliases
├── pelicans.sqlite                 # SQLite database (models, providers, model_aliases, model_sources + views)
├── models/
│   └── <provider>/                 # Aligned with models.dev provider IDs (openai, anthropic, google, alibaba, zai, ...)
│       ├── <model_id>.svg          # Original SVG source (present when has_svg = true)
│       └── <model_id>.png          # Browser-rendered PNG (1024px wide, white background) or normalized PNG
├── scripts/
│   ├── sync.py                     # End-to-end incremental sync entry point
│   ├── 01_fetch_all.py             # Fetches Simon Willison pelican-riding-a-bicycle posts & static HTML grids
│   ├── 02_harvest_sources.py       # Merges UncleK/pelicanmap + Simon Willison direct SVGs & grids
│   ├── 03_map_models_dev.py        # Canonical models.dev provider/model_id alignment
│   ├── 04_select_and_download.py   # Deterministic representative selection & SVG validation
│   ├── 05_render_pngs.mjs          # Cross-platform headless Chromium/Edge CDP incremental PNG renderer
│   └── 06_build_database.py        # Integrity verification + catalog.json / pelicans.sqlite / README builder
├── .github/workflows/auto-sync.yml # Scheduled daily incremental update workflow
├── LICENSE                         # MIT License (scripts, schema & documentation)
├── NOTICE.md                       # Upstream rights, provenance & attribution notice
├── README.md                       # English documentation
└── README.zh.md                    # Chinese documentation
```

---

## `models.dev` ID Alignment & Selection Policy

1. **Canonical `provider/model_id` format**: Every entry follows the [`models.dev`](https://models.dev) convention (`{provider}/{model_id}`), such as:
   - `openai/gpt-6.2-astra`, `openai/gpt-5.4`, `openai/o1-preview`
   - `anthropic/claude-fable-5-2`, `anthropic/claude-opus-5-5`, `anthropic/claude-3-7-sonnet`
   - `google/gemini-4-neon`, `google/gemini-2.5-pro`, `google/gemma-4-31b-it`
   - `alibaba/qwen3.6-27b`, `deepseek/deepseek-v4-pro`, `zai/glm-5.2`, `moonshotai/kimi-k3.1-pro`
2. **Native lab ownership enforcement**: Models resold through routers or third-party platforms (e.g., OpenRouter, cloud gateways) are canonicalized back to their native lab provider to prevent duplicate or misattributed entries.
3. **Full provenance fields**: Every record preserves both `model_id` (canonical normalized ID) and `models_dev_id` (exact key matched in live `models.dev/api.json`, or `null` for retired/historical snapshots), alongside `models_dev_exact`, `models_dev_first_party`, `raw_model_aliases`, and `all_source_urls`.
4. **Deterministic representative selection** (1 sample per canonical `model_id`):
   - Real `.svg` source strictly prioritized over raster-only screenshots (`has_svg: false` samples are retained and normalized to `.png` only when no `.svg` exists)
   - Simon Willison's canonical test preferred when available
   - Classic *"pelican riding a bicycle"* prompt prioritized over enhanced/derivative variants (non-pelican derivatives and multi-model collages are excluded)
   - Default / high reasoning effort preferred over `minimal` / `none` effort

---

## Top Providers

<!-- PROVIDERS:START -->
| Provider (`models.dev`) | Models | With SVG | Raster-only | Exact `models.dev` | Simon Tested |
|---|---:|---:|---:|---:|---:|
| `openai` | 72 | 61 | 11 | 62 | 39 |
| `google` | 63 | 51 | 12 | 34 | 35 |
| `alibaba` | 62 | 53 | 9 | 49 | 19 |
| `anthropic` | 30 | 30 | 0 | 23 | 22 |
| `meta` | 21 | 18 | 3 | 17 | 12 |
| `mistral` | 21 | 18 | 3 | 18 | 7 |
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
| `community` | 8 | 5 | 3 | 0 | 3 |
| `xiaomi` | 7 | 7 | 0 | 6 | 0 |
| `inception` | 5 | 5 | 0 | 4 | 0 |
| `tencent-tokenhub` | 5 | 5 | 0 | 5 | 2 |
| `cohere` | 4 | 4 | 0 | 4 | 0 |
| `ibm` | 4 | 4 | 0 | 1 | 1 |
| `perplexity` | 4 | 4 | 0 | 4 | 0 |
| `aion-labs` | 3 | 3 | 0 | 2 | 0 |
| `arcee` | 3 | 3 | 0 | 3 | 0 |
| *(+43 more providers)* | — | — | — | — | — |
<!-- PROVIDERS:END -->

---

## Quick Usage

### Query with SQLite

```sql
-- List all models tested by Simon Willison that include raw SVG source
SELECT model_id, models_dev_id, svg_path, png_path, date
FROM models
WHERE tested_by_simon = 1 AND has_svg = 1
ORDER BY provider, model_id;

-- Resolve an informal/raw model name to its canonical models.dev ID
SELECT a.raw_model, m.model_id, m.svg_path, m.png_path
FROM model_aliases a
JOIN models m ON m.model_id = a.model_id
WHERE a.raw_model LIKE '%Claude 3.7%';

-- Provider breakdown
SELECT * FROM providers ORDER BY model_count DESC;
```

### Load with Python

```python
import json
from pathlib import Path

catalog = json.loads(Path("catalog.json").read_text(encoding="utf-8"))
by_id = {m["model_id"]: m for m in catalog["models"]}

sample = by_id["google/gemini-4-neon"]
print(sample["svg_path"], sample["png_path"], sample["source_url"])
```

### Run Incremental Sync Locally

Requires Python 3.10+, Node.js 22+, and Chrome / Chromium / Edge:

```bash
pip install -r requirements.txt
python scripts/sync.py
```

The GitHub Actions workflow (`.github/workflows/auto-sync.yml`) runs this incremental sync automatically every day at `09:00 UTC`, using SHA-256 hashing so only new or changed specimens are re-rendered.

---

## Credits & Acknowledgements

This database stands on the shoulders of the creators, archivists, and open-source maintainers who invented, curated, and standardized the pelican benchmark ecosystem:

- **[Simon Willison](https://simonwillison.net/)** — Creator of the iconic *"Generate an SVG of a pelican riding a bicycle"* LLM benchmark. Direct blog posts, HTML comparison grids, and original SVGs are sourced from [simonwillison.net/tags/pelican-riding-a-bicycle](https://simonwillison.net/tags/pelican-riding-a-bicycle/) and [simonw/pelican-bicycle](https://github.com/simonw/pelican-bicycle).
- **[UncleK / Pelican Map](https://github.com/UncleK/pelicanmap)** ([pelicanmap.aveniqa.com](https://pelicanmap.aveniqa.com)) — For building and maintaining an extraordinarily thorough, daily-updated multilingual archive of LLM pelican specimens with preserved provenance and original media.
- **[models.dev](https://models.dev)** ([anomalyco/models.dev](https://github.com/anomalyco/models.dev)) — For maintaining the open, community-driven canonical catalog of AI provider and model identifiers (`api.json`) that this database aligns to.
- **Community Benchmarks & Testers** — Including **Tihu** (`tihu.app`), **Pelican Zoo** (`pelicanzoo.ai`), **Museum of Models** (`museumofmodels.com`), **Pelicans.wtf**, **Pelican Benchmark**, and all individual researchers and community testers across X, GitHub, Reddit, and Hugging Face. Original attribution, dates, and source URLs are preserved for every entry in `catalog.json` and `pelicans.sqlite`.

---

## License & Rights Notice

- Pipeline scripts, schema, and original documentation are licensed under the **[MIT License](LICENSE)**.
- Archived SVG/PNG model outputs and upstream metadata remain subject to their original creators' rights and upstream notices. Please see **[NOTICE.md](NOTICE.md)** for full rights, provenance, and attribution correction details.

---

## About Folkbench

This repository is the official Pelican reference database maintained by **[Folkbench](https://folkbench.com/)**, built to power **Folkbench's model authenticity and identity verification detection** — helping verify whether AI API endpoints and relays serve genuine upstream models rather than substituted, spoofed, or silently downgraded models.
