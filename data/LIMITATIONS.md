# Limitations — what APPXML features can and cannot say

This project uses **published application full text** (weekly APPXML / IPA zips). That is everything the USPTO releases **up front** when an application first publishes (~18 months after filing). It is **not** the prosecution file history.

## What we can measure (drafting and complexity proxies)

- **Claim load:** counts, lengths, independent vs dependent split — reasonable proxies for how much claim language an examiner must parse.
- **Specification load:** description length and rough paragraph count — proxies for reading burden and disclosure bulk.
- **Family and citation structure:** related documents, applicant-side references — **not** examiner search activity.
- **Simple text metrics** on the first independent claim (readability score, token redundancy) — **relative** comparisons only; patent claim 1 is almost never “readable” in a general-public sense.

These support questions like: “Did applications in our corpus become more verbose or more claim-heavy after tools that lower drafting cost became common?” — with strong caveats below.

## What we cannot measure from APPXML alone

- **Real examiner workload:** office-action counts, hours, internal database searches, interviews, and **quality of search** are absent.
- **Final outcomes:** allowance, abandonment, appeal — need **PatEx** or similar (PEDS-based) products.
- **Office action content:** rejection types (102/103/112), prior art cited in OAs — need the **Office Action Research Dataset** (bulk through 2017) and/or **USPTO APIs** for newer years.
- **Whether a patent was drafted with AI:** filings are not labeled. Any before/after chart around late 2022 is a **reduced-form time comparison**, not proof of AI use.

## How to describe results honestly

- Prefer language such as **“associated with calendar time / application cohort”** rather than **“caused by AI.”**
- **IPA** XML **under-reports attorney `rep-type`**; `n_attorneys` may be zero on many rows — do not infer “pro se” from that field alone.
- The **`cited_by_examiner`** bit in citations is usually **sparse on application publications** and more meaningful on **grant** XML (`ipg*`). Treat `n_refs_examiner_flagged` as a weak signal on IPA-only corpora.

## Optional follow-ups (out of current scope)

1. **Grant full text** (`ipg*`) for the same applications to enrich citation roles after examination.
2. **PatEx + office actions** to link these drafting proxies to prosecution intensity, pendency, and outcomes.
