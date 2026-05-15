Parse USPTO
===========

Python tools for **patent application publication XML** (Red Book / ICE, v4.x such as `us-patent-application-v46`), including **full body text** (abstract, description, claims) and optional PostgreSQL export.

## Requirements

- Python **3.10+**
- USPTO **API key** for bulk download via the Open Data Portal API ([API catalog](https://developer.uspto.gov/api-catalog/bulk-search-and-download)). Set `USPTO_API_KEY` or pass `--api-key`.

Install:

```bash
cd pipeline/utils/upsto-parse
pip install -e .
```

Dependencies are listed in `requirements.txt` (PyPI package name **`beautifulsoup4`**, not `bs4`).

## Getting XML data

### Option A: Open Data Portal API (recommended for dated pulls)

List or download weekly **APPXML** zip files (same content family as bulk “Patent Application Full Text” XML):

```bash
set USPTO_API_KEY=your-key-here
parse-uspto-xml download --from-date 2025-05-13 --to-date 2026-05-13 --output-dir ./zips
```

Print discovered `.zip` URLs only (no download):

```bash
parse-uspto-xml download --from-date 2025-05-13 --to-date 2026-05-13 --print-urls
```

Equivalent `curl` for the product listing:

```bash
curl -sS -X GET \
  "https://api.uspto.gov/api/v1/datasets/products/APPXML?fileDataFromDate=2025-05-13&fileDataToDate=2026-05-13&includeFiles=true" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -H "x-api-key: %USPTO_API_KEY%"
```

Unzip the archives, then parse the contained `.xml` files (see below).

### Option B: Legacy bulk HTTPS (no API key)

Historical weekly/yearly files are still published under [USPTO bulk data](https://bulkdata.uspto.gov/) (see older `wget` examples in git history if needed).

## Parsing local XML

Multi-patent weeklies concatenate many `<?xml ...?>` documents in one file. The parser splits on that header, skips sequence listings (`sequence-cwu`), and extracts metadata plus text.

**Full patent text:** each parsed record includes:

- `abstract`, `descriptions`, `claims` — lists of strings (description and claims use structured extraction so nested tags such as `claim-text` are merged).
- `full_text` — single string: title, abstract, description, and claims for search or LLM input.

Parse into **JSON Lines** (no database):

```bash
parse-uspto-xml parse path/to/ipa260507.xml --jsonl out/patents.jsonl
```

Parse into **PostgreSQL** (same as before: `config/postgres.tsv` or `DATABASE_*` env vars):

```bash
parse-uspto-xml parse path/to/dir --postgres-config config/postgres.tsv
```

The console script ``parse-uspto-xml`` calls ``parse_uspto_xml.parse_patent:main`` (download and parse subcommands are implemented in ``parse_patent.py``).

You can also invoke the module directly (legacy: bare paths default to PostgreSQL):

```bash
python parse_uspto_xml/parse_patent.py file1.xml dir/
```

Scripts target **v4.0+** application/grant XML (2005–present). Sample layout: root `us-patent-application` with `description` / `claims` / `claim-text` as in weekly APPXML (e.g. `ipa260507.xml`).

## Database

See [config/README.md](config/README.md) for PostgreSQL setup. The in-memory dict may contain `full_text`; the provided SQL schema stores `abstract`, `description`, and `claims` columns — join those in SQL or extend the table if you want `full_text` persisted verbatim.
