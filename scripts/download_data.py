#!/usr/bin/env python3
"""Download the public source files into data/raw and record their digests.

    python3 scripts/download_data.py          # fetch anything missing
    python3 scripts/download_data.py --list   # print the catalog

Sources
  OSHA Injury Tracking Application, Form 300A summaries, calendar years 2016-2024
  OSHA Severe Injury Reports, January 2015 to November 2025
  EPA Risk Management Program database, as released by the Data Liberation
  Project from a FOIA request (facilities, submissions, accident histories)
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OSHA = "https://www.osha.gov/sites/default/files/"
DLP = "https://raw.githubusercontent.com/data-liberation-project/epa-rmp-spreadsheets/main/data/output/"

CATALOG = [
    ("ITA_Data_CY_2016.zip", OSHA + "ITA%20Data%20CY%202016.zip"),
    ("ITA_Data_CY_2017.zip", OSHA + "ITA%20Data%20CY%202017.zip"),
    ("ITA_Data_CY_2018.zip", OSHA + "ITA%20Data%20CY%202018.zip"),
    ("ITA_Data_CY_2019.zip", OSHA + "ITA%20Data%20CY%202019.zip"),
    ("ITA_Data_CY_2020.zip", OSHA + "ITA%20Data%20CY%202020.zip"),
    ("ITA_Data_CY_2021.zip", OSHA + "ITA%20Data%20CY%202021.zip"),
    ("ITA_Data_CY_2022.zip", OSHA + "ITA%20Data%20CY%202022.zip"),
    ("ITA_300A_Summary_Data_2023_through_12-31-2024.zip",
     OSHA + "ITA_300A_Summary_Data_2023_through_12-31-2024.zip"),
    ("ITA_300A_Summary_Data_2024_through_12-31-2025.zip",
     OSHA + "ITA_300A_Summary_Data_2024_through_12-31-2025.zip"),
    ("January2015toNovember2025.zip", OSHA + "January2015toNovember2025.zip"),
    ("facilities.csv", DLP + "facilities.csv"),
    ("submissions.csv", DLP + "submissions.csv"),
    ("accidents.csv", DLP + "accidents.csv"),
    ("naics-codes.csv", DLP + "naics-codes.csv"),
]
UA = {"User-Agent": "Mozilla/5.0 (research download; ehs-chemical-peers)"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url, dest):
    req = urllib.request.Request(url, headers=UA)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as fh:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
    tmp.replace(dest)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if a.list:
        for name, url in CATALOG:
            print("%-52s %s" % (name, url))
        return 0
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, url in CATALOG:
        dest = RAW / name
        if a.force or not dest.exists():
            print("fetching", name, file=sys.stderr)
            fetch(url, dest)
        manifest.append({"file": name, "url": url, "bytes": dest.stat().st_size,
                         "sha256": sha256(dest)})
    (RAW / "manifest.json").write_text(json.dumps({
        "retrieved_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "files": manifest}, indent=1))
    print("%d files in %s" % (len(manifest), RAW))
    return 0


if __name__ == "__main__":
    sys.exit(main())
