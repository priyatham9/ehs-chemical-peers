# Benchmarking US Chemical Plants Against Their Peers from Public Records: A Linked EPA RMP and OSHA Dataset

Priyatham Chimmani

Working paper, version 0.1 (October 2026). Not peer reviewed and not submitted to any venue.

Code and data: https://github.com/priyatham9/ehs-chemical-peers. Every number in this paper is read from `outputs/summary.json`, which `scripts/build_data.py` writes from the public source files. The tables are generated from that file by `scripts/paper_tables.py`, and `tests/test_paper_consistency.py` fails if the text or the tables disagree with it.

## Abstract

Chemical manufacturing plants are often compared on their OSHA total recordable incident rate (TRIR). That rate is a measure of personal injuries, and it is weak evidence about the event that matters most in process safety, a release of a hazardous chemical. We link three US government sources for chemical manufacturing (NAICS 325): OSHA Form 300A injury summaries (2016-2024), EPA Risk Management Program (RMP) facility registrations and five-year accident histories (FOIA copy through 2025), and OSHA Severe Injury Reports (January 2015 to November 2025). No identifier is shared across agencies, so plants are joined on ZIP code and street number with a name-token fallback. The result covers 10,597 plants; 48.83% of the 2,773 RMP-registered plants join to an OSHA injury filing. Three findings follow from the linked data. First, at small plants one recordable case moves the rate by several points (3.53 points at the median plant under 50 employees), and year-to-year rank correlation of the rate is 0.314 for those plants against 0.742 for plants of 1,000 or more. Second, a plant's injury rate is not consistently associated with an RMP-reportable release the following year: among plants of 100-249 employees, plants at or below the median rate had a release in 3.9% of plant-years and plants above it in 3.4%. Third, release history and chemical inventory are associated with next-year releases: plants with a release on file in the previous five years had one in 12.06% of plant-years against 1.47% for plants without (8.2 times as often), and plants holding 5 million lb or more of regulated chemicals had one in 8.12% against 0.9% for plants under 100,000 lb. These are associations in self-reported data, not causes. We release the pipeline, the linked dataset and a peer explorer that compares any plant with a chosen peer group using exact Poisson limits.

## 1 Introduction

Process safety is concerned with loss of containment of hazardous materials: fires, explosions and toxic releases. Occupational (personal) safety is concerned with slips, falls, cuts and strains. The two are measured differently, and a good record on one says little about the other. The US Chemical Safety and Hazard Investigation Board (CSB) made this point in its investigation of the March 2005 BP Texas City refinery explosion, finding that company executives "relied unduly on injury statistics in assessing the safety of their facilities" and recommending the development of process safety performance indicators [CSB 2007]. Hopkins [2009] sets out why personal injury rates cannot stand in for process safety indicators and how the two kinds of indicator differ.

Despite this, injury rates remain the most widely available number for comparing plants. They are published for individual establishments through OSHA's Injury Tracking Application [OSHA ITA], and they are what an outside party (a community group, an insurer, a customer, a new EHS manager) can most easily look up. EPA's RMP database, which records the chemicals each covered facility holds and its five-year accident history, has been available in bulk only through FOIA releases [DLP]. OSHA's Severe Injury Reports, which list amputations, eye losses and in-patient hospitalizations by employer and address, are a third public source [OSHA SIR]. None of the three shares an identifier with the others.

Earlier work linked these sources for the late 1990s. Kleindorfer et al. [2003] and Elliott, Kleindorfer and Lowe [2003] analysed RMP accident histories and found that accident frequency was associated with facility size and process hazardousness. Elliott et al. [2008] matched OSHA occupational injury and illness rates to RMP accidents for 1996-2000 and found only weak evidence that everyday safety performance predicts major accidents, with the simple association confounded by total hazard. This paper revisits that question with a decade of more recent public data, adds the serious-injury reports that became available after OSHA's 2015 reporting rule [29 CFR 1904.39], and treats the plant-level comparison as a statistical problem: how much of a difference between a plant and its peers is within the range chance explains.

The contribution is practical rather than theoretical. We describe (1) a reproducible, standard-library-only pipeline that joins the three sources for NAICS 325 and records how each join was made, (2) descriptive evidence on the noise in plant-level injury rates and on which public signals are and are not associated with next-year releases and serious injuries, and (3) a peer explorer that lets a user pick a plant, define its peers by product type, chemical family, size, state and years, and compare it against exact Poisson limits.

## 2 Data

### 2.1 Sources

| Source | Publisher | Years used | What it contributes |
|---|---|---|---|
| Injury Tracking Application, Form 300A summaries | OSHA [OSHA ITA] | Calendar years 2016-2024 | Establishment-year hours worked, average employees, and counts of days-away, job-transfer and other recordable cases |
| Risk Management Program database, FOIA copy | EPA, republished by the Data Liberation Project [DLP; EPA RMP] | Submissions 1994-2025 | Facility identity and NAICS codes, regulated chemicals and quantities held, five-year accident histories with flags for what happened, the source, contributing causes and changes made afterwards |
| Severe Injury Reports | OSHA [OSHA SIR] | January 2015 to November 2025 | Employer, address, date, outcome (amputation, eye loss, hospitalization) and a narrative for each report |

`scripts/download_data.py` fetches 14 files (nine Form 300A archives, the Severe Injury Reports archive, and four RMP tables) and writes their SHA-256 digests to `data/raw/manifest.json`. The digests of the files behind the committed build are in `docs/data/meta.json` (`built_from`).

The reporting rules shape what each source can show. Form 300A data must be submitted electronically by establishments with 250 or more employees and by establishments with 20 to 249 employees in industries listed in Appendix A to Subpart E of Part 1904 [29 CFR 1904.41]. Severe injuries are reportable within 24 hours of an in-patient hospitalization, amputation or loss of an eye [29 CFR 1904.39], and the public file covers only incidents under federal OSHA jurisdiction, not state-plan states [OSHA SIR]. An RMP five-year accident history must include accidental releases from covered processes that caused deaths, injuries or significant property damage on site, or known offsite deaths, injuries, evacuations, sheltering in place, property damage or environmental damage [40 CFR 68.42].

### 2.2 Scope and join

A plant is either an RMP facility with a NAICS 325 code in any submission (identifier `R` plus the EPA facility ID) or an OSHA Form 300A establishment in NAICS 325 that did not join to one (identifier `I` plus the OSHA establishment ID). The join (`src/chempeers/link.py`, `src/chempeers/build.py`) proceeds as follows.

1. Every NAICS 325 RMP facility becomes a plant and is indexed by 5-digit ZIP plus street number, and by ZIP alone with a set of name tokens (facility and company name, with common words such as "Inc", "Plant" and "Chemical" removed).
2. Each Form 300A establishment-year is matched, newest filing first, to an RMP plant at the same ZIP and street number (`address`); if several plants share that address, the one with the highest name-token Jaccard overlap is chosen (`address+name`). Otherwise the best name match within the ZIP is accepted if the overlap is at least 0.34 (`zip+name`). Unmatched establishments become `osha only` plants. If two filings fall on one plant-year, the one with more hours is kept; they are not added.
3. RMP accidents attach to their facility directly.
4. Severe Injury Reports are matched to a plant with the same address index, and the match is discarded if the states disagree. Unmatched reports still count in sector-level tallies.

Every plant records its join method. Table 1 gives the coverage of the committed build.

Table 1. Coverage of the linked dataset. Source: `outputs/summary.json` (`coverage`).

<!-- BEGIN table:coverage -->
| Quantity | Value |
|---|--:|
| Plants in the linked dataset | 10,597 |
| EPA RMP-registered plants (NAICS 325) | 2,773 |
| Plants with at least one OSHA Form 300A filing | 9,178 |
| RMP plants joined to an OSHA filing | 1,354 (48.83%) |
| OSHA Form 300A establishment-years kept | 42,794 |
| RMP accident-history records (releases) | 2,611 |
| OSHA Severe Injury Reports (NAICS 325) | 1,913 |
| Severe Injury Reports joined to a plant | 1,210 (63.25%) |
<!-- END table:coverage -->

Fewer than half of RMP-registered chemical plants join to an injury filing. Many RMP plants are small and may fall below the Form 300A submission threshold; others will have filed under an address that does not match. Of the 1,913 serious-injury reports, 63.25% join to a known plant.

### 2.3 Screening and labels

Form 300A filings whose hours per average employee fall outside 120 to 4,500 a year are excluded from every rate. This is the plausibility screen developed in the companion `ehs-osha-analysis` repository, which documents how a small share of implausible hours entries can dominate pooled rates. Each plant receives a product type from its NAICS code (17 groups plus "Other chemical", with older NAICS vintages folded into current groups by prefix) and zero or more chemical families from the chemicals it holds above the RMP threshold (12 families, such as ammonia, chlorine and chlor-alkali, strong acids, isocyanates and reactive oxides). Both tables are in `src/chempeers/taxonomy.py`.

## 3 Methods

All computations are in `src/chempeers/analysis.py` and `src/chempeers/stats.py` and use only the Python standard library.

**Injury rate.** TRIR is recordable cases (days-away, job-transfer and other recordable) times 200,000 divided by hours worked. The one-case swing at a given number of hours is 200,000 divided by hours: the amount a single additional case moves the rate.

**Size noise.** For each workforce band (average employees under 50, 50-99, 100-249, 250-999, 1,000 or more), we report the number of screened plant-years, median hours, the one-case swing at median hours, the share of plant-years with zero recordable cases, and the pooled rate.

**Year-to-year stability.** For each plant and each pair of consecutive years, from 2016-2017 to 2023-2024, in which both years pass the screen, we take the rate in each year and compute the Spearman rank correlation (average ranks for ties) within the band of the first year.

**Injury rate against next-year outcomes.** For each screened plant-year from 2016 to 2023, we record whether the plant had an RMP release or a serious-injury report in the following calendar year. Plant-years are split by size (under 100, 100-249, 250 or more) into those with zero cases and, among the rest, those at or below and above the median rate of their size group. Serious-injury comparisons use only plants outside state-plan states, because the federal file does not include those states. Release comparisons use only RMP plants in years when an accident would be on file (below).

**Release coverage window.** An RMP accident appears in the data only if it fell in the five years before one of the facility's submissions. We therefore treat a plant-year as observed for releases only between five years before the plant's first submission (and no earlier than 2010) and 2024, or the year of its last submission if the plant is no longer active.

**Release predictors.** Over observed RMP plant-years 2010-2024, we compare the share with at least one release by: whether a release was on file in the previous five years; total pounds of regulated chemicals held (under 100,000 lb, 100,000 lb to 1 million, 1 million to 5 million, 5 million or more); number of regulated chemicals held; and chemical family. Inventory, chemical count and family are taken from the plant's latest RMP data and are not time-varying in this analysis.

**Prior-year record of serious-injury plants.** For each serious-injury report at a joined plant outside state-plan states whose previous calendar year has a screened Form 300A filing, we record whether that filing showed zero recordable cases.

**Peer comparison (explorer).** The explorer compares a plant's injury count with a peer rate. Under the hypothesis that the plant runs at the peer rate, its count over H hours is Poisson with mean peer rate times H / 200,000. The comparison band uses exact Poisson quantiles at 2.5% and 97.5% (about 95%) and at 0.1% and 99.9% (about 99.8%), rather than a normal approximation, because small plants have expected counts well below 5. This is the funnel-plot approach to institutional comparison described by Spiegelhalter [2005], applied to establishment injury counts.

No model is fitted and no confidence intervals or hypothesis tests are reported for the group comparisons in Section 4; the tables give event counts and denominators so readers can judge the size of each group.

## 4 Results

### 4.1 Injury rates at small plants are mostly noise

Table 2 shows how the information in a plant's injury rate depends on its size. The median plant-year with under 50 employees worked 56,687 hours, so one recordable case moves its rate by 3.53 points, larger than the pooled rate for that band (3.01). In 55.63% of those plant-years the plant recorded no cases at all. At 50-99 employees the median is 138,777 hours, the one-case swing is 1.44 points, and 32.71% of plant-years have zero cases. At 1,000 or more employees the swing is 0.06 points and 1.42% of plant-years have zero cases.

Table 2. Size and noise in screened Form 300A plant-years. Source: `outputs/summary.json` (`size_noise`).

<!-- BEGIN table:size_noise -->
| Average employees | Plant-years | Median hours | One-case swing (TRIR points) | Plant-years with zero cases (%) | Pooled TRIR |
|---|--:|--:|--:|--:|--:|
| Under 50 | 16,467 | 56,687 | 3.53 | 55.63 | 3.01 |
| 50-99 | 9,693 | 138,777 | 1.44 | 32.71 | 2.68 |
| 100-249 | 8,357 | 294,840 | 0.68 | 21.29 | 2.13 |
| 250-999 | 4,791 | 788,987 | 0.25 | 10.52 | 1.45 |
| 1,000+ | 705 | 3,173,256 | 0.06 | 1.42 | 0.79 |
<!-- END table:size_noise -->

The rate is correspondingly unstable from one year to the next (Table 3). The Spearman correlation between a plant's rate in one year and the next rises with size from 0.314 for plants under 50 employees and 0.444 for 50-99 to 0.742 for plants of 1,000 or more. A ranking of small plants on one year's rate will be substantially reshuffled the following year.

Table 3. Rank correlation of a plant's rate in consecutive years. Source: `outputs/summary.json` (`stability`).

<!-- BEGIN table:stability -->
| Average employees (first year) | Consecutive-year pairs | Spearman rho |
|---|--:|--:|
| Under 50 | 11,120 | 0.314 |
| 50-99 | 6,985 | 0.444 |
| 100-249 | 6,031 | 0.587 |
| 250-999 | 3,530 | 0.706 |
| 1,000+ | 529 | 0.742 |
<!-- END table:stability -->

### 4.2 Injury rate and next-year releases

Table 4 compares next-year RMP releases across injury-rate groups for 6,319 observed plant-years. There is no consistent direction. Under 100 employees, plants at or below the median rate had a release in 1.60% of plant-years and plants above it in 1.80%. At 100-249 employees the figures are 3.9% and 3.4%; at 250 or more, 6.30% and 3.92%. The groups are small: at 100-249 employees the comparison rests on 23 and 20 releases. Release shares rise with size in every injury-rate group, which is consistent with the size and hazard confounding reported by Elliott et al. [2008].

Table 4. Share of plant-years with an RMP release in the following year, by injury-rate group (events / plant-years). Source: `outputs/summary.json` (`trir_vs_outcomes.release_next_year`).

<!-- BEGIN table:trir_release -->
| Average employees | Zero cases | TRIR at or below median | TRIR above median | Median TRIR (non-zero) |
|---|--:|--:|--:|--:|
| Under 100 | 26 / 1,648 (1.58%) | 16 / 1,001 (1.60%) | 18 / 1,000 (1.80%) | 3.29 |
| 100-249 | 12 / 433 (2.77%) | 23 / 589 (3.90%) | 20 / 589 (3.40%) | 1.57 |
| 250+ | 6 / 140 (4.29%) | 29 / 460 (6.30%) | 18 / 459 (3.92%) | 0.92 |
<!-- END table:trir_release -->

### 4.3 Injury rate and next-year serious injuries

For serious injuries the picture differs (Table 5, 22,826 plant-years in federal-OSHA states). At 100 employees or more, plants with zero recordable cases had the lowest share of next-year serious-injury reports and plants above the median rate the highest: at 100-249 employees, 2.07%, 3.35% and 5.1%; at 250 or more, 5.34%, 6.15% and 7.25%. Under 100 employees the order does not hold (0.98%, 1.95% and 1.54%). A higher injury rate is therefore weakly associated with more serious injuries the next year at larger plants, but a clean record does not rule them out: of the 703 serious injuries at joined plants with a usable prior-year filing, 128 (18.21%) occurred at plants that recorded zero cases the year before.

Table 5. Share of plant-years with a serious-injury report in the following year, by injury-rate group, federal-OSHA states only (events / plant-years). Source: `outputs/summary.json` (`trir_vs_outcomes.serious_injury_next_year`).

<!-- BEGIN table:trir_serious -->
| Average employees | Zero cases | TRIR at or below median | TRIR above median | Median TRIR (non-zero) |
|---|--:|--:|--:|--:|
| Under 100 | 68 / 6,950 (0.98%) | 76 / 3,905 (1.95%) | 60 / 3,905 (1.54%) | 3.95 |
| 100-249 | 23 / 1,113 (2.07%) | 65 / 1,943 (3.35%) | 99 / 1,942 (5.10%) | 1.96 |
| 250+ | 18 / 337 (5.34%) | 84 / 1,366 (6.15%) | 99 / 1,365 (7.25%) | 1.10 |
<!-- END table:trir_serious -->

### 4.4 Release history and inventory

Across 27,058 observed RMP plant-years, 2.62% had at least one release (Table 6). Plant-years with a release on file in the previous five years had one in 12.06% of cases, against 1.47% for plant-years without, a ratio of 8.2. The share rises steadily with inventory, from 0.9% for plants holding under 100,000 lb of regulated chemicals to 8.12% for plants holding 5 million lb or more, and with the number of regulated chemicals held, from 1.26% for plants with one to 8.49% for plants with five or more.

Table 6. Share of observed RMP plant-years with a release, by release history, inventory and number of regulated chemicals (events / plant-years). Source: `outputs/summary.json` (`release_predictors`).

<!-- BEGIN table:release_predictors -->
| Group | Plant-years with a release / plant-years (%) |
|---|--:|
| All covered plant-years | 710 / 27,058 (2.62%) |
| Release on file in the previous five years | 356 / 2,952 (12.06%) |
| No release on file in the previous five years | 354 / 24,106 (1.47%) |
| Inventory: Under 100k lb | 59 / 6,525 (0.90%) |
| Inventory: 100k-1M lb | 159 / 11,546 (1.38%) |
| Inventory: 1M-5M lb | 176 / 5,093 (3.46%) |
| Inventory: 5M+ lb | 316 / 3,894 (8.12%) |
| Regulated chemicals held: 1 chemical | 200 / 15,891 (1.26%) |
| Regulated chemicals held: 2 | 146 / 5,296 (2.76%) |
| Regulated chemicals held: 3-4 | 152 / 3,365 (4.52%) |
| Regulated chemicals held: 5+ | 207 / 2,438 (8.49%) |
<!-- END table:release_predictors -->

By chemical family (Table 7; a plant counts in every family it holds), the highest shares are for sulfur compounds (7.33%), the epoxy chain (7.15%) and strong acids (6.99%), and the lowest for isocyanates (1.37%). Families are not independent of inventory and chemical count, so these differences should not be read as the effect of the chemistry alone.

Table 7. Share of observed RMP plant-years with a release, by chemical family held (events / plant-years). Source: `outputs/summary.json` (`release_predictors.family`).

<!-- BEGIN table:families -->
| Chemical family held | Plant-years with a release / plant-years (%) |
|---|--:|
| Formaldehyde | 77 / 2,053 (3.75%) |
| Epoxy chain | 50 / 699 (7.15%) |
| Ammonia | 318 / 10,257 (3.10%) |
| Chlorine & chlor-alkali | 310 / 5,106 (6.07%) |
| Strong acids | 190 / 2,718 (6.99%) |
| Isocyanates | 10 / 731 (1.37%) |
| Reactive oxides | 80 / 1,439 (5.56%) |
| Monomers | 138 / 2,914 (4.74%) |
| Amines | 91 / 2,011 (4.53%) |
| Silanes | 19 / 438 (4.34%) |
| Sulfur compounds | 117 / 1,596 (7.33%) |
| Flammable gases & liquids | 349 / 11,279 (3.09%) |
<!-- END table:families -->

### 4.5 What the release and serious-injury records describe

The 2,611 RMP accident records for these plants report 2,278 worker injuries in total. Table 8 tallies the yes/no flags on each record; one release can carry several flags in each field. Gas releases (1,667) outnumber liquid spills (878). The most often flagged contributing causes are equipment failure (1,068) and human error (992), and the most often reported changes are better equipment (1,245), rewritten procedures (1,237) and retraining (1,152). Holding less chemical was reported 22 times. For the 75 releases involving formaldehyde, liquid spills (53) outnumber gas releases (13), and 7 involved a runaway reaction.

Table 8. Flags on RMP accident-history records for NAICS 325 plants. Source: `outputs/summary.json` (`release_anatomy_all`).

<!-- BEGIN table:release_anatomy -->
| Field | Flag | Releases flagged |
|---|---|--:|
| What happened | Liquid spill | 878 |
| What happened | Gas release | 1,667 |
| What happened | Fire | 310 |
| What happened | Explosion | 118 |
| What happened | Runaway reaction | 38 |
| Where from | Process vessel or reactor | 534 |
| Where from | Storage tank | 275 |
| Where from | Piping | 731 |
| Where from | Valve | 481 |
| Where from | Transfer hose | 236 |
| Where from | Pump | 125 |
| Where from | Joint or flange | 152 |
| Contributing cause | Equipment failed | 1,068 |
| Contributing cause | Human error | 992 |
| Contributing cause | Procedure wrong or not followed | 612 |
| Contributing cause | During or due to maintenance | 467 |
| Contributing cause | Pressure built up too high | 308 |
| Contributing cause | Process upset | 221 |
| Contributing cause | Design flaw | 249 |
| Contributing cause | Wrong equipment for the job | 153 |
| Contributing cause | Management system gap | 133 |
| Contributing cause | Safety system bypassed | 53 |
| Contributing cause | Weather | 75 |
| Change made afterwards | Better equipment | 1,245 |
| Change made afterwards | Rewrote procedures | 1,237 |
| Change made afterwards | Retrained people | 1,152 |
| Change made afterwards | Changed maintenance | 691 |
| Change made afterwards | New process controls | 434 |
| Change made afterwards | New mitigation systems | 195 |
| Change made afterwards | Changed the process | 175 |
| Change made afterwards | Updated emergency plan | 243 |
| Change made afterwards | Held less chemical | 22 |
| Change made afterwards | No change reported | 168 |
<!-- END table:release_anatomy -->

Of the 1,913 serious-injury reports, 628 involved an amputation and 1,475 an in-patient hospitalization. Grouped by the energy involved (Table 9), being caught in machinery accounts for the largest group (661), followed by slips, trips and falls (373) and chemical exposure (217). In resin and plastics plants, 114 of 290 reports involved an amputation.

Table 9. Serious-injury reports by energy group. Source: `outputs/summary.json` (`injury_anatomy_all`).

<!-- BEGIN table:injury_anatomy -->
| Energy group | Reports |
|---|--:|
| Caught in machinery | 661 |
| Heat, steam & hot material | 187 |
| Chemical exposure | 217 |
| Struck by object or vehicle | 185 |
| Slip, trip or fall | 373 |
| Vehicle or forklift | 120 |
| Rubbed, cut or pinched | 15 |
| Fire or explosion | 85 |
| Electricity | 22 |
| Strain or overexertion | 23 |
| Violence or other | 10 |
| Unclassified | 15 |
<!-- END table:injury_anatomy -->

## 5 Limitations and threats to validity

**Join error.** No identifier is shared across agencies. Address joins miss plants whose filings use different addresses (a mailing address, a renamed street, a different suite) and can attach two employers at one shared site to the same plant. Only 48.83% of RMP plants join to an injury filing, and the joined plants are not a random sample: they are more likely to be large enough to file Form 300A. Results that use the join (Sections 4.2 and 4.3) describe joined plants only.

**Coverage windows.** RMP accident histories cover only the five years before a submission, and our observation window assumes continuous coverage between the first submission (less five years) and the last. A plant whose submissions are more than five years apart, or one that stopped filing, may have unobserved releases counted as release-free years. Serious-injury reports cover federal-OSHA states only, and the state-plan list used to exclude the rest is fixed in code.

**Release history is partly mechanical.** A plant with a release on file is, by construction, a plant whose reporting window and reporting practice put releases on file. Some of the association between past and next-year releases may reflect reporting behaviour rather than underlying hazard.

**Confounding.** Size, inventory, chemical count and chemical family are correlated with each other, and the tables are one-way breakdowns. No adjustment is made. Inventory and chemical family come from the latest RMP data and are applied to every year.

**Self-reported data.** All three sources are filed by employers. Under-recording of injuries, misclassification of cases, implausible hours (addressed only by the screen) and under-reporting of releases all bias the measures in ways that cannot be checked from public data.

**Small groups and no inference.** Several cells in Tables 4 and 5 rest on a few dozen events. We report counts rather than tests, and differences of a percentage point or two between groups should not be over-read.

**Moving sources.** OSHA adds a year of Form 300A data each spring and updates the Severe Injury Reports file, and the RMP extract is refreshed through new FOIA requests [DLP]. A rebuild against newer files will change the numbers; the file digests identify the build reported here.

**Scope of use.** The dataset is suitable for peer comparison, teaching and hypothesis generation. It is not an audit of any plant, and it is not suitable for enforcement or for ranking plants for public blame (`DATASHEET.md`, following Gebru et al. [2021]).

## 6 Related work

The gap between personal injury rates and process safety performance is a central lesson of the CSB's Texas City investigation [CSB 2007] and of Hopkins's analysis of process safety indicators [Hopkins 2009]. The closest empirical antecedents are the Wharton Risk Center studies of RMP data: Kleindorfer et al. [2003] described accident histories and worst-case scenarios in the first RMP submissions; Elliott, Kleindorfer and Lowe [2003] related accident frequency and severity to facility size, process hazardousness and other regulatory programs; and Elliott et al. [2008] linked OSHA injury and illness rates to RMP accidents and found only weak evidence that everyday safety performance predicts catastrophic loss. This paper uses the same kinds of sources for a later period, adds OSHA serious-injury reports, and releases the join and the analysis as code. The peer-comparison method follows the funnel plot of Spiegelhalter [2005], developed for comparing hospitals and other institutions. The dataset documentation follows Gebru et al. [2021].

## 7 Reproducibility

The pipeline needs Python 3.9 or later and no third-party packages.

```bash
git clone https://github.com/priyatham9/ehs-chemical-peers
cd ehs-chemical-peers
make data      # download the 14 public files into data/raw and record SHA-256 digests
make build     # link, analyse, write outputs/summary.json and docs/data/*.json
make paper     # regenerate the tables in this paper from outputs/summary.json
make test      # unit tests; real-data tests rebuild from data/raw and compare with the committed summary
```

Without `data/raw`, `make test` still checks this paper against the committed `outputs/summary.json`: `tests/test_paper_consistency.py` runs `scripts/paper_tables.py --check` and checks every number quoted in the prose. `tests/test_real_data.py` rebuilds the summary from `data/raw` and fails if it differs from the committed file.

## Suggested citation

Chimmani, P. (2026). *Benchmarking US Chemical Plants Against Their Peers from Public Records: A Linked EPA RMP and OSHA Dataset* (Working paper, version 0.1). https://github.com/priyatham9/ehs-chemical-peers/blob/main/docs/paper.md

## References

[29 CFR 1904.39] Occupational Safety and Health Administration. 29 CFR 1904.39, Reporting fatalities, hospitalizations, amputations, and losses of an eye as a result of work-related incidents to OSHA. https://www.ecfr.gov/current/title-29/subtitle-B/chapter-XVII/part-1904/subpart-E/section-1904.39

[29 CFR 1904.41] Occupational Safety and Health Administration. 29 CFR 1904.41, Electronic submission of Employer Identification Number (EIN) and injury and illness records to OSHA. https://www.ecfr.gov/current/title-29/subtitle-B/chapter-XVII/part-1904/subpart-E/section-1904.41

[40 CFR 68.42] US Environmental Protection Agency. 40 CFR 68.42, Five-year accident history. https://www.law.cornell.edu/cfr/text/40/68.42

[CSB 2007] US Chemical Safety and Hazard Investigation Board (2007). BP America (Texas City) Refinery Explosion, Final Investigation Report, released March 20, 2007. https://www.csb.gov/bp-america-texas-city-refinery-explosion/

[DLP] Data Liberation Project. EPA Risk Management Program Database (obtained by FOIA request; data through December 31, 2025). https://www.data-liberation-project.org/datasets/epa-risk-management-program-database/

[Elliott, Kleindorfer and Lowe 2003] Elliott, M. R., Kleindorfer, P. R., & Lowe, R. A. (2003). The role of hazardousness and regulatory practice in the accidental release of chemicals at U.S. industrial facilities. Risk Analysis, 23(5), 883-896. https://doi.org/10.1111/1539-6924.00366

[Elliott et al. 2008] Elliott, M. R., Kleindorfer, P. R., DuBois, J. J., Wang, Y., & Rosenthal, I. (2008). Linking OII and RMP data: does everyday safety prevent catastrophic loss? International Journal of Risk Assessment and Management (published online November 1, 2008). https://www.inderscience.com/info/e_inarticle.php?artid=21058

[EPA RMP] US Environmental Protection Agency. Risk Management Program (RMP) Rule. https://www.epa.gov/rmp

[Gebru et al. 2021] Gebru, T., Morgenstern, J., Vecchione, B., Vaughan, J. W., Wallach, H., Daumé III, H., & Crawford, K. (2021). Datasheets for datasets. Communications of the ACM. https://doi.org/10.1145/3458723

[Hopkins 2009] Hopkins, A. (2009). Thinking about process safety indicators. Safety Science, 47(4), 460-465. https://doi.org/10.1016/j.ssci.2007.12.006

[Kleindorfer et al. 2003] Kleindorfer, P. R., Belke, J. C., Elliott, M. R., Lee, K., Lowe, R. A., & Feldman, H. I. (2003). Accident epidemiology and the U.S. chemical industry: accident history and worst-case data from RMP*Info. Risk Analysis, 23(5), 865-881. https://doi.org/10.1111/1539-6924.00365

[OSHA ITA] Occupational Safety and Health Administration. Injury Tracking Application (ITA) Data: Establishment and Case Detail Work-related Injury and Illness Data. https://www.osha.gov/Establishment-Specific-Injury-and-Illness-Data

[OSHA SIR] Occupational Safety and Health Administration. Severe Injury Reports. https://www.osha.gov/severe-injury-reports

[Spiegelhalter 2005] Spiegelhalter, D. J. (2005). Funnel plots for comparing institutional performance. Statistics in Medicine, 24(8), 1185-1202. https://doi.org/10.1002/sim.1970
