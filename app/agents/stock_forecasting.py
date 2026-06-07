# ruff: noqa
import os
import datetime
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types
from integrations.mongodb_client import get_db
from integrations.arize_client import trace_step


# ── Tool 1: two-stage aggregation ────────────────────────────────────────────
def get_top_3_critical_drugs(drug_names: list[str], countries: list[str]) -> list:
    """Get top 3 most critical drugs by avg supply across importing countries."""
    trace_step("top_3_drugs", {"count": len(drug_names)})
    db = get_db()
    pipeline = [
        {"$match": {"drug_name": {"$in": drug_names}}},
        {"$group": {
            "_id": {"drug_name": "$drug_name", "country": "$country"},
            "avg_supply_in_country": {"$avg": "$days_of_supply"}
        }},
        {"$match": {"_id.country": {"$in": countries}}},
        {"$group": {
            "_id": "$_id.drug_name",
            "avg_supply_across_countries": {"$avg": "$avg_supply_in_country"}
        }},
        {"$sort": {"avg_supply_across_countries": 1}},
        {"$limit": 3},
        {"$project": {"_id": 0, "drug_name": "$_id", "avg_supply_across_countries": 1}}
    ]
    results = list(db.inventory.aggregate(pipeline))

    enriched = []
    for r in results:
        drug_info = db.drug_ingredients.find_one(
            {"drug_name": r["drug_name"]},
            {"_id": 0, "active_ingredient": 1, "category": 1}
        )
        enriched.append({
            "drug_name":                   r["drug_name"],
            "avg_supply_across_countries": r["avg_supply_across_countries"],
            "api_name":                    drug_info.get("active_ingredient", "Unknown") if drug_info else "Unknown",
            "category":                    drug_info.get("category", "Unknown") if drug_info else "Unknown"
        })
    return enriched


# ── Tool 2: $group + $sum aggregation ────────────────────────────────────────
def get_top_3_affected_countries(drug_name: str, countries: list[str]) -> list:
    """Get top 3 most affected countries for a drug by total summed population."""
    trace_step("top_3_countries", {"drug": drug_name})
    db = get_db()
    pipeline = [
        {"$match": {
            "country": {"$in": countries},
            "critical_drugs": {"$in": [drug_name]}
        }},
        {"$group": {
            "_id": "$country",
            "population_served":       {"$sum": "$population_served"},
            "healthcare_buffer_weeks": {"$min": "$healthcare_buffer_weeks"}
        }},
        {"$sort": {"population_served": -1}},
        {"$limit": 3},
        {"$project": {
            "_id": 0,
            "country":                 "$_id",
            "population_served":       1,
            "healthcare_buffer_weeks": 1
        }}
    ]
    return list(db.health_systems.aggregate(pipeline))


# ── Tool 3: suppliers query + stockout calc ───────────────────────────────────
def calculate_stockout_forecast(
        drug_name: str,
        api_name: str,
        disrupted_country: str,
        destination_country: str,
        population_served: int,
        avg_supply_days: float) -> dict:
    """Fetch alternative suppliers and calculate stockout probability."""
    trace_step("stockout_forecast", {"drug": drug_name, "country": destination_country})
    db = get_db()

    disruption = 60
    if disruption >= avg_supply_days:
        probability = 95
    elif disruption >= avg_supply_days * 0.7:
        probability = 78
    elif disruption >= avg_supply_days * 0.5:
        probability = 55
    else:
        probability = 25

    days_until_critical = max(0, avg_supply_days - 14 - 7)
    action_deadline = (
        datetime.datetime.utcnow() +
        datetime.timedelta(days=max(1, days_until_critical))
    ).strftime("%Y-%m-%d")

    suppliers = list(db.suppliers.find(
        {
            "api_name": api_name,
            "country": {"$nin": [disrupted_country]},
            "type": "API_manufacturer",
            "export_status": "active"
        },
        {"_id": 0, "supplier_id": 1, "name": 1,
         "country": 1, "reliability_score": 1, "lead_time_days": 1}
    ).sort("reliability_score", -1).limit(5))

    return {
        "drug_name":                    drug_name,
        "api_name":                     api_name,
        "destination_country":          destination_country,
        "population_served":            population_served,
        "patients_at_risk":             int(population_served * 0.15),
        "avg_supply_days":              avg_supply_days,
        "stockout_probability_percent": probability,
        "action_deadline":              action_deadline,
        "suppliers":                    suppliers
    }


# ── Tool 4: pure math — no DB call ───────────────────────────────────────────
def filter_top3_suppliers_by_lead_reliability(
        drug_name: str,
        country: str,
        suppliers: list[dict]) -> dict:
    """Filter and rank suppliers by lead time + reliability only."""
    trace_step("filter_suppliers", {"drug": drug_name, "country": country})

    scored = []
    for s in suppliers:
        lead_time   = s.get("lead_time_days", 60)
        reliability = s.get("reliability_score", 0.5)

        lead_score        = max(0, 100 - lead_time)
        reliability_score = reliability * 100
        combined          = (lead_score * 0.50) + (reliability_score * 0.50)

        scored.append({
            "supplier_id":                  s.get("supplier_id", ""),
            "supplier_name":                s.get("name", "Unknown"),
            "supplier_country":             s.get("country", "Unknown"),
            "lead_time_days":               lead_time,
            "reliability_score":            reliability,
            "lead_score":                   round(lead_score, 2),
            "reliability_score_normalized": round(reliability_score, 2),
            "lead_reliability_combined":    round(combined, 2)
        })

    scored.sort(key=lambda x: x["lead_reliability_combined"], reverse=True)
    top3 = scored[:3]

    return {
        "drug_name":          drug_name,
        "country":            country,
        "top3_suppliers":     top3,
        "selection_criteria": "Lead time (50%) + Reliability (50%)"
    }


stock_forecasting_agent = Agent(
    name="stock_forecasting_agent",
    description="Identifies top 3 critical drugs, top 3 affected countries, calculates stockout forecasts, and filters top 3 suppliers per combo. Returns all results to main agent.",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Stock Forecasting Agent.

STEP 1: Call get_top_3_critical_drugs(drug_names, countries)
  drug_names: from main agent input
  countries: importing countries from main agent input

Print immediately:
**Critical Drugs Identified:**
1. [drug_name] — avg supply: [avg_supply_across_countries] days
2. [drug_name] — avg supply: [avg_supply_across_countries] days
3. [drug_name] — avg supply: [avg_supply_across_countries] days

STEP 2: For each of the 3 drugs call get_top_3_affected_countries(drug_name, countries)
  countries: importing countries from main agent input
  Returns top 3 countries by total population for that drug.
  This gives 9 combos total (3 drugs × 3 countries).

STEP 3: For each of the 9 combos call calculate_stockout_forecast(
    drug_name=drug_name,
    api_name=api_name from Step 1,
    disrupted_country=disrupted_country,
    destination_country=country from Step 2,
    population_served=population_served from Step 2,
    avg_supply_days=avg_supply_across_countries from Step 1)

STEP 4: For each combo call filter_top3_suppliers_by_lead_reliability(
    drug_name=drug_name,
    country=destination_country,
    suppliers=suppliers from Step 3 result)

Present each combo:

**Drug:** [drug_name] | **Country:** [country]
- Population at risk: [patients_at_risk]
- Days until stockout: [avg_supply_days]
- Probability of shortage: [stockout_probability_percent]%
- Action deadline: [action_deadline]

Top 3 suppliers (lead time + reliability):
1. [supplier_name] ([supplier_country]) — reliability [reliability_score], lead time [lead_time_days] days
2. [supplier_name] ([supplier_country]) — reliability [reliability_score], lead time [lead_time_days] days
3. [supplier_name] ([supplier_country]) — reliability [reliability_score], lead time [lead_time_days] days

---

STEP 5: Return complete summary to main agent:
"FORECASTING COMPLETE. Here are all combos with top 3 suppliers:

Combo 1: [drug_name] | [country]
  patients_at_risk: [number]
  stockout_probability: [percent]%
  top3_suppliers: [list with supplier_id, supplier_name, supplier_country, lead_time_days, reliability_score]

Combo 2: ...
[all 9 combos]"

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
    ],
)