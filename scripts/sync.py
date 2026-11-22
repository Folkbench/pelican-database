"""End-to-end incremental sync pipeline for Folkbench/pelican-database."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent.parent
CACHE = BASE / "cache"
SCRIPTS = BASE / "scripts"
PELICANMAP_DIR = CACHE / "pelicanmap"
MDEV_CACHE = CACHE / "models_dev.json"


def run_step(cmd: list[str], desc: str):
    print(f"\n==> {desc}: {' '.join(cmd)}", flush=True)
    res = subprocess.run(cmd, cwd=str(BASE))
    if res.returncode != 0:
        raise SystemExit(f"Step failed ({res.returncode}): {desc}")


def refresh_models_dev():
    CACHE.mkdir(parents=True, exist_ok=True)
    print("\n==> Fetching latest models.dev/api.json...", flush=True)
    r = requests.get("https://models.dev/api.json", headers={"User-Agent": "FolkbenchPelicanDB/1.0"}, timeout=30)
    r.raise_for_status()
    data = r.json()
    MDEV_CACHE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {MDEV_CACHE} ({len(data)} providers)", flush=True)


def refresh_pelicanmap():
    CACHE.mkdir(parents=True, exist_ok=True)
    if (PELICANMAP_DIR / ".git").exists():
        run_step(["git", "-C", str(PELICANMAP_DIR), "pull", "--ff-only", "--depth", "1"], "Update UncleK/pelicanmap")
    else:
        run_step(
            ["git", "clone", "--depth", "1", "https://github.com/UncleK/pelicanmap.git", str(PELICANMAP_DIR)],
            "Clone UncleK/pelicanmap",
        )


def main():
    parser = argparse.ArgumentParser(description="Incrementally sync Folkbench Pelican Database")
    parser.add_argument("--refresh-all-pages", action="store_true", help="Re-fetch all Simon Willison tag pages")
    parser.add_argument("--force-render", action="store_true", help="Force re-render all PNGs")
    args = parser.parse_args()

    refresh_models_dev()
    refresh_pelicanmap()

    step1 = [sys.executable, str(SCRIPTS / "01_fetch_all.py")]
    if args.refresh_all_pages:
        step1.append("--refresh-all-pages")
    run_step(step1, "Fetch Simon Willison pelican-riding-a-bicycle posts & grids")
    run_step([sys.executable, str(SCRIPTS / "02_harvest_sources.py")], "Harvest all candidate specimens")
    run_step([sys.executable, str(SCRIPTS / "03_map_models_dev.py")], "Align model IDs to models.dev")
    run_step([sys.executable, str(SCRIPTS / "04_select_and_download.py")], "Select & download representative SVG/raster files")

    step5 = ["node", str(SCRIPTS / "05_render_pngs.mjs")]
    if args.force_render:
        step5.append("--force")
    run_step(step5, "Render new/changed SVGs and convert rasters to PNG")

    run_step([sys.executable, str(SCRIPTS / "06_build_database.py")], "Build catalog.json, pelicans.sqlite, and READMEs")
    print("\nSync completed successfully!")


if __name__ == "__main__":
    main()
