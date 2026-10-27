# How stable are a plant's nearest peers?

The explorer compares a plant with a group of peers. Which plants count as
"nearest" depends on choices: which attributes are compared and how much each
one counts. This page measures how much a plant's nearest peers change when
those choices are perturbed. The code is `src/chempeers/stability.py`, the
build is `scripts/build_stability.py`, and it uses only the committed
`docs/data/plants.json`. It is seeded and deterministic: the same inputs give
byte-identical outputs.

Outputs:

* `outputs/peer_stability.csv`: one row per plant (10,575 plants with an employee count).
* `outputs/peer_stability.json`: parameters, coverage and summaries.
* `docs/data/stability.json`: median stability of the plants in each comparison-page group, shown on [compare.html](compare.html).

## Method

**Similarity.** Each plant has 15 attributes: product type, 12 chemical-family
flags, size band and inventory level (the pounds band, or 0 when there is no
pounds figure). The distance between two plants is a weighted sum of
differences: 0 or 1 for the product type and each family flag, and the level
difference divided by 4 for size band and inventory level. Baseline weights are
2 for product type and size band and 1 for each family flag and for inventory
level. These weights are a judgement, not fitted to anything. A plant's peers
are its `k = 10` nearest other plants. Plants at exactly the same distance are
ordered by a seeded random priority.

**Perturbations.** Each replicate recomputes every plant's peers. There are
100 replicates for each of three schemes:

1. `tiebreak`: baseline weights, new random priorities only.
2. `bootstrap`: the 15 attributes are resampled with replacement and each
   weight is the baseline weight times the number of times the attribute was drawn
   (zero if not drawn). This is feature resampling.
3. `noise`: each baseline weight is multiplied by exp(0.5 z), z standard normal.

**Scores.** Two scores per plant and scheme, each averaged over replicates:

* `exact`: the share of the baseline peers (the same plants) still among the new nearest 10.
* `neighbourhood`: the share of the new nearest 10 that are no farther from the plant, at baseline weights, than the baseline 10th peer. Plants tied with that peer all count, so swapping one equally close plant for another is not penalised.

The headline `stability` in the CSV is the `bootstrap` neighbourhood score.
The seed and all parameters are written into `outputs/peer_stability.json`.

## What it shows

* **Typical plant.** The median `stability` is 0.509 (middle half 0.450 to 0.553). In plain terms: after resampling the attributes, about half of the plant's new nearest peers would have been just as good a match under the original weights, and about half would not. 53.15% of plants score at least 0.5; none score 0.9 or more.
* **Weight noise barely matters.** Under `noise`, the median neighbourhood score is 1.000. Scaling every weight by a random factor around 1 rarely brings in a plant that was not already as close. What moves the peer set is dropping or doubling whole attributes (`bootstrap`), not nudging their weights.
* **The exact list is mostly arbitrary.** The median exact retention is 0.025 under `bootstrap` and 0.041 even under `tiebreak` alone, where only the order among equally close plants changes. The reason is ties: the median plant has 195 other plants exactly as close as its 10th peer, and 6,965 of the 10,575 plants have 100 or more. Fifteen coarse attributes cannot single out ten peers. A named list of "the ten nearest peers" would overstate what the data can say; a group defined by the attributes (what the explorer filters do) is the honest object.
* **By size band** (median `stability`): Under 50, 0.525; 50-99, 0.469; 100-249, 0.456; 250-999, 0.471; 1,000+, 0.573. By product type, see `outputs/peer_stability.json`.

## How to read it, and limits

* A high score means the plant's peer group does not depend much on which attributes you compare. A low score means it does, so a comparison against that group is more sensitive to the grouping chosen. It says nothing about whether the plant is safe, and it is not a quality score for the plant.
* It measures sensitivity to the attributes and weights, not to errors in the data. Employee counts, pounds held, family labels and the EPA to OSHA join (see [method.html](method.html)) are taken as given.
* Only the attributes in `plants.json` are used. State, injury rates and release history are not part of the similarity, so the peers here are structural peers, not outcome peers. The "Match my plant" button uses a subset of the same attributes.
* The baseline weights and the choice of `k = 10` are judgements. The bootstrap treats the 15 attributes as exchangeable draws, which they are not (12 are family flags that overlap). The scores are comparisons between settings of this particular design, not probabilities.
* Plants without an employee count (22) are not scored. Product type is the first listed type, as in the explorer, which can differ from the NAICS grouping used in the injury groups on the comparison page; group medians there use the plant's own attributes.
* The results are for this snapshot of the committed data and 100 replicates per scheme.

Reproduce: `make stability` (about two minutes). `python3 scripts/build_stability.py --check` compares a fresh build with the committed files.

This is independent analysis of public records. It is not an audit of any plant and is not affiliated with any vendor.
