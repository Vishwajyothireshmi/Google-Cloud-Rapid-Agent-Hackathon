import os
import random
import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
import sys


load_dotenv()

client = MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("MONGODB_DB_NAME", "healthcare_supply_chain")]

# ── REAL WORLD DATA POOLS ─────────────────────────────

COUNTRIES = {
    "India": {"risk": 0.7, "reliability_base": 0.85},
    "China": {"risk": 0.8, "reliability_base": 0.78},
    "Germany": {"risk": 0.1, "reliability_base": 0.95},
    "Switzerland": {"risk": 0.1, "reliability_base": 0.96},
    "Netherlands": {"risk": 0.1, "reliability_base": 0.94},
    "USA": {"risk": 0.2, "reliability_base": 0.92},
    "Italy": {"risk": 0.2, "reliability_base": 0.91},
    "Spain": {"risk": 0.2, "reliability_base": 0.90},
    "Japan": {"risk": 0.15, "reliability_base": 0.93},
    "South Korea": {"risk": 0.2, "reliability_base": 0.89},
    "Israel": {"risk": 0.4, "reliability_base": 0.88},
    "Bangladesh": {"risk": 0.6, "reliability_base": 0.75},
    "Pakistan": {"risk": 0.65, "reliability_base": 0.72},
    "Iran": {"risk": 0.9, "reliability_base": 0.60},
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
    # Antibiotics
    "Ciprofloxacin", "Amoxicillin", "Azithromycin",
    "Doxycycline", "Metronidazole", "Cephalexin",
    "Levofloxacin", "Clindamycin", "Vancomycin",
    "Meropenem",
    # Diabetes
    "Metformin", "Insulin Glargine", "Sitagliptin",
    "Empagliflozin", "Glimepiride", "Pioglitazone",
    # Cardiovascular
    "Atorvastatin", "Rosuvastatin", "Amlodipine",
    "Losartan", "Ramipril", "Bisoprolol",
    "Clopidogrel", "Warfarin", "Digoxin",
    # Pain/Fever
    "Paracetamol", "Ibuprofen", "Diclofenac",
    "Tramadol", "Morphine", "Fentanyl",
    # Respiratory
    "Salbutamol", "Budesonide", "Montelukast",
    "Theophylline", "Ipratropium",
    # Mental Health
    "Sertraline", "Fluoxetine", "Risperidone",
    "Olanzapine", "Lithium Carbonate",
    # Oncology
    "Imatinib", "Docetaxel", "Paclitaxel",
    "Capecitabine", "Erlotinib",
    # HIV/Infectious
    "Tenofovir", "Efavirenz", "Lopinavir",
    "Oseltamivir", "Acyclovir",
    # Other Essential
    "Omeprazole", "Pantoprazole", "Ondansetron",
    "Dexamethasone", "Prednisolone",
]

DRUGS = [
    # Antibiotics
    {"drug_name": "Ciprobay", "api": "Ciprofloxacin", "category": "antibiotic"},
    {"drug_name": "Ciplox", "api": "Ciprofloxacin", "category": "antibiotic"},
    {"drug_name": "Amoxil", "api": "Amoxicillin", "category": "antibiotic"},
    {"drug_name": "Augmentin", "api": "Amoxicillin", "category": "antibiotic"},
    {"drug_name": "Zithromax", "api": "Azithromycin", "category": "antibiotic"},
    {"drug_name": "Azee", "api": "Azithromycin", "category": "antibiotic"},
    {"drug_name": "Vibramycin", "api": "Doxycycline", "category": "antibiotic"},
    {"drug_name": "Flagyl", "api": "Metronidazole", "category": "antibiotic"},
    {"drug_name": "Keflex", "api": "Cephalexin", "category": "antibiotic"},
    {"drug_name": "Tavanic", "api": "Levofloxacin", "category": "antibiotic"},
    # Diabetes
    {"drug_name": "Glucophage", "api": "Metformin", "category": "diabetes"},
    {"drug_name": "Formet", "api": "Metformin", "category": "diabetes"},
    {"drug_name": "Lantus", "api": "Insulin Glargine", "category": "diabetes"},
    {"drug_name": "Januvia", "api": "Sitagliptin", "category": "diabetes"},
    {"drug_name": "Jardiance", "api": "Empagliflozin", "category": "diabetes"},
    {"drug_name": "Amaryl", "api": "Glimepiride", "category": "diabetes"},
    {"drug_name": "Actos", "api": "Pioglitazone", "category": "diabetes"},
    # Cardiovascular
    {"drug_name": "Lipitor", "api": "Atorvastatin", "category": "cardiovascular"},
    {"drug_name": "Crestor", "api": "Rosuvastatin", "category": "cardiovascular"},
    {"drug_name": "Norvasc", "api": "Amlodipine", "category": "cardiovascular"},
    {"drug_name": "Cozaar", "api": "Losartan", "category": "cardiovascular"},
    {"drug_name": "Tritace", "api": "Ramipril", "category": "cardiovascular"},
    {"drug_name": "Concor", "api": "Bisoprolol", "category": "cardiovascular"},
    {"drug_name": "Plavix", "api": "Clopidogrel", "category": "cardiovascular"},
    {"drug_name": "Coumadin", "api": "Warfarin", "category": "cardiovascular"},
    # Pain
    {"drug_name": "Panadol", "api": "Paracetamol", "category": "painkiller"},
    {"drug_name": "Calpol", "api": "Paracetamol", "category": "painkiller"},
    {"drug_name": "Brufen", "api": "Ibuprofen", "category": "painkiller"},
    {"drug_name": "Voltaren", "api": "Diclofenac", "category": "painkiller"},
    {"drug_name": "Tramal", "api": "Tramadol", "category": "painkiller"},
    # Respiratory
    {"drug_name": "Ventolin", "api": "Salbutamol", "category": "respiratory"},
    {"drug_name": "Pulmicort", "api": "Budesonide", "category": "respiratory"},
    {"drug_name": "Singulair", "api": "Montelukast", "category": "respiratory"},
    # Mental Health
    {"drug_name": "Zoloft", "api": "Sertraline", "category": "mental_health"},
    {"drug_name": "Prozac", "api": "Fluoxetine", "category": "mental_health"},
    {"drug_name": "Risperdal", "api": "Risperidone", "category": "mental_health"},
    {"drug_name": "Zyprexa", "api": "Olanzapine", "category": "mental_health"},
    # Oncology
    {"drug_name": "Gleevec", "api": "Imatinib", "category": "oncology"},
    {"drug_name": "Taxotere", "api": "Docetaxel", "category": "oncology"},
    {"drug_name": "Taxol", "api": "Paclitaxel", "category": "oncology"},
    {"drug_name": "Xeloda", "api": "Capecitabine", "category": "oncology"},
    # HIV
    {"drug_name": "Viread", "api": "Tenofovir", "category": "hiv"},
    {"drug_name": "Sustiva", "api": "Efavirenz", "category": "hiv"},
    {"drug_name": "Tamiflu", "api": "Oseltamivir", "category": "antiviral"},
    {"drug_name": "Zovirax", "api": "Acyclovir", "category": "antiviral"},
    # GI
    {"drug_name": "Prilosec", "api": "Omeprazole", "category": "gastrointestinal"},
    {"drug_name": "Pantoloc", "api": "Pantoprazole", "category": "gastrointestinal"},
    {"drug_name": "Zofran", "api": "Ondansetron", "category": "gastrointestinal"},
    # Steroids
    {"drug_name": "Decadron", "api": "Dexamethasone", "category": "steroid"},
    {"drug_name": "Deltasone", "api": "Prednisolone", "category": "steroid"},
]

HEALTH_SYSTEMS = [
    # South Asia
    {"id": "HS001", "name": "Dhaka Medical College", "country": "Bangladesh", "pop": 2100000, "buffer": 4},
    {"id": "HS002", "name": "Chittagong General Hospital", "country": "Bangladesh", "pop": 980000, "buffer": 3},
    {"id": "HS003", "name": "Kathmandu General", "country": "Nepal", "pop": 850000, "buffer": 3},
    {"id": "HS004", "name": "BP Koirala Institute", "country": "Nepal", "pop": 620000, "buffer": 2},
    {"id": "HS005", "name": "Karachi Civil Hospital", "country": "Pakistan", "pop": 3200000, "buffer": 3},
    {"id": "HS006", "name": "Lahore General Hospital", "country": "Pakistan", "pop": 2800000, "buffer": 4},
    {"id": "HS007", "name": "Colombo National Hospital", "country": "Sri Lanka", "pop": 980000, "buffer": 5},
    # Southeast Asia
    {"id": "HS008", "name": "Yangon General Hospital", "country": "Myanmar", "pop": 1500000, "buffer": 2},
    {"id": "HS009", "name": "Mandalay General", "country": "Myanmar", "pop": 890000, "buffer": 2},
    {"id": "HS010", "name": "Phnom Penh Hospital", "country": "Cambodia", "pop": 1200000, "buffer": 3},
    {"id": "HS011", "name": "Vientiane Central", "country": "Laos", "pop": 450000, "buffer": 2},
    {"id": "HS012", "name": "Dili National Hospital", "country": "East Timor", "pop": 320000, "buffer": 2},
    # Middle East
    {"id": "HS013", "name": "Baghdad Medical City", "country": "Iraq", "pop": 4500000, "buffer": 3},
    {"id": "HS014", "name": "Sanaa Central Hospital", "country": "Yemen", "pop": 2100000, "buffer": 1},
    {"id": "HS015", "name": "Aleppo University Hospital", "country": "Syria", "pop": 1800000, "buffer": 1},
    # Africa
    {"id": "HS016", "name": "Lagos University Hospital", "country": "Nigeria", "pop": 5200000, "buffer": 3},
    {"id": "HS017", "name": "Nairobi National Hospital", "country": "Kenya", "pop": 2100000, "buffer": 4},
    {"id": "HS018", "name": "Addis Ababa Black Lion", "country": "Ethiopia", "pop": 3800000, "buffer": 2},
    {"id": "HS019", "name": "Dar es Salaam Hospital", "country": "Tanzania", "pop": 1900000, "buffer": 3},
    {"id": "HS020", "name": "Kampala Mulago Hospital", "country": "Uganda", "pop": 1600000, "buffer": 2},
]

ELASTIC_EVENTS = [
    {"event_type": "sanctions", "country": "India", "severity": "high",
     "description": "US imposes trade restrictions on Indian pharmaceutical exports affecting API supply",
     "keywords": ["sanctions", "pharma", "export", "restriction", "India"]},
    {"event_type": "export_ban", "country": "India", "severity": "critical",
     "description": "Indian government restricts export of 26 API ingredients amid domestic shortage concerns",
     "keywords": ["export", "ban", "API", "India", "shortage"]},
    {"event_type": "conflict", "country": "China", "severity": "critical",
     "description": "Geopolitical tensions disrupt Chinese API manufacturing and export capacity",
     "keywords": ["conflict", "API", "manufacturing", "disruption", "China"]},
    {"event_type": "shipping_disruption", "country": "Yemen", "severity": "critical",
     "description": "Houthi attacks force pharmaceutical shipments to reroute around Cape of Good Hope adding 14 days",
     "keywords": ["shipping", "Suez", "Houthi", "delay", "reroute"]},
    {"event_type": "sanctions", "country": "Iran", "severity": "high",
     "description": "New US sanctions on Iranian petrochemicals disrupt precursor supply for IV fluids",
     "keywords": ["Iran", "sanctions", "petrochemical", "IV", "precursor"]},
    {"event_type": "simultaneous_disruption", "country": "India", "severity": "critical",
     "description": "Simultaneous trade restrictions on India and China create critical global API shortage",
     "keywords": ["sanctions", "China", "India", "API", "critical", "global"]},
    {"event_type": "natural_disaster", "country": "India", "severity": "high",
     "description": "Severe flooding in Gujarat disrupts pharmaceutical manufacturing plants",
     "keywords": ["flood", "Gujarat", "manufacturing", "disruption"]},
    {"event_type": "trade_dispute", "country": "China", "severity": "high",
     "description": "US-China trade war escalation threatens pharmaceutical ingredient exports",
     "keywords": ["trade", "war", "tariff", "China", "pharmaceutical"]},
]


def generate_suppliers():
    suppliers = []
    sid = 1

    # Indian suppliers
    for company in INDIAN_COMPANIES:
        for api in random.sample(APIS, random.randint(2, 4)):
            suppliers.append({
                "supplier_id": f"SUP{sid:03d}",
                "name": company,
                "country": "India",
                "type": "API_manufacturer",
                "api_name": api,
                "reliability_score": round(random.uniform(0.80, 0.92), 2),
                "lead_time_days": random.randint(30, 55),
                "annual_capacity_kg": random.randint(5000, 50000),
                "gmp_certified": True,
                "last_audit": "2024-01-15",
            })
            sid += 1

    # Chinese suppliers
    for company in CHINESE_COMPANIES:
        for api in random.sample(APIS, random.randint(2, 4)):
            suppliers.append({
                "supplier_id": f"SUP{sid:03d}",
                "name": company,
                "country": "China",
                "type": "API_manufacturer",
                "api_name": api,
                "reliability_score": round(random.uniform(0.72, 0.85), 2),
                "lead_time_days": random.randint(45, 70),
                "annual_capacity_kg": random.randint(8000, 80000),
                "gmp_certified": random.choice([True, False]),
                "last_audit": "2023-11-20",
            })
            sid += 1

    # European suppliers (alternatives)
    for company in EUROPEAN_COMPANIES:
        country = company.split()[-1]
        if country not in COUNTRIES:
            country = "Germany"
        for api in random.sample(APIS, random.randint(1, 3)):
            suppliers.append({
                "supplier_id": f"SUP{sid:03d}",
                "name": company,
                "country": country,
                "type": "API_manufacturer",
                "api_name": api,
                "reliability_score": round(random.uniform(0.90, 0.98), 2),
                "lead_time_days": random.randint(15, 30),
                "annual_capacity_kg": random.randint(2000, 20000),
                "gmp_certified": True,
                "last_audit": "2024-03-10",
            })
            sid += 1

    return suppliers


def generate_drug_ingredients():
    return [
        {
            "drug_name": d["drug_name"],
            "active_ingredient": d["api"],
            "category": d["category"],
            "criticality": "essential",
            "who_essential": True,
            "global_demand_kg_annual": random.randint(10000, 500000),
        }
        for d in DRUGS
    ]


def generate_inventory():
    inventory = []
    for d in DRUGS:
        days = random.randint(10, 120)
        stock = random.randint(1000, 25000)
        reorder = int(stock * random.uniform(0.5, 0.9))
        inventory.append({
            "drug_name": d["drug_name"],
            "category": d["category"],
            "current_stock": stock,
            "reorder_threshold": reorder,
            "days_of_supply": days,
            "unit": "units",
            "location": random.choice([
                "Central Warehouse",
                "Regional Warehouse",
                "Port Storage"
            ]),
            "risk_level": (
                "CRITICAL" if days < 30
                else "HIGH" if days < 60
                else "MEDIUM"
            ),
            "last_updated": datetime.datetime.utcnow().isoformat(),
        })
    return inventory


def generate_health_systems():
    all_drug_names = [d["drug_name"] for d in DRUGS]
    health_systems = []
    for hs in HEALTH_SYSTEMS:
        critical = random.sample(all_drug_names,
                                 random.randint(5, 12))
        health_systems.append({
            "hospital_id": hs["id"],
            "name": hs["name"],
            "country": hs["country"],
            "critical_drugs": critical,
            "population_served": hs["pop"],
            "healthcare_buffer_weeks": hs["buffer"],
            "import_dependency": random.choice([
                "India", "China", "Both", "Europe"
            ]),
            "emergency_stock_days": random.randint(7, 30),
        })
    return health_systems


def seed_elastic(events):
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        ))
        from integrations.elastic_client import get_elastic
        es = get_elastic()
        index = os.getenv("ELASTIC_INDEX", "geopolitical-events")
        for event in events:
            event["timestamp"] = datetime.datetime.now(
                datetime.timezone.utc).isoformat()
            es.index(index=index, document=event)
        print(f"✅ Elastic events: {len(events)} records")
    except Exception as e:
        print(f"⚠️  Elastic seeding failed: {e}")

def seed_database():
    print("🌱 Generating data...\n")

    suppliers = generate_suppliers()
    drug_ingredients = generate_drug_ingredients()
    inventory = generate_inventory()
    health_systems = generate_health_systems()

    print("🌱 Seeding MongoDB...")
    db.suppliers.drop()
    db.drug_ingredients.drop()
    db.inventory.drop()
    db.health_systems.drop()
    db.incident_reports.drop()

    db.suppliers.insert_many(suppliers)
    print(f"✅ Suppliers: {len(suppliers)} records")

    db.drug_ingredients.insert_many(drug_ingredients)
    print(f"✅ Drug ingredients: {len(drug_ingredients)} records")

    db.inventory.insert_many(inventory)
    print(f"✅ Inventory: {len(inventory)} records")

    db.health_systems.insert_many(health_systems)
    print(f"✅ Health systems: {len(health_systems)} records")

    print("\n🌱 Seeding Elastic...")
    seed_elastic(ELASTIC_EVENTS)

    print("\n✅ All done! Summary:")
    print(f"   Suppliers:       {len(suppliers)}")
    print(f"   Drugs:           {len(drug_ingredients)}")
    print(f"   Inventory items: {len(inventory)}")
    print(f"   Health systems:  {len(health_systems)}")
    print(f"   Elastic events:  {len(ELASTIC_EVENTS)}")


if __name__ == "__main__":
    seed_database()