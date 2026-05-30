# ruff: noqa
import os
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types
import google.auth

load_dotenv()

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

from integrations.mongodb_client import get_db
from integrations.elastic_client import get_elastic
from integrations.arize_client import trace_step

# ── Tool 1 ────────────────────────────────────────────
def detect_geopolitical_event(country: str) -> dict:
    """Search Elastic for geopolitical events affecting a country.
    Args:
        country: Country name to search events for
    Returns:
        Latest event details or empty dict
    """
    trace_step("detect_event", {"country": country})
    try:
        client = get_elastic()
        index = os.getenv("ELASTIC_INDEX", "geopolitical-events")
        result = client.search(index=index, body={
            "query": {
                "bool": {
                    "must": [
                        {"match": {"country": country}},
                        {"terms": {"severity": ["high", "critical"]}}
                    ]
                }
            },
            "sort": [{"timestamp": {"order": "desc"}}],
            "size": 1
        })
        hits = result["hits"]["hits"]
        if hits:
            return hits[0]["_source"]
        return {"status": "no_events", "country": country}
    except Exception as e:
        return {"error": str(e), "country": country}

# ── Tool 2 ────────────────────────────────────────────
def find_affected_apis(country: str) -> list:
    """Query MongoDB for pharmaceutical APIs sourced from a country.
    Args:
        country: Country name to find API suppliers for
    Returns:
        List of affected API suppliers
    """
    trace_step("find_apis", {"country": country})
    db = get_db()
    results = list(db.suppliers.find(
        {"country": country, "type": "API_manufacturer"},
        {"_id": 0, "supplier_id": 1, "api_name": 1,
         "reliability_score": 1, "lead_time_days": 1}
    ))
    return results

# ── Tool 3 ────────────────────────────────────────────
def find_drugs_at_risk(api_names: list) -> list:
    """Find finished drugs that depend on given APIs.
    Args:
        api_names: List of API names at risk
    Returns:
        List of drugs at risk
    """
    trace_step("find_drugs", {"apis": str(api_names)})
    db = get_db()
    results = list(db.drug_ingredients.find(
        {"active_ingredient": {"$in": api_names}},
        {"_id": 0, "drug_name": 1, 
         "active_ingredient": 1, "category": 1}
    ))
    return results

# ── Tool 4 ────────────────────────────────────────────
def assess_inventory_risk(drug_names: list) -> list:
    """Check current inventory levels against reorder thresholds.
    Args:
        drug_names: List of drug names to check
    Returns:
        List of drugs with risk scores
    """
    trace_step("assess_inventory", {"drugs": str(drug_names)})
    db = get_db()
    results = list(db.inventory.find(
        {"drug_name": {"$in": drug_names}},
        {"_id": 0, "drug_name": 1, "current_stock": 1,
         "reorder_threshold": 1, "days_of_supply": 1}
    ))
    for r in results:
        r["risk_level"] = (
            "CRITICAL" if r["days_of_supply"] < 30
            else "HIGH" if r["days_of_supply"] < 60
            else "MEDIUM"
        )
    return results

# ── Tool 5 ────────────────────────────────────────────
def find_vulnerable_populations(
        drug_names: list,
        countries: list) -> list:
    """Identify health systems depending on at-risk drugs.
    Args:
        drug_names: Drugs at risk
        countries: Countries that import them
    Returns:
        List of vulnerable health systems
    """
    trace_step("find_populations", {"drugs": str(drug_names)})
    db = get_db()
    results = list(db.health_systems.find(
        {
            "country": {"$in": countries},
            "critical_drugs": {"$in": drug_names}
        },
        {"_id": 0, "hospital_id": 1, "country": 1,
         "population_served": 1, "critical_drugs": 1}
    ))
    return results

# ── Tool 6 ────────────────────────────────────────────
def find_alternative_suppliers(
        api_name: str,
        exclude_country: str) -> list:
    """Find alternative API suppliers outside affected country.
    Args:
        api_name: The API to source alternatively
        exclude_country: Country to exclude
    Returns:
        Ranked list of alternative suppliers
    """
    trace_step("find_alternatives", {"api": api_name})
    db = get_db()
    results = list(db.suppliers.find(
        {
            "api_name": api_name,
            "country": {"$ne": exclude_country},
            "type": "API_manufacturer"
        },
        {"_id": 0, "supplier_id": 1, "country": 1,
         "api_name": 1, "reliability_score": 1,
         "lead_time_days": 1}
    ).sort("reliability_score", -1).limit(3))
    return results

# ── Tool 7 ────────────────────────────────────────────
def log_incident_report(report: dict) -> dict:
    """Save incident report to MongoDB and return confirmation.
    Args:
        report: Full risk assessment report
    Returns:
        Confirmation with incident ID
    """
    trace_step("log_incident", {"event": report.get("event_type")})
    db = get_db()
    import datetime
    report["created_at"] = datetime.datetime.utcnow()
    report["status"] = "pending_review"
    result = db.incident_reports.insert_one(report)
    return {
        "incident_id": str(result.inserted_id),
        "status": "logged",
        "message": "Incident report saved successfully"
    }

# ── Agent ─────────────────────────────────────────────
root_agent = Agent(
    name="geopolitical_health_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are a Geopolitical Health Supply Chain Risk Agent.

Your job is to detect geopolitical events and trace their impact 
on healthcare supply chains.

When given a country or event, you MUST complete ALL 7 steps:

1. detect_geopolitical_event(country) 
   → Search Elastic for sanctions/conflicts/disruptions

2. find_affected_apis(country) 
   → Find pharmaceutical APIs sourced from that country

3. find_drugs_at_risk(api_names) 
   → Find which finished drugs depend on those APIs

4. assess_inventory_risk(drug_names) 
   → Check stock levels, flag CRITICAL/HIGH/MEDIUM risks

5. find_vulnerable_populations(drug_names, countries) 
   → Find which health systems and populations are exposed
   → Use these import-dependent countries for India: 
     [Bangladesh, Nepal, Pakistan, Myanmar, Sri Lanka]
   → Use these for China: 
     [Cambodia, Laos, Myanmar, Nigeria, Kenya]

6. find_alternative_suppliers(api_name, exclude_country) 
   → Find 3 backup suppliers outside the affected country

7. log_incident_report(report) 
   → Save full risk assessment to MongoDB

After all 7 steps, provide a structured summary:
- Event detected
- APIs at risk
- Drugs affected
- Risk levels (CRITICAL/HIGH/MEDIUM)
- Populations exposed
- Alternative suppliers found
- Incident ID logged""",
    tools=[
        detect_geopolitical_event,
        find_affected_apis,
        find_drugs_at_risk,
        assess_inventory_risk,
        find_vulnerable_populations,
        find_alternative_suppliers,
        log_incident_report,
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)