# A Foundry-style ontology for US chemical plants

This is an independent design in the style of a Palantir Foundry Ontology. It
is built only on public EPA and OSHA records and this repository's own
outputs. It is not affiliated with or endorsed by Palantir, it does not need a
Foundry account, and it uses no employer data.

Code: `src/chempeers/ontology/`. Spec: `src/chempeers/ontology/spec.json`.
Tests: `tests/test_ontology.py`. Like the rest of the repository it uses the
Python standard library only.

## Why an ontology on top of the join

The pipeline already joins three agencies' records into one plant list. The
join is the weakest step: no identifier is shared, so a plant's EPA
registration and its OSHA injury logs are matched by address and name. An EHS
analyst using these data needs to see each match as a thing in its own right
(how it was made, how far to trust it), to say "these two records are not the
same plant" and have every downstream number follow, and to hold a plant out
of peer comparisons while it is checked, all with an audit trail. In Foundry
those needs map to object types, link types with a backing join object,
actions and functions. This package builds the same structure in plain Python
so it runs anywhere and can be checked by tests.

## Foundry concept to this build

| Foundry concept | This build |
|---|---|
| Ontology (object and link type definitions) | `spec.json`, loaded and checked by `spec.load_spec()`. Checks: primary and title keys exist; primary keys are non-nullable and not editable; property types are known; links point at real types; foreign keys match the target key's type and are read-only; join objects carry the declared link properties; link names do not clash; actions edit only editable properties and reference real parameters; each function's `reuses` path imports. Every error is reported at once. |
| Object type (primary key, title, typed properties) | `object_types`. `ObjectStore.add_objects()` coerces each value to its declared type (including `string_array`) and rejects nulls in non-nullable properties and duplicate keys. |
| Multi-source backing datasets | `materialise.build_store()`. EPA RMP (registrations, processes, holdings, accidents), OSHA Form 300A (establishments, plant-years) and OSHA Severe Injury Reports become separate object types, all from the committed linked dataset in `docs/data/*.json`. SizeBand comes from `outputs/summary.json`. The same function accepts `chempeers.build.assemble` output, so the raw downloads or the synthetic fixture can back it instead. Every object has a `source` property. |
| Link type (cardinality, foreign key) | `link_types` with `one_to_one`, `many_to_one` or `many_to_many`. One-to-one links are checked for duplicate targets. `integrity_report()` counts resolved, null and dangling keys for every link. |
| Many-to-many link backed by a join object, with link properties | `rmp_osha_match` (RmpRegistration to OshaEstablishment) is backed by `PlantMatch` objects. `match_method`, `confidence` and `review_status` travel with each traversal through `ObjectStore.link_rows()`. A match with `review_status = rejected` is not traversed (`hide_when`). `accident_chemicals` is a many-to-many link backed by an array property. |
| Object Set, filters, Search Around | `ObjectSet.where()`, `.filter()`, `.search_around(link)` and `ObjectStore.linked(obj, link)`. |
| Function (on objects or the whole ontology) | `functions.py`. Each function turns objects back into the records the pipeline reads (`pipeline_view`) and calls the module named in the spec under `reuses`. No rate, band or finding is written a second time. |
| Action type (parameters, submission criteria, edits) | `action_types`. Parameters can declare `required`, `required_when`, `allowed_values`, `min_length` and `max_length`. Submission criteria check the target's current state and carry a failure message. Edits set editable properties to literals or `$parameter` values. |
| Writeback | The editable `PlantMatch.review_*` and `Plant.review_*` properties. `ObjectStore.apply()` is the only way to change them. |
| Action log / edit history | Each applied action appends an entry with id, action type, actor, UTC timestamp, parameters, and the before and after value of every edit. `edit_history(type, pk)` returns one object's history. A rejected action changes nothing and logs nothing. |
| Export | `export.export_sqlite()` writes one table per object type with typed columns and an enforced primary key, a `link_<name>` table per many-to-many link, `action_log` and `ontology_spec`. `export.export_json()` writes the same content as strict JSON. |

## Object types

Counts are for the committed linked dataset. The first six match
`outputs/summary.json` `coverage` exactly, and the tests assert it.

| Object type | Key | Objects | Backing data | Decision it supports |
|---|---|---|---|---|
| Plant | `plant_id` | 10,597 | `plants.json` | The plant a comparison is about; carries product type, size band, join method and the review writeback. |
| RmpRegistration | `epa_facility_id` | 2,773 | `plants.json` rows with an EPA ID | What the plant holds and when it filed with EPA. |
| OshaEstablishment | `osha_key` | 9,178 | `plants.json` injury-log years | The OSHA side of a plant, kept apart from the EPA side so the join between them can be reviewed. |
| PlantMatch | `match_key` | 1,354 | `plants.json` `match` for EPA plants with logs | Is this EPA registration really this OSHA establishment? |
| Accident | `accident_key` | 2,611 | `releases.json` | What a plant's five-year RMP accident history says happened, where, why and what changed. |
| SeriousInjury | `injury_key` | 1,913 | `injuries.json` | Amputations, eye losses and hospitalisations, joined to a plant where the address allows. |
| InjuryLogYear | `log_key` | 40,369 | `plants.json` injury-log years | Does this plant-year enter a rate (hours screen) and with what counts? |
| Process | `process_key` | 3,227 | product types of each EPA plant | Which product types an EPA registration declares. |
| ChemicalHolding | `holding_key` | 5,155 | `plants.json` chemicals (top ten per plant) | Pounds of each chemical held; the join object between registration and chemical. |
| Chemical | `chemical_name` | 124 | names in holdings and accidents | Which plants hold, and which accidents released, a given chemical. |
| PeerGroup | `peer_group_key` | 79 | product type x size band over Plant | The explorer's default "match my plant" peer set. |
| SizeBand | `band` | 5 | `outputs/summary.json` `size_noise` and `stability` | How far one injury moves a rate at this size, and how stable rankings are. |

## The RMP to OSHA join as a link

`PlantMatch` holds the pipeline's join method and a confidence level. The
confidence is this ontology's own rubric over the method; it is not a pipeline
output and has not been validated against a third source.

| Method | Matches | Confidence | Rule (`chempeers.link.AddressIndex.find`) |
|---|---|---|---|
| `address` | 1,163 | high | One EPA plant at the 5-digit ZIP and street number. |
| `address+name` | 96 | medium | Several EPA plants at that address; the best name-token overlap was picked. |
| `zip+name` | 95 | low | Street number differs or is missing; same ZIP and name-token Jaccard of at least 0.34. |

## Actions

| Action | Parameters | Submission criteria | Effect |
|---|---|---|---|
| `reject_match` (flag a match as wrong) | match, reason (enum), note (required if reason is `other`) | the match is not already rejected | `review_status = rejected`; the link is hidden and the OSHA logs leave the EPA plant in every function |
| `confirm_match` | match, note (10-500 characters) | the match is unreviewed | `review_status = confirmed` |
| `mark_plant_for_review` | plant, reason (enum), note (required if reason is `other`) | the plant is not under review | `review_status = under_review`; left out of default peer sets |
| `clear_plant_review` | plant, note (10-500 characters) | the plant is under review | `review_status = none` |

Rejecting a match moves the numbers the way undoing the join would: the
OSHA logs become a separate OSHA-only plant, so `coverage()` reports one more
plant and one fewer linked plant, and the EPA plant's rates and release
predictors no longer use those logs. The tests check this.

## Functions

| Function | Input | Reuses | Check |
|---|---|---|---|
| `coverage` | store | `chempeers.analysis.coverage` | Equals `summary.json` `coverage` (except `ita_plant_years`, below). |
| `size_noise` | store | `chempeers.analysis.size_noise` | Equals `summary.json` exactly. |
| `release_predictors` | store | `chempeers.analysis.release_predictors` | Equals `summary.json` exactly. |
| `green_dashboard` | store | `chempeers.analysis.green_dashboard` | Equals `summary.json` exactly. |
| `plant_rates` | Plant | `chempeers.stats.rate` | Pooled TRIR over screened years. |
| `funnel_position` | Plant, optional peer set | `chempeers.stats.classify` | Above, below or within the exact-Poisson 95% band of the peers' pooled rate. |

On the synthetic fixture the first four functions equal
`chempeers.analysis.findings` on the pipeline's own records, field for field.

## Running it

```bash
make ontology                                                   # committed data -> build/ontology
PYTHONPATH=src python3 -m chempeers.ontology --out /tmp/ontology --raw data/raw   # after make data
python3 -m unittest tests/test_ontology.py
```

The command prints the object census, the link integrity report and
`coverage()`, then writes `ontology.sqlite` and `ontology.json` to `--out`.
It never writes under `outputs/` or `docs/`. From Python:

```python
from chempeers.ontology.materialise import build_store
from chempeers.ontology import functions as F

store = build_store()
match = next(iter(store.objects("PlantMatch").where(confidence="low")))
reg = store.linked(match, "registration").one()
store.link_rows(reg, "osha_establishments")        # linked establishment + link properties
store.apply("reject_match", {"match": match, "reason": "name_match_wrong"}, actor="you@example.org")
F.coverage(store)["linked_plants"]                  # one fewer than before
store.action_log[-1].to_json()
```

## Limits

- The committed export does not publish OSHA establishment IDs, so an
  OshaEstablishment is the set of injury logs the pipeline attributed to one
  plant (`establishment_ids` is empty unless the store is built from
  `build.assemble`). Where two establishments fall on one plant-year the
  pipeline keeps the larger, which is why 42,794 establishment-years in
  `summary.json` become 40,369 InjuryLogYear objects.
- Nothing here re-runs the address join. Rejecting a match only undoes it;
  there is no action that proposes a new match.
- ChemicalHolding has the ten largest holdings per plant, as the site export
  does; RmpRegistration `inventory_lb` is the full total.
- Process is the product-type level of an RMP process. The committed extract
  keeps NAICS codes per facility, so a Process has no chemicals of its own.
- 1,210 of 1,913 serious-injury reports join to a plant; the rest have a null
  `plant_id`. Reports from state-plan states are not in the source file.
- The store lives in memory. Actions are checked against the spec, but there
  is no user or permission model: `actor` is whatever string the caller passes.
