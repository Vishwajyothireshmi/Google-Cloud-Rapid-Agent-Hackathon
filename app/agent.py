# ruff: noqa
import os
import datetime
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.genai import types
from mcp import StdioServerParameters
import google.auth

load_dotenv()

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

from integrations.mongodb_client import get_db
from integrations.elastic_client import get_elastic
from integrations.arize_client import trace_step

# ── MongoDB MCP Toolset ───────────────────────────────────────────────────────
# This gives Gemini direct access to MongoDB via MCP protocol
# Gemini can use find, aggregate, insert operations natively
mongodb_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=["-y", "mongodb-mcp-server"],
            env={
                "MDB_MCP_CONNECTION_STRING": os.getenv("MONGODB_URI"),
            },
        ),
        timeout=30,
    ),
)

# ── Tool 1: Detect geopolitical event via Elastic ─────────────────────────────
def detect_geopolitical_event(country: str) -> dict:
    """Search Elastic for geopolitical events affecting a country.
    Args:
        country: Country name to search events for
    Returns:
        Latest high/critical event details or status dict
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


# ── Tool 2: Find APIs sourced from affected country ───────────────────────────
def find_affected_apis(country: str) -> list:
    """Query MongoDB suppliers for all APIs manufactured in a country.
    Args:
        country: Country name to find API suppliers for
    Returns:
        List of unique API names at risk
    """
    trace_step("find_apis", {"country": country})
    db = get_db()
    results = list(db.suppliers.find(
        {
            "country": country,
            "type": "API_manufacturer",
            "export_status": "active"
        },
        {"_id": 0, "api_name": 1, "name": 1,
         "reliability_score": 1, "lead_time_days": 1,
         "warehouse_stock_kg": 1}
    ))
    return results


# ── Tool 3: Find finished drugs that depend on at-risk APIs ───────────────────
def find_drugs_at_risk(api_names: list[str]) -> list:
    """Find finished drugs that depend on given APIs.
    Args:
        api_names: List of API names at risk
    Returns:
        List of drugs with their API dependency
    """
    trace_step("find_drugs", {"apis": str(api_names)})
    db = get_db()
    results = list(db.drug_ingredients.find(
        {"active_ingredient": {"$in": api_names}},
        {"_id": 0, "drug_name": 1,
         "active_ingredient": 1, "category": 1,
         "source_countries": 1}
    ))
    return results


# ── Tool 4: Check inventory stock levels ──────────────────────────────────────
def assess_inventory_risk(drug_names: list[str]) -> list:
    """Check current inventory levels at hospitals for affected drugs.
    Args:
        drug_names: List of drug names to check
    Returns:
        List of drugs with stock details — days remaining,
        hospital, country, daily consumption
    """
    trace_step("assess_inventory", {"drugs": str(drug_names)})
    db = get_db()
    results = list(db.inventory.find(
        {"drug_name": {"$in": drug_names}},
        {"_id": 0,
         "drug_name": 1,
         "hospital_id": 1,
         "hospital_name": 1,
         "country": 1,
         "current_stock": 1,
         "daily_consumption": 1,
         "days_of_supply": 1,
         "reorder_threshold": 1}
    ).sort("days_of_supply", 1))  # worst first
    return results


# ── Tool 5: Find vulnerable populations ───────────────────────────────────────
def find_vulnerable_populations(
        drug_names: list[str],
        countries: list[str]) -> list:
    """Find populations depending on at-risk drugs by country.
    Args:
        drug_names: Drugs at risk
        countries: Countries that import from affected source
    Returns:
        List of health systems with population counts
    """
    trace_step("find_populations", {"drugs": str(drug_names)})
    db = get_db()
    results = list(db.health_systems.find(
        {
            "country": {"$in": countries},
            "critical_drugs": {"$in": drug_names}
        },
        {"_id": 0,
         "country": 1,
         "name": 1,
         "population_served": 1,
         "critical_drugs": 1,
         "import_dependency": 1,
         "healthcare_buffer_weeks": 1}
    ))
    return results


# ── Tool 6: Find alternative suppliers ────────────────────────────────────────
def find_alternative_suppliers(
        api_name: str,
        exclude_country: str) -> list:
    """Find alternative API suppliers outside the affected country.
    Args:
        api_name: The API name to source alternatively
        exclude_country: Country to exclude from results
    Returns:
        Top 3 alternative suppliers ranked by reliability
    """
    trace_step("find_alternatives", {"api": api_name})
    db = get_db()
    results = list(db.suppliers.find(
        {
            "api_name": api_name,
            "country": {"$ne": exclude_country},
            "type": "API_manufacturer",
            "export_status": "active"
        },
        {"_id": 0,
         "name": 1,
         "country": 1,
         "api_name": 1,
         "reliability_score": 1,
         "lead_time_days": 1,
         "warehouse_stock_kg": 1}
    ).sort("reliability_score", -1).limit(3))
    return results


# ── Tool 7: Log incident report to MongoDB ────────────────────────────────────
def log_incident_report(
        event_type: str,
        country: str,
        severity: str,
        summary: str) -> dict:
    """Save the full risk assessment as an incident report in MongoDB.
    Args:
        event_type: Type of geopolitical event detected
        country: Affected source country
        severity: Event severity (critical/high)
        summary: Full text summary of findings
    Returns:
        Confirmation with incident ID
    """
    trace_step("log_incident", {"event": event_type})
    db = get_db()
    report = {
        "event_type":  event_type,
        "country":     country,
        "severity":    severity,
        "summary":     summary[:2000],
        "created_at":  datetime.datetime.now(datetime.timezone.utc),
        "status":      "pending_review",
    }
    result = db.incident_reports.insert_one(report)
    return {
        "incident_id": str(result.inserted_id),
        "status":      "logged",
        "message":     "Incident report saved. Pending human review."
    }


# ── Agent definition ──────────────────────────────────────────────────────────
root_agent = Agent(
    name="geopolitical_health_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are a Geopolitical Health Supply Chain Risk Agent.

Your job: detect geopolitical disruptions and trace their full
impact on global healthcare supply chains.

You have two types of tools:
- Custom tools: query Elastic and MongoDB with domain logic
- MongoDB MCP tools: direct database access for deeper queries

When given a country or event, ALWAYS complete ALL 7 steps:

STEP 1: detect_geopolitical_event(country)
  Search Elastic for active sanctions, export bans,
  conflicts, or port closures affecting that country.

STEP 2: find_affected_apis(country)
  Find all pharmaceutical APIs manufactured in
  the affected country using MongoDB suppliers collection.

STEP 3: find_drugs_at_risk(api_names)
  Find all finished drugs that depend on those APIs
  using MongoDB drug_ingredients collection.

STEP 4: assess_inventory_risk(drug_names)
  Check current stock levels for all affected drugs
  using MongoDB inventory collection.

STEP 5: find_vulnerable_populations(drug_names, countries)
  Find which populations depend on the affected drugs.
  For India events use countries:
    [Bangladesh, Nepal, Pakistan, Myanmar, Sri Lanka,
     Nigeria, Kenya, Ethiopia, Tanzania, Uganda]
  For China events use countries:
    [Cambodia, Laos, Myanmar, Nigeria, Kenya,
     Bangladesh, Ethiopia]

STEP 6: find_alternative_suppliers(api_name, exclude_country)
  For the top 5 most critical APIs find alternative
  suppliers outside the affected country.

STEP 7: log_incident_report(event_type, country,
                             severity, summary)
  Save the complete assessment to MongoDB.

After completing all 7 steps present EXACTLY
this output format — nothing more, nothing less:

════════════════════════════════════════
GEOPOLITICAL HEALTH SUPPLY CHAIN REPORT
════════════════════════════════════════

EVENT DETECTED:
[event_type] in [country]
Severity: [severity]
[one sentence description from Elastic]

APIs AT RISK:
[api_name], [api_name], [api_name]...
(these are raw pharmaceutical ingredients
 no longer available from [country])

DRUGS AFFECTED:
[drug_name] — made from [api_name],
[drug_name] — made from [api_name],
[drug_name] — made from [api_name]
(list every drug and its API dependency)

POPULATIONS EXPOSED:
[Country]: [sum of population_served] patients
[Country]: [sum of population_served] patients
(sum all hospitals per country that depend
 on any of the affected drugs)

ALTERNATIVE SUPPLIERS:
[API name] — [Country1], [Country2], [Country3]
[API name] — [Country1], [Country2] 
(just list the API and which countries 
 can supply it as alternatives)


INCIDENT LOGGED: [incident_id]
════════════════════════════════════════

STRICT RULES — never break these:
1. Never use the words CRITICAL, HIGH, MEDIUM
2. Never mention hospital IDs (HS001 etc)
3. Never mention warehouse names
4. Always sum population per country
   not per individual hospital
5. Always show which API each drug depends on
6. Always show lead_time for every alternative
7. Always complete all 7 steps before responding
""",
    tools=[
        detect_geopolitical_event,
        find_affected_apis,
        find_drugs_at_risk,
        assess_inventory_risk,
        find_vulnerable_populations,
        find_alternative_suppliers,
        log_incident_report,
        mongodb_toolset,
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)