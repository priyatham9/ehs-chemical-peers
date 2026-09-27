"""A tiny, obviously fake raw-data folder with known answers.

Three plants:
  A  EPA-registered formaldehyde resin plant, files OSHA logs at the same
     address (joins on ZIP + street number), one release in 2019.
  B  OSHA-only adhesives plant whose EPA-style name differs; joins on nothing.
  C  EPA-registered chlorine plant whose OSHA filing uses a different street
     number but the same ZIP and a close name (joins on ZIP + name).
One serious injury at A (federal-OSHA state) and one at an unrelated employer.
"""
import csv
import io
import zipfile
from pathlib import Path

ITA_HEAD = ["id", "company_name", "establishment_name", "ein", "street_address", "city", "state",
            "zip_code", "naics_code", "industry_description", "annual_average_employees",
            "total_hours_worked", "no_injuries_illnesses", "total_deaths", "total_dafw_cases",
            "total_djtr_cases", "total_other_cases", "total_dafw_days", "total_djtr_days",
            "total_injuries", "total_poisonings", "total_respiratory_conditions",
            "total_skin_disorders", "total_hearing_loss", "total_other_illnesses",
            "establishment_id", "establishment_type", "size", "year_filing_for",
            "created_timestamp", "change_reason"]


def _ita_row(est, name, company, street, city, state, zip5, naics, emp, hours, dafw, djtr, other,
             year):
    r = dict.fromkeys(ITA_HEAD, "0")
    r.update(id=est + str(year), company_name=company, establishment_name=name, ein="",
             street_address=street, city=city, state=state, zip_code=zip5, naics_code=naics,
             industry_description="", annual_average_employees=str(emp),
             total_hours_worked=str(hours), total_dafw_cases=str(dafw), total_djtr_cases=str(djtr),
             total_other_cases=str(other), establishment_id=est, year_filing_for=str(year),
             created_timestamp="", change_reason="")
    return r


def _zip_csv(path, name, head, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=head)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(name, buf.getvalue())


def _csv(path, head, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=head)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in head})


def build(raw):
    raw = Path(raw)
    raw.mkdir(parents=True, exist_ok=True)
    rows = []
    for y in (2018, 2019, 2020):
        rows.append(_ita_row("1", "Resin Plant A", "Acme Resins", "100 Main St", "Town", "TX",
                             "77001", "325211", 60, 120000, 1 if y == 2019 else 0, 0, 0, y))
        rows.append(_ita_row("2", "Glue Works B", "Bond Co", "5 Side Rd", "Ville", "OH", "44001",
                             "325520", 30, 60000, 0, 0, 1, y))
        rows.append(_ita_row("3", "Chlor Plant C", "Chlor Corp", "900 River Rd", "City", "LA",
                             "70001", "325180", 300, 600000, 2, 1, 3, y))
    # one implausible filing (hours per employee far above 4,500) that must be screened out
    rows.append(_ita_row("2", "Glue Works B", "Bond Co", "5 Side Rd", "Ville", "OH", "44001",
                         "325520", 30, 90000000, 0, 0, 0, 2021))
    _zip_csv(raw / "ITA_Data_CY_2018.zip", "ITA Data CY 2018.csv", ITA_HEAD, rows)

    fac_head = ["EPAFacilityID", "Name", "LatestCompany1", "LatestCompany2", "LatestOperator",
                "Addr1", "Addr2", "City", "State", "ZipCode", "CountyFIPS", "Lat", "Lng",
                "NumSubmissions", "LatestValidationDate", "LatestReceiptDate", "LatestDeregDate",
                "LatestDeregEffDate", "NAICSCodesInLatest", "ChemicalsInLatest",
                "AccidentChemicalsInLatest", "NumAccidentsInLatest"]
    _csv(raw / "facilities.csv", fac_head, [
        {"EPAFacilityID": "900", "Name": "Acme Resins Town Plant", "LatestCompany1": "Acme Resins",
         "Addr1": "100 Main Street", "City": "TOWN", "State": "TX", "ZipCode": "77001",
         "NAICSCodesInLatest": "325211 • 325199",
         "ChemicalsInLatest": "Formaldehyde (solution) {3000000} • Ammonia (conc 20% or greater) {200000}"},
        {"EPAFacilityID": "901", "Name": "Chlor Corp Plant C", "LatestCompany1": "Chlor Corp",
         "Addr1": "1 Industrial Pkwy", "City": "CITY", "State": "LA", "ZipCode": "70001",
         "NAICSCodesInLatest": "325180", "ChemicalsInLatest": "Chlorine {500000}"},
        {"EPAFacilityID": "902", "Name": "Water Plant", "LatestCompany1": "City",
         "Addr1": "1 Lake Rd", "City": "X", "State": "TX", "ZipCode": "77002",
         "NAICSCodesInLatest": "22131", "ChemicalsInLatest": "Chlorine {10000}"},
    ])
    sub_head = ["SubmissionID", "ReceiptDate", "ValidationDate", "DeregDate", "DeregEffDate",
                "SubType", "SubReason", "EPAFacilityID", "FacName", "FacLat", "FacLng", "FRSLat",
                "FRSLng", "FacFTE", "FacCompany1", "FacCompany2", "FacOperator", "NAICSCodes",
                "Chemicals", "AccidentChemicals", "NumAccidents", "LatestAccidentDate"]
    _csv(raw / "submissions.csv", sub_head, [
        {"SubmissionID": "1", "ReceiptDate": "2014-06-01", "EPAFacilityID": "900", "FacFTE": "55",
         "NAICSCodes": "325211"},
        {"SubmissionID": "2", "ReceiptDate": "2019-06-01", "EPAFacilityID": "900", "FacFTE": "60",
         "NAICSCodes": "325211 • 325199"},
        {"SubmissionID": "3", "ReceiptDate": "2016-06-01", "EPAFacilityID": "901", "FacFTE": "300",
         "NAICSCodes": "325180"},
        {"SubmissionID": "4", "ReceiptDate": "2016-06-01", "EPAFacilityID": "902", "FacFTE": "5",
         "NAICSCodes": "22131"},
    ])
    acc_head = ["EPAFacilityID", "SubmissionID", "AccidentHistoryID", "AccidentDate",
                "AccidentChemicals", "NAICSCode", "RE_Spill", "RE_Gas", "RS_ProcessVessel",
                "CF_HumanError", "CF_EquipmentFailure", "CI_RevisedTraining", "InjuriesWorkers",
                "InjuriesPublicResponders", "InjuriesPublic", "DeathsWorkers",
                "DeathsPublicResponders", "DeathsPublic", "Evacuated", "ShelteredInPlace",
                "OnsitePropertyDamage", "OffsitePropertyDamage"]
    _csv(raw / "accidents.csv", acc_head, [
        {"EPAFacilityID": "900", "AccidentDate": "2019-03-02",
         "AccidentChemicals": "Formaldehyde (solution) {500}", "RE_Spill": "Yes",
         "RS_ProcessVessel": "Yes", "CF_HumanError": "Yes", "CI_RevisedTraining": "Yes",
         "InjuriesWorkers": "1"},
        {"EPAFacilityID": "902", "AccidentDate": "2019-01-01", "AccidentChemicals": "Chlorine {5}",
         "RE_Gas": "Yes"},
    ])
    sir_head = ["ID", "UPA", "EventDate", "Employer", "Address1", "Address2", "City", "State", "Zip",
                "Latitude", "Longitude", "Primary NAICS", "Hospitalized", "Amputation",
                "Loss of Eye", "Inspection", "Final Narrative", "Nature", "NatureTitle",
                "Part of Body", "Part of Body Title", "Event", "EventTitle", "Source",
                "SourceTitle", "Secondary Source", "Secondary Source Title", "FederalState"]
    base = dict.fromkeys(sir_head, "")
    _zip_csv(raw / "January2015toNovember2025.zip", "January2015toNovember2025.csv", sir_head, [
        dict(base, ID="1", EventDate="4/5/2020", Employer="Acme Resins", Address1="100 Main St",
             City="TOWN", State="TEXAS", Zip="77001", **{"Primary NAICS": "325211"},
             Hospitalized="0", Amputation="1", **{"Final Narrative": "Finger caught in mixer."},
             Event="6411", EventTitle="Caught in running equipment", SourceTitle="Mixer"),
        dict(base, ID="2", EventDate="7/1/2021", Employer="Other Chem", Address1="1 Nowhere",
             City="ELSE", State="OHIO", Zip="44999", **{"Primary NAICS": "325998"},
             Hospitalized="1", Amputation="0", Event="5531", EventTitle="Chemical burn"),
        dict(base, ID="3", EventDate="7/1/2021", Employer="Bakery", Address1="1 Bread St",
             City="ELSE", State="OHIO", Zip="44999", **{"Primary NAICS": "311812"},
             Hospitalized="1", Event="4"),
    ])
    return raw
