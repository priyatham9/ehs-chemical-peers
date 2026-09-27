"""Plain-language groupings for chemical plants.

Two independent labels are attached to every plant:

* ``subsector``: one label from the plant's NAICS code (what the government
  says the plant makes). Old NAICS vintages (1997-2007 codes such as 325188)
  are folded into the current 2022 groups by prefix.
* ``families``: zero or more labels from the chemicals the plant holds above
  the EPA Risk Management Program threshold (what is actually in the tanks).
  Only RMP-registered plants have families.

Both tables are data, not logic, so they can be edited without touching code.
"""

# (label, NAICS prefixes). First match wins, so longer prefixes come first.
SUBSECTORS = [
    ("Resins & plastics", ("325211",)),
    ("Synthetic rubber", ("325212",)),
    ("Fibers", ("32522",)),
    ("Petrochemicals", ("32511",)),
    ("Industrial gases", ("32512",)),
    ("Dyes & pigments", ("32513",)),
    ("Acids & inorganics", ("32518",)),
    ("Ethanol & biofuels", ("325193",)),
    ("Other basic organics (incl. formaldehyde)", ("32519",)),
    ("Fertilizer & ag chemicals", ("3253",)),
    ("Pharmaceuticals", ("3254",)),
    ("Paints & coatings", ("32551",)),
    ("Adhesives", ("32552",)),
    ("Soaps, cleaners & personal care", ("3256",)),
    ("Explosives", ("32592",)),
    ("Compounding & specialty", ("3259",)),
    ("Plastics resins (older code)", ("32521",)),
]

# (family, plain description, substrings matched against RMP chemical names)
FAMILIES = [
    ("Formaldehyde", "Makes or uses formaldehyde (resin plants, formaldehyde producers)",
     ("Formaldehyde",)),
    ("Epoxy chain", "Epichlorohydrin, the building block of epoxy resins",
     ("Epichlorohydrin",)),
    ("Ammonia", "Anhydrous or aqueous ammonia",
     ("Ammonia",)),
    ("Chlorine & chlor-alkali", "Chlorine gas and chlorinated feedstocks",
     ("Chlorine", "Vinyl chloride", "Methyl chloride", "Ethyl chloride", "Chloroform",
      "Vinylidene chloride", "Phosgene", "Phosphorus trichloride", "Phosphorus oxychloride",
      "Titanium tetrachloride")),
    ("Strong acids", "Hydrofluoric, hydrochloric, nitric, oleum and sulfur trioxide",
     ("Hydrogen fluoride", "Hydrogen chloride", "Hydrochloric acid", "Nitric acid", "Oleum",
      "Sulfur trioxide", "Peracetic acid", "Hydrocyanic acid", "Fluorine")),
    ("Isocyanates", "Toluene diisocyanate and related (polyurethane chain)",
     ("diisocyanate", "isocyanate")),
    ("Reactive oxides", "Ethylene oxide and propylene oxide",
     ("Ethylene oxide", "Propylene oxide")),
    ("Monomers", "Vinyl acetate, acrylonitrile, butadiene, isoprene",
     ("Vinyl acetate", "Acrylonitrile", "Butadiene", "Isoprene", "Acrolein", "Allyl alcohol")),
    ("Amines", "Methylamines, ethylenediamine and other amines",
     ("amine", "Piperidine", "Hydrazine")),
    ("Silanes", "Chlorosilanes (silicones chain)",
     ("silane",)),
    ("Sulfur compounds", "Sulfur dioxide, hydrogen sulfide, carbon disulfide, mercaptans",
     ("Sulfur dioxide", "Hydrogen sulfide", "Carbon disulfide", "mercaptan")),
    ("Flammable gases & liquids", "Hydrocarbons such as propane, propylene, ethylene, pentane",
     ("Flammable Mixture", "Propane", "Propylene", "Ethylene", "Pentane", "Butane", "Butene",
      "Methane", "Ethane", "Hydrogen", "Acetylene", "ether", "Pentene", "butene", "Isobutane",
      "Methylpropene", "Acetaldehyde", "Methyl formate")),
]

# Families that the flammables rule would otherwise swallow by substring.
_NOT_FLAMMABLE = ("Ethylene oxide", "Propylene oxide", "Hydrogen fluoride", "Hydrogen chloride",
                  "Hydrogen sulfide", "Ethylenediamine", "Vinyl methyl ether")

SIZE_BANDS = [
    ("Under 50", 0, 50),
    ("50-99", 50, 100),
    ("100-249", 100, 250),
    ("250-999", 250, 1000),
    ("1,000+", 1000, float("inf")),
]

INVENTORY_BANDS = [
    ("Under 100k lb", 0, 1e5),
    ("100k-1M lb", 1e5, 1e6),
    ("1M-5M lb", 1e6, 5e6),
    ("5M+ lb", 5e6, float("inf")),
]


def clean_naics(code):
    """'325211.00' -> '325211'; blanks -> ''."""
    s = str(code or "").strip()
    if "." in s:
        s = s.split(".", 1)[0]
    return s if s.isdigit() else ""


def is_chemical(code):
    return clean_naics(code).startswith("325")


def subsector(code):
    s = clean_naics(code)
    for label, prefixes in SUBSECTORS:
        if any(s.startswith(p) for p in prefixes):
            return label
    return "Other chemical" if s.startswith("325") else ""


def families(chemical_names):
    """Map RMP chemical names to family labels, in FAMILIES order."""
    out = []
    for fam, _desc, keys in FAMILIES:
        for name in chemical_names:
            if fam == "Flammable gases & liquids" and any(n in name for n in _NOT_FLAMMABLE):
                continue
            if any(k.lower() in name.lower() for k in keys):
                out.append(fam)
                break
    return out


def band(value, bands):
    if value is None:
        return ""
    for label, lo, hi in bands:
        if lo <= value < hi:
            return label
    return ""
