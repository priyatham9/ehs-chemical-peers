"""Readers for the three public sources, filtered to chemical manufacturing.

Every reader streams its file and keeps only NAICS 325 rows (for RMP, any
facility whose latest or any past submission lists a 325 code), so memory
stays small even though the source files hold every industry.
"""
import csv
import io
import re
import zipfile
from pathlib import Path

from . import taxonomy

csv.field_size_limit(10 ** 8)

# Same plausibility screen as ehs-osha-analysis (hours per average employee).
MIN_HOURS_PER_EMPLOYEE = 120.0
MAX_HOURS_PER_EMPLOYEE = 4500.0


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _year(v):
    s = str(v or "").strip()
    return int(float(s)) if s else None


def _zip5(v):
    d = re.sub(r"\D", "", str(v or ""))
    return d[:5].zfill(5) if d else ""


# --------------------------------------------------------------------- ITA
def ita_files(raw):
    return sorted(Path(raw).glob("ITA*.zip"))


def read_ita(raw):
    """Yield one dict per NAICS 325 establishment-year from every ITA zip.

    Later files win when the same establishment-year appears twice (the
    2023-2025 files overlap on year 2024 at the file boundary only for late
    amendments).
    """
    seen = {}
    for path in ita_files(raw):
        with zipfile.ZipFile(path) as zf:
            name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            with zf.open(name) as fh:
                for r in csv.DictReader(io.TextIOWrapper(fh, encoding="latin-1")):
                    naics = taxonomy.clean_naics(r.get("naics_code"))
                    if not naics.startswith("325"):
                        continue
                    year = _year(r.get("year_filing_for"))
                    est = str(r.get("establishment_id") or "").split(".")[0].strip()
                    if not year or not est:
                        continue
                    emp = _num(r.get("annual_average_employees"))
                    hours = _num(r.get("total_hours_worked"))
                    hpe = hours / emp if emp > 0 else 0
                    rec = {
                        "est": est,
                        "year": year,
                        "name": (r.get("establishment_name") or "").strip(),
                        "company": (r.get("company_name") or "").strip(),
                        "ein": re.sub(r"\D", "", r.get("ein") or ""),
                        "street": (r.get("street_address") or "").strip(),
                        "city": (r.get("city") or "").strip(),
                        "state": (r.get("state") or "").strip().upper(),
                        "zip": _zip5(r.get("zip_code")),
                        "naics": naics,
                        "emp": emp,
                        "hours": hours,
                        "plausible": MIN_HOURS_PER_EMPLOYEE <= hpe <= MAX_HOURS_PER_EMPLOYEE,
                        "dafw": _num(r.get("total_dafw_cases")),
                        "djtr": _num(r.get("total_djtr_cases")),
                        "other": _num(r.get("total_other_cases")),
                        "deaths": _num(r.get("total_deaths")),
                        "dafw_days": _num(r.get("total_dafw_days")),
                        "resp": _num(r.get("total_respiratory_conditions")),
                        "pois": _num(r.get("total_poisonings")),
                        "skin": _num(r.get("total_skin_disorders")),
                    }
                    seen[(est, year)] = rec
    return list(seen.values())


# --------------------------------------------------------------------- RMP
_QTY = re.compile(r"^(.*?)\s*\{(\d+)\}\s*$")


def parse_chemicals(field):
    """'Formaldehyde (solution) {3500000} • Ammonia {250000}' -> [(name, lb), ...]."""
    out = []
    for part in str(field or "").split("•"):
        part = part.strip()
        if not part:
            continue
        m = _QTY.match(part)
        if m:
            out.append((re.sub(r"\s+", " ", m.group(1)).strip(), float(m.group(2))))
        else:
            out.append((re.sub(r"\s+", " ", part), 0.0))
    return out


def read_rmp(raw):
    """Return (facilities, accidents) for chemical-manufacturing RMP facilities."""
    raw = Path(raw)
    subs_by_fac = {}
    with open(raw / "submissions.csv", encoding="utf-8", errors="ignore") as fh:
        for r in csv.DictReader(fh):
            subs_by_fac.setdefault(r["EPAFacilityID"], []).append(r)

    facilities = {}
    with open(raw / "facilities.csv", encoding="utf-8", errors="ignore") as fh:
        for r in csv.DictReader(fh):
            fid = r["EPAFacilityID"]
            subs = subs_by_fac.get(fid, [])
            codes = set()
            for s in subs:
                codes.update(taxonomy.clean_naics(c) for c in str(s.get("NAICSCodes", "")).split("•"))
            latest = [taxonomy.clean_naics(c) for c in r.get("NAICSCodesInLatest", "").split("•")]
            chem_codes = [c for c in latest if c.startswith("325")] or sorted(
                c for c in codes if c.startswith("325"))
            if not chem_codes:
                continue
            years = sorted(int(s["ReceiptDate"][:4]) for s in subs if s.get("ReceiptDate"))
            fte = 0.0
            for s in sorted(subs, key=lambda s: s.get("ReceiptDate", "")):
                if _num(s.get("FacFTE")) > 0:
                    fte = _num(s.get("FacFTE"))
            chems = parse_chemicals(r.get("ChemicalsInLatest"))
            by_name = {}
            for n, q in chems:
                by_name[n] = by_name.get(n, 0.0) + q
            facilities[fid] = {
                "rmp_id": fid,
                "name": (r.get("Name") or "").strip(),
                "company": (r.get("LatestCompany1") or r.get("LatestOperator") or "").strip(),
                "street": (r.get("Addr1") or "").strip(),
                "city": (r.get("City") or "").strip().title(),
                "state": (r.get("State") or "").strip().upper(),
                "zip": _zip5(r.get("ZipCode")),
                "lat": _num(r.get("Lat")) or None,
                "lng": _num(r.get("Lng")) or None,
                "naics": chem_codes[0],
                "naics_all": chem_codes,
                "chemicals": sorted(by_name.items(), key=lambda kv: -kv[1]),
                "fte": fte or None,
                "first_year": years[0] if years else None,
                "last_year": years[-1] if years else None,
                "active": not (r.get("LatestDeregDate") or "").strip(),
            }

    accidents = []
    with open(raw / "accidents.csv", encoding="utf-8", errors="ignore") as fh:
        for r in csv.DictReader(fh):
            if r["EPAFacilityID"] in facilities:
                accidents.append(r)
    return facilities, accidents


# --------------------------------------------------------------------- SIR
def sir_file(raw):
    files = sorted(Path(raw).glob("January2015to*.zip"))
    return files[-1] if files else None


def read_sir(raw):
    path = sir_file(raw)
    if path is None:
        return []
    out = []
    with zipfile.ZipFile(path) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(name) as fh:
            for r in csv.DictReader(io.TextIOWrapper(fh, encoding="latin-1")):
                naics = taxonomy.clean_naics(r.get("Primary NAICS"))
                if not naics.startswith("325"):
                    continue
                d = str(r.get("EventDate") or "").strip()
                m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", d)
                date = "%s-%02d-%02d" % (m.group(3), int(m.group(1)), int(m.group(2))) if m else d[:10]
                out.append({
                    "id": r.get("ID"),
                    "date": date,
                    "employer": (r.get("Employer") or "").strip(),
                    "street": (r.get("Address1") or "").strip(),
                    "city": (r.get("City") or "").strip().title(),
                    "state": (r.get("State") or "").strip().upper(),
                    "zip": _zip5(r.get("Zip")),
                    "naics": naics,
                    "hosp": _num(r.get("Hospitalized")),
                    "amp": _num(r.get("Amputation")),
                    "eye": _num(r.get("Loss of Eye")),
                    "narrative": re.sub(r"\s+", " ", r.get("Final Narrative") or "").strip(),
                    "nature": (r.get("NatureTitle") or "").strip(),
                    "body": (r.get("Part of Body Title") or "").strip(),
                    "event": str(r.get("Event") or "").split(".")[0],
                    "event_title": (r.get("EventTitle") or "").strip(),
                    "source": (r.get("SourceTitle") or "").strip(),
                })
    return out
