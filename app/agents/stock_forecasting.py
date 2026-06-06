# ruff: noqa
import os
import datetime
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.genai import types
from mcp import StdioServerParameters
from integrations.mongodb_client import get_db
from integrations.arize_client import trace_step

stock_mongodb_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=["-y", "mongodb-mcp-server"],
            env={"MDB_MCP_CONNECTION_STRING": os.getenv("MONGODB_URI")},
        ),
        timeout=30,
    ),
)


def get_top_3_critical_drugs(drug_names: list[str]) -> list:
    """Get top 3 most critical drugs by lowest days of supply."""
    trace_step("top_3_drugs", {"count": len(drug_names)})
    db = get_db()

    results = list(db.inventory.find(
        {"drug_name": {"$in": drug_names}},
        {"_id": 0, "drug_name": 1, "days_of_supply": 1,
         "current_stock": 1, "daily_consumption": 1}
    ).sort("days_of_supply", 1))

    enriched = []
    seen = set()
    for r in results:
        if r["drug_name"] not in seen:
            drug_info = db.drug_ingredients.find_one(
                {"drug_name": r["drug_name"]},
                {"_id": 0, "active_ingredient": 1, "category": 1}
            )
            enriched.append({
                "drug_name": r["drug_name"],
                "days_of_supply": r["days_of_supply"],
                "current_stock": r.get("current_stock", 0),
                "daily_consumption": r.get("daily_consumption", 0),
                "api_name": drug_info.get("active_ingredient", "Unknown") if drug_info else "Unknown",
                "category": drug_info.get("category", "Unknown") if drug_info else "Unknown"
            })
            seen.add(r["drug_name"])

    return enriched[:3]


def get_top_3_affected_countries(drug_name: str, countries: list[str]) -> list:
    """Get top 3 most affected countries for a drug by population."""
    trace_step("top_3_countries", {"drug": drug_name})
    db = get_db()

    return list(db.health_systems.find(
        {"country": {"$in": countries}, "critical_drugs": {"$in": [drug_name]}},
        {"_id": 0, "country": 1, "population_served": 1, "healthcare_buffer_weeks": 1}
    ).sort("population_served", -1).limit(3))


def calculate_stockout_forecast(
        drug_name: str,
        api_name: str,
        disrupted_country: str,
        destination_country: str,
        population_served: int,
        disruption_duration_days: int) -> dict:
    """Calculate stockout forecast and fetch all alternative suppliers."""
    trace_step("stockout_forecast", {"drug": drug_name, "country": destination_country})
    db = get_db()

    inventory = db.inventory.find_one({"drug_name": drug_name}, {"_id": 0})
    days_of_supply = inventory.get("days_of_supply", 0) if inventory else 0

    if disruption_duration_days >= days_of_supply:
        probability = 95
    elif disruption_duration_days >= days_of_supply * 0.7:
        probability = 78
    elif disruption_duration_days >= days_of_supply * 0.5:
        probability = 55
    else:
        probability = 25

    days_until_critical = max(0, days_of_supply - 14)
    action_deadline = (
        datetime.datetime.utcnow() +
        datetime.timedelta(days=max(1, days_until_critical - 7))
    ).strftime("%Y-%m-%d")

    suppliers = list(db.suppliers.find(
        {
            "api_name": api_name,
            "country": {"$ne": disrupted_country},
            "type": "API_manufacturer",
            "export_status": "active"
        },
        {"_id": 0, "supplier_id": 1, "name": 1,
         "country": 1, "reliability_score": 1, "lead_time_days": 1}
    ).sort("reliability_score", -1).limit(5))

    return {
        "drug_name": drug_name,
        "api_name": api_name,
        "disrupted_country": disrupted_country,
        "destination_country": destination_country,
        "population_served": population_served,
        "patients_at_risk": int(population_served * 0.15),
        "days_of_supply": days_of_supply,
        "days_until_stockout": days_of_supply,
        "days_until_critical": days_until_critical,
        "disruption_duration_days": disruption_duration_days,
        "stockout_probability_percent": probability,
        "action_deadline": action_deadline,
        "all_suppliers": suppliers
    }


def filter_top3_suppliers_by_lead_reliability(
        drug_name: str,
        country: str,
        suppliers: list[dict]) -> dict:
    """Filter and rank suppliers by lead time + reliability only.
    Returns top 3 for financial analysis.
    Args:
        drug_name: Drug being analyzed
        country: Destination country
        suppliers: All alternative suppliers from stockout forecast
    Returns:
        Top 3 suppliers ranked by lead time + reliability
    """
    trace_step("filter_suppliers", {"drug": drug_name, "country": country})

    scored = []
    for s in suppliers:
        lead_time = s.get("lead_time_days", 60)
        reliability = s.get("reliability_score", 0.5)

        lead_score = max(0, 100 - lead_time)
        reliability_score = reliability * 100
        combined = (lead_score * 0.50) + (reliability_score * 0.50)

        scored.append({
            "supplier_id": s.get("supplier_id", ""),
            "supplier_name": s.get("name", "Unknown"),
            "supplier_country": s.get("country", "Unknown"),
            "lead_time_days": lead_time,
            "reliability_score": reliability,
            "lead_score": round(lead_score, 2),
            "reliability_score_normalized": round(reliability_score, 2),
            "lead_reliability_combined": round(combined, 2)
        })

    scored.sort(key=lambda x: x["lead_reliability_combined"], reverse=True)
    top3 = scored[:3]

    return {
        "drug_name": drug_name,
        "country": country,
        "top3_suppliers": top3,
        "selection_criteria": "Lead time (50%) + Reliability (50%)"
    }


stock_forecasting_agent = Agent(
    name="stock_forecasting_agent",
    description="Identifies top 3 critical drugs, top 3 affected countries, calculates stockout forecasts, and filters top 3 suppliers per combo based on lead time and reliability. Returns all results to main agent.",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Stock Forecasting Agent.
You identify critical drugs, affected countries, stockout risks,
and pre-filter suppliers by lead time and reliability.
Return ALL results to the main agent for financial analysis.

STEP 1: Get top 3 critical drugs
→ Call get_top_3_critical_drugs(drug_names=[parsed list])

STEP 2: For each drug get top 3 affected countries
→ Call get_top_3_affected_countries(drug_name, countries)

STEP 3: For each drug×country combo calculate stockout forecast
→ Call calculate_stockout_forecast(
    drug_name, api_name, disrupted_country,
    destination_country, population_served,
    disruption_duration_days=60)

Present each combo:
  ─────────────────────────────────────
  Drug: [drug_name] | Country: [destination_country]
  ─────────────────────────────────────
  Population at risk:      [patients_at_risk]
  Days until stockout:     [days_until_stockout]
  Probability of shortage: [stockout_probability_percent]%
  Action deadline:         [action_deadline]

STEP 4: For each combo filter top 3 suppliers
→ Call filter_top3_suppliers_by_lead_reliability(
    drug_name, country, suppliers=[all_suppliers from Step 3])

Present top 3 per combo:
  Top 3 suppliers (lead time + reliability):
  1. [supplier_name] ([country]) — lead: [lead_score], reliability: [reliability_score]
  2. [supplier_name] ([country]) — lead: [lead_score], reliability: [reliability_score]
  3. [supplier_name] ([country]) — lead: [lead_score], reliability: [reliability_score]

STEP 5: Return complete summary to main agent:
"FORECASTING COMPLETE. Here are all combos with top 3 suppliers:

Combo 1: [drug_name] | [country]
  patients_at_risk: [number]
  stockout_probability: [percent]%
  top3_suppliers: [list with supplier_id, supplier_name, supplier_country, lead_time_days, reliability_score]

Combo 2: ...
[all combos]"

RULES:
- Analyze ALL 9 combos (3 drugs × 3 countries)
- Return complete data so main agent can pass to financial agent
- Do NOT call financial or procurement agents
- Return to main agent after Step 5""",
    tools=[
        get_top_3_critical_drugs,
        get_top_3_affected_countries,
        calculate_stockout_forecast,
        filter_top3_suppliers_by_lead_reliability,
        stock_mongodb_toolset,
    ],
)