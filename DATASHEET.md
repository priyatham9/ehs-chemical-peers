# Datasheet: ehs-chemical-peers linked plant dataset

Following the questions in Gebru et al., "Datasheets for Datasets".

## Motivation

Built to let anyone compare a US chemical manufacturing plant with its peers using only public records, and to test which public signals say anything about chemical releases and serious injuries.

## Composition

* **Plants** (`docs/data/plants.json`): one row per chemical manufacturing plant (NAICS 325). A plant is either an EPA Risk Management Program facility with a NAICS 325 code in any submission (id `R<EPA facility ID>`), or an OSHA injury-log establishment that did not join to one (id `I<OSHA establishment ID>`). Each row carries identity, product types, chemical families, up to ten chemicals with pounds held, and one record per injury-log year: hours, average employees, days-away, job-transfer and other recordable cases, illness count, days-away days, and whether the filing passed the hours screen.
* **Releases** (`docs/data/releases.json`): EPA RMP accident-history records for those plants, with yes/no flags for what happened, the source, contributing causes and changes made afterwards, plus injuries, evacuations and damage.
* **Serious injuries** (`docs/data/injuries.json`): OSHA Severe Injury Reports with a NAICS 325 primary code, with the plant they joined to (or none), the energy group, outcome, and the narrative cut to 420 characters.

## Collection and joins

Files are downloaded by `scripts/download_data.py` from osha.gov and from the Data Liberation Project's GitHub release of the EPA RMP database. Joins are by 5-digit ZIP and street number; where that fails, by ZIP and overlap of name tokens (at least a third of distinct tokens, with common words such as "Inc" and "Plant" removed). Two OSHA filings for one plant-year keep the larger. Every plant records its join method (`address`, `address+name`, `zip+name`, `epa only`, `osha only`).

## Known gaps

* OSHA injury logs are required only from establishments above a size threshold, so many small EPA-registered plants have none.
* Serious-injury reports cover federal-OSHA states only.
* RMP accident histories cover the five years before each submission, and only releases that meet EPA's reporting criteria.
* Address joins miss plants whose two filings use different addresses, and can join two different employers at one shared address.
* Everything is self-reported by employers.

## Uses

Peer comparison, teaching, and hypothesis generation. Not suitable for enforcement, ranking plants for public blame, or causal claims.

## Distribution and licence

Code under MIT. Source records are US government public records; the RMP extract is republished by the Data Liberation Project.
