# ruff: noqa
import os
import math
import datetime
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.agent_tool import AgentTool
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

from app.agents.stock_forecasting import stock_forecasting_agent
from app.agents.financial_impact import financial_impact_agent
from app.agents.procurement import procurement_agent

# ── MongoDB MCP Toolset ───────────────────────────────────────────────────────
mongodb_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=["-y", "mongodb-mcp-server"],
            env={"MDB_MCP_CONNECTION_STRING": os.getenv("MONGODB_URI")},
        ),
        timeout=30,
    ),
)


# ── Tool 1 ────────────────────────────────────────────────────────────────────
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


# ── Tool 2 ────────────────────────────────────────────────────────────────────
def find_affected_apis(country: str) -> list:
    """Query MongoDB for unique APIs manufactured in a country.
    Args:
        country: Country name to find API suppliers for
    Returns:
        List of unique API names at risk
    """
    trace_step("find_apis", {"country": country})
    db = get_db()
    return db.suppliers.distinct(
        "api_name",
        {
            "country": country,
            "type": "API_manufacturer",
            "export_status": "active"
        }
    )


# ── Tool 3 ────────────────────────────────────────────────────────────────────
def find_drugs_at_risk(api_names: list[str]) -> list:
    """Find finished drugs that depend on given APIs.
    Args:
        api_names: List of API names at risk
    Returns:
        List of drugs with their API dependency
    """
    trace_step("find_drugs", {"apis": str(api_names)})
    db = get_db()
    return list(db.drug_ingredients.find(
        {"active_ingredient": {"$in": api_names}},
        {"_id": 0, "drug_name": 1,
         "active_ingredient": 1, "category": 1,
         "source_countries": 1}
    ))


# ── Tool 4 ────────────────────────────────────────────────────────────────────
def assess_inventory_risk(drug_names: list[str]) -> list:
    """Check current inventory levels for affected drugs.
    Args:
        drug_names: List of drug names to check
    Returns:
        List of drugs with stock details sorted by days of supply
    """
    trace_step("assess_inventory", {"drugs": str(drug_names)})
    db = get_db()
    return list(db.inventory.find(
        {"drug_name": {"$in": drug_names}},
        {"_id": 0, "drug_name": 1, "hospital_id": 1,
         "hospital_name": 1, "country": 1,
         "current_stock": 1, "daily_consumption": 1,
         "days_of_supply": 1, "reorder_threshold": 1}
    ).sort("days_of_supply", 1))


# ── Tool 5 ────────────────────────────────────────────────────────────────────
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
    return list(db.health_systems.find(
        {
            "country": {"$in": countries},
            "critical_drugs": {"$in": drug_names}
        },
        {"_id": 0, "country": 1, "name": 1,
         "population_served": 1, "critical_drugs": 1,
         "import_dependency": 1, "healthcare_buffer_weeks": 1}
    ))


# ── Tool 6 ────────────────────────────────────────────────────────────────────
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
    return list(db.suppliers.find(
        {
            "api_name": api_name,
            "country": {"$ne": exclude_country},
            "type": "API_manufacturer",
            "export_status": "active"
        },
        {"_id": 0, "name": 1, "country": 1,
         "api_name": 1, "reliability_score": 1,
         "lead_time_days": 1, "warehouse_stock_kg": 1}
    ).sort("reliability_score", -1).limit(3))


# ── Tool 7 ────────────────────────────────────────────────────────────────────
def log_incident_report(
        event_type: str,
        country: str,
        severity: str,
        summary: str) -> dict:
    """Save the full risk assessment as an incident report in MongoDB.
    Args:
        event_type: Type of geopolitical event
        country: Affected source country
        severity: Event severity
        summary: Full text summary of findings
    Returns:
        Confirmation with incident ID
    """
    trace_step("log_incident", {"event": event_type})
    db = get_db()
    result = db.incident_reports.insert_one({
        "event_type":  event_type,
        "country":     country,
        "severity":    severity,
        "summary":     summary[:2000],
        "created_at":  datetime.datetime.now(datetime.timezone.utc),
        "status":      "pending_review",
    })
    return {
        "incident_id": str(result.inserted_id),
        "status":      "logged",
        "message":     "Incident report saved. Pending human review."
    }


# ── Tool 8: Pick Best For ALL Combos ─────────────────────────────────────────
def pick_best_for_all_combos(combos: list[dict]) -> list[dict]:
    """Pick best supplier for ALL drug×country combos in one call.
    Uses log scale ROI to differentiate suppliers.
    Scoring: ROI (33%) + Lead Time (33%) + Reliability (33%).
    Args:
        combos: List of dicts each containing:
            drug_name, country, api_name,
            patients_at_risk, stockout_probability_percent,
            suppliers_with_roi: list of suppliers with
                roi_percent, lead_time_days, reliability_score,
                supplier_name, supplier_country, supplier_id
    Returns:
        List of best supplier selections for all combos
    """
    trace_step("pick_best_all", {"combos": len(combos)})

    results = []
    for combo in combos:
        drug_name = combo.get("drug_name", "")
        country = combo.get("country", "")
        api_name = combo.get("api_name", "")
        patients_at_risk = combo.get("patients_at_risk", 0)
        stockout_prob = combo.get("stockout_probability_percent", 0)
        suppliers = combo.get("suppliers_with_roi", [])

        if not suppliers:
            results.append({
                "drug_name": drug_name,
                "country": country,
                "error": "No suppliers available"
            })
            continue

        scored = []
        for s in suppliers:
            roi = s.get("roi_percent", 0)
            lead_time = s.get("lead_time_days", 60)
            reliability = s.get("reliability_score", 0.5)
            supplier_name = (
                s.get("supplier_name") or
                s.get("name") or "Unknown"
            )
            supplier_country = (
                s.get("supplier_country") or
                s.get("country") or "Unknown"
            )
            supplier_id = s.get("supplier_id", "")

            # Log scale ROI — differentiates suppliers meaningfully
            roi_score = min(100, math.log10(max(1, roi)) * 20)
            lead_time_score = max(0, 100 - lead_time)
            reliability_score = reliability * 100
            combined = (
                roi_score * 0.33 +
                lead_time_score * 0.33 +
                reliability_score * 0.33
            )

            scored.append({
                "supplier_id":                  supplier_id,
                "supplier_name":                supplier_name,
                "supplier_country":             supplier_country,
                "reliability_score":            reliability,
                "lead_time_days":               lead_time,
                "roi_percent":                  roi,
                "combined_score":               round(combined, 2),
                "roi_score":                    round(roi_score, 2),
                "lead_time_score":              round(lead_time_score, 2),
                "reliability_score_normalized": round(reliability_score, 2)
            })

        scored.sort(key=lambda x: x["combined_score"], reverse=True)
        best = scored[0]

        results.append({
            "drug_name":                    drug_name,
            "country":                      country,
            "api_name":                     api_name,
            "patients_at_risk":             patients_at_risk,
            "stockout_probability_percent": stockout_prob,
            "best_supplier":                best,
            "all_scored":                   scored
        })

    return results


# ── Agent ─────────────────────────────────────────────────────────────────────
root_agent = Agent(
    name="geopolitical_health_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Geopolitical Health Supply Chain Risk Agent.
You are the ROOT AGENT coordinating all specialists.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 1 — RISK ASSESSMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1: detect_geopolitical_event(country)
STEP 2: find_affected_apis(country)
STEP 3: find_drugs_at_risk(api_names)
STEP 4: assess_inventory_risk(drug_names)
STEP 5: find_vulnerable_populations(drug_names, countries)
  For India: [Bangladesh, Nepal, Pakistan, Myanmar,
    Sri Lanka, Nigeria, Kenya, Ethiopia, Tanzania, Uganda]
  For China: [Cambodia, Laos, Myanmar, Nigeria,
    Kenya, Bangladesh, Ethiopia]
STEP 6: find_alternative_suppliers(api_name, exclude_country)
  For top 5 most critical APIs only
STEP 7: log_incident_report(event_type, country, severity, summary)

After Step 7 write Phase 1 report:

══════════════════════════════════════════
GEOPOLITICAL HEALTH SUPPLY CHAIN REPORT
══════════════════════════════════════════
EVENT DETECTED:
[event_type] in [country]
Severity: [severity]
[one sentence description]

APIs AT RISK:
Copy EXACTLY what find_affected_apis tool returned.
Do NOT use your own knowledge. Do NOT summarize.
List every single API name from the tool result.
Example if tool returned ['Metformin', 'Azithromycin', 'Paracetamol'...]:
Metformin, Azithromycin, Paracetamol, [all others...]

DRUGS AFFECTED:
Copy EXACTLY what find_drugs_at_risk tool returned.
Do NOT use your own knowledge. Do NOT summarize.
List every drug with its API:
[drug_name] — made from [active_ingredient]
[repeat for ALL drugs returned by the tool]

DRUGS AFFECTED:
Copy EXACTLY what find_drugs_at_risk tool returned.
Do NOT use your own knowledge. Do NOT summarize.
List every drug with its API:
[drug_name] — made from [active_ingredient]
[repeat for ALL drugs returned by the tool]


POPULATIONS EXPOSED:
[Country]: [sum population_served] patients

ALTERNATIVE SUPPLIERS:
[API] — [Country] (lead_time: X days)

INCIDENT LOGGED: [incident_id]
══════════════════════════════════════════

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 2 — SUPPLY CHAIN RESPONSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 8: Call stock_forecasting_agent
→ Send: "drug_names: [comma separated from Step 3]
  countries: [comma separated from Step 5]
  disrupted_country: [country from Step 1]"
→ Receive: combos with top 3 suppliers per combo
→ Write BEFORE calling next agent:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STOCKOUT FORECAST RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[For EVERY combo write:]
─────────────────────────────────────
Drug: [drug_name] | Country: [country]
─────────────────────────────────────
Population at risk:      [patients_at_risk]
Days until stockout:     [days_until_stockout]
Probability of shortage: [probability]%
Action deadline:         [action_deadline]
Top 3 suppliers (lead time + reliability):
* [supplier_name] ([country]) — reliability [score], lead time [days] days
* [supplier_name] ([country]) — reliability [score], lead time [days] days
* [supplier_name] ([country]) — reliability [score], lead time [days] days

STEP 9: Call financial_impact_agent with this plain text message
(NO JSON, NO code — just plain text):
"Calculate financial impact for these combos:
combo 1: drug=[drug_name], country=[country], population=[population_served], disruption_days=60, suppliers: [supplier_name] ([supplier_country]) lead=[days] reliability=[score], [supplier_name] ([supplier_country]) lead=[days] reliability=[score]
combo 2: drug=[drug_name], country=[country], population=[population_served], disruption_days=60, suppliers: [supplier_name] ([supplier_country]) lead=[days] reliability=[score]
[one line per combo, fill in actual values from Step 8]"
→ Receive: ROI analysis per supplier per combo
→ Write BEFORE calling next agent:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINANCIAL ANALYSIS RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[For EVERY combo write:]
FINANCIAL ANALYSIS: [drug_name] | [country]
Cost of doing nothing:  $[cost_of_stockout_usd]
  Direct health cost:   $[direct_health_cost_usd]
  Emergency care:       $[emergency_care_cost_usd]
  Productivity loss:    $[productivity_loss_usd]
Suppliers ranked by ROI:
1. [supplier_name] ([country]) ROI: [roi]% | Cost: $[cost] → [recommendation]
2. [supplier_name] ([country]) ROI: [roi]% | Cost: $[cost] → [recommendation]

STEP 10: Call pick_best_for_all_combos() ONCE with ALL combos
→ Pass: combos=[list of all combos, each with:
    drug_name, country, api_name,
    patients_at_risk, stockout_probability_percent,
    suppliers_with_roi: [ranked_suppliers from Step 9
      each with: supplier_id, supplier_name, supplier_country,
      roi_percent, lead_time_days, reliability_score]]
→ Write ONE combined output after the single call:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUPPLIER SELECTION RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[For EVERY combo write on one line:]
[Drug] | [Country] → ✅ [supplier_name] ([supplier_country])
  Score: [combined_score]/100 (ROI: [roi_score] | Lead: [lead_time_score] | Reliability: [reliability_score_normalized])

STEP 11: Call procurement_agent with this plain text message
(one combo per line, NO JSON arrays):
"File purchase orders for these combos:
combo 1 — drug: [drug_name], api: [api_name], country: [country], patients: [patients_at_risk], supplier_id: [id], supplier: [name], supplier_country: [country], lead_time: [days], roi: [roi_percent], probability: [prob], score: [combined_score]
combo 2 — drug: [drug_name]...
[all combos, one per line]"
→ Receive: order IDs

STEP 12: Write final summary:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 2 COMPLETE — SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| Drug | Country | Supplier | Units | Cost | Order ID |
|------|---------|----------|-------|------|----------|
| [drug] | [country] | [supplier] | [qty] | $[cost] | [id] |

Orders filed: [count]
⚠️ All orders require human approval before execution.

STRICT RULES:
1. Never use CRITICAL, HIGH, MEDIUM in Phase 1
2. Never mention hospital IDs
3. Always sum population per country not per hospital
4. Complete ALL Phase 1 steps before Phase 2
5. ALWAYS write STOCKOUT FORECAST RESULTS after Step 8
6. ALWAYS write FINANCIAL ANALYSIS RESULTS after Step 9
7. Call pick_best_for_all_combos() ONCE with ALL combos
8. NEVER pass JSON arrays to procurement_agent — use plain text
9. ALWAYS call procurement_agent after supplier selection
10. NEVER stop after Phase 1 — Phase 2 is mandatory
11. Write output at EACH step before proceeding
12. ALWAYS use tool return values for APIs AT RISK and DRUGS AFFECTED
13. NEVER use your own knowledge to fill these fields
14. Copy tool results exactly — do not abbreviate or summarize""",
    tools=[
        detect_geopolitical_event,
        find_affected_apis,
        find_drugs_at_risk,
        assess_inventory_risk,
        find_vulnerable_populations,
        find_alternative_suppliers,
        log_incident_report,
        pick_best_for_all_combos,
        mongodb_toolset,
        AgentTool(agent=stock_forecasting_agent),
        AgentTool(agent=financial_impact_agent),
        AgentTool(agent=procurement_agent),
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)