# APPXML feature pipeline

Impact-of-AI research uses **published application full text** (weekly IPA / APPXML zips). This folder holds download helpers, zips (`appxml_zips/`), per-week Parquet features (`features/`), and analysis output.

## Quick start

1. Put USPTO weekly zips in [`appxml_zips/`](appxml_zips/) (e.g. `ipa260507.zip`).
2. Install deps: `pip install -r requirements.txt` and install the parser package `pip install -e ../upsto-parse` (needs `beautifulsoup4`, `lxml` from there).
3. Extract features:

   ```bash
   python parse_zips_to_features.py --input-dir appxml_zips --output-dir features
   ```

   Re-run is safe: existing non-empty `features/ipaYYMMDD.parquet` files are skipped unless you pass `--overwrite`.

4. Aggregate and chart:

   ```bash
   python analyze_features.py --features-dir features
   ```

   Writes `charts/`, `sanity.json`, `distributions.csv`, `cohort_diff.csv`, and `findings.md` in **this directory** (override with `--output-dir`).

## Documentation

- **Feature columns:** [features_README.md](features_README.md)
- **What APPXML cannot measure (examiner workload, OA counts, AI ground truth):** [LIMITATIONS.md](LIMITATIONS.md)

## Optional flags

- `parse_zips_to_features.py`: `--limit N` (smoke test), `--workers N` (parallel weeks), `--only ipa260507.zip`
- `analyze_features.py`: `--application-type ""` to include all application types; cohort years via `--pre-start`, `--post-start`, etc.
