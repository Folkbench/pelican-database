import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_TAG = BASE_DIR / "cache" / "tag_pages"
CACHE_POSTS = BASE_DIR / "cache" / "posts"
CACHE_STATIC = BASE_DIR / "cache" / "simon_static"
CACHE_TAG.mkdir(parents=True, exist_ok=True)
CACHE_POSTS.mkdir(parents=True, exist_ok=True)
CACHE_STATIC.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; FolkbenchPelicanDB/1.0)"})

TAG_URL = "https://simonwillison.net/tags/pelican-riding-a-bicycle/"


def fetch_url(url: str, cache_path: Path, retries: int = 3, force: bool = False) -> str:
    if not force and cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path.read_text(encoding="utf-8", errors="replace")
    for attempt in range(retries):
        try:
            r = SESSION.get(url, timeout=30)
            r.raise_for_status()
            text = r.text
            cache_path.write_text(text, encoding="utf-8")
            return text
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}")


def fetch_all_tag_pages(refresh_pages: bool = False):
    pages_html = []
    page = 1
    while True:
        url = TAG_URL if page == 1 else f"{TAG_URL}?page={page}"
        html = fetch_url(url, CACHE_TAG / f"page_{page}.html", force=(refresh_pages or page == 1))
        pages_html.append((page, url, html))
        soup = BeautifulSoup(html, "html.parser")
        pag = soup.find("div", class_="pagination")
        next_link = None
        if pag:
            for a in pag.find_all("a", href=True):
                if "next" in a.get_text(" ", strip=True).lower():
                    next_link = a["href"]
                    break
        if not next_link:
            break
        page += 1
        time.sleep(0.2)
    return pages_html


def parse_segments(pages_html):
    tag_desc_html = None
    items = []
    seen_keys = set()

    for page_num, page_url, html in pages_html:
        soup = BeautifulSoup(html, "html.parser")
        primary = soup.find(id="primary")
        if page_num == 1:
            td = primary.find("div", class_="tag-description")
            if td:
                tag_desc_html = str(td)

        current_year = None
        for child in primary.find_all(recursive=False):
            classes = child.get("class") or []
            if "blog-mixed-list-year" in classes:
                current_year = child.get_text(strip=True)
                continue
            if "segment" not in classes:
                continue

            item_type = "unknown"
            for t in ("entry", "blogmark", "quotation", "note", "beat"):
                if t in classes:
                    item_type = t
                    break

            # Find permalink on simonwillison.net
            permalink = None
            title = ""
            date_str = ""

            # Look for heading or permalink anchor (must have slug: /YYYY/Mon/DD/slug/)
            slug_re = re.compile(r"^/\d{4}/[A-Z][a-z]{2}/\d{1,2}/[^/#?]+/?$")
            h = child.find(["h2", "h3", "h4"])
            if h:
                title = h.get_text(" ", strip=True)
                a = h.find("a", href=True)
                if a and slug_re.match(a["href"]):
                    permalink = urljoin("https://simonwillison.net", a["href"])

            # Look for metadata footer / permalink '#' or time link with slug
            for a in child.find_all("a", href=True):
                href = a["href"]
                txt = a.get_text(" ", strip=True)
                if re.match(r"^/\d{4}/[A-Z][a-z]{2}/\d{1,2}/$", href) and not date_str:
                    date_str = txt
                if slug_re.match(href):
                    full = urljoin("https://simonwillison.net", href)
                    if txt in ("#", "Permalink") or re.search(r"\d:\d\d\s*(?:am|pm)", txt, re.I):
                        permalink = full
                    elif not permalink:
                        permalink = full

            # Fallback title from first strong/a/p
            if not title:
                first_a = child.find("a")
                if first_a:
                    title = first_a.get_text(" ", strip=True)
                else:
                    title = child.get_text(" ", strip=True)[:100]

            # Extract date from permalink if available
            iso_date = ""
            if permalink:
                m = re.search(r"/(\d{4})/([A-Z][a-z]{2})/(\d{1,2})/", permalink)
                if m:
                    months = {
                        "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                        "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                        "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
                    }
                    iso_date = f"{m.group(1)}-{months.get(m.group(2), '00')}-{int(m.group(3)):02d}"

            key = permalink or hashlib.md5(str(child).encode("utf-8")).hexdigest()
            if key in seen_keys:
                continue
            seen_keys.add(key)

            items.append({
                "index": len(items) + 1,
                "page": page_num,
                "year": current_year,
                "date": iso_date,
                "date_raw": date_str,
                "type": item_type,
                "classes": classes,
                "title": title,
                "permalink": permalink,
                "segment_html": str(child),
            })

    return tag_desc_html, items


def cache_name_for_url(url: str) -> str:
    p = urlparse(url).path.strip("/").replace("/", "__")
    p = re.sub(r"[^a-zA-Z0-9._-]", "_", p)
    if not p:
        p = hashlib.md5(url.encode()).hexdigest()
    return p[:150] + ".html"


def fetch_post(item):
    url = item.get("permalink")
    if not url or not url.startswith("https://simonwillison.net/"):
        return item["index"], None, None
    fname = cache_name_for_url(url)
    fpath = CACHE_POSTS / fname
    try:
        html = fetch_url(url, fpath)
        return item["index"], str(fpath), len(html)
    except Exception as e:
        return item["index"], f"ERROR: {e}", 0


def sync_static_pelican_grids(items):
    """Discover and cache static.simonwillison.net/*.html pelican comparison grids."""
    grid_urls = set()
    for it in items:
        pc = it.get("post_cache")
        if not pc or not Path(pc).exists():
            continue
        html = Path(pc).read_text(encoding="utf-8", errors="replace")
        for u in re.findall(r"https://static\.simonwillison\.net/static/\d{4}/[a-zA-Z0-9._-]+\.html", html):
            low = u.lower()
            if any(k in low for k in ("pelican", "gemini-4-carbon", "gemini-4-pelican", "openai-pelican", "claude-pelican", "gpt-pelican")):
                if not any(b in low for b in ("possum", "opossum", "count-pelicans", "bbox")):
                    grid_urls.add(u)
    downloaded = 0
    for u in sorted(grid_urls):
        fname = u.split("/")[-1]
        fpath = CACHE_STATIC / fname
        if not fpath.exists() or fpath.stat().st_size == 0:
            try:
                fetch_url(u, fpath)
                downloaded += 1
            except Exception as e:
                print(f"  WARN static html {u}: {e}")
    print(f"Static pelican HTML grids: {len(grid_urls)} total ({downloaded} newly downloaded)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-all-pages", action="store_true", help="Re-fetch all tag pages instead of only page 1")
    args = parser.parse_args()

    print("Fetching tag pages...")
    pages_html = fetch_all_tag_pages(refresh_pages=args.refresh_all_pages)
    print(f"Fetched {len(pages_html)} tag pages.")

    tag_desc_html, items = parse_segments(pages_html)
    print(f"Parsed {len(items)} segments.")

    from collections import Counter
    print("Types:", Counter(x["type"] for x in items))

    print("Fetching full post pages (cached posts skipped)...")
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(fetch_post, it) for it in items]
        for fut in concurrent.futures.as_completed(futs):
            idx, fpath, length = fut.result()
            it = items[idx - 1]
            if fpath and str(fpath).startswith("ERROR:"):
                errors.append((idx, it["permalink"], fpath))
                it["post_cache"] = None
            else:
                it["post_cache"] = fpath
                it["post_html_len"] = length

    print(f"Done fetching posts. Errors: {len(errors)}")
    for e in errors:
        print("  ERR:", e)

    sync_static_pelican_grids(items)

    out_path = BASE_DIR / "cache" / "posts_index.json"
    (BASE_DIR / "cache" / "posts_full.json").write_text(
        json.dumps({"tag_description_html": tag_desc_html, "items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary = [{k: v for k, v in it.items() if k != "segment_html"} for it in items]
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
