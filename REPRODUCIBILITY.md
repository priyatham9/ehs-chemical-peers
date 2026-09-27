# Reproducibility

```bash
make data    # downloads 14 files into data/raw and writes data/raw/manifest.json with SHA-256 digests
make build   # about 11 seconds on a 2023 laptop; writes outputs/summary.json and docs/data/*.json
make pages   # re-renders docs/story.html from templates/story.src.html and re-applies the shared header
make test
```

`docs/data/meta.json` records a short digest of every raw file the site data was built from (`built_from`). `tests/test_real_data.py` rebuilds from `data/raw` and fails if the result differs from the committed `outputs/summary.json`.

The source files change: OSHA adds a year of injury logs each spring and updates the Severe Injury Reports file, and the Data Liberation Project refreshes the RMP extract. A rebuild against newer files will change the numbers; the digests say which files a given build used.
