"""Join the three sources into one list of plants.

There is no shared ID across EPA and OSHA data, so plants are joined on
address: 5-digit ZIP plus the street number, with a name check as the
fallback when the street number is missing or differs. Every join records
how it was made so the match rate can be reported rather than assumed.
"""
import re

STATES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR", "CALIFORNIA": "CA",
    "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE", "DISTRICT OF COLUMBIA": "DC",
    "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL",
    "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA",
    "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN",
    "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
    "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR",
    "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT", "VIRGINIA": "VA",
    "WASHINGTON": "WA", "WEST VIRGINIA": "WV", "WISCONSIN": "WI", "WYOMING": "WY",
    "PUERTO RICO": "PR", "GUAM": "GU", "VIRGIN ISLANDS": "VI", "AMERICAN SAMOA": "AS",
    "NORTHERN MARIANA ISLANDS": "MP",
}

_STOP = {"INC", "LLC", "CO", "CORP", "CORPORATION", "COMPANY", "LP", "LTD", "THE", "OF", "PLANT",
         "FACILITY", "SITE", "USA", "US", "AMERICA", "AMERICAS", "HOLDINGS", "GROUP", "AND",
         "DIVISION", "OPERATIONS", "WORKS", "MFG", "MANUFACTURING", "CHEMICAL", "CHEMICALS"}


def state_code(s):
    s = (s or "").strip().upper()
    return STATES.get(s, s if len(s) == 2 else "")


def street_number(street):
    m = re.match(r"\s*(\d+)", street or "")
    return m.group(1) if m else ""


def name_tokens(*names):
    toks = set()
    for n in names:
        for t in re.findall(r"[A-Z0-9]+", (n or "").upper()):
            if len(t) > 1 and t not in _STOP:
                toks.add(t)
    return toks


def jaccard(a, b):
    return len(a & b) / float(len(a | b)) if a and b else 0.0


class AddressIndex:
    """Look up plants by (zip5, street number) and by zip5 alone."""

    def __init__(self):
        self.by_num = {}
        self.by_zip = {}

    def add(self, key, zip5, street, names):
        num = street_number(street)
        if zip5 and num:
            self.by_num.setdefault((zip5, num), []).append(key)
        if zip5:
            self.by_zip.setdefault(zip5, []).append((key, name_tokens(*names)))

    def find(self, zip5, street, names, min_name=0.34):
        """Return (key, method) or (None, None)."""
        num = street_number(street)
        toks = name_tokens(*names)
        if zip5 and num and (zip5, num) in self.by_num:
            cands = self.by_num[(zip5, num)]
            if len(cands) == 1:
                return cands[0], "address"
            # several plants at one address: pick by name
            best = max(cands, key=lambda k: jaccard(toks, self._tokens(zip5, k)))
            return best, "address+name"
        best, score = None, 0.0
        for key, t in self.by_zip.get(zip5, []):
            s = jaccard(toks, t)
            if s > score:
                best, score = key, s
        if best is not None and score >= min_name:
            return best, "zip+name"
        return None, None

    def _tokens(self, zip5, key):
        for k, t in self.by_zip.get(zip5, []):
            if k == key:
                return t
        return set()
