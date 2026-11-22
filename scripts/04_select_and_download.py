import concurrent.futures
import json
import re
import shutil
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

import requests

BASE = Path(__file__).resolve().parent.parent
CANDS_PATH = BASE / "cache" / "all_candidates.json"
MAP_PATH = BASE / "cache" / "model_mapping.json"
MODELS_DIR = BASE / "models"
RASTER_CACHE = BASE / "cache" / "raster_originals"
SVG_CACHE = BASE / "cache" / "svg_downloads"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
RASTER_CACHE.mkdir(parents=True, exist_ok=True)
SVG_CACHE.mkdir(parents=True, exist_ok=True)

EFFORT_RANK = {
    "": 0,
    "high": 1,
    "medium": 2,
    "xhigh": 3,
    "max": 4,
    "low": 5,
    "minimal": 6,
    "none": 7,
}

PROMPT_RANK = {
    "classic": 0,
    "classic prompt": 0,
    "source-documented test": 1,
    "": 2,
    "classic-or-unknown": 3,
    "enhanced": 4,
}


def candidate_sort_key(c: dict):
    has_svg = 0 if c.get("has_svg") else 1
    is_simon = 0 if c.get("is_simon") else 1
    # Prefer direct original SVG over cropped/preview
    orig_form = (c.get("original_form") or "").lower()
    form_rank = 0 if orig_form in ("svg", "svg-static") else (1 if "svg" in orig_form else 2)
    p_rank = PROMPT_RANK.get((c.get("prompt_category") or "").lower(), 2)
    e_rank = EFFORT_RANK.get((c.get("effort") or "").lower(), 3)
    # Prefer pelicanmap / simon_direct / simon_static_grid cleanly
    origin_rank = {"simon_direct_svg": 0, "simon_static_grid": 1, "simon_static_html": 1, "pelicanmap": 2}.get(c.get("origin", ""), 3)
    # Prefer slightly newer date when all else equal (negated string via tuple)
    date_str = c.get("date") or "0000-00-00"
    return (has_svg, is_simon, form_rank, p_rank, e_rank, origin_rank, date_str)


def is_valid_svg_bytes(data: bytes) -> bool:
    if not data or len(data) < 60:
        return False
    head = data[:2000].decode("utf-8", errors="ignore").lower()
    if "<svg" not in head:
        return False
    # Check closing tag exists
    tail = data[-1000:].decode("utf-8", errors="ignore").lower()
    if "</svg>" not in tail and "</svg>" not in data.decode("utf-8", errors="ignore").lower():
        return False
    return True


def sanitize_svg_bytes(data: bytes) -> bytes:
    """Ensure SVG has xmlns if missing so headless browser renders it cleanly."""
    text = data.decode("utf-8", errors="replace").strip()
    # Strip markdown code fence if any slipped in
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # Trim anything before <?xml or <svg
    idx_xml = text.find("<?xml")
    idx_svg = text.lower().find("<svg")
    start = idx_xml if (idx_xml != -1 and (idx_svg == -1 or idx_xml < idx_svg)) else idx_svg
    if start > 0:
        text = text[start:]
    # Trim anything after last </svg>
    end = text.lower().rfind("</svg>")
    if end != -1:
        text = text[: end + 6]
    # Add xmlns if missing on <svg>
    m = re.match(r"^(<\?xml[^>]*>\s*)?(<svg\b[^>]*>)", text, flags=re.I | re.S)
    if m and "xmlns=" not in m.group(2).lower():
        svg_open = m.group(2)[:-1] + ' xmlns="http://www.w3.org/2000/svg">'
        text = (m.group(1) or "") + svg_open + text[m.end():]
    return text.encode("utf-8")


def download_bytes(url: str, cache_path: Path, retries: int = 3) -> bytes:
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path.read_bytes()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; PelicanDBBuilder/1.0)"}
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=25)
            if r.status_code == 200 and len(r.content) > 0:
                cache_path.write_bytes(r.content)
                return r.content
            if r.status_code in (404, 410):
                return b""
        except Exception:
            pass
        time.sleep(1.0 * (attempt + 1))
    return b""


def process_one_model(item):
    model_id, info, cands = item
    provider = info["provider"]
    slug = info["slug"]
    out_dir = MODELS_DIR / provider
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_cache_key = re.sub(r"[^a-zA-Z0-9._-]+", "_", f"{provider}__{slug}")

    # Sort candidates by priority
    ranked = sorted(cands, key=candidate_sort_key)

    # First try to obtain a valid SVG from any candidate that has_svg
    chosen = None
    svg_path = None
    raster_path = None
    svg_bytes_len = 0

    for idx, c in enumerate(ranked):
        if not c.get("has_svg"):
            continue
        raw_bytes = b""
        if c.get("local_svg_path") and Path(c["local_svg_path"]).exists():
            raw_bytes = Path(c["local_svg_path"]).read_bytes()
        elif c.get("svg_url"):
            cpath = SVG_CACHE / f"{safe_cache_key}__{idx}.svg"
            raw_bytes = download_bytes(c["svg_url"], cpath)
        if is_valid_svg_bytes(raw_bytes):
            clean_bytes = sanitize_svg_bytes(raw_bytes)
            dest = out_dir / f"{slug}.svg"
            dest.write_bytes(clean_bytes)
            chosen = c
            svg_path = str(dest.relative_to(BASE)).replace("\\", "/")
            svg_bytes_len = len(clean_bytes)
            break

    # If no valid SVG found, fall back to best raster image
    if chosen is None:
        for idx, c in enumerate(ranked):
            rurl = c.get("raster_url")
            if not rurl:
                continue
            ext = Path(urlparse(rurl).path).suffix.lower() or ".png"
            if ext not in (".png", ".jpg", ".jpeg", ".webp"):
                ext = ".png"
            cpath = RASTER_CACHE / f"{safe_cache_key}__{idx}{ext}"
            raw_bytes = download_bytes(rurl, cpath)
            if len(raw_bytes) > 200:
                chosen = c
                raster_path = str(cpath)
                break

    if chosen is None:
        return model_id, None

    any_simon = any(c.get("is_simon") for c in cands)
    raw_aliases = sorted(set(c["raw_model"] for c in cands))
    sources = sorted(set(c["source_url"] for c in cands if c.get("source_url")))

    record = {
        "model_id": model_id,
        "provider": provider,
        "slug": slug,
        "models_dev_id": info["models_dev_id"],
        "models_dev_exact": info["models_dev_exact"],
        "models_dev_first_party": info["models_dev_first_party"],
        "mdev_name": info["mdev_name"],
        "mdev_family": info["mdev_family"],
        "mdev_release_date": info["mdev_release_date"],
        "mdev_reasoning": info["mdev_reasoning"],
        "mdev_open_weights": info["mdev_open_weights"],
        "has_svg": svg_path is not None,
        "svg_path": svg_path,
        "png_path": f"models/{provider}/{slug}.png",
        "svg_bytes": svg_bytes_len,
        "raster_source_cache": raster_path,
        "tested_by_simon": any_simon,
        "selected_is_simon": bool(chosen.get("is_simon")),
        "selected_author": chosen.get("author", ""),
        "selected_date": chosen.get("date", ""),
        "selected_origin": chosen.get("origin", ""),
        "selected_source_url": chosen.get("source_url", ""),
        "selected_pelicanmap_url": chosen.get("pelicanmap_url", ""),
        "selected_media_url": chosen.get("svg_url") if svg_path else chosen.get("raster_url"),
        "selected_effort": chosen.get("effort", ""),
        "selected_prompt_category": chosen.get("prompt_category", ""),
        "selected_original_form": chosen.get("original_form", ""),
        "total_candidates": len(cands),
        "raw_model_aliases": raw_aliases,
        "all_source_urls": sources[:20],
    }
    return model_id, record


def main():
    cands = json.loads(CANDS_PATH.read_text(encoding="utf-8"))
    mapping = json.loads(MAP_PATH.read_text(encoding="utf-8"))

    grouped = defaultdict(list)
    meta_by_cid = {}
    for c in cands:
        raw = c["raw_model"]
        if raw not in mapping:
            continue
        info = mapping[raw]
        cid = info["model_id"]
        grouped[cid].append(c)
        # Keep richest models.dev metadata for this canonical id
        if cid not in meta_by_cid or (not meta_by_cid[cid]["models_dev_exact"] and info["models_dev_exact"]):
            meta_by_cid[cid] = info

    work = [(cid, meta_by_cid[cid], grouped[cid]) for cid in sorted(grouped.keys())]
    print(f"Downloading & selecting 1 representative specimen for {len(work)} models...")

    results = []
    failed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(process_one_model, item) for item in work]
        done = 0
        for fut in concurrent.futures.as_completed(futs):
            cid, rec = fut.result()
            done += 1
            if rec is None:
                failed.append(cid)
            else:
                results.append(rec)
            if done % 100 == 0 or done == len(work):
                print(f"  Progress: {done}/{len(work)} (ok={len(results)}, failed={len(failed)})")

    results.sort(key=lambda r: r["model_id"].lower())
    with_svg = sum(1 for r in results if r["has_svg"])
    raster_only = sum(1 for r in results if not r["has_svg"])
    simon_tested = sum(1 for r in results if r["tested_by_simon"])
    simon_selected = sum(1 for r in results if r["selected_is_simon"])

    print(f"\nDONE! Total models saved: {len(results)} | failed: {len(failed)}")
    print(f"  With real .svg: {with_svg}")
    print(f"  Raster-only (has_svg=false): {raster_only}")
    print(f"  Tested by Simon Willison: {simon_tested} (selected Simon specimen: {simon_selected})")
    if failed:
        print("  Failed model_ids:", failed[:20])

    out = BASE / "cache" / "selected_models.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
