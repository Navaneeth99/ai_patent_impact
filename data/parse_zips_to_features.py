#!/usr/bin/env python3
"""
Stream-parse weekly USPTO APPXML zips into compact per-publication feature
Parquet files.

For each `.zip` in --input-dir, this script:
  1. Opens the archive and reads the single contained .xml into memory.
  2. Splits/parses the concatenated weekly XML via parse_uspto_xml
     (reused from ../upsto-parse).
  3. Converts each parsed patent dict into a small feature row -- claim
     counts, claim length stats, description length, reference counts,
     CPC sections, attorney info, and two cheap text-quality proxies on
     the first independent claim.
  4. Writes one Parquet per weekly zip into --output-dir
     (default: ./features).

The job is idempotent: a week is skipped if its Parquet already exists
and is non-empty (use --overwrite to force re-parse). Revision archives
(ipaYYMMDD_r1.zip, _r2.zip, ...) are skipped when the base
ipaYYMMDD.zip is present; otherwise the highest-numbered _rN is used.

Per-publication feature columns are documented in features_README.md
next to this file.
"""
from __future__ import annotations

import argparse
import gc
import logging
import os
import re
import sys
import time
import zipfile
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_PKG_DIR = _THIS_DIR.parent / "upsto-parse"
if str(_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(_PKG_DIR))

import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

from parse_uspto_xml.parse_patent import load_from_data  # noqa: E402

logger = logging.getLogger("parse_zips_to_features")


# ---------------------------------------------------------------------------
# Feature derivation helpers
# ---------------------------------------------------------------------------

# Heuristic dependent-claim detector. A claim is "dependent" if it references
# another claim by number or refers to the/a preceding claim. False-positive
# rate is low for USPTO claim language; tighten later if needed.
_DEP_RE = re.compile(
    r"\b(?:claim\s+\d+"
    r"|preceding\s+claims?"
    r"|any\s+(?:one\s+)?of\s+claims?"
    r"|claims?\s+\d+\s*[\-,]\s*\d+)\b",
    re.IGNORECASE,
)


def is_dependent_claim(claim_text: str) -> bool:
    if not claim_text:
        return False
    return _DEP_RE.search(claim_text) is not None


def _count_syllables(word: str) -> int:
    word = word.lower()
    if not word:
        return 0
    n = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in "aeiouy"
        if is_vowel and not prev_vowel:
            n += 1
        prev_vowel = is_vowel
    if word.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def flesch_reading_ease(text: str) -> float | None:
    if not text:
        return None
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    words = re.findall(r"[A-Za-z]+", text)
    if not sentences or not words:
        return None
    syllables = sum(_count_syllables(w) for w in words)
    return (
        206.835
        - 1.015 * (len(words) / len(sentences))
        - 84.6 * (syllables / len(words))
    )


def unique_token_ratio(text: str) -> float | None:
    tokens = re.findall(r"[A-Za-z]+", (text or "").lower())
    if not tokens:
        return None
    return len(set(tokens)) / len(tokens)


def _word_count(text: str) -> int:
    return len(text.split()) if text else 0


def _iso_date(yyyymmdd: str | None) -> str | None:
    if not yyyymmdd:
        return None
    s = yyyymmdd.strip()
    if len(s) != 8 or not s.isdigit():
        return None
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


_RELATED_DOC_TYPES = {
    "continuation",
    "division",
    "continuation-in-part",
    "reissue",
    "substitution",
    "provisional",
    "prior",
    "priority-claim",
}


def compute_features(patent: dict, source_zip: str) -> dict:
    claims = patent.get("claims") or []
    descriptions = patent.get("descriptions") or []
    abstract = patent.get("abstract") or []

    claim_word_counts = [_word_count(c) for c in claims]
    indep_flags = [not is_dependent_claim(c) for c in claims]
    n_total = len(claims)
    n_indep = sum(1 for f in indep_flags if f)
    n_dep = n_total - n_indep
    claim_words_mean = (sum(claim_word_counts) / n_total) if n_total else 0.0
    claim_words_max = max(claim_word_counts) if claim_word_counts else 0

    first_indep_idx = next((i for i, f in enumerate(indep_flags) if f), None)
    first_indep_text = claims[first_indep_idx] if first_indep_idx is not None else ""
    claim_words_first_indep = _word_count(first_indep_text)
    flesch_first = flesch_reading_ease(first_indep_text)
    utr_first = unique_token_ratio(first_indep_text)

    description_text = "\n".join(descriptions)
    description_paragraphs = sum(1 for ln in description_text.splitlines() if ln.strip())
    description_words = _word_count(description_text)

    abstract_text = "\n".join(abstract)
    abstract_words = _word_count(abstract_text)

    refs = patent.get("referential_documents") or []
    n_refs_patent = sum(1 for r in refs if r.get("document_type") == "patent-reference")
    n_refs_examiner = sum(
        1
        for r in refs
        if r.get("document_type") == "patent-reference" and r.get("cited_by_examiner")
    )
    n_refs_applicant = max(0, n_refs_patent - n_refs_examiner)
    n_other_citations = sum(
        1 for r in refs if r.get("document_type") == "other-reference"
    )
    n_related_docs = sum(
        1 for r in refs if r.get("document_type") in _RELATED_DOC_TYPES
    )

    def _join(seq: list[str] | None) -> str:
        return "|".join(seq) if seq else ""

    return {
        "publication_number": patent.get("publication_number") or "",
        "application_number": patent.get("application_number") or "",
        "application_type": patent.get("application_type") or "",
        "application_status": patent.get("application_status") or "",
        "publication_date": _iso_date(patent.get("publication_date")),
        "application_date": _iso_date(patent.get("application_date")),
        "grant_date": _iso_date(patent.get("grant_date")),
        "title": (patent.get("publication_title") or "")[:512],
        "n_inventors": len(patent.get("authors") or []),
        "n_applicant_orgs": len(patent.get("organizations") or []),
        "n_attorneys": len(patent.get("attorneys") or []),
        "attorney_organizations": _join(patent.get("attorney_organizations")),
        "sections": _join(patent.get("sections")),
        "section_classes": _join(patent.get("section_classes")),
        "section_class_subclass_groups": _join(
            patent.get("section_class_subclass_groups")
        ),
        "n_claims_total": n_total,
        "n_claims_independent": n_indep,
        "n_claims_dependent": n_dep,
        "claim_words_mean": float(claim_words_mean),
        "claim_words_max": int(claim_words_max),
        "claim_words_first_indep": int(claim_words_first_indep),
        "description_words": int(description_words),
        "description_paragraphs": int(description_paragraphs),
        "abstract_words": int(abstract_words),
        "n_refs_total": len(refs),
        "n_refs_examiner_flagged": int(n_refs_examiner),
        "n_refs_applicant": int(n_refs_applicant),
        "n_other_citations": int(n_other_citations),
        "n_related_docs": int(n_related_docs),
        "flesch_first_indep_claim": flesch_first,
        "unique_token_ratio_first_indep_claim": utr_first,
        "source_zip": source_zip,
    }


# ---------------------------------------------------------------------------
# Parquet schema (kept stable so weekly files concatenate cleanly)
# ---------------------------------------------------------------------------

SCHEMA = pa.schema(
    [
        ("publication_number", pa.string()),
        ("application_number", pa.string()),
        ("application_type", pa.string()),
        ("application_status", pa.string()),
        ("publication_date", pa.string()),
        ("application_date", pa.string()),
        ("grant_date", pa.string()),
        ("title", pa.string()),
        ("n_inventors", pa.int32()),
        ("n_applicant_orgs", pa.int32()),
        ("n_attorneys", pa.int32()),
        ("attorney_organizations", pa.string()),
        ("sections", pa.string()),
        ("section_classes", pa.string()),
        ("section_class_subclass_groups", pa.string()),
        ("n_claims_total", pa.int32()),
        ("n_claims_independent", pa.int32()),
        ("n_claims_dependent", pa.int32()),
        ("claim_words_mean", pa.float32()),
        ("claim_words_max", pa.int32()),
        ("claim_words_first_indep", pa.int32()),
        ("description_words", pa.int32()),
        ("description_paragraphs", pa.int32()),
        ("abstract_words", pa.int32()),
        ("n_refs_total", pa.int32()),
        ("n_refs_examiner_flagged", pa.int32()),
        ("n_refs_applicant", pa.int32()),
        ("n_other_citations", pa.int32()),
        ("n_related_docs", pa.int32()),
        ("flesch_first_indep_claim", pa.float32()),
        ("unique_token_ratio_first_indep_claim", pa.float32()),
        ("source_zip", pa.string()),
    ]
)


# ---------------------------------------------------------------------------
# Per-zip pipeline
# ---------------------------------------------------------------------------

# Weekly APPXML is usually ipaYYMMDD.zip; legacy bulk sometimes uses paYYMMDD.zip.
_WEEK_STEM_RE = re.compile(r"^(ipa|pa)(\d{6})(?:_r\d+)?$", re.IGNORECASE)


def base_week_stem(zip_name: str) -> str | None:
    """Return canonical week stem (e.g. ipa260507 or pa030501) for a zip name, or None."""
    stem = Path(zip_name).stem
    m = _WEEK_STEM_RE.match(stem)
    return (m.group(1) + m.group(2)).lower() if m else None


def select_zips_per_week(zip_paths: list[Path]) -> list[Path]:
    """Pick one zip per week: prefer base ipaYYMMDD.zip, else highest _rN."""
    by_week: dict[str, list[Path]] = {}
    for p in zip_paths:
        week = base_week_stem(p.name)
        if not week:
            continue
        by_week.setdefault(week, []).append(p)

    chosen: list[Path] = []
    for week, paths in by_week.items():
        base = next((p for p in paths if Path(p.name).stem.lower() == week), None)
        if base is not None:
            chosen.append(base)
        else:
            paths.sort(key=lambda p: p.name)
            chosen.append(paths[-1])
    chosen.sort(key=lambda p: p.name)
    return chosen


def parse_one_zip(
    zip_path: Path,
    out_dir: Path,
    overwrite: bool = False,
    batch_size: int = 50,
    limit: int | None = None,
) -> tuple[int, float]:
    """Parse one weekly zip into a Parquet file. Returns (n_rows, elapsed_s)."""
    week = base_week_stem(zip_path.name)
    if not week:
        logger.warning("Skipping %s: unrecognized name", zip_path.name)
        return 0, 0.0
    out_path = out_dir / f"{week}.parquet"
    if out_path.exists() and out_path.stat().st_size > 0 and not overwrite:
        logger.info("Skip %s (exists)", out_path.name)
        return 0, 0.0

    t0 = time.monotonic()
    with zipfile.ZipFile(zip_path) as zf:
        xml_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        if not xml_names:
            logger.warning("No .xml found inside %s", zip_path.name)
            return 0, 0.0
        # Each weekly APPXML zip contains exactly one big concatenated XML.
        xml_text = zf.read(xml_names[0]).decode("utf-8", errors="replace")

    rows: list[dict] = []

    def push(patents: list[dict]) -> None:
        for p in patents:
            try:
                rows.append(compute_features(p, source_zip=zip_path.name))
            except Exception:
                logger.exception(
                    "Feature compute failed for %s in %s",
                    p.get("publication_number"),
                    zip_path.name,
                )

    load_from_data(
        xml_text,
        filename=zip_path.name,
        push_to_func=push,
        batch_size=batch_size,
        max_patents=limit,
        keep_log=False,
    )

    # Free the huge XML string before serialising rows.
    del xml_text
    gc.collect()

    if not rows:
        logger.warning("No rows parsed from %s", zip_path.name)
        return 0, time.monotonic() - t0

    table = pa.Table.from_pylist(rows, schema=SCHEMA)
    tmp_path = out_path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp_path, compression="snappy")
    os.replace(tmp_path, out_path)
    elapsed = time.monotonic() - t0
    logger.info(
        "Wrote %s (%d rows, %.1fs, %.0f rows/s)",
        out_path.name,
        len(rows),
        elapsed,
        len(rows) / max(elapsed, 1e-6),
    )
    return len(rows), elapsed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--input-dir",
        default=str(_THIS_DIR / "appxml_zips"),
        help="Directory of weekly APPXML zips (default: ./appxml_zips).",
    )
    ap.add_argument(
        "--output-dir",
        default=str(_THIS_DIR / "features"),
        help="Directory for per-week .parquet files (default: ./features).",
    )
    ap.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-parse weeks even when their Parquet already exists.",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap publications per zip (useful for smoke tests).",
    )
    ap.add_argument(
        "--max-zips",
        type=int,
        default=None,
        help="Only process the first N selected weekly zips.",
    )
    ap.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Optional list of zip file names to restrict to.",
    )
    ap.add_argument("--batch-size", type=int, default=50)
    ap.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel weeks via multiprocessing (default: 1).",
    )
    ap.add_argument("--log-level", default="INFO")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    in_dir = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_zips = sorted(in_dir.glob("*.zip"))
    selected = select_zips_per_week(all_zips)
    if args.only:
        only_set = set(args.only)
        selected = [p for p in selected if p.name in only_set]
    if args.max_zips is not None:
        selected = selected[: args.max_zips]

    if not selected:
        logger.error("No zips selected from %s", in_dir)
        return 1

    logger.info("Processing %d zip(s) from %s", len(selected), in_dir)

    total_rows = 0
    total_elapsed = 0.0
    if args.workers > 1:
        import multiprocessing as mp

        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=args.workers) as pool:
            results = pool.starmap(
                parse_one_zip,
                [
                    (p, out_dir, args.overwrite, args.batch_size, args.limit)
                    for p in selected
                ],
            )
        for n_rows, dt in results:
            total_rows += n_rows
            total_elapsed += dt
    else:
        for p in selected:
            try:
                n_rows, dt = parse_one_zip(
                    p,
                    out_dir,
                    overwrite=args.overwrite,
                    batch_size=args.batch_size,
                    limit=args.limit,
                )
            except Exception:
                logger.exception("Failed on %s", p.name)
                continue
            total_rows += n_rows
            total_elapsed += dt

    logger.info(
        "Done. total_rows=%d, total_parse_time=%.1fs", total_rows, total_elapsed
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
