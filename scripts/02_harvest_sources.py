import base64
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent.parent
PELICANMAP_CATALOG = BASE / "cache" / "pelicanmap" / "site" / "catalog.en.json"
SIMON_STATIC_DIR = BASE / "cache" / "simon_static"
SIMON_EXTRACTED_DIR = BASE / "cache" / "simon_extracted_svgs"
SIMON_DIRECT_DIR = BASE / "cache" / "simon_direct_svgs"
SIMON_EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
SIMON_DIRECT_DIR.mkdir(parents=True, exist_ok=True)

PELICANMAP_HOST = "https://pelicanmap.aveniqa.com"

NON_PELICAN_WORDS = (
    "beagle", "opossum", "possum", "raccoon", "racoon", "flamingo",
    "seagull", "otter", "hedgehog", "capybara", "cat riding", "dog riding",
    "pelican-family",
)

MULTI_MODEL_PATTERNS = [
    r"^\d+\s+models\b",
    r"^\d+\s+svgs\b",
    r"^multi\b",
    r"^four models",
    r"^unspecified\b",
    r"^多模型",
    r"\s+vs\.?\s+",
    r"\s+/\s+.*\s+/\s+",  # 3+ models separated by ' / '
    r"×\s*\d+\s*effort",
    r"multi-effort",
    r"comparison",
]

# Known direct .svg URLs from Simon Willison's 161 blog posts -> explicit model name + date + post
SIMON_DIRECT_SVG_MAP = {
    "https://static.simonwillison.net/static/2026/glm-5.2-pelican.svg": ("GLM-5.2", "2026-06-17"),
    "https://static.simonwillison.net/static/2025/gemini-2.5-flash-preview-05-20-animated.svg": ("gemini-2.5-flash-preview-05-20", "2025-05-20"),
    "https://static.simonwillison.net/static/2025/pelican-claude-3.7-sonnet.svg": ("claude-3-7-sonnet", "2025-02-24"),
    "https://static.simonwillison.net/static/2025/pelican-claude-3.7-sonnet-thinking.svg": ("claude-3-7-sonnet-thinking", "2025-02-24"),
    "https://static.simonwillison.net/static/2025/gemma-3-pelican.svg": ("gemma-3-27b-it", "2025-03-12"),
    "https://static.simonwillison.net/static/2025/gemini-2.0-pro-exp-02-05.svg": ("gemini-2.0-pro-exp-02-05", "2025-02-05"),
    "https://static.simonwillison.net/static/2025/gemini-2.0-flash.svg": ("gemini-2.0-flash", "2025-02-05"),
    "https://static.simonwillison.net/static/2025/gemini-2.0-flash-lite-preview-02-05.svg": ("gemini-2.0-flash-lite-preview-02-05", "2025-02-05"),
    "https://static.simonwillison.net/static/2025/r1-peli-1.svg": ("deepseek-r1", "2025-01-20"),
    "https://static.simonwillison.net/static/2025/r1-peli-2.svg": ("deepseek-r1", "2025-01-20"),
    "https://static.simonwillison.net/static/2025/phi4-pelican.svg": ("phi-4", "2025-01-08"),
    "https://static.simonwillison.net/static/2024/pelican-bicycle-llama.svg": ("llama-3.3-70b-instruct", "2024-12-09"),
    "https://static.simonwillison.net/static/2024/gemini-exp-1206.svg": ("gemini-exp-1206", "2024-12-06"),
    "https://static.simonwillison.net/static/2024/qwq-pelican.svg": ("qwq-32b-preview", "2024-11-27"),
    "https://static.simonwillison.net/static/2024/gemini-exp-1121.svg": ("gemini-exp-1121", "2024-11-22"),
    "https://static.simonwillison.net/static/2024/qwen-pelican.svg": ("qwen2.5-coder-32b-instruct", "2024-11-12"),
    "https://static.simonwillison.net/static/2024/pelican-bicycles/o1-preview.svg": ("o1-preview", "2024-10-25"),
    "https://static.simonwillison.net/static/2024/pelican-bicycles/o1-mini.svg": ("o1-mini", "2024-10-25"),
    "https://static.simonwillison.net/static/2024/pelican-bicycles/gpt-4o.svg": ("gpt-4o", "2024-10-25"),
}


def is_multi_model(name: str) -> bool:
    s = name.strip()
    if not s or len(s) > 100:
        return True
    low = s.lower()
    for pat in MULTI_MODEL_PATTERNS:
        if re.search(pat, low):
            return True
    # Two distinct models separated by " / " (spaces around slash)
    if " / " in s:
        return True
    if low in {"model", "unknown", "various", "other", "none", "n/a"}:
        return True
    return False


def is_non_pelican(text: str) -> bool:
    low = (text or "").lower()
    return any(w in low for w in NON_PELICAN_WORDS)


def harvest_pelicanmap():
    cat = json.loads(PELICANMAP_CATALOG.read_text(encoding="utf-8"))
    items = cat["items"]
    candidates = []
    skipped_non_svg = 0
    skipped_non_pelican = 0
    skipped_multi = 0

    for it in items:
        fmt = (it.get("format") or "").lower()
        orig_form = (it.get("originalForm") or "").lower()
        media = it.get("media") or []

        # Must be SVG-benchmark category (format == svg, or svg in originalForm, or has .svg media)
        has_svg_media = any(str(m.get("src", "")).split("?")[0].lower().endswith(".svg") for m in media)
        if fmt != "svg" and "svg" not in orig_form and not has_svg_media:
            skipped_non_svg += 1
            continue

        # Exclude non-pelican derivatives
        if is_non_pelican(it.get("promptCategory")) or is_non_pelican(it.get("title")):
            skipped_non_pelican += 1
            continue

        raw_model = (it.get("model") or "").strip()
        if is_multi_model(raw_model):
            skipped_multi += 1
            continue

        # Exclude explicit grid/collage originals that have no individual svg
        if orig_form in ("svg-grid", "svg-static-grid") and not has_svg_media:
            skipped_multi += 1
            continue

        svg_urls = []
        raster_urls = []
        for m in media:
            src = (m.get("src") or "").strip()
            if not src:
                continue
            full_url = PELICANMAP_HOST + src if src.startswith("/") else src
            ext = Path(src.split("?")[0]).suffix.lower()
            if ext == ".svg":
                svg_urls.append(full_url)
            elif ext in (".png", ".jpg", ".jpeg", ".webp"):
                raster_urls.append(full_url)

        if not svg_urls and not raster_urls:
            continue

        author = (it.get("author") or "").strip()
        source_url = (it.get("sourceUrl") or "").strip()
        is_simon = (
            "simon" in author.lower()
            or "simonwillison.net" in source_url.lower()
            or "simonw/" in source_url.lower()
        )

        # Infer effort from title/notes/filename if present
        effort = ""
        blob = f"{it.get('title', '')} {it.get('notes', '')} {' '.join(svg_urls + raster_urls)}".lower()
        for eff in ("xhigh", "max", "high", "medium", "low", "minimal", "none"):
            if re.search(rf"(?:^|[\s_\-(]){eff}(?:$|[\s_\-).])", blob):
                effort = eff
                break

        candidates.append({
            "candidate_id": f"pmap:{it.get('id')}",
            "origin": "pelicanmap",
            "raw_model": raw_model,
            "title": (it.get("title") or "").strip(),
            "author": author,
            "is_simon": is_simon,
            "date": (it.get("date") or "").strip(),
            "source_type": (it.get("source") or "").strip(),
            "source_url": source_url,
            "pelicanmap_url": (it.get("url") or "").strip(),
            "prompt_category": (it.get("promptCategory") or "").strip(),
            "original_form": (it.get("originalForm") or "").strip(),
            "effort": effort,
            "has_svg": len(svg_urls) > 0,
            "svg_url": svg_urls[0] if svg_urls else None,
            "local_svg_path": None,
            "raster_url": raster_urls[0] if raster_urls else None,
        })

    print(f"pelicanmap: kept {len(candidates)} | skipped_non_svg={skipped_non_svg} skipped_non_pelican={skipped_non_pelican} skipped_multi={skipped_multi}")
    return candidates


def clean_grid_header(text: str) -> str:
    # Remove pricing info like "$8 input · $40 output / 1M tokens"
    s = re.split(r"\$\d", text)[0].strip()
    s = re.sub(r"\s+", " ", s).strip(" -·|")
    return s


def harvest_simon_static_grids():
    candidates = []
    grid_dates = {
        "gemini-4-carbon-neon-hydrogen.html": "2026-11-18",
        "openai-pelicans-november-2026.html": "2026-11-17",
        "gemini-4-pelicans.html": "2026-11-12",
        "openai-pelicans-october-2026.html": "2026-10-26",
        "gpt-pelicans-grid.html": "2026-09-22",
        "claude-pelicans-grid.html": "2026-09-22",
        "gpt-6-and-5.6-pelicans.html": "2026-09-04",
        "gpt-5.6-pelicans.html": "2026-07-09",
        "hy3-preview-pelican.html": "2026-07-06",
        "glm-5.1-pelican-fixed.html": "2026-04-07",
    }

    for html_path in sorted(SIMON_STATIC_DIR.glob("*.html")):
        fname = html_path.name
        date = grid_dates.get(fname, "2026-01-01")
        source_url = f"https://static.simonwillison.net/static/2026/{fname}"
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8", errors="replace"), "html.parser")

        # Case 1: standalone inline SVG pages
        if fname in ("hy3-preview-pelican.html", "glm-5.1-pelican-fixed.html"):
            svg = soup.find("svg")
            if svg:
                raw_model = "hy3-preview" if "hy3" in fname else "glm-5.1"
                svg_bytes = str(svg).encode("utf-8")
                out_svg = SIMON_EXTRACTED_DIR / f"{fname.replace('.html', '')}.svg"
                out_svg.write_bytes(svg_bytes)
                candidates.append({
                    "candidate_id": f"simon-static:{fname}",
                    "origin": "simon_static_html",
                    "raw_model": raw_model,
                    "title": f"{raw_model} (Simon Willison)",
                    "author": "Simon Willison",
                    "is_simon": True,
                    "date": date,
                    "source_type": "simon_static",
                    "source_url": source_url,
                    "pelicanmap_url": "",
                    "prompt_category": "classic",
                    "original_form": "svg",
                    "effort": "",
                    "has_svg": True,
                    "svg_url": source_url,
                    "local_svg_path": str(out_svg),
                    "raster_url": None,
                })
            continue

        # Case 2: comparison grid table
        table = soup.find("table")
        if not table:
            continue
        headers = []
        thead = table.find("thead")
        header_row = thead.find("tr") if thead else table.find("tr")
        if header_row:
            headers = [clean_grid_header(th.get_text(" ", strip=True)) for th in header_row.find_all(["th", "td"])]

        tbody = table.find("tbody") or table
        rows = tbody.find_all("tr")
        for r_idx, tr in enumerate(rows):
            cells = tr.find_all(["th", "td"])
            if not cells or (thead is None and r_idx == 0):
                continue
            effort = cells[0].get_text(" ", strip=True).lower()
            for c_idx, cell in enumerate(cells[1:], start=1):
                if c_idx >= len(headers):
                    continue
                model_name = headers[c_idx]
                if not model_name:
                    continue
                img = cell.find("img", src=True)
                if not img:
                    continue
                src = img["src"]
                if not src.startswith("data:image/svg+xml;base64,"):
                    continue
                b64 = src.split(",", 1)[1]
                try:
                    svg_bytes = base64.b64decode(b64)
                except Exception:
                    continue
                slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", f"{fname[:-5]}__{model_name}__{effort}")
                out_svg = SIMON_EXTRACTED_DIR / f"{slug}.svg"
                out_svg.write_bytes(svg_bytes)
                candidates.append({
                    "candidate_id": f"simon-grid:{slug}",
                    "origin": "simon_static_grid",
                    "raw_model": model_name,
                    "title": f"{model_name} ({effort})",
                    "author": "Simon Willison",
                    "is_simon": True,
                    "date": date,
                    "source_type": "simon_static_grid",
                    "source_url": source_url,
                    "pelicanmap_url": "",
                    "prompt_category": "classic",
                    "original_form": "svg",
                    "effort": effort,
                    "has_svg": True,
                    "svg_url": source_url,
                    "local_svg_path": str(out_svg),
                    "raster_url": None,
                })

    print(f"simon_static_grids: extracted {len(candidates)} SVGs")
    return candidates


def harvest_simon_direct_svgs():
    # Also scan all 161 cached posts for any additional static.simonwillison.net/*.svg URLs
    posts = json.loads((BASE / "cache" / "posts_index.json").read_text(encoding="utf-8"))
    found_urls = dict(SIMON_DIRECT_SVG_MAP)
    for p in posts:
        pc = p.get("post_cache")
        if not pc or not Path(pc).exists():
            continue
        html = Path(pc).read_text(encoding="utf-8", errors="replace")
        for m in re.findall(r"https://static\.simonwillison\.net/[^\s\"'<>]+\.svg", html, re.I):
            if m in found_urls:
                continue
            if is_non_pelican(m) or "animated" in m.lower() or "recraft" in m.lower():
                continue
            # Derive raw_model from filename
            stem = Path(urlparse(m).path).stem
            found_urls[m] = (stem, p.get("date") or "")

    candidates = []
    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0 (compatible; PelicanDBBuilder/1.0)"})
    for url, (raw_model, date) in sorted(found_urls.items()):
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(urlparse(url).path).name)
        out_svg = SIMON_DIRECT_DIR / slug
        if not out_svg.exists() or out_svg.stat().st_size == 0:
            try:
                r = sess.get(url, timeout=20)
                if r.status_code == 200 and b"<svg" in r.content.lower():
                    out_svg.write_bytes(r.content)
                else:
                    print(f"  WARN skip direct svg {r.status_code}: {url}")
                    continue
            except Exception as e:
                print(f"  ERR direct svg {url}: {e}")
                continue
        candidates.append({
            "candidate_id": f"simon-direct:{slug}",
            "origin": "simon_direct_svg",
            "raw_model": raw_model,
            "title": f"{raw_model} (Simon Willison direct SVG)",
            "author": "Simon Willison",
            "is_simon": True,
            "date": date,
            "source_type": "simon_direct_svg",
            "source_url": url,
            "pelicanmap_url": "",
            "prompt_category": "classic",
            "original_form": "svg",
            "effort": "high" if "thinking" in raw_model.lower() else "",
            "has_svg": True,
            "svg_url": url,
            "local_svg_path": str(out_svg),
            "raster_url": None,
        })

    print(f"simon_direct_svgs: downloaded/cached {len(candidates)} SVGs")
    return candidates


def main():
    c_pmap = harvest_pelicanmap()
    c_grid = harvest_simon_static_grids()
    c_direct = harvest_simon_direct_svgs()
    all_c = c_pmap + c_grid + c_direct
    out = BASE / "cache" / "all_candidates.json"
    out.write_text(json.dumps(all_c, ensure_ascii=False, indent=2), encoding="utf-8")
    unique_raw = sorted(set(c["raw_model"] for c in all_c))
    print(f"TOTAL candidates: {len(all_c)} | unique raw_model strings: {len(unique_raw)}")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
