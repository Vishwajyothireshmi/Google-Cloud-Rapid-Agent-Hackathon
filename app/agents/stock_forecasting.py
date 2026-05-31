# ruff: noqa
import os
import datetime
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.tools.agent_tool import AgentTool
from google.genai import types
from integrations.mongodb_client import get_db
from integrations.arize_client import trace_step

from app.agents.financial_impact import financial_impact_agent
from app.agents.procurement import procurement_agent


# ══════════════════════════════════════════════════════
# STOCK FORECASTING AGENT TOOLS
# ══════════════════════════════════════════════════════

def get_top_3_critical_drugs(drug_names: list[str]) -> list:
    """Get top 3 most critical drugs by lowest days of supply.
    Args:
        drug_names: List of drug names to check
    Returns:
        Top 3 drugs with lowest days of supply + API name
    """
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
                "api_name": drug_info.get(
                    "active_ingredient", "Unknown"
                ) if drug_info else "Unknown",
                "category": drug_info.get(
                    "category", "Unknown"
                ) if drug_info else "Unknown"
            })
            seen.add(r["drug_name"])

    return enriched[:3]


def get_top_3_affected_countries(
        drug_name: str,
        countries: list[str]) -> list:
    """Get top 3 most affected countries for a drug by population.
    Args:
        drug_name: Drug at risk
        countries: List of countries that import this drug
    Returns:
        Top 3 countries sorted by population served
    """
    trace_step("top_3_countries", {"drug": drug_name})
    db = get_db()

    results = list(db.health_systems.find(
        {
            "country": {"$in": countries},
            "critical_drugs": {"$in": [drug_name]}
        },
        {"_id": 0, "country": 1, "population_served": 1,
         "healthcare_buffer_weeks": 1}
    ).sort("population_served", -1).limit(3))

    return results


def calculate_stockout_forecast(
        drug_name: str,
        api_name: str,
        disrupted_country: str,
        destination_country: str,
        population_served: int,
        disruption_duration_days: int) -> dict:
    """Calculate stockout forecast for one drug×country combo.
    Also fetches alternative suppliers for that API.
    Args:
        drug_name: Name of the drug
        api_name: Active pharmaceutical ingredient
        disrupted_country: Country where disruption occurred (exclude from suppliers)
        destination_country: Affected import country
        population_served: Population depending on this drug
        disruption_duration_days: Expected disruption length
    Returns:
        Stockout forecast + alternative suppliers
    """
    trace_step("stockout_forecast", {
        "drug": drug_name,
        "country": destination_country
    })
    db = get_db()

    inventory = db.inventory.find_one(
        {"drug_name": drug_name},
        {"_id": 0}
    )

    days_of_supply = inventory.get(
        "days_of_supply", 0
    ) if inventory else 0
    current_stock = inventory.get(
        "current_stock", 0
    ) if inventory else 0

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

    # Exclude disrupted country not destination country
    suppliers = list(db.suppliers.find(
        {
            "api_name": api_name,
            "country": {"$ne": disrupted_country},
            "type": "API_manufacturer",
            "export_status": "active"
        },
        {"_id": 0, "supplier_id": 1, "name": 1,
         "country": 1, "reliability_score": 1,
         "lead_time_days": 1}
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
        "alternative_suppliers": suppliers
    }


def pick_best_supplier_for_combo(
        drug_name: str,
        country: str,
        financial_rankings: list[dict]) -> dict:
    """Pick best supplier for a drug×country combo.
    Scores equally: ROI (33%) + lead time (33%) + reliability (33%).
    Args:
        drug_name: Drug being analyzed
        country: Affected country
        financial_rankings: Ranked suppliers from financial agent
    Returns:
        Best supplier with combined score and full reasoning
    """
    trace_step("pick_best", {
        "drug": drug_name,
        "country": country
    })

    if not financial_rankings:
        return {
            "error": f"No suppliers for {drug_name} | {country}"
        }

    scored = []
    for s in financial_rankings:
        roi = s.get("roi_percent", 0)
        lead_time = s.get("lead_time_days", 60)
        reliability = s.get("reliability_score", 0.5)

        roi_score = min(100, roi / 3)
        lead_time_score = max(0, 100 - lead_time)
        reliability_score = reliability * 100

        combined = (
            roi_score * 0.33 +
            lead_time_score * 0.33 +
            reliability_score * 0.33
        )

        scored.append({
            **s,
            "combined_score": round(combined, 2),
            "roi_score": round(roi_score, 2),
            "lead_time_score": round(lead_time_score, 2),
            "reliability_score_normalized": round(reliability_score, 2)
        })

    scored.sort(key=lambda x: x["combined_score"], reverse=True)
    best = scored[0]

    return {
        "drug_name": drug_name,
        "country": country,
        "best_supplier": best,
        "all_scored_options": scored,
        "selection_reasoning": (
            f"Selected {best.get('supplier_name', best.get('supplier_country', 'Unknown'))} "
            f"— Combined: {best['combined_score']}/100 "
            f"(ROI: {best['roi_score']:.0f}/100, "
            f"Lead time: {best['lead_time_score']:.0f}/100, "
            f"Reliability: {best['reliability_score_normalized']:.0f}/100)"
        )
    }


# ══════════════════════════════════════════════════════
# STOCK FORECASTING AGENT
# ══════════════════════════════════════════════════════

stock_forecasting_agent = Agent(
    name="stock_forecasting_agent",
    description="Coordinates full supply chain risk analysis — identifies top 3 critical drugs × top 3 countries, gets financial analysis, picks best supplier, triggers procurement orders",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Stock Forecasting Agent — coordinator
of Phase 2 supply chain risk analysis.

You receive a message containing:
- drug_names: comma separated list of drug names
- countries: comma separated list of affected countries
- disrupted_country: the country where disruption occurred

Parse these from the message and proceed.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STOCK FORECASTING ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1: Get top 3 critical drugs
→ Call get_top_3_critical_drugs(drug_names=[list of drug names])
→ Present:

  Top 3 Critical Drugs (lowest stock):
  1. [drug_name] ([api_name])
  2. [drug_name] ([api_name])
  3. [drug_name] ([api_name])

STEP 2: For each of the 3 drugs get top 3 affected countries
→ Call get_top_3_affected_countries(
    drug_name=[drug], countries=[list of countries])

STEP 3: For each drug×country combo (9 total) calculate forecast
→ Call calculate_stockout_forecast(
    drug_name, api_name, disrupted_country,
    destination_country, population_served,
    disruption_duration_days=60)
→ Present each combo:

  ─────────────────────────────────────
  Drug: [drug_name] | Country: [destination_country]
  ─────────────────────────────────────
  Population at risk:      [patients_at_risk]
  Days until stockout:     [days_until_stockout]
  Probability of shortage: [stockout_probability_percent]%
  Action deadline:         [action_deadline]

  Alternative suppliers:
  * [name] ([country]) — reliability [score], lead time [days] days

STEP 4: Call financial_impact_agent
→ Pass ALL 9 combos in one message:
  "Calculate financial impact for these combos:
   [list each combo with drug_name, destination_country,
    population_served, disruption_duration_days=60,
    suppliers list]"
→ financial_impact_agent will return ranked suppliers with ROI

STEP 5: For each combo call pick_best_supplier_for_combo(
    drug_name, country=destination_country,
    financial_rankings=[ranked suppliers from financial agent])
→ Present:

  ─────────────────────────────────────
  SUPPLIER SELECTION: [drug] | [country]
  ─────────────────────────────────────
  * [supplier] — ROI: [X]/100, Lead: [Y]/100, Reliability: [Z]/100 → [score]/100
  ✅ SELECTED: [name] ([country]) — Score: [score]/100

STEP 6: Call procurement_agent
→ Pass ALL selections in one message:
  "File purchase orders for these combos:
   [list each combo with all supplier details]"

STEP 7: Present final summary:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 2 COMPLETE — SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Drug | Country | Supplier | Qty | Cost | Order ID
(all 9 rows)

Total intervention cost: $[sum]
Total cost avoided: $[sum]
Orders filed: 9
All orders require human approval.

RULES:
1. Always complete all 9 combos
2. Never skip a combo
3. Always show financial analysis before selection
4. Always confirm order IDs""",
    tools=[
        get_top_3_critical_drugs,
        get_top_3_affected_countries,
        calculate_stockout_forecast,
        pick_best_supplier_for_combo,
        AgentTool(agent=financial_impact_agent),
        AgentTool(agent=procurement_agent),
    ],
)