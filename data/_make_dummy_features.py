"""One-off helper to sanity-check analyze_features (not part of main pipeline)."""
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from parse_zips_to_features import SCHEMA

rows = [
    {
        "publication_number": "US20190000001A1",
        "application_number": "16111111",
        "application_type": "utility",
        "application_status": "pending",
        "publication_date": "2019-06-01",
        "application_date": "2018-06-01",
        "grant_date": None,
        "title": "A",
        "n_inventors": 1,
        "n_applicant_orgs": 1,
        "n_attorneys": 0,
        "attorney_organizations": "",
        "sections": "G",
        "section_classes": "G06",
        "section_class_subclass_groups": "G06N",
        "n_claims_total": 10,
        "n_claims_independent": 1,
        "n_claims_dependent": 9,
        "claim_words_mean": 100.0,
        "claim_words_max": 200,
        "claim_words_first_indep": 80,
        "description_words": 5000,
        "description_paragraphs": 50,
        "abstract_words": 100,
        "n_refs_total": 5,
        "n_refs_examiner_flagged": 0,
        "n_refs_applicant": 5,
        "n_other_citations": 0,
        "n_related_docs": 0,
        "flesch_first_indep_claim": -10.5,
        "unique_token_ratio_first_indep_claim": 0.4,
        "source_zip": "ipa190604.zip",
    },
    {
        "publication_number": "US20240000001A1",
        "application_number": "18111111",
        "application_type": "utility",
        "application_status": "pending",
        "publication_date": "2024-06-01",
        "application_date": "2023-06-01",
        "grant_date": None,
        "title": "B",
        "n_inventors": 1,
        "n_applicant_orgs": 1,
        "n_attorneys": 0,
        "attorney_organizations": "",
        "sections": "G",
        "section_classes": "G06",
        "section_class_subclass_groups": "G06N",
        "n_claims_total": 12,
        "n_claims_independent": 1,
        "n_claims_dependent": 11,
        "claim_words_mean": 120.0,
        "claim_words_max": 250,
        "claim_words_first_indep": 100,
        "description_words": 8000,
        "description_paragraphs": 60,
        "abstract_words": 120,
        "n_refs_total": 6,
        "n_refs_examiner_flagged": 0,
        "n_refs_applicant": 6,
        "n_other_citations": 0,
        "n_related_docs": 0,
        "flesch_first_indep_claim": -12.0,
        "unique_token_ratio_first_indep_claim": 0.35,
        "source_zip": "ipa240604.zip",
    },
]

if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "_test_features"
    out.mkdir(exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), out / "ipa_dummy.parquet")
    print("wrote", out / "ipa_dummy.parquet")
