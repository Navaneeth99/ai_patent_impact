# AI Patent Impact

Research on how **generative AI writing tools** (widely available from late 2022 onward) may affect **patent application drafting** and **USPTO examination**. This repository builds a corpus from USPTO **published application full text** (weekly APPXML / IPA zips), extracts structured features, and runs descriptive cohort analyses. Prosecution outcomes and examiner behavior require **additional datasets** not yet integrated (see [Data availability](#data-availability)).

> **Important:** USPTO filings are not labeled as “AI-drafted.” Research objectives below are framed as hypotheses to test by linking **drafting proxies** (and eventually text models) to **prosecution records**. Calendar-time comparisons around 2022–2023 are **not** proof that any filing used AI.

## Research objectives

1. **Examination timing** — Do AI-drafted patents take longer to examine (time to first action)?
2. **Examiner citations** — Do examiners cite fewer or less relevant references against AI-drafted applications?
3. **Grant rates** — Are AI-drafted patents granted at higher or lower rates?
4. **Post-examination intensity** — Do AI-drafted patents face more RCEs or appeals post-examination?

Operational definitions (to be fixed in analysis plans):

| Objective | Example outcomes | Typical covariates |
|-----------|------------------|--------------------|
| Time to first action | Days from filing (or publication) to first office action | Art unit, CPC, entity status, filing year |
| Citation quality / quantity | Count of 102/103 references in OAs; overlap with applicant citations; forward citations | Technology class, claim scope proxies |
| Grant rate | Allowance vs abandonment (or granted patent indicator) | Same as above + continuation family |
| RCE / appeal | Count of RCE filings; PTAB / appeal events | Pendency, rejection types |

**AI-drafted** will be proxied (not observed directly), e.g. application cohort (pre/post late 2022), text-based classifiers, or firm-level adoption measures—until labeled data exist.

## Repository layout

| Path | Purpose |
|------|---------|
| [`data/`](data/) | Download APPXML zips, extract features, run cohort analysis ([`data/README.md`](data/README.md)) |
| [`upsto-parse/`](upsto-parse/) | Parser for USPTO application/grant XML ([`upsto-parse/README.md`](upsto-parse/README.md)) |

### Quick start (current pipeline)

```bash
cd data
pip install -r requirements.txt
pip install -e ../upsto-parse

# 1. Place weekly zips in data/appxml_zips/ (e.g. ipa260507.zip)
python parse_zips_to_features.py --input-dir appxml_zips --output-dir features

# 2. Aggregate and compare pre/post cohorts
python analyze_features.py --features-dir features
```

Outputs include `findings.md`, `cohort_diff.csv`, and charts under `data/charts/`. See [`data/features_README.md`](data/features_README.md) for column definitions and [`data/LIMITATIONS.md`](data/LIMITATIONS.md) for what APPXML can and cannot measure.

## Current status

The **descriptive drafting layer** is in place: ~31k publications with claim/spec length, citation counts, and CPC-section cohort comparisons (pre 2018–2021 vs post 2023+ on `application_date`). See [`data/findings.md`](data/findings.md).

The **prosecution / examiner layer** for the four research objectives above is **not yet built**—no PAIR, PatEx, PatentsView, or office-action tables are loaded in this repo.

## Data availability

### In this repository today (APPXML → `data/features/`)

| Field / concept | Available? | Where / notes |
|-----------------|------------|---------------|
| Application number | Yes | Join key to external prosecution DBs |
| Application (filing) date | Yes | `application_date` — use for AI-adoption cohorts |
| Publication date | Yes | Lags filing ~18 months |
| Title, CPC sections | Yes | Coarse technology controls |
| Full specification & claims text | Parsed in memory only | Not stored in feature Parquet; export separately if needed |
| Applicant-side references | Yes | `n_refs_applicant`, `n_refs_total` on publication |
| Examiner-cited references (quality) | Weak / sparse | `n_refs_examiner_flagged` — mostly empty on IPA; better on grant XML (`ipg*`) |
| Office action timestamps | **No** | Not in APPXML |
| Time to first action | **No** | Requires prosecution history |
| Examiner ID | **No** | Not in APPXML |
| Art unit | **No** | Not in APPXML |
| Allowance / abandonment | **No** | IPA is pre-grant publication |
| RCE / appeal counts | **No** | Prosecution events only in PAIR-like sources |

### USPTO PAIR / Patent Center (not integrated)

[PAIR](https://portal.uspto.gov/pair/PublicPair) and [Patent Center](https://patentcenter.uspto.gov/) are the systems of record for **prosecution history** (office actions, responses, RCEs, appeals, transaction dates). This project does **not** currently ingest PAIR exports or Patent Center API pulls.

| Needed for objectives | In PAIR / prosecution bulk? | In this repo? |
|------------------------|-----------------------------|---------------|
| Filing date | Yes | Partially — `application_date` from APPXML (verify against PatEx) |
| Office action dates (e.g. first OA) | Yes | **No** |
| RCE / appeal events & dates | Yes | **No** |
| Examiner name / ID on application | Often in prosecution records | **No** |
| Art unit | Yes (assignment data) | **No** |
| OA prior art (examiner citations) | Yes (document text / metadata) | **No** — only applicant refs on publication |
| Grant / abandonment outcome | Yes (status + grant docs) | **No** |

**Practical bulk alternatives** (recommended for research scale):

- **[Patent Examination Research Dataset (PatEx)](https://www.uspto.gov/ip-policy/economic-research/research-datasets/patent-examination-research-dataset)** — PEDS-based; pendency, disposition, rejection/RCE-related fields; join on application number.
- **[Office Action Research Dataset](https://www.uspto.gov/ip-policy/economic-research/research-datasets/office-action-research-dataset)** — OA text and structured fields (bulk through 2017; newer years via APIs/other products).
- **USPTO Open Data Portal** — APIs for status and documents where bulk snapshots are insufficient.

### PatentsView (not integrated)

[PatentsView](https://patentsview.org/) provides **granted-patent** and related bibliographic tables (assignees, classifications, citations). Some releases include **examiner** and **art unit** on issued patents; prosecution-level timelines are **not** a substitute for PatEx/PAIR for objectives 1 and 4.

| Needed for objectives | PatentsView (typical) | In this repo? |
|------------------------|----------------------|---------------|
| Examiner ID / name | Often on **grants**; application-level examiner linkage varies by product/version | **No** |
| Art unit | Available on patent/application tables in bulk releases | **No** |
| Examiner experience | Derivable from examiner history (custom build) | **No** |
| Filing & OA timestamps | Limited; use PatEx/PEDS for prosecution | **No** |
| Grant rate / RCE / appeal | Partially via disposition proxies; prefer PatEx for prosecution events | **No** |

### Mapping objectives → data you still need

| Research objective | Minimum additional data |
|--------------------|-------------------------|
| Time to first action | PatEx or PAIR-derived event dates: filing + first OA (and ideally art unit) |
| Examiner citation quantity/relevance | Office Action Research Dataset and/or OA text; optionally grant XML for citation roles |
| Grant rates | PatEx disposition / PatentsView grant indicator linked by `application_number` |
| RCE / appeals | PatEx prosecution events or PAIR transaction history |

**Join strategy:** use `application_number` (and optionally `publication_number`) from `data/features/` to merge APPXML drafting proxies with PatEx, PatentsView, and OA datasets.

## Suggested roadmap

1. **Complete APPXML corpus** — fill missing weeks in `appxml_zips/`; refresh `analyze_features.py`.
2. **Optional text export** — store `abstract` / `claims` / `description` for NLP proxies of “AI-like” drafting.
3. **Ingest PatEx** — pendency, first OA timing, disposition, RCE-related fields.
4. **Ingest PatentsView (or USPTO examiner assignment bulk)** — art unit, examiner ID, experience covariates.
5. **Ingest OA corpus** — examiner-cited prior art for objective 2.
6. **Estimation** — cohort / DiD / examiner FE models with clear non-causal language until AI labels exist.

## License and attribution

USPTO bulk data are subject to [USPTO terms of use](https://www.uspto.gov/learning-and-resources/open-data-and-mobility). Cite the specific USPTO research datasets (PatEx, OARD, APPXML) used in published work.

## References

- [`data/LIMITATIONS.md`](data/LIMITATIONS.md) — honest scope of APPXML-only analyses  
- [`data/findings.md`](data/findings.md) — latest descriptive cohort results  
