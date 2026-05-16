#!/usr/bin/env python3
"""
Aggregate the per-week APPXML feature Parquet files into:

  1. Monthly time-series of key drafting-complexity metrics
     (``<output-dir>/charts/``; default: ``data/charts/`` when using defaults).
  2. Sanity checks: publications per week, missing weeks vs the USPTO
     Tuesday calendar, and overall distribution summaries
     (``<output-dir>/sanity.json`` and ``<output-dir>/distributions.csv``).
  3. Pre vs post late-2022 cohort comparison by CPC section, with
     bootstrap 95% CI on the difference of means
     (``<output-dir>/cohort_diff.csv``).
  4. An auto-generated ``findings.md`` in the output directory (default: the
     same folder as this script) that stitches headline numbers and chart links.

Cohorts use ``application_date`` (when the draft was written) rather
than ``publication_date`` (which lags ~18 months).

Defaults:
  pre        : application_date 2018-01-01 .. 2021-12-31
  transition : application_date 2022 (reported but not pooled)
  post       : application_date 2023-01-01 .. corpus end
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

logger = logging.getLogger("analyze_features")

OUTCOMES = [
    "n_claims_total",
    "n_claims_independent",
    "n_claims_dependent",
    "claim_words_mean",
    "claim_words_first_indep",
    "description_words",
    "description_paragraphs",
    "abstract_words",
    "n_refs_total",
    "n_related_docs",
    "flesch_first_indep_claim",
    "unique_token_ratio_first_indep_claim",
]

PRIMARY_OUTCOMES_FOR_PLOTS = [
    "n_claims_total",
    "n_claims_independent",
    "claim_words_first_indep",
    "description_words",
    "n_refs_total",
    "n_related_docs",
]

LOAD_COLUMNS = [
    "publication_number",
    "application_number",
    "publication_date",
    "application_date",
    "sections",
    "application_type",
    *OUTCOMES,
]


def load_features(features_dir: Path) -> pd.DataFrame:
    parquet_files = sorted(features_dir.glob("*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(f"No .parquet files under {features_dir}")
    logger.info("Loading %d parquet shards from %s", len(parquet_files), features_dir)
    dataset = ds.dataset([str(p) for p in parquet_files], format="parquet")
    available = set(dataset.schema.names)
    use_cols = [c for c in LOAD_COLUMNS if c in available]
    df = dataset.to_table(columns=use_cols).to_pandas()
    logger.info("Loaded %d rows, %d columns", len(df), len(df.columns))

    for col in ("application_date", "publication_date"):
        if col in df:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    df["primary_section"] = (
        df["sections"].fillna("").str.split("|").str[0].replace("", pd.NA)
    )
    return df


def assign_cohort(
    application_date: pd.Series,
    pre_start: int = 2018,
    pre_end: int = 2021,
    post_start: int = 2023,
) -> pd.Series:
    year = application_date.dt.year
    cohort = pd.Series("other", index=application_date.index, dtype="object")
    cohort.loc[(year >= pre_start) & (year <= pre_end)] = "pre"
    cohort.loc[year == 2022] = "transition"
    cohort.loc[year >= post_start] = "post"
    cohort.loc[application_date.isna()] = "unknown"
    return cohort


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------

def sanity_checks(df: pd.DataFrame, out_dir: Path) -> dict:
    pub = df.dropna(subset=["publication_date"])
    by_week = pub.groupby(pub["publication_date"].dt.to_period("W-WED")).size()

    rows_per_week = by_week.describe().to_dict()

    if not by_week.empty:
        all_weeks = pd.period_range(by_week.index.min(), by_week.index.max(), freq="W-WED")
        missing_weeks = sorted(set(all_weeks) - set(by_week.index))
        missing_weeks_iso = [str(p.start_time.date()) for p in missing_weeks[:20]]
        missing_weeks_count = len(missing_weeks)
    else:
        missing_weeks_iso = []
        missing_weeks_count = 0

    distributions = (
        df[OUTCOMES]
        .describe(percentiles=[0.05, 0.25, 0.5, 0.75, 0.95])
        .T
    )
    distributions.to_csv(out_dir / "distributions.csv")

    summary = {
        "n_rows": int(len(df)),
        "n_publications_per_week": rows_per_week,
        "missing_weeks_count": missing_weeks_count,
        "missing_weeks_first_20": missing_weeks_iso,
        "application_date_range": [
            str(df["application_date"].min()),
            str(df["application_date"].max()),
        ],
        "publication_date_range": [
            str(df["publication_date"].min()),
            str(df["publication_date"].max()),
        ],
        "rows_with_missing_application_date": int(df["application_date"].isna().sum()),
        "rows_with_missing_primary_section": int(df["primary_section"].isna().sum()),
    }
    with (out_dir / "sanity.json").open("w") as f:
        json.dump(summary, f, indent=2, default=str)
    return summary


# ---------------------------------------------------------------------------
# Monthly time-series plots
# ---------------------------------------------------------------------------

def monthly_means(df: pd.DataFrame, value_col: str, date_col: str) -> pd.Series:
    g = df.dropna(subset=[date_col, value_col]).copy()
    g["ym"] = g[date_col].dt.to_period("M").dt.to_timestamp()
    return g.groupby("ym")[value_col].mean()


def plot_monthly_trends(df: pd.DataFrame, charts_dir: Path) -> list[Path]:
    charts_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for col in PRIMARY_OUTCOMES_FOR_PLOTS:
        if col not in df.columns:
            continue
        s_app = monthly_means(df, col, "application_date")
        s_pub = monthly_means(df, col, "publication_date")

        fig, ax = plt.subplots(figsize=(10, 4.5))
        if not s_app.empty:
            ax.plot(s_app.index, s_app.values, label="by application date", linewidth=1.4)
        if not s_pub.empty:
            ax.plot(
                s_pub.index,
                s_pub.values,
                label="by publication date",
                linewidth=1.0,
                alpha=0.6,
            )
        # Reference line at ChatGPT release (2022-11-30) for visual context.
        ax.axvline(pd.Timestamp("2022-11-30"), color="gray", linestyle="--", linewidth=0.9)
        ax.text(
            pd.Timestamp("2022-11-30"),
            ax.get_ylim()[1],
            " 2022-11-30",
            color="gray",
            va="top",
            fontsize=8,
        )
        ax.set_title(f"Monthly mean: {col}")
        ax.set_xlabel("month")
        ax.set_ylabel(col)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best", fontsize=9)
        fig.tight_layout()
        out_path = charts_dir / f"trend_{col}.png"
        fig.savefig(out_path, dpi=130)
        plt.close(fig)
        written.append(out_path)
        logger.info("Wrote %s", out_path.name)
    return written


def plot_publications_per_week(df: pd.DataFrame, charts_dir: Path) -> Path | None:
    pub = df.dropna(subset=["publication_date"])
    if pub.empty:
        return None
    by_week = pub.groupby(pub["publication_date"].dt.to_period("W-WED")).size()
    by_week.index = by_week.index.to_timestamp()
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.plot(by_week.index, by_week.values, linewidth=1.0)
    ax.axvline(pd.Timestamp("2022-11-30"), color="gray", linestyle="--", linewidth=0.9)
    ax.set_title("Publications per USPTO week")
    ax.set_xlabel("week (Wednesday)")
    ax.set_ylabel("count")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out_path = charts_dir / "publications_per_week.png"
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# Cohort comparison
# ---------------------------------------------------------------------------

def bootstrap_diff_ci(
    a: np.ndarray, b: np.ndarray, n_boot: int = 2000, seed: int = 0
) -> tuple[float, float, float]:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a[~np.isnan(a)]
    b = b[~np.isnan(b)]
    if a.size == 0 or b.size == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    boot_means_a = a[rng.integers(0, a.size, size=(n_boot, a.size))].mean(axis=1)
    boot_means_b = b[rng.integers(0, b.size, size=(n_boot, b.size))].mean(axis=1)
    diffs = boot_means_b - boot_means_a
    return (
        float(b.mean() - a.mean()),
        float(np.percentile(diffs, 2.5)),
        float(np.percentile(diffs, 97.5)),
    )


def cohort_diff_table(
    df: pd.DataFrame,
    outcomes: list[str],
    n_boot: int = 2000,
    seed: int = 0,
) -> pd.DataFrame:
    df = df[df["cohort"].isin(["pre", "post"])].copy()
    df = df.dropna(subset=["primary_section"])

    rows = []
    sections = sorted(df["primary_section"].dropna().unique())
    for sect in sections + ["ALL"]:
        sub = df if sect == "ALL" else df[df["primary_section"] == sect]
        pre = sub[sub["cohort"] == "pre"]
        post = sub[sub["cohort"] == "post"]
        n_pre = len(pre)
        n_post = len(post)
        for col in outcomes:
            if col not in sub.columns:
                continue
            diff, lo, hi = bootstrap_diff_ci(
                pre[col].to_numpy(), post[col].to_numpy(), n_boot=n_boot, seed=seed
            )
            pre_mean = float(pre[col].mean()) if n_pre else float("nan")
            post_mean = float(post[col].mean()) if n_post else float("nan")
            rel = (
                (post_mean - pre_mean) / pre_mean
                if pre_mean not in (0.0, float("nan")) and not np.isnan(pre_mean)
                else float("nan")
            )
            rows.append(
                {
                    "section": sect,
                    "outcome": col,
                    "n_pre": n_pre,
                    "n_post": n_post,
                    "mean_pre": pre_mean,
                    "mean_post": post_mean,
                    "diff": diff,
                    "diff_ci_lo": lo,
                    "diff_ci_hi": hi,
                    "rel_change": rel,
                    "signif_95": bool(
                        not np.isnan(lo) and not np.isnan(hi) and (lo > 0 or hi < 0)
                    ),
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Markdown writeup
# ---------------------------------------------------------------------------

def write_findings_md(
    out_dir: Path,
    sanity: dict,
    cohort_df: pd.DataFrame,
    chart_paths: list[Path],
    pubs_chart: Path | None,
) -> Path:
    lines: list[str] = []
    lines.append("# AI tools and patent drafting -- descriptive findings\n")
    lines.append(
        "Auto-generated by `analyze_features.py`. Edit freely; rerun the script to refresh tables and charts.\n"
    )

    lines.append("## Corpus coverage\n")
    lines.append(f"- rows: **{sanity['n_rows']:,}**")
    lines.append(
        f"- application_date range: **{sanity['application_date_range'][0]}** to **{sanity['application_date_range'][1]}**"
    )
    lines.append(
        f"- publication_date range: **{sanity['publication_date_range'][0]}** to **{sanity['publication_date_range'][1]}**"
    )
    lines.append(
        f"- rows with missing application_date: {sanity['rows_with_missing_application_date']:,}"
    )
    lines.append(
        f"- rows with missing primary CPC section: {sanity['rows_with_missing_primary_section']:,}"
    )
    if pubs_chart is not None:
        lines.append("")
        lines.append(f"![Publications per week](charts/{pubs_chart.name})")
    lines.append("")

    lines.append("## Monthly trends in drafting-complexity proxies\n")
    lines.append(
        "Solid line: mean by **application date** (when the draft was written; the more meaningful axis for an AI-adoption story). Faint line: mean by **publication date** (USPTO release; lags ~18 months). Dashed grey vertical: 2022-11-30 (a convenient reference, not a treatment).\n"
    )
    for cp in chart_paths:
        lines.append(f"![{cp.stem}](charts/{cp.name})")
    lines.append("")

    lines.append("## Pre vs post cohort comparison\n")
    lines.append(
        "Cohorts defined on **application_date**: pre = 2018-2021, post = 2023+. 2022 is reported as a transition cohort but excluded from the comparison. Difference and 95% CI from a percentile bootstrap (B=2000). `signif_95=True` when the CI excludes zero.\n"
    )
    overall = cohort_df[cohort_df["section"] == "ALL"].copy()
    if not overall.empty:
        lines.append("### Overall (all CPC sections pooled)\n")
        cols = ["outcome", "n_pre", "n_post", "mean_pre", "mean_post", "diff", "diff_ci_lo", "diff_ci_hi", "rel_change", "signif_95"]
        lines.append(overall[cols].to_markdown(index=False, floatfmt=".3f"))
        lines.append("")

    by_section = cohort_df[cohort_df["section"] != "ALL"].copy()
    if not by_section.empty:
        lines.append("### By primary CPC section\n")
        cols = ["section", "outcome", "n_pre", "n_post", "mean_pre", "mean_post", "diff", "diff_ci_lo", "diff_ci_hi", "signif_95"]
        lines.append(by_section[cols].to_markdown(index=False, floatfmt=".3f"))
        lines.append("")

    lines.append("## How to interpret\n")
    lines.append(
        "- A positive `diff` on `n_claims_total`, `description_words`, or `claim_words_first_indep` means **post-2022 drafts are more verbose / claim-heavy on this corpus**, which is what one would expect if LLM-assisted drafting is lowering the cost of producing more text. It is **not** evidence that any particular filing was AI-written."
    )
    lines.append(
        "- A change in `n_refs_total` or `n_related_docs` reflects shifts in citation/continuation behaviour, not examiner search effort (which is not in this dataset)."
    )
    lines.append(
        "- Comparing within `section` is the minimal control for technology mix; for stronger inference also condition on `attorney_organizations` and assignee, and consult `LIMITATIONS.md`."
    )
    lines.append("")

    lines.append("See [LIMITATIONS.md](LIMITATIONS.md) for what this dataset can and cannot say about examiners.\n")

    findings_path = out_dir / "findings.md"
    findings_path.write_text("\n".join(lines), encoding="utf-8")
    return findings_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--features-dir",
        default=str(_THIS_DIR / "features"),
        help="Directory of per-week feature Parquet files.",
    )
    ap.add_argument(
        "--output-dir",
        default=str(_THIS_DIR),
        help="Directory to write charts/, sanity.json, cohort_diff.csv, findings.md (default: this data folder).",
    )
    ap.add_argument("--pre-start", type=int, default=2018)
    ap.add_argument("--pre-end", type=int, default=2021)
    ap.add_argument("--post-start", type=int, default=2023)
    ap.add_argument("--bootstrap-iters", type=int, default=2000)
    ap.add_argument("--bootstrap-seed", type=int, default=0)
    ap.add_argument(
        "--application-type",
        default="utility",
        help="Restrict to one application_type (default: utility). Pass empty string to keep all.",
    )
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    features_dir = Path(args.features_dir)
    out_dir = Path(args.output_dir)
    charts_dir = out_dir / "charts"
    out_dir.mkdir(parents=True, exist_ok=True)
    charts_dir.mkdir(parents=True, exist_ok=True)

    df = load_features(features_dir)
    if args.application_type:
        before = len(df)
        df = df[df["application_type"] == args.application_type].copy()
        logger.info(
            "Filtered to application_type=%s: %d -> %d rows",
            args.application_type,
            before,
            len(df),
        )

    df["cohort"] = assign_cohort(
        df["application_date"],
        pre_start=args.pre_start,
        pre_end=args.pre_end,
        post_start=args.post_start,
    )

    sanity = sanity_checks(df, out_dir)
    logger.info(
        "sanity: rows=%d, missing weeks=%d", sanity["n_rows"], sanity["missing_weeks_count"]
    )

    chart_paths = plot_monthly_trends(df, charts_dir)
    pubs_chart = plot_publications_per_week(df, charts_dir)

    cohort_df = cohort_diff_table(
        df,
        outcomes=OUTCOMES,
        n_boot=args.bootstrap_iters,
        seed=args.bootstrap_seed,
    )
    cohort_csv = out_dir / "cohort_diff.csv"
    cohort_df.to_csv(cohort_csv, index=False)
    logger.info("Wrote %s (%d rows)", cohort_csv.name, len(cohort_df))

    findings_path = write_findings_md(
        out_dir,
        sanity=sanity,
        cohort_df=cohort_df,
        chart_paths=chart_paths,
        pubs_chart=pubs_chart,
    )
    logger.info("Wrote %s", findings_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
