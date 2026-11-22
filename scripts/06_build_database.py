import datetime
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SELECTED_PATH = BASE / "cache" / "selected_models.json"
MANIFEST_PATH = BASE / "cache" / "render_manifest.json"
CATALOG_OUT = BASE / "catalog.json"
SQLITE_OUT = BASE / "pelicans.sqlite"
README_EN = BASE / "README.md"
README_ZH = BASE / "README.zh.md"


def verify_png(p: Path):
    if not p.exists():
        return False, 0, 0, 0
    data = p.read_bytes()
    if len(data) < 24 or data[:4] != b"\x89PNG":
        return False, len(data), 0, 0
    w = int.from_bytes(data[16:20], "big")
    h = int.from_bytes(data[20:24], "big")
    return (w > 0 and h > 0), len(data), w, h


def build_sqlite(records: list, provider_rows: list):
    if SQLITE_OUT.exists():
        SQLITE_OUT.unlink()
    conn = sqlite3.connect(str(SQLITE_OUT))
    cur = conn.cursor()

    cur.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE providers (
            provider TEXT PRIMARY KEY,
            model_count INTEGER NOT NULL,
            svg_count INTEGER NOT NULL,
            raster_only_count INTEGER NOT NULL,
            models_dev_exact_count INTEGER NOT NULL,
            simon_tested_count INTEGER NOT NULL
        );

        CREATE TABLE models (
            model_id TEXT PRIMARY KEY,
            provider TEXT NOT NULL REFERENCES providers(provider),
            slug TEXT NOT NULL,
            models_dev_id TEXT,
            models_dev_exact INTEGER NOT NULL,
            models_dev_first_party INTEGER NOT NULL,
            display_name TEXT,
            family TEXT,
            release_date TEXT,
            reasoning INTEGER,
            open_weights INTEGER,
            has_svg INTEGER NOT NULL,
            svg_path TEXT,
            png_path TEXT NOT NULL,
            svg_bytes INTEGER NOT NULL,
            png_bytes INTEGER NOT NULL,
            png_width INTEGER NOT NULL,
            png_height INTEGER NOT NULL,
            render_mode TEXT,
            tested_by_simon INTEGER NOT NULL,
            selected_is_simon INTEGER NOT NULL,
            author TEXT,
            date TEXT,
            origin TEXT,
            source_url TEXT,
            pelicanmap_url TEXT,
            media_url TEXT,
            effort TEXT,
            prompt_category TEXT,
            total_candidates INTEGER NOT NULL
        );

        CREATE TABLE model_aliases (
            raw_model TEXT NOT NULL,
            model_id TEXT NOT NULL REFERENCES models(model_id),
            PRIMARY KEY (raw_model, model_id)
        );

        CREATE TABLE model_sources (
            model_id TEXT NOT NULL REFERENCES models(model_id),
            source_url TEXT NOT NULL,
            PRIMARY KEY (model_id, source_url)
        );

        CREATE INDEX idx_models_provider ON models(provider);
        CREATE INDEX idx_models_mdev_id ON models(models_dev_id);
        CREATE INDEX idx_models_has_svg ON models(has_svg);
        CREATE INDEX idx_models_simon ON models(tested_by_simon);
        CREATE INDEX idx_aliases_model_id ON model_aliases(model_id);

        CREATE VIEW v_simon_models AS
            SELECT model_id, provider, models_dev_id, has_svg, svg_path, png_path, selected_is_simon, date, source_url
            FROM models
            WHERE tested_by_simon = 1
            ORDER BY provider, model_id;

        CREATE VIEW v_svg_models AS
            SELECT model_id, provider, models_dev_id, svg_path, png_path, svg_bytes, png_width, png_height, author, date
            FROM models
            WHERE has_svg = 1
            ORDER BY provider, model_id;
        """
    )

    cur.executemany(
        """
        INSERT INTO providers (provider, model_count, svg_count, raster_only_count, models_dev_exact_count, simon_tested_count)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        provider_rows,
    )

    for r in records:
        cur.execute(
            """
            INSERT INTO models (
                model_id, provider, slug, models_dev_id, models_dev_exact, models_dev_first_party,
                display_name, family, release_date, reasoning, open_weights,
                has_svg, svg_path, png_path, svg_bytes, png_bytes, png_width, png_height, render_mode,
                tested_by_simon, selected_is_simon, author, date, origin,
                source_url, pelicanmap_url, media_url, effort, prompt_category, total_candidates
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                r["model_id"],
                r["provider"],
                r["slug"],
                r["models_dev_id"],
                1 if r["models_dev_exact"] else 0,
                1 if r["models_dev_first_party"] else 0,
                r["display_name"],
                r["family"],
                r["release_date"],
                None if r["reasoning"] is None else (1 if r["reasoning"] else 0),
                None if r["open_weights"] is None else (1 if r["open_weights"] else 0),
                1 if r["has_svg"] else 0,
                r["svg_path"],
                r["png_path"],
                r["svg_bytes"],
                r["png_bytes"],
                r["png_width"],
                r["png_height"],
                r["render_mode"],
                1 if r["tested_by_simon"] else 0,
                1 if r["selected_is_simon"] else 0,
                r["author"],
                r["date"],
                r["origin"],
                r["source_url"],
                r["pelicanmap_url"],
                r["media_url"],
                r["effort"],
                r["prompt_category"],
                r["total_candidates"],
            ),
        )
        for alias in r["raw_model_aliases"]:
            cur.execute(
                "INSERT OR IGNORE INTO model_aliases (raw_model, model_id) VALUES (?, ?)",
                (alias, r["model_id"]),
            )
        for surl in r["all_source_urls"]:
            cur.execute(
                "INSERT OR IGNORE INTO model_sources (model_id, source_url) VALUES (?, ?)",
                (r["model_id"], surl),
            )

    conn.commit()
    conn.close()


def replace_marker_block(text: str, marker: str, replacement: str) -> str:
    pattern = re.compile(
        rf"(<!-- {marker}:START -->).*?(<!-- {marker}:END -->)",
        flags=re.DOTALL,
    )
    return pattern.sub(rf"\1\n{replacement}\n\2", text)


def update_readmes(stats: dict, provider_rows: list):
    svg_pct = stats["with_svg"] * 100 / stats["total_models"] if stats["total_models"] else 0
    mdev_pct = stats["models_dev_exact"] * 100 / stats["total_models"] if stats["total_models"] else 0

    en_stats = "\n".join([
        "| Metric | Value |",
        "|---|---:|",
        f"| **Last Updated (UTC)** | `{stats['generated_at']}` |",
        f"| **Unique Models (`provider/model_id`)** | **{stats['total_models']}** |",
        f"| **Providers Covered** | **{stats['total_providers']}** |",
        f"| **Original `.svg` + Rendered `.png`** | **{stats['with_svg']}** ({svg_pct:.1f}%) |",
        f"| **Raster-only (`has_svg: false`, normalized `.png`)** | **{stats['raster_only']}** |",
        f"| **Exact Match in Live `models.dev/api.json`** | **{stats['models_dev_exact']}** ({mdev_pct:.1f}%) |",
        f"| **Tested by Simon Willison** | **{stats['tested_by_simon']}** |",
    ])

    zh_stats = "\n".join([
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| **最后更新（UTC）** | `{stats['generated_at']}` |",
        f"| **唯一模型数（`provider/model_id`）** | **{stats['total_models']}** |",
        f"| **覆盖 Provider 数** | **{stats['total_providers']}** |",
        f"| **含原始 `.svg` + 渲染 `.png`** | **{stats['with_svg']}** ({svg_pct:.1f}%) |",
        f"| **仅截图样本（`has_svg: false`，已统一转 `.png`）** | **{stats['raster_only']}** |",
        f"| **精确命中活跃 `models.dev/api.json`** | **{stats['models_dev_exact']}** ({mdev_pct:.1f}%) |",
        f"| **含 Simon Willison 实测记录** | **{stats['tested_by_simon']}** |",
    ])

    en_prov = [
        "| Provider (`models.dev`) | Models | With SVG | Raster-only | Exact `models.dev` | Simon Tested |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    zh_prov = [
        "| Provider（`models.dev`） | 模型数 | 含 SVG | 仅截图 | 精确命中 `models.dev` | Simon 实测 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for p, mc, sc, rc, ec, st in provider_rows[:25]:
        row = f"| `{p}` | {mc} | {sc} | {rc} | {ec} | {st} |"
        en_prov.append(row)
        zh_prov.append(row)
    if len(provider_rows) > 25:
        rem = len(provider_rows) - 25
        en_prov.append(f"| *(+{rem} more providers)* | — | — | — | — | — |")
        zh_prov.append(f"| *（另有 {rem} 个 Provider）* | — | — | — | — | — |")

    if README_EN.exists():
        txt = README_EN.read_text(encoding="utf-8")
        txt = replace_marker_block(txt, "STATS", en_stats)
        txt = replace_marker_block(txt, "PROVIDERS", "\n".join(en_prov))
        README_EN.write_text(txt, encoding="utf-8")

    if README_ZH.exists():
        txt = README_ZH.read_text(encoding="utf-8")
        txt = replace_marker_block(txt, "STATS", zh_stats)
        txt = replace_marker_block(txt, "PROVIDERS", "\n".join(zh_prov))
        README_ZH.write_text(txt, encoding="utf-8")


def main():
    selected = json.loads(SELECTED_PATH.read_text(encoding="utf-8"))
    render_data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    rmanifest = render_data["manifest"]

    records = []
    missing_pngs = []
    missing_svgs = []

    for m in selected:
        cid = m["model_id"]
        png_abs = BASE / m["png_path"]
        ok_png, png_bytes, pw, ph = verify_png(png_abs)
        if not ok_png:
            missing_pngs.append(cid)
            continue

        has_svg = bool(m["has_svg"])
        svg_path = m["svg_path"]
        svg_bytes = m["svg_bytes"]
        if has_svg:
            svg_abs = BASE / svg_path
            if not svg_abs.exists() or svg_abs.stat().st_size == 0:
                missing_svgs.append(cid)
                has_svg = False
                svg_path = None
                svg_bytes = 0

        rinfo = rmanifest.get(cid, {})
        records.append({
            "model_id": cid,
            "provider": m["provider"],
            "slug": m["slug"],
            "models_dev_id": m["models_dev_id"],
            "models_dev_exact": bool(m["models_dev_exact"]),
            "models_dev_first_party": bool(m["models_dev_first_party"]),
            "display_name": m["mdev_name"] or m["slug"],
            "family": m["mdev_family"],
            "release_date": m["mdev_release_date"],
            "reasoning": m["mdev_reasoning"],
            "open_weights": m["mdev_open_weights"],
            "has_svg": has_svg,
            "svg_path": svg_path,
            "png_path": m["png_path"],
            "svg_bytes": svg_bytes,
            "png_bytes": png_bytes,
            "png_width": pw,
            "png_height": ph,
            "render_mode": rinfo.get("mode", ""),
            "tested_by_simon": bool(m["tested_by_simon"]),
            "selected_is_simon": bool(m["selected_is_simon"]),
            "author": m["selected_author"],
            "date": m["selected_date"],
            "origin": m["selected_origin"],
            "source_url": m["selected_source_url"],
            "pelicanmap_url": m["selected_pelicanmap_url"],
            "media_url": m["selected_media_url"],
            "effort": m["selected_effort"],
            "prompt_category": m["selected_prompt_category"],
            "total_candidates": m["total_candidates"],
            "raw_model_aliases": m["raw_model_aliases"],
            "all_source_urls": m["all_source_urls"],
        })

    records.sort(key=lambda r: (r["provider"], r["slug"].lower()))

    provs = sorted(set(r["provider"] for r in records))
    provider_rows = []
    for p in provs:
        sub = [r for r in records if r["provider"] == p]
        provider_rows.append((
            p,
            len(sub),
            sum(1 for r in sub if r["has_svg"]),
            sum(1 for r in sub if not r["has_svg"]),
            sum(1 for r in sub if r["models_dev_exact"]),
            sum(1 for r in sub if r["tested_by_simon"]),
        ))
    provider_rows.sort(key=lambda x: (-x[1], x[0]))

    stats = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_models": len(records),
        "total_providers": len(provs),
        "with_svg": sum(1 for r in records if r["has_svg"]),
        "raster_only": sum(1 for r in records if not r["has_svg"]),
        "models_dev_exact": sum(1 for r in records if r["models_dev_exact"]),
        "models_dev_first_party": sum(1 for r in records if r["models_dev_first_party"]),
        "tested_by_simon": sum(1 for r in records if r["tested_by_simon"]),
        "selected_is_simon": sum(1 for r in records if r["selected_is_simon"]),
        "render_modes": dict(Counter(r["render_mode"] for r in records)),
    }

    catalog = {
        "schema_version": "1.0",
        "alignment_standard": "models.dev",
        "sources": [
            "https://simonwillison.net/tags/pelican-riding-a-bicycle/",
            "https://github.com/UncleK/pelicanmap",
            "https://models.dev/api.json",
        ],
        "stats": stats,
        "models": records,
    }

    CATALOG_OUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    build_sqlite(records, provider_rows)
    update_readmes(stats, provider_rows)

    print("=== DATABASE BUILD COMPLETE ===")
    print(json.dumps(stats, indent=2))
    print(f"Missing/invalid PNGs: {len(missing_pngs)} {missing_pngs[:10]}")
    print(f"Missing/invalid SVGs: {len(missing_svgs)} {missing_svgs[:10]}")


if __name__ == "__main__":
    main()
