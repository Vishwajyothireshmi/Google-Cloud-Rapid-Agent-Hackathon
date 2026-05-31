"""
seed_data.py
Complete data generation for healthcare supply chain agent.
Fixes all 4 gaps:
  Gap 1: inventory now has hospital_id + country
  Gap 2: inventory now has daily_consumption
  Gap 3: suppliers now has export_status
  Gap 4: suppliers now has warehouse_stock_kg

Run:
  python data/seed_data.py
"""

import os
import random
import sys
import datetime
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("MONGODB_DB_NAME", "healthcare_supply_chain")]

# ── REFERENCE DATA ─────────────────────────────────────────────────────────────

COUNTRIES = {
    "India":        {"risk": 0.7, "reliability_base": 0.85},
    "China":        {"risk": 0.8, "reliability_base": 0.78},
    "Germany":      {"risk": 0.1, "reliability_base": 0.95},
    "Switzerland":  {"risk": 0.1, "reliability_base": 0.96},
    "Netherlands":  {"risk": 0.1, "reliability_base": 0.94},
    "USA":          {"risk": 0.2, "reliability_base": 0.92},
    "Italy":        {"risk": 0.2, "reliability_base": 0.91},
    "Spain":        {"risk": 0.2, "reliability_base": 0.90},
    "Japan":        {"risk": 0.15, "reliability_base": 0.93},
    "South Korea":  {"risk": 0.2, "reliability_base": 0.89},
    "Israel":       {"risk": 0.4, "reliability_base": 0.88},
    "Bangladesh":   {"risk": 0.6, "reliability_base": 0.75},
    "Pakistan":     {"risk": 0.65, "reliability_base": 0.72},
    "Iran":         {"risk": 0.9, "reliability_base": 0.60},
}

INDIAN_COMPANIES = [
    "Aurobindo Pharma", "Sun Pharma", "Dr Reddys",
    "Cipla", "Lupin", "Divi Laboratories",
    "Biocon", "Cadila Healthcare", "Torrent Pharma",
    "Alkem Laboratories", "Glenmark Pharma", "IPCA Labs",
    "Ajanta Pharma", "Natco Pharma", "Granules India",
    "Aarti Drugs", "Solara Active Pharma", "Laurus Labs",
    "Sequent Scientific", "Strides Pharma",
]

CHINESE_COMPANIES = [
    "Zhejiang Conba", "CSPC Pharma", "Hisun Pharma",
    "Northeast Pharma", "Zhejiang Huahai", "Joincare Pharma",
    "Humanwell Healthcare", "Sino Biopharmaceutical",
    "Shanghai Pharma", "Hengrui Medicine",
    "CITIC Pharma", "Fosun Pharma", "Kelun Pharma",
    "CR Pharma", "Zhangmen Pharma",
]

EUROPEAN_COMPANIES = [
    "Sandoz Germany", "Lonza Switzerland", "DSM Netherlands",
    "Roche Switzerland", "Novartis Switzerland",
    "Bayer Germany", "Boehringer Germany", "BASF Germany",
    "Evonik Germany", "Merck KGaA Germany",
    "Patheon Italy", "Recordati Italy", "Zambon Italy",
    "Almirall Spain", "Faes Farma Spain",
]

APIS = [
    "Ciprofloxacin", "Amoxicillin", "Azithromycin",
    "Doxycycline", "Metronidazole", "Cephalexin",
    "Levofloxacin", "Clindamycin", "Vancomycin", "Meropenem",
    "Metformin", "Insulin Glargine", "Sitagliptin",
    "Empagliflozin", "Glimepiride", "Pioglitazone",
    "Atorvastatin", "Rosuvastatin", "Amlodipine",
    "Losartan", "Ramipril", "Bisoprolol",
    "Clopidogrel", "Warfarin", "Digoxin",
    "Paracetamol", "Ibuprofen", "Diclofenac",
    "Tramadol", "Morphine", "Fentanyl",
    "Salbutamol", "Budesonide", "Montelukast", "Theophylline",
    "Sertraline", "Fluoxetine", "Risperidone",
    "Olanzapine", "Lithium Carbonate",
    "Imatinib", "Docetaxel", "Paclitaxel",
    "Capecitabine", "Erlotinib",
    "Tenofovir", "Efavirenz", "Lopinavir",
    "Oseltamivir", "Acyclovir",
    "Omeprazole", "Pantoprazole", "Ondansetron",
    "Dexamethasone", "Prednisolone",
]

DRUGS = [
    {"drug_name": "Ciprobay",   "api": "Ciprofloxacin",  "category": "antibiotic"},
    {"drug_name": "Ciplox",     "api": "Ciprofloxacin",  "category": "antibiotic"},
    {"drug_name": "Amoxil",     "api": "Amoxicillin",    "category": "antibiotic"},
    {"drug_name": "Augmentin",  "api": "Amoxicillin",    "category": "antibiotic"},
    {"drug_name": "Zithromax",  "api": "Azithromycin",   "category": "antibiotic"},
    {"drug_name": "Azee",       "api": "Azithromycin",   "category": "antibiotic"},
    {"drug_name": "Vibramycin", "api": "Doxycycline",    "category": "antibiotic"},
    {"drug_name": "Flagyl",     "api": "Metronidazole",  "category": "antibiotic"},
    {"drug_name": "Keflex",     "api": "Cephalexin",     "category": "antibiotic"},
    {"drug_name": "Tavanic",    "api": "Levofloxacin",   "category": "antibiotic"},
    {"drug_name": "Glucophage", "api": "Metformin",      "category": "diabetes"},
    {"drug_name": "Formet",     "api": "Metformin",      "category": "diabetes"},
    {"drug_name": "Lantus",     "api": "Insulin Glargine","category": "diabetes"},
    {"drug_name": "Januvia",    "api": "Sitagliptin",    "category": "diabetes"},
    {"drug_name": "Jardiance",  "api": "Empagliflozin",  "category": "diabetes"},
    {"drug_name": "Amaryl",     "api": "Glimepiride",    "category": "diabetes"},
    {"drug_name": "Actos",      "api": "Pioglitazone",   "category": "diabetes"},
    {"drug_name": "Lipitor",    "api": "Atorvastatin",   "category": "cardiovascular"},
    {"drug_name": "Crestor",    "api": "Rosuvastatin",   "category": "cardiovascular"},
    {"drug_name": "Norvasc",    "api": "Amlodipine",     "category": "cardiovascular"},
    {"drug_name": "Cozaar",     "api": "Losartan",       "category": "cardiovascular"},
    {"drug_name": "Tritace",    "api": "Ramipril",       "category": "cardiovascular"},
    {"drug_name": "Concor",     "api": "Bisoprolol",     "category": "cardiovascular"},
    {"drug_name": "Plavix",     "api": "Clopidogrel",    "category": "cardiovascular"},
    {"drug_name": "Coumadin",   "api": "Warfarin",       "category": "cardiovascular"},
    {"drug_name": "Panadol",    "api": "Paracetamol",    "category": "painkiller"},
    {"drug_name": "Calpol",     "api": "Paracetamol",    "category": "painkiller"},
    {"drug_name": "Brufen",     "api": "Ibuprofen",      "category": "painkiller"},
    {"drug_name": "Voltaren",   "api": "Diclofenac",     "category": "painkiller"},
    {"drug_name": "Tramal",     "api": "Tramadol",       "category": "painkiller"},
    {"drug_name": "Ventolin",   "api": "Salbutamol",     "category": "respiratory"},
    {"drug_name": "Pulmicort",  "api": "Budesonide",     "category": "respiratory"},
    {"drug_name": "Singulair",  "api": "Montelukast",    "category": "respiratory"},
    {"drug_name": "Zoloft",     "api": "Sertraline",     "category": "mental_health"},
    {"drug_name": "Prozac",     "api": "Fluoxetine",     "category": "mental_health"},
    {"drug_name": "Risperdal",  "api": "Risperidone",    "category": "mental_health"},
    {"drug_name": "Zyprexa",    "api": "Olanzapine",     "category": "mental_health"},
    {"drug_name": "Gleevec",    "api": "Imatinib",       "category": "oncology"},
    {"drug_name": "Taxotere",   "api": "Docetaxel",      "category": "oncology"},
    {"drug_name": "Taxol",      "api": "Paclitaxel",     "category": "oncology"},
    {"drug_name": "Xeloda",     "api": "Capecitabine",   "category": "oncology"},
    {"drug_name": "Viread",     "api": "Tenofovir",      "category": "hiv"},
    {"drug_name": "Sustiva",    "api": "Efavirenz",      "category": "hiv"},
    {"drug_name": "Tamiflu",    "api": "Oseltamivir",    "category": "antiviral"},
    {"drug_name": "Zovirax",    "api": "Acyclovir",      "category": "antiviral"},
    {"drug_name": "Prilosec",   "api": "Omeprazole",     "category": "gastrointestinal"},
    {"drug_name": "Pantoloc",   "api": "Pantoprazole",   "category": "gastrointestinal"},
    {"drug_name": "Zofran",     "api": "Ondansetron",    "category": "gastrointestinal"},
    {"drug_name": "Decadron",   "api": "Dexamethasone",  "category": "steroid"},
    {"drug_name": "Deltasone",  "api": "Prednisolone",   "category": "steroid"},
]

# Hospital definitions with country, population, critical drugs, buffer
HEALTH_SYSTEMS = [
    {
        "id": "HS001", "name": "Dhaka Medical College",
        "country": "Bangladesh", "pop": 2100000, "buffer": 4,
        "import_dep": "India",
        "critical_drugs": ["Glucophage", "Azee", "Amoxil",
                           "Augmentin", "Zithromax", "Lantus"]
    },
    {
        "id": "HS002", "name": "Chittagong General Hospital",
        "country": "Bangladesh", "pop": 980000, "buffer": 3,
        "import_dep": "India",
        "critical_drugs": ["Formet", "Ciplox", "Flagyl",
                           "Jardiance", "Zofran"]
    },
    {
        "id": "HS003", "name": "Kathmandu General",
        "country": "Nepal", "pop": 850000, "buffer": 3,
        "import_dep": "India",
        "critical_drugs": ["Panadol", "Amaryl", "Flagyl",
                           "Singulair", "Taxol"]
    },
    {
        "id": "HS004", "name": "BP Koirala Institute",
        "country": "Nepal", "pop": 620000, "buffer": 2,
        "import_dep": "India",
        "critical_drugs": ["Tritace", "Concor", "Taxotere",
                           "Zyprexa", "Calpol"]
    },
    {
        "id": "HS005", "name": "Karachi Civil Hospital",
        "country": "Pakistan", "pop": 3200000, "buffer": 3,
        "import_dep": "India",
        "critical_drugs": ["Ciplox", "Coumadin", "Lantus",
                           "Singulair", "Decadron"]
    },
    {
        "id": "HS006", "name": "Lahore General Hospital",
        "country": "Pakistan", "pop": 2800000, "buffer": 4,
        "import_dep": "India",
        "critical_drugs": ["Glucophage", "Lipitor", "Pulmicort",
                           "Pantoloc", "Risperdal"]
    },
    {
        "id": "HS007", "name": "Colombo National Hospital",
        "country": "Sri Lanka", "pop": 980000, "buffer": 5,
        "import_dep": "India",
        "critical_drugs": ["Augmentin", "Crestor", "Panadol",
                           "Taxol", "Risperdal"]
    },
    {
        "id": "HS008", "name": "Yangon General Hospital",
        "country": "Myanmar", "pop": 1500000, "buffer": 2,
        "import_dep": "China",
        "critical_drugs": ["Azee", "Lipitor", "Formet",
                           "Singulair", "Pulmicort"]
    },
    {
        "id": "HS009", "name": "Mandalay General",
        "country": "Myanmar", "pop": 890000, "buffer": 2,
        "import_dep": "China",
        "critical_drugs": ["Panadol", "Tritace", "Prozac",
                           "Augmentin", "Crestor"]
    },
    {
        "id": "HS010", "name": "Phnom Penh Hospital",
        "country": "Cambodia", "pop": 1200000, "buffer": 3,
        "import_dep": "China",
        "critical_drugs": ["Amoxil", "Glucophage", "Zofran",
                           "Decadron", "Brufen"]
    },
    {
        "id": "HS011", "name": "Vientiane Central",
        "country": "Laos", "pop": 450000, "buffer": 2,
        "import_dep": "China",
        "critical_drugs": ["Azee", "Panadol", "Flagyl",
                           "Glucophage", "Ventolin"]
    },
    {
        "id": "HS012", "name": "Dili National Hospital",
        "country": "East Timor", "pop": 320000, "buffer": 2,
        "import_dep": "India",
        "critical_drugs": ["Amoxil", "Panadol", "Decadron",
                           "Glucophage", "Azee"]
    },
    {
        "id": "HS013", "name": "Baghdad Medical City",
        "country": "Iraq", "pop": 4500000, "buffer": 3,
        "import_dep": "India",
        "critical_drugs": ["Ciprobay", "Lantus", "Decadron",
                           "Glucophage", "Plavix"]
    },
    {
        "id": "HS014", "name": "Sanaa Central Hospital",
        "country": "Yemen", "pop": 2100000, "buffer": 1,
        "import_dep": "India",
        "critical_drugs": ["Amoxil", "Panadol", "Glucophage",
                           "Decadron", "Azee"]
    },
    {
        "id": "HS015", "name": "Aleppo University Hospital",
        "country": "Syria", "pop": 1800000, "buffer": 1,
        "import_dep": "India",
        "critical_drugs": ["Flagyl", "Panadol", "Calpol",
                           "Decadron", "Ciprobay"]
    },
    {
        "id": "HS016", "name": "Lagos University Hospital",
        "country": "Nigeria", "pop": 5200000, "buffer": 3,
        "import_dep": "India",
        "critical_drugs": ["Azee", "Amoxil", "Panadol",
                           "Glucophage", "Lipitor"]
    },
    {
        "id": "HS017", "name": "Nairobi National Hospital",
        "country": "Kenya", "pop": 2100000, "buffer": 4,
        "import_dep": "India",
        "critical_drugs": ["Glucophage", "Formet", "Azee",
                           "Lantus", "Ciplox"]
    },
    {
        "id": "HS018", "name": "Addis Ababa Black Lion",
        "country": "Ethiopia", "pop": 3800000, "buffer": 2,
        "import_dep": "India",
        "critical_drugs": ["Amoxil", "Panadol", "Azee",
                           "Glucophage", "Decadron"]
    },
    {
        "id": "HS019", "name": "Dar es Salaam Hospital",
        "country": "Tanzania", "pop": 1900000, "buffer": 3,
        "import_dep": "India",
        "critical_drugs": ["Azee", "Amoxil", "Glucophage",
                           "Panadol", "Flagyl"]
    },
    {
        "id": "HS020", "name": "Kampala Mulago Hospital",
        "country": "Uganda", "pop": 1600000, "buffer": 2,
        "import_dep": "India",
        "critical_drugs": ["Amoxil", "Azee", "Glucophage",
                           "Panadol", "Decadron"]
    },
]

# Elastic events with severity + affected_apis (Gap fix)
ELASTIC_EVENTS = [
    {
        "event_type": "export_ban",
        "country": "India",
        "severity": "critical",
        "description": "Indian government restricts export of 26 API ingredients amid domestic shortage",
        "affected_apis": ["Metformin", "Amoxicillin", "Azithromycin",
                          "Paracetamol", "Ciprofloxacin", "Doxycycline"],
        "keywords": ["export ban", "API", "India", "shortage", "restriction"],
        "severity_reason": "India supplies 60%+ of global generics — full export ban affects entire supply chain"
    },
    {
        "event_type": "sanctions",
        "country": "India",
        "severity": "high",
        "description": "US imposes trade restrictions on Indian pharmaceutical exports",
        "affected_apis": ["Metformin", "Atorvastatin", "Ciprofloxacin"],
        "keywords": ["sanctions", "pharma", "export", "restriction", "India"],
        "severity_reason": "Partial sanctions — specific APIs restricted, not full ban"
    },
    {
        "event_type": "conflict",
        "country": "China",
        "severity": "critical",
        "description": "Geopolitical tensions disrupt Chinese API manufacturing and export capacity",
        "affected_apis": ["Dexamethasone", "Paclitaxel", "Docetaxel",
                          "Imatinib", "Rosuvastatin"],
        "keywords": ["conflict", "API", "manufacturing", "disruption", "China"],
        "severity_reason": "China is primary source for oncology APIs — disruption causes immediate shortage"
    },
    {
        "event_type": "port_closure",
        "country": "Yemen",
        "severity": "critical",
        "description": "Houthi attacks force pharmaceutical shipments to reroute around Cape of Good Hope adding 14 days",
        "affected_apis": [],
        "affected_corridors": ["Red Sea", "Suez Canal"],
        "keywords": ["shipping", "Suez", "Houthi", "delay", "reroute", "port closure"],
        "severity_reason": "14+ day delay affects all drugs in transit — CRITICAL for hospitals with <30 days stock"
    },
    {
        "event_type": "sanctions",
        "country": "Iran",
        "severity": "high",
        "description": "New US sanctions on Iranian petrochemicals disrupt precursor supply for IV fluids",
        "affected_apis": ["Morphine", "Fentanyl"],
        "keywords": ["Iran", "sanctions", "petrochemical", "IV", "precursor"],
        "severity_reason": "Iran supplies precursor chemicals for pain management APIs"
    },
    {
        "event_type": "simultaneous_disruption",
        "country": "India",
        "severity": "critical",
        "description": "Simultaneous trade restrictions on India and China create critical global API shortage",
        "affected_apis": ["Metformin", "Amoxicillin", "Paracetamol",
                          "Dexamethasone", "Atorvastatin"],
        "secondary_country": "China",
        "keywords": ["sanctions", "China", "India", "API", "critical", "global"],
        "severity_reason": "India + China together supply 80%+ of global APIs — simultaneous disruption is catastrophic"
    },
    {
        "event_type": "natural_disaster",
        "country": "India",
        "severity": "high",
        "description": "Severe flooding in Gujarat disrupts pharmaceutical manufacturing plants",
        "affected_apis": ["Metformin", "Ciprofloxacin", "Amoxicillin"],
        "affected_region": "Gujarat",
        "keywords": ["flood", "Gujarat", "manufacturing", "disruption", "India"],
        "severity_reason": "Gujarat is India's pharmaceutical hub — flooding halts 40% of API production"
    },
    {
        "event_type": "trade_dispute",
        "country": "China",
        "severity": "high",
        "description": "US-China trade war escalation threatens pharmaceutical ingredient exports",
        "affected_apis": ["Dexamethasone", "Imatinib", "Paclitaxel"],
        "keywords": ["trade war", "tariff", "China", "pharmaceutical", "escalation"],
        "severity_reason": "Tariff increases make Chinese APIs 40% more expensive — procurement disruption likely"
    },
]


# ── GENERATORS ─────────────────────────────────────────────────────────────────

def generate_suppliers():
    """
    GAP 3 FIX: Added export_status field
    GAP 4 FIX: Added warehouse_stock_kg field
    """
    suppliers = []
    sid = 1

    for company in INDIAN_COMPANIES:
        for api in random.sample(APIS, random.randint(2, 4)):
            suppliers.append({
                "supplier_id":         f"SUP{sid:03d}",
                "name":                company,
                "country":             "India",
                "type":                "API_manufacturer",
                "api_name":            api,
                "reliability_score":   round(random.uniform(0.80, 0.92), 2),
                "lead_time_days":      random.randint(30, 55),
                "annual_capacity_kg":  random.randint(5000, 50000),
                "warehouse_stock_kg":  random.randint(500, 8000),   # GAP 4 FIX
                "export_status":       "active",                     # GAP 3 FIX
                "gmp_certified":       True,
                "last_audit":          "2024-01-15",
            })
            sid += 1

    for company in CHINESE_COMPANIES:
        for api in random.sample(APIS, random.randint(2, 4)):
            suppliers.append({
                "supplier_id":         f"SUP{sid:03d}",
                "name":                company,
                "country":             "China",
                "type":                "API_manufacturer",
                "api_name":            api,
                "reliability_score":   round(random.uniform(0.72, 0.85), 2),
                "lead_time_days":      random.randint(45, 70),
                "annual_capacity_kg":  random.randint(8000, 80000),
                "warehouse_stock_kg":  random.randint(1000, 15000),  # GAP 4 FIX
                "export_status":       "active",                     # GAP 3 FIX
                "gmp_certified":       random.choice([True, False]),
                "last_audit":          "2023-11-20",
            })
            sid += 1

    for company in EUROPEAN_COMPANIES:
        country = company.split()[-1]
        if country not in COUNTRIES:
            country = "Germany"
        for api in random.sample(APIS, random.randint(1, 3)):
            suppliers.append({
                "supplier_id":         f"SUP{sid:03d}",
                "name":                company,
                "country":             country,
                "type":                "API_manufacturer",
                "api_name":            api,
                "reliability_score":   round(random.uniform(0.90, 0.98), 2),
                "lead_time_days":      random.randint(15, 30),
                "annual_capacity_kg":  random.randint(2000, 20000),
                "warehouse_stock_kg":  random.randint(200, 5000),    # GAP 4 FIX
                "export_status":       "active",                     # GAP 3 FIX
                "gmp_certified":       True,
                "last_audit":          "2024-03-10",
            })
            sid += 1

    return suppliers


def generate_drug_ingredients():
    """
    GAP (partial) FIX: Added source_countries derived from DRUGS/APIS mapping
    """
    # Build source country map from supplier data context
    api_source_map = {
        "Ciprofloxacin":  ["India", "China"],
        "Amoxicillin":    ["India", "China", "Germany"],
        "Azithromycin":   ["India", "China"],
        "Doxycycline":    ["India", "China"],
        "Metronidazole":  ["India", "China", "Italy"],
        "Cephalexin":     ["India", "China"],
        "Levofloxacin":   ["India", "China"],
        "Metformin":      ["India", "China", "Germany"],
        "Insulin Glargine":["Denmark", "Germany", "USA"],
        "Sitagliptin":    ["India", "USA"],
        "Empagliflozin":  ["Germany", "India"],
        "Glimepiride":    ["India", "Germany"],
        "Atorvastatin":   ["India", "China", "Ireland"],
        "Rosuvastatin":   ["India", "China"],
        "Amlodipine":     ["India", "China"],
        "Paracetamol":    ["India", "China", "France"],
        "Ibuprofen":      ["India", "China"],
        "Salbutamol":     ["India", "UK"],
        "Budesonide":     ["Sweden", "India"],
        "Montelukast":    ["India", "China"],
        "Sertraline":     ["India", "China", "USA"],
        "Fluoxetine":     ["India", "China", "USA"],
        "Risperidone":    ["India", "China"],
        "Imatinib":       ["India", "China", "Switzerland"],
        "Docetaxel":      ["China", "Spain"],
        "Paclitaxel":     ["China", "India"],
        "Dexamethasone":  ["China", "India", "USA"],
        "Omeprazole":     ["India", "China", "Sweden"],
        "Ondansetron":    ["India", "Switzerland"],
    }

    return [
        {
            "drug_name":              d["drug_name"],
            "active_ingredient":      d["api"],
            "category":               d["category"],
            "criticality":            "essential",
            "who_essential":          True,
            "global_demand_kg_annual": random.randint(10000, 500000),
            "source_countries":       api_source_map.get(
                                        d["api"],
                                        ["India", "China"]
                                      ),  # GAP partial FIX
        }
        for d in DRUGS
    ]


def generate_inventory():
    """
    GAP 1 FIX: Added hospital_id + country to every inventory record
    GAP 2 FIX: Added daily_consumption field
    Inventory = RECEIVER SIDE — stock at hospitals in destination countries
    """
    inventory = []
    inv_id = 1

    for hs in HEALTH_SYSTEMS:
        for drug_name in hs["critical_drugs"]:

            category = next(
                (d["category"] for d in DRUGS
                 if d["drug_name"] == drug_name),
                "general"
            )

            daily_consumption = random.randint(20, 120)   # GAP 2 FIX
            days = random.randint(10, 120)
            current_stock = daily_consumption * days
            reorder_threshold = daily_consumption * 45    # 45-day policy

            inventory.append({
                "inventory_id":       f"INV-{inv_id:04d}",
                "hospital_id":        hs["id"],           # GAP 1 FIX
                "hospital_name":      hs["name"],         # GAP 1 FIX
                "country":            hs["country"],      # GAP 1 FIX
                "drug_name":          drug_name,
                "category":           category,
                "current_stock":      current_stock,
                "daily_consumption":  daily_consumption,  # GAP 2 FIX
                "reorder_threshold":  reorder_threshold,
                "days_of_supply":     days,
                "unit":               "units",
                "location":           "hospital_pharmacy",
                "risk_level": (
                    "CRITICAL" if days < 30
                    else "HIGH" if days < 60
                    else "MEDIUM"
                ),
                "last_updated": datetime.datetime.now(
                    datetime.timezone.utc).isoformat(),
            })
            inv_id += 1

    return inventory


def generate_health_systems():
    """Health systems — receiver side — unchanged but richer."""
    return [
        {
            "hospital_id":             hs["id"],
            "name":                    hs["name"],
            "country":                 hs["country"],
            "critical_drugs":          hs["critical_drugs"],
            "population_served":       hs["pop"],
            "healthcare_buffer_weeks": hs["buffer"],
            "import_dependency":       hs["import_dep"],
            "emergency_stock_days":    random.randint(7, 30),
        }
        for hs in HEALTH_SYSTEMS
    ]


def seed_elastic(events):
    """Seed Elastic with geopolitical trigger events."""
    try:
        sys.path.insert(0, os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        ))
        from integrations.elastic_client import get_elastic
        es = get_elastic()
        index = os.getenv("ELASTIC_INDEX", "geopolitical-events")

        # Delete existing index and recreate
        if es.indices.exists(index=index):
            es.indices.delete(index=index)

        es.indices.create(index=index, body={
            "mappings": {
                "properties": {
                    "event_type":    {"type": "keyword"},
                    "country":       {"type": "keyword"},
                    "severity":      {"type": "keyword"},
                    "description":   {"type": "text"},
                    "affected_apis": {"type": "keyword"},
                    "keywords":      {"type": "keyword"},
                    "timestamp":     {"type": "date"},
                }
            }
        })

        for event in events:
            event["timestamp"] = datetime.datetime.now(
                datetime.timezone.utc).isoformat()
            es.index(index=index, document=event)

        print(f"  ✅ Elastic events:    {len(events)} records")
    except Exception as e:
        print(f"  ⚠️  Elastic seeding failed: {e}")


def seed_database():
    print("\n🌱 Generating healthcare supply chain data...\n")

    suppliers      = generate_suppliers()
    drug_ingr      = generate_drug_ingredients()
    inventory      = generate_inventory()
    health_systems = generate_health_systems()

    print("🌱 Seeding MongoDB...")
    for col in ["suppliers", "drug_ingredients",
                "inventory", "health_systems", "incident_reports"]:
        db[col].drop()

    db.suppliers.insert_many(suppliers)
    db.suppliers.create_index("country")
    db.suppliers.create_index("api_name")
    db.suppliers.create_index("export_status")          # NEW index
    print(f"  ✅ suppliers:        {len(suppliers)} records")

    db.drug_ingredients.insert_many(drug_ingr)
    db.drug_ingredients.create_index("active_ingredient")
    db.drug_ingredients.create_index("drug_name")
    print(f"  ✅ drug_ingredients: {len(drug_ingr)} records")

    db.inventory.insert_many(inventory)
    db.inventory.create_index("drug_name")
    db.inventory.create_index("hospital_id")            # NEW index
    db.inventory.create_index("country")                # NEW index
    db.inventory.create_index("risk_level")
    print(f"  ✅ inventory:        {len(inventory)} records")

    db.health_systems.insert_many(health_systems)
    db.health_systems.create_index("country")
    db.health_systems.create_index("critical_drugs")
    db.health_systems.create_index("hospital_id")
    print(f"  ✅ health_systems:   {len(health_systems)} records")

    db.incident_reports.create_index("created_at")
    db.incident_reports.create_index("status")
    print(f"  ✅ incident_reports: 0 records (agent writes here)")

    print("\n🌱 Seeding Elastic...")
    seed_elastic(ELASTIC_EVENTS)

    print("\n📊 Summary:")
    print(f"   Suppliers:          {len(suppliers)}")
    print(f"   Drug ingredients:   {len(drug_ingr)}")
    print(f"   Inventory records:  {len(inventory)} "
          f"(across {len(HEALTH_SYSTEMS)} hospitals)")
    print(f"   Health systems:     {len(health_systems)}")
    print(f"   Elastic events:     {len(ELASTIC_EVENTS)}")

    print("\n✅ Gaps fixed:")
    print("   Gap 1: inventory now has hospital_id + country")
    print("   Gap 2: inventory now has daily_consumption")
    print("   Gap 3: suppliers now has export_status")
    print("   Gap 4: suppliers now has warehouse_stock_kg")
    print("   Bonus: drug_ingredients now has source_countries")
    print("   Bonus: Elastic events now have affected_apis\n")


if __name__ == "__main__":
    seed_database()