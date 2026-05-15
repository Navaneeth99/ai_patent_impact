# Feature dictionary — per-publication APPXML extract

Each row in `features/ipaYYMMDD.parquet` (or rarely `paYYMMDD.parquet` for
legacy bulk names) is one US patent application publication parsed from the
corresponding weekly USPTO APPXML zip in `appxml_zips/`. Features are computed by
[`parse_zips_to_features.py`](parse_zips_to_features.py), which reuses
`parse_uspto_xml.parse_uspto_file` from `../upsto-parse` for the heavy
XML work and then derives the compact columns below.

The schema is fixed in `parse_zips_to_features.SCHEMA` so weekly files
concatenate cleanly via `pyarrow.dataset` or `pandas.concat`.

## Identity & bibliography

| Column                          | Type   | Notes |
|---------------------------------|--------|-------|
| `publication_number`            | string | `USYYYYNNNNNNNA1`-style id from `<publication-reference>`. |
| `application_number`            | string | Application doc-number; primary key for joining to PatEx / OA datasets later. |
| `application_type`              | string | e.g. `utility`, `design`, `plant` — from `<application-reference appl-type="...">`. |
| `application_status`            | string | `pending` for IPA, `granted` if a grant XML is ever passed in. |
| `publication_date`              | string | ISO `YYYY-MM-DD`. |
| `application_date`              | string | ISO; **use this for AI-adoption cohorts** (it dates the drafting, not the 18-month-lagged publication). |
| `grant_date`                    | string | Empty for IPA. |
| `title`                         | string | Invention title (truncated to 512 chars). |
| `n_inventors`                   | int32  | Count of inventor names with first+last present. |
| `n_applicant_orgs`              | int32  | Applicant organisations parsed by `build_org`. |
| `n_attorneys`                   | int32  | Counts only `<agent rep-type="attorney">` entries. **Often 0 in IPA** because USPTO does not require `rep-type` on application publications; do not treat 0 as "pro se". |
| `attorney_organizations`        | string | Pipe-joined `"org, city, country"` strings — same caveat as `n_attorneys`. |
| `sections`                      | string | Pipe-joined IPC/CPC sections (single letters), e.g. `A\|B\|G`. |
| `section_classes`               | string | Pipe-joined section+class codes, e.g. `A01\|B62`. |
| `section_class_subclass_groups` | string | Pipe-joined full IPC classifications including main/subgroup, e.g. `A01B 69/00`. |

## Examiner-workload / drafting-complexity proxies

These are the primary outcomes for the AI-impact analysis.

| Column                       | Type   | Definition |
|------------------------------|--------|------------|
| `n_claims_total`             | int32  | Number of `<claim>` elements. |
| `n_claims_independent`       | int32  | Claims whose text does **not** match the dependent-claim regex `_DEP_RE` (matches `claim N`, `preceding claim(s)`, `any of claims …`, `claims N-M`). |
| `n_claims_dependent`         | int32  | `n_claims_total - n_claims_independent`. |
| `claim_words_mean`           | float  | Mean whitespace-token count across all claims. |
| `claim_words_max`            | int32  | Longest claim word count. |
| `claim_words_first_indep`    | int32  | Word count of the first independent claim. |
| `description_words`          | int32  | Whitespace tokens in the concatenated description paragraphs. |
| `description_paragraphs`     | int32  | Non-empty newline-separated lines produced by the parser (each `<p>` becomes one line). |
| `abstract_words`             | int32  | Whitespace tokens in the abstract. |
| `n_refs_total`               | int32  | Total entries in `referential_documents` (citations + continuations + provisional + …). |
| `n_refs_examiner_flagged`    | int32  | `cited_by_examiner=True` patent-references. **Expected to be sparse on IPA** — the examiner-citation `<category>` field is populated mostly on **grant XML** (`ipg*`). |
| `n_refs_applicant`           | int32  | Patent-references not flagged as examiner-cited. |
| `n_other_citations`          | int32  | Non-patent literature citations (`document_type="other-reference"`). |
| `n_related_docs`             | int32  | Family/continuation links (continuation, division, CIP, reissue, provisional, prior, priority-claim). |

### Text-quality proxies (computed on the first independent claim only)

Claim 1 is by far the most legally consequential and small enough to score quickly.

| Column                                 | Type  | Definition |
|----------------------------------------|-------|------------|
| `flesch_first_indep_claim`             | float | Flesch reading ease with an approximate syllable counter. **Often deeply negative** because patent claim 1 is typically a single very long sentence; treat as a *relative* metric, not an absolute. |
| `unique_token_ratio_first_indep_claim` | float | `len(set(tokens)) / len(tokens)` over `[A-Za-z]+` tokens, lowercased — a crude redundancy proxy. |

## Provenance

| Column        | Type   | Notes |
|---------------|--------|-------|
| `source_zip`  | string | e.g. `ipa260507.zip` — useful for traceability when revisions (`_r1`) replace a base file later. |

## Heuristic caveats

- **Dependent-claim detection** uses a regex on plain claim text. False positives are very rare for USPTO drafting language but possible (e.g., an independent claim quoting prior art "claim 1 of patent X"). False negatives can happen when a claim references a previous claim only obliquely. Tighten by inspecting the `<claim-ref>` XML element directly if needed.
- **Description word counts** treat each `<p>` as one paragraph regardless of length. Equation-heavy or table-heavy descriptions may inflate `description_paragraphs` without proportionally inflating `description_words`.
- **Attorney counts** undercount on IPA documents, see column note above. Use `attorney_organizations` for firm-level clustering only on the cohort of records where it is non-empty.
- **Examiner-citation field** is included for forward compatibility (and is populated when grant XML is fed into the same pipeline) but should be treated as a weak/noisy signal on the IPA-only corpus.
