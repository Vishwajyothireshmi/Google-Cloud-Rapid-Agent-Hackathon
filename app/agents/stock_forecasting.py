# ruff: noqa
import os
import datetime
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.tools.agent_tool import AgentTool
from google.genai import types
from integrations.mongodb_client import get_db
from integrations.arize_client import trace_step

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
        disrupted_country: Country where disruption occurred
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


def calculate_financial_and_pick_best(
        drug_name: str,
        api_name: str,
        destination_country: str,
        population_served: int,
        disruption_duration_days: int,
        suppliers: list[dict]) -> dict:
    """Calculate financial impact AND pick best supplier in one step.
    Ensures real ROI is always used for supplier selection.
    Args:
        drug_name: Drug at risk
        api_name: Active ingredient
        destination_country: Affected country
        population_served: Population served (total not patients)
        disruption_duration_days: Duration of disruption in days
        suppliers: Alternative suppliers list from stockout forecast
    Returns:
        Financial analysis + best supplier selection with real ROI
    """
    trace_step("financial_and_pick", {
        "drug": drug_name,
        "country": destination_country
    })

    if not suppliers:
        return {
            "error": f"No suppliers for {drug_name} | {destination_country}"
        }

    # Calculate stockout cost
    affected_patients = int(population_served * 0.15)
    daily_cost_per_patient = 4.50

    direct_cost = (
        daily_cost_per_patient *
        affected_patients *
        disruption_duration_days
    )
    emergency_cost = direct_cost * 0.30
    productivity_loss = direct_cost * 0.20
    total_stockout_cost = (
        direct_cost + emergency_cost + productivity_loss
    )

    # Cost factors by supplier country
    country_cost_factor = {
        "Germany": 1.15, "Switzerland": 1.20,
        "Netherlands": 1.12, "Italy": 1.08,
        "Spain": 1.05, "Japan": 1.18,
        "USA": 1.25, "South Korea": 1.10,
        "China": 0.85, "India": 0.80,
    }

    days_needed = 90
    daily_consumption = max(1, affected_patients // 365)
    quantity_needed = daily_consumption * days_needed

    # Score each supplier
    ranked = []
    for s in suppliers:
        supplier_country = s.get("country", "Unknown")
        supplier_name = s.get("name", supplier_country)
        lead_time = s.get("lead_time_days", 30)
        reliability = s.get("reliability_score", 0.8)

        base_cost = 2.50
        factor = country_cost_factor.get(supplier_country, 1.0)
        unit_cost = base_cost * factor
        if lead_time < 20:
            unit_cost *= 1.10

        switching_cost = unit_cost * quantity_needed
        logistics_cost = switching_cost * 0.08
        total_cost = switching_cost + logistics_cost
        savings = total_stockout_cost - total_cost
        roi = (savings / total_cost * 100) if total_cost > 0 else 0

        # Combined score
        roi_score = min(100, roi / 100)
        #roi_score = min(100, roi / 3)
        lead_time_score = max(0, 100 - lead_time)
        reliability_score = reliability * 100
        combined = (
            roi_score * 0.33 +
            lead_time_score * 0.33 +
            reliability_score * 0.33
        )

        ranked.append({
            "supplier_id": s.get("supplier_id", ""),
            "supplier_name": supplier_name,
            "supplier_country": supplier_country,
            "reliability_score": reliability,
            "lead_time_days": lead_time,
            "unit_cost_usd": round(unit_cost, 2),
            "total_cost_usd": round(total_cost, 2),
            "cost_of_inaction_usd": round(total_stockout_cost, 2),
            "projected_savings_usd": round(savings, 2),
            "roi_percent": round(roi, 1),
            "roi_score": round(roi_score, 2),
            "lead_time_score": round(lead_time_score, 2),
            "reliability_score_normalized": round(reliability_score, 2),
            "combined_score": round(combined, 2),
            "recommendation": (
                "STRONGLY RECOMMENDED" if roi > 200
                else "RECOMMENDED" if roi > 100
                else "CONSIDER" if roi > 0
                else "NOT RECOMMENDED"
            )
        })

    ranked.sort(key=lambda x: x["combined_score"], reverse=True)
    best = ranked[0]

    return {
        "drug_name": drug_name,
        "api_name": api_name,
        "destination_country": destination_country,
        "population_served": population_served,
        "patients_at_risk": affected_patients,
        "cost_of_inaction_usd": round(total_stockout_cost, 2),
        "direct_health_cost_usd": round(direct_cost, 2),
        "emergency_care_cost_usd": round(emergency_cost, 2),
        "productivity_loss_usd": round(productivity_loss, 2),
        "all_supplier_options": ranked,
        "best_supplier": best,
        "selection_reasoning": (
            f"Selected {best['supplier_name']} ({best['supplier_country']}) "
            f"— Combined: {best['combined_score']}/100 "
            f"(ROI: {best['roi_score']:.0f}/100 [{best['roi_percent']:.0f}%], "
            f"Lead time: {best['lead_time_score']:.0f}/100 [{best['lead_time_days']} days], "
            f"Reliability: {best['reliability_score_normalized']:.0f}/100 "
            f"[{best['reliability_score']}])"
        )
    }


# ══════════════════════════════════════════════════════
# STOCK FORECASTING AGENT
# ══════════════════════════════════════════════════════

stock_forecasting_agent = Agent(
    name="stock_forecasting_agent",
    description="Coordinates full supply chain risk analysis — identifies top 3 critical drugs × top 3 countries, calculates financial impact, picks best supplier, triggers procurement orders",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Stock Forecasting Agent — coordinator
of Phase 2 supply chain risk analysis.

You receive a message with:
- drug_names: comma separated drug names
- countries: comma separated affected countries
- disrupted_country: country where disruption occurred

Parse these and follow ALL steps strictly.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STOCK FORECASTING ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1: Get top 3 critical drugs
→ Call get_top_3_critical_drugs(drug_names=[parsed list])
→ Present:
  Top 3 Critical Drugs (lowest stock):
  1. [drug_name] ([api_name])
  2. [drug_name] ([api_name])
  3. [drug_name] ([api_name])

STEP 2: For each drug get top 3 affected countries
→ Call get_top_3_affected_countries(
    drug_name, countries=[parsed list])
→ Note country + population_served for each

STEP 3: For each drug×country combo (9 total):
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

STEP 4: For each combo that has alternative_suppliers
→ Call calculate_financial_and_pick_best(
    drug_name, api_name, destination_country,
    population_served, disruption_duration_days=60,
    suppliers=[alternative_suppliers from Step 3])
→ Present:

  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  FINANCIAL ANALYSIS: [drug] | [country]
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Cost of doing nothing:  $[cost_of_inaction_usd]
    Direct health cost:   $[direct_health_cost_usd]
    Emergency care:       $[emergency_care_cost_usd]
    Productivity loss:    $[productivity_loss_usd]

  Supplier options ranked:
  1. [supplier_name] ([country])
     ROI: [roi_percent]% | Cost: $[total_cost_usd]
     Savings: $[projected_savings_usd]
     → [recommendation]
  2. [supplier_name] ([country])
     ROI: [roi_percent]% | Cost: $[total_cost_usd]
     → [recommendation]

  ─────────────────────────────────────
  SUPPLIER SELECTION: [drug] | [country]
  ─────────────────────────────────────
  Scoring:
  * [supplier] — ROI: [roi_score]/100, Lead: [lead_time_score]/100, Reliability: [reliability_score_normalized]/100 → [combined_score]/100
  ✅ SELECTED: [supplier_name] ([supplier_country])
     Combined score: [combined_score]/100
     Reason: [selection_reasoning]

STEP 5: After ALL 9 combos are processed
→ Call procurement_agent with this message:
"File purchase orders for these combos:
[For each combo with a best_supplier:]
- drug_name: [drug_name]
  api_name: [api_name]
  destination_country: [destination_country]
  population_served: [patients_at_risk from result]
  supplier_id: [best_supplier.supplier_id]
  supplier_name: [best_supplier.supplier_name]
  supplier_country: [best_supplier.supplier_country]
  unit_cost_usd: [best_supplier.unit_cost_usd]
  lead_time_days: [best_supplier.lead_time_days]
  roi_percent: [best_supplier.roi_percent]
  stockout_probability_percent: [stockout_probability_percent]
  combined_score: [best_supplier.combined_score]"

→ WAIT for procurement_agent to complete and return
  all order IDs before presenting the summary
→ Use the actual order_id from procurement_agent response
→ NEVER use [ORDER_ID_NOT_AVAILABLE] in the summary
→ Only present PHASE 2 COMPLETE after all orders confirmed

STEP 6: Present final summary:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PHASE 2 COMPLETE — SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Drug | Country | Supplier | ROI% | Cost | Order ID
(one row per combo)

Total intervention cost: $[sum]
Total cost avoided:      $[sum of projected_savings_usd]
Orders filed: [count]
All orders require human approval.

CRITICAL RULES:
1. ALWAYS call calculate_financial_and_pick_best for every combo
2. NEVER skip financial analysis — it provides real ROI
3. ALWAYS call procurement_agent after ALL combos
4. Skip combos where alternative_suppliers is empty
5. Complete ALL steps before finishing""",
    tools=[
        get_top_3_critical_drugs,
        get_top_3_affected_countries,
        calculate_stockout_forecast,
        calculate_financial_and_pick_best,
        AgentTool(agent=procurement_agent),
    ],
)