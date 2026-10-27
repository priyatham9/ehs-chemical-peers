# Changelog

## Unreleased

- Peer-stability analysis `src/chempeers/stability.py` (`scripts/build_stability.py`, `make stability`): how often each plant keeps its 10 nearest peers when the 15 similarity attributes are resampled with replacement, when the weights get log-normal noise, and when only ties are re-broken (100 seeded replicates each; exact and tie-robust "neighbourhood" scores). Writes `outputs/peer_stability.csv` and `.json` and `docs/data/stability.json`; `compare.html` shows the median stability of each group beside its rate. Method, interpretation and limits in `docs/stability.md`; `tests/test_stability.py` checks the cell engine against a plain plant-by-plant reference, known-answer toy cases, determinism, and the committed outputs and quoted numbers (full rebuild check with `CHEMPEERS_FULL_STABILITY=1`).
- `.zenodo.json` and `codemeta.json` (title, description, creators from `CITATION.cff`, MIT licence, keywords, related identifiers for the sibling repositories and the programme site; no DOI or ORCID) so a release is archived with correct metadata once Zenodo is linked; `CITATION.cff` gains `keywords`. `tools/check_citation.py` (stdlib, run by `.github/workflows/citation.yml`) checks the required CFF 1.2.0 fields and that `CITATION.cff`, `.zenodo.json`, `codemeta.json` and `LICENSE` agree on title, authors, keywords and licence. No release or tag created.
- `src/chempeers/ontology/`: Foundry-style ontology over the linked dataset (JSON spec of 12 object types, 15 link types, 4 actions and 6 functions; the RMP-to-OSHA join is a link backed by a match object carrying method, confidence and review; validating runtime with link traversal, actions and an action log; SQLite/JSON export; `make ontology`). Built from the committed `docs/data` and `outputs/summary.json`; its functions reuse `analysis.py` and `stats.py` and `tests/test_ontology.py` checks they reproduce the summary. Documented in `docs/ontology.md`; independent design on public data, not affiliated with Palantir.
- Comparison page `docs/compare.html`: pick any two groups (size band, product type, chemical family, inventory, release history) and see release or injury rates side by side with exact intervals (Clopper-Pearson and Wilson; Garwood Poisson) and an exact test of whether the gap is distinguishable from noise. Stdlib build step `scripts/build_compare.py` (`make compare`) writes `docs/data/compare.json` from `outputs/summary.json` and `docs/data/plants.json`; `tests/test_compare.py` checks the statistics against brute-force sums and every group against the committed outputs.
- Working paper `docs/paper.md`: data, method, results, limitations and verified references. Tables are generated from `outputs/summary.json` by `scripts/paper_tables.py` (`make paper`), and `tests/test_paper_consistency.py` checks the tables and every number quoted in the prose.

## 0.1.0 - 2026-09-27

First version.

- Pipeline joining OSHA Form 300A injury logs (2016-2024), EPA Risk Management Program facilities and accident histories (Data Liberation Project FOIA copy, through 2025) and OSHA Severe Injury Reports (January 2015 to November 2025) for NAICS 325 plants, by ZIP plus street number with a name fallback.
- Plain-language product types (from NAICS) and chemical families (from chemicals held).
- Findings in `outputs/summary.json`: size noise, year-to-year stability, injury rate against next-year releases and serious injuries, release predictors, release and serious-injury anatomy.
- Plant explorer (`docs/index.html`): baseline picker, filters, exact-Poisson comparison band, year-by-year view, releases, serious injuries, peer list with CSV download.
- Story (`docs/story.html`) and data and method page (`docs/method.html`).
- Synthetic fixture tests, real-data regression tests, README number check.
