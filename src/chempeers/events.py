"""Plain-language coding for serious injuries and chemical releases.

Serious injuries come from OSHA Severe Injury Reports, coded with the BLS
OIICS 2.01 event code. We group them by the kind of energy that hurt the
person, because energy is what a plant can find and control before anyone is
hurt. Releases come from EPA Risk Management Program accident histories,
which carry yes/no flags for what happened, where it came from, why, and what
the plant changed afterwards.
"""

# Energy groups keyed by OIICS event-code prefix. Longest prefix wins.
ENERGY_BY_EVENT = [
    ("64", "Caught in machinery"),
    ("65", "Caught in machinery"),
    ("62", "Struck by object or vehicle"),
    ("63", "Struck by object or vehicle"),
    ("66", "Rubbed, cut or pinched"),
    ("67", "Rubbed, cut or pinched"),
    ("53", "Heat, steam & hot material"),
    ("55", "Chemical exposure"),
    ("56", "Chemical exposure"),
    ("57", "Chemical exposure"),
    ("51", "Electricity"),
    ("50", "Electricity"),
    ("3", "Fire or explosion"),
    ("4", "Slip, trip or fall"),
    ("2", "Vehicle or forklift"),
    ("6", "Struck by object or vehicle"),
    ("7", "Strain or overexertion"),
    ("5", "Chemical exposure"),
    ("1", "Violence or other"),
]

ENERGY_ORDER = [
    "Caught in machinery", "Heat, steam & hot material", "Chemical exposure",
    "Struck by object or vehicle", "Slip, trip or fall", "Vehicle or forklift",
    "Rubbed, cut or pinched", "Fire or explosion", "Electricity",
    "Strain or overexertion", "Violence or other", "Unclassified",
]


def energy(event_code, source_title=""):
    """Map an OIICS event code (e.g. '6411') to an energy group."""
    code = str(event_code or "").strip().split(".")[0]
    best = None
    for prefix, label in ENERGY_BY_EVENT:
        if code.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, label)
    label = best[1] if best else "Unclassified"
    src = (source_title or "").lower()
    if label == "Struck by object or vehicle" and ("forklift" in src or "truck" in src):
        return "Vehicle or forklift"
    return label


# RMP accident columns -> plain labels. Order is the display order.
RELEASE_TYPE = [
    ("RE_Spill", "Liquid spill"), ("RE_Gas", "Gas release"), ("RE_Fire", "Fire"),
    ("RE_Explosion", "Explosion"), ("RE_ReactiveIncident", "Runaway reaction"),
]
RELEASE_SOURCE = [
    ("RS_ProcessVessel", "Process vessel or reactor"), ("RS_StorageVessel", "Storage tank"),
    ("RS_Piping", "Piping"), ("RS_Valve", "Valve"), ("RS_TransferHose", "Transfer hose"),
    ("RS_Pump", "Pump"), ("RS_Joint", "Joint or flange"),
]
RELEASE_CAUSE = [
    ("CF_EquipmentFailure", "Equipment failed"),
    ("CF_HumanError", "Human error"),
    ("CF_ImproperProcedure", "Procedure wrong or not followed"),
    ("CF_Maintenance", "During or due to maintenance"),
    ("CF_Overpressurization", "Pressure built up too high"),
    ("CF_UpsetCondition", "Process upset"),
    ("CF_ProcessDesignFailure", "Design flaw"),
    ("CF_UnsuitableEquipment", "Wrong equipment for the job"),
    ("CF_ManagementError", "Management system gap"),
    ("CF_BypassCondition", "Safety system bypassed"),
    ("CF_UnusualWeather", "Weather"),
]
RELEASE_FIX = [
    ("CI_ImprovedEquipment", "Better equipment"),
    ("CI_RevisedOpProcedures", "Rewrote procedures"),
    ("CI_RevisedTraining", "Retrained people"),
    ("CI_RevisedMaintenance", "Changed maintenance"),
    ("CI_NewProcessControls", "New process controls"),
    ("CI_NewMitigationSystems", "New mitigation systems"),
    ("CI_ChangedProcess", "Changed the process"),
    ("CI_RevisedERPlan", "Updated emergency plan"),
    ("CI_ReducedInventory", "Held less chemical"),
    ("CI_None", "No change reported"),
]


def flags(row, table):
    """Return the indices into ``table`` whose column is 'Yes' in ``row``."""
    return [i for i, (col, _label) in enumerate(table) if str(row.get(col, "")).strip() == "Yes"]
