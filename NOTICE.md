# Rights, Provenance, and Attribution Notice

## Scope of the MIT License

The root [MIT License](LICENSE) applies to this repository's original pipeline scripts (`scripts/`), GitHub Actions workflows (`.github/`), database schema, catalog index structure, and original documentation (`README.md`, `README.zh.md`).

It does **not** relicense third-party SVG artworks, screenshots, prompts, model outputs, or upstream benchmark records indexed in this database. Those materials remain subject to their respective authors' rights and any applicable upstream licenses.

## Provenance & Upstream Attribution

Every model record in `catalog.json` and `pelicans.sqlite` preserves:
- Original source URL (`source_url`, `all_source_urls`)
- Original author / tester attribution (`author`, `tested_by_simon`)
- Publication / capture date (`date`)
- Upstream archive link (`pelicanmap_url`, `media_url`)
- Original raw model aliases (`raw_model_aliases`)

Primary upstream sources acknowledged and credited:
1. **Simon Willison** — Creator of the *"Generate an SVG of a pelican riding a bicycle"* LLM evaluation prompt ([simonwillison.net/tags/pelican-riding-a-bicycle](https://simonwillison.net/tags/pelican-riding-a-bicycle/), [simonw/pelican-bicycle](https://github.com/simonw/pelican-bicycle)).
2. **UncleK / Pelican Map** — Multilingual daily pelican archive ([github.com/UncleK/pelicanmap](https://github.com/UncleK/pelicanmap), MIT-licensed code & documentation, [NOTICE.md](https://github.com/UncleK/pelicanmap/blob/main/NOTICE.md)).
3. **models.dev** — Open canonical AI model ID and metadata registry ([models.dev](https://models.dev), [anomalyco/models.dev](https://github.com/anomalyco/models.dev)).
4. **Community Benchmarks & Researchers** — Tihu, Pelican Zoo, Museum of Models, Pelicans.wtf, Pelican Benchmark, and individual contributors whose original links are preserved per record.

## Attribution Corrections & Removal Requests

If you are a rights holder or original author and would like an attribution corrected or a specific sample updated/removed, please [open an issue](https://github.com/Folkbench/pelican-database/issues/new) with the `model_id`, source URL, and requested change.
