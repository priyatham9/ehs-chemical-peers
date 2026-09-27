# ehs-chemical-peers

[![tests](https://github.com/priyatham9/ehs-chemical-peers/actions/workflows/tests.yml/badge.svg)](https://github.com/priyatham9/ehs-chemical-peers/actions/workflows/tests.yml) [![site](https://img.shields.io/badge/site-priyatham9.github.io-blue)](https://priyatham9.github.io/ehs-chemical-peers/)

Part of the Grounded research programme: https://priyatham9.github.io/grounded/

A peer explorer for US chemical manufacturing plants (NAICS 325), built only from public records. It joins three government sources by address: OSHA injury logs, EPA chemical-release histories, and OSHA serious-injury reports. With it you can pick any plant, choose its peers by product type, chemicals held, size, state and years, and see whether a difference in its injury rate is real or within the range chance explains.

It does not audit any plant, it does not say why a plant's numbers are what they are, and it cannot see anything a plant did not report to the government.

Every number below comes from `scripts/build_data.py` and is copied from `outputs/summary.json`. `tests/test_readme_consistency.py` reads the numbers back out of this file and fails if they disagree with the summary.

**At a glance**

| Field | Value |
|---|---|
| Site | [Plant explorer](https://priyatham9.github.io/ehs-chemical-peers/) · [Story](https://priyatham9.github.io/ehs-chemical-peers/story.html) · [Data & method](https://priyatham9.github.io/ehs-chemical-peers/method.html) |
| Data | real public records; a synthetic fixture exists for offline tests only |
| Plants | 10,597 chemical plants (2,773 EPA-registered, 9,178 filing OSHA injury logs) |
| Tests | stdlib `unittest`; real-data tests skip when `data/raw` is empty |
| Dependencies | Python 3.9+ standard library only |
| Quickstart | `make data && make build && make test` |
| Licence | MIT |

---

## Why this exists

Chemical plants are often ranked on their injury rate (TRIR: recordable injuries per 200,000 hours, about 100 full-time workers for a year). For a small plant that number is mostly noise, and it says very little about the event that matters most at a chemical plant, a release of a hazardous chemical.

The data behind the explorer shows this directly:

* **One injury is the whole score at a small plant.** A plant with 50-99 people works a median of 138,777 hours a year, so one recordable injury moves its rate by 1.44 points. In 32.71% of those plant-years the plant recorded no injuries at all.
* **Rankings don't hold from one year to the next.** The rank correlation between a plant's rate in one year and the next is 0.314 for plants under 50 people and 0.444 for 50-99, against 0.742 for plants of 1,000 or more.
* **A low injury rate says nothing useful about releases.** Among plants with 100-249 people, those below the median injury rate had a release the next year in 3.9% of plant-years; those above it, 3.4%.
* **Release history and inventory do.** A plant with an EPA-reportable release in the past five years had one the next year in 12.06% of plant-years, against 1.47% for plants without one (8.2 times as often). Plants holding 5 million lb or more of regulated chemicals: 8.12%. Under 100,000 lb: 0.9%.
* **Serious injuries happen behind clean records.** 18.21% of serious injuries (amputations, eye losses, hospital stays) with a usable prior-year log happened at plants that recorded zero injuries the year before.

These are correlations in reported data, not causes.

## What is in the explorer

* **Baseline picker.** Search any of the 10,597 plants by name, company, city or EPA facility ID. The baseline goes in the URL (`?plant=R<EPA ID>`), so a comparison can be shared as a link.
* **Filters.** Product type (from the industry code: resins and plastics, basic organics including formaldehyde, acids and inorganics, petrochemicals, adhesives, and 12 more), chemical family (from the chemicals held: formaldehyde, epoxy chain, ammonia, chlorine, strong acids, isocyanates, reactive oxides, monomers, amines, silanes, sulfur compounds, flammables), individual chemical, workforce band, pounds held, state, OSHA program type, company name, record type, active status, and year range. "Match my plant" sets product type, chemical family and neighbouring size bands from the baseline.
* **Fair comparison chart.** Each peer's pooled injury rate against its hours, with the band chance alone produces for a plant at the peer rate (exact Poisson limits, 95% and 99.8%).
* **Year by year.** The baseline's rate each year against the peer rate, with the size of a one-injury jump.
* **Releases.** Peer release rate per plant-year, per worker or per million lb; why, where from, what happened and what changed afterwards, with the baseline's own releases listed.
* **Serious injuries.** Peer serious injuries grouped by the kind of energy involved, with the reports' own narratives.
* **Peer list.** Sortable, with a CSV download.

## Sources

| Source | Years | Rows kept (NAICS 325) |
|---|---|---|
| [OSHA Injury Tracking Application, Form 300A](https://www.osha.gov/Establishment-Specific-Injury-and-Illness-Data) | 2016-2024 | 42,794 establishment-years |
| [EPA Risk Management Program](https://www.epa.gov/rmp), FOIA copy from the [Data Liberation Project](https://www.data-liberation-project.org/datasets/epa-risk-management-program-database/) | 1994-2025 | 2,773 facilities, 2,611 releases |
| [OSHA Severe Injury Reports](https://www.osha.gov/severe-injury-reports) | Jan 2015 - Nov 2025 | 1,913 reports |

## Method in brief

* **Joins.** No ID is shared across EPA and OSHA, so plants are joined on 5-digit ZIP plus street number, with a name-token check as the fallback. 48.83% of EPA-registered chemical plants join to an OSHA injury log (many EPA-registered plants are too small to file one), and 63.25% of serious-injury reports join to a known plant. Every plant records how it was joined.
* **Screen.** Injury-log filings with fewer than 120 or more than 4,500 hours per employee are dropped from every rate (the screen from [ehs-osha-analysis](https://github.com/priyatham9/ehs-osha-analysis)).
* **Serious injuries** are published only for states where federal OSHA covers private employers, so plants in state-plan states are left out of every serious-injury comparison.
* **Releases** are on file when they fall in the five years before one of the plant's EPA submissions; a plant-year counts toward release rates only when a submission covers it.
* **Labels.** Product type comes from NAICS (older codes folded into current groups); chemical family from the chemicals a plant holds above EPA's threshold. Both tables live in `src/chempeers/taxonomy.py` and can be edited.

Full detail: [method.html](https://priyatham9.github.io/ehs-chemical-peers/method.html) and [DATASHEET.md](DATASHEET.md).

## Run it

```bash
make data    # download the public files into data/raw (about 300 MB)
make build   # link, analyse, write outputs/summary.json and docs/data/*.json
make test    # unit tests on a synthetic fixture, plus real-data checks when data/raw is present
make serve   # open http://localhost:8000
```

## Layout

```
src/chempeers/   load.py (readers) · link.py (address joins) · build.py (assembly)
                 taxonomy.py (product types, chemical families) · events.py (plain-language coding)
                 stats.py (rates, exact Poisson limits) · analysis.py (findings) · export.py (site data)
scripts/         download_data.py · build_data.py · build_story.py · apply_header.py
docs/            index.html (explorer) · story.html · method.html · data/*.json
tests/           synthetic fixture and tests
```

## Licence

MIT. The source data are US government records in the public domain; the RMP extract is republished by the Data Liberation Project.
