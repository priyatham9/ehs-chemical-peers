# Contributing

## Running the tests

```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

The real-data tests skip when `data/raw` is empty, so the suite passes on a fresh clone without a network. Everything else runs on the synthetic fixture in `tests/_fixture.py`.

## Dependencies

Python 3.9 or later, standard library only. The site is plain HTML and JavaScript with no build step beyond `scripts/build_story.py` and `scripts/apply_header.py`.

## Numbers

Every number in the README, the story and the site comes from `scripts/build_data.py`:

1. `outputs/summary.json` holds the findings; `docs/data/meta.json` carries the same object for the site.
2. `tests/test_readme_consistency.py` reads the README numbers back and compares them with the summary.
3. The story page is rendered from a template whose numbers are tokens resolved against the summary; an unknown token stops the build.
4. No number is typed by hand or carried over from another source.

## Labels

Product types and chemical families are tables in `src/chempeers/taxonomy.py`. Change the table, rebuild, and the explorer's filters follow.

## Style

No em dashes. Plain words over jargon in anything a reader sees.
