# ruff: noqa
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types
from integrations.mongodb_client import get_db
from integrations.arize_client import trace_step


def calculate_financial_impact_per_combo(
        drug_name: str,
        country: str,
        population_served: int,
        disruption_duration_days: int,
        suppliers: list[dict]) -> dict:
    """Calculate ROI for each supplier for a drug×country combo.
    Args:
        drug_name: Drug at risk
        country: Affected country
        population_served: Population depending on drug
        disruption_duration_days: How long shortage lasts
        suppliers: Top 3 suppliers with lead_time_days,
                   reliability_score, supplier_name, supplier_country
    Returns:
        ROI and cost analysis per supplier
    """
    trace_step("financial_impact", {"drug": drug_name, "country": country})
    db = get_db()

    affected_patients = int(population_served * 0.15)
    daily_cost_per_patient = 4.50

    direct_cost = (
        daily_cost_per_patient *
        affected_patients *
        disruption_duration_days
    )
    emergency_cost = direct_cost * 0.30
    productivity_loss = direct_cost * 0.20
    total_stockout_cost = direct_cost + emergency_cost + productivity_loss

    inventory = db.inventory.find_one(
        {"drug_name": drug_name},
        {"_id": 0, "daily_consumption": 1}
    )
    daily_consumption = inventory.get(
        "daily_consumption", 100
    ) if inventory else 100

    country_cost_factor = {
        "Germany": 1.15, "Switzerland": 1.20,
        "Netherlands": 1.12, "Italy": 1.08,
        "Spain": 1.05, "Japan": 1.18,
        "USA": 1.25, "South Korea": 1.10,
        "China": 0.85, "India": 0.80,
    }

    days_needed = 90
    quantity_needed = daily_consumption * days_needed

    ranked = []
    for s in suppliers:
        supplier_country = (
            s.get("supplier_country") or
            s.get("country", "Unknown")
        )
        supplier_name = (
            s.get("supplier_name") or
            s.get("name", "Unknown")
        )
        supplier_id = s.get("supplier_id", "")
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

        ranked.append({
            "supplier_id":           supplier_id,
            "supplier_name":         supplier_name,
            "supplier_country":      supplier_country,
            "reliability_score":     reliability,
            "lead_time_days":        lead_time,
            "unit_cost_usd":         round(unit_cost, 2),
            "total_cost_usd":        round(total_cost, 2),
            "cost_of_inaction_usd":  round(total_stockout_cost, 2),
            "projected_savings_usd": round(savings, 2),
            "roi_percent":           round(roi, 1),
            "recommendation": (
                "STRONGLY RECOMMENDED" if roi > 200
                else "RECOMMENDED" if roi > 100
                else "CONSIDER" if roi > 0
                else "NOT RECOMMENDED"
            )
        })

    ranked.sort(key=lambda x: x["roi_percent"], reverse=True)

    return {
        "drug_name":               drug_name,
        "country":                 country,
        "affected_patients":       affected_patients,
        "daily_consumption":       daily_consumption,
        "cost_of_stockout_usd":    round(total_stockout_cost, 2),
        "direct_health_cost_usd":  round(direct_cost, 2),
        "emergency_care_cost_usd": round(emergency_cost, 2),
        "productivity_loss_usd":   round(productivity_loss, 2),
        "ranked_suppliers":        ranked
    }


financial_impact_agent = Agent(
    name="financial_impact_agent",
    description="Calculates ROI for top 3 suppliers per drug×country combo. Returns financial rankings to main agent.",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Financial Impact Agent.
You receive combos in plain text like:
"combo 1: drug=Glucophage, country=Nigeria, population=5200000,
  disruption_days=60, suppliers: Lonza Switzerland (Switzerland)
  lead=19 reliability=0.98, Recordati Italy (Italy) lead=25 reliability=0.94
combo 2: drug=Ciplox, country=Pakistan, population=3200000,
  disruption_days=60, suppliers: DSM Netherlands (Netherlands)
  lead=16 reliability=0.95, Zambon Italy (Italy) lead=16 reliability=0.93"

For EACH combo:
1. Parse drug_name, country, population_served, suppliers
2. Call calculate_financial_impact_per_combo(
    drug_name=[parsed drug],
    country=[parsed country],
    population_served=[parsed population as integer],
    disruption_duration_days=60,
    suppliers=[list of dicts:
      {"supplier_name": [name], "supplier_country": [country],
       "lead_time_days": [days as integer],
       "reliability_score": [score as float]}])

Present results as you calculate each combo:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINANCIAL ANALYSIS: [drug] | [country]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Cost of doing nothing: $[cost_of_stockout_usd]
  Direct health cost:  $[direct_health_cost_usd]
  Emergency care:      $[emergency_care_cost_usd]
  Productivity loss:   $[productivity_loss_usd]

Suppliers ranked by ROI:
1. [supplier_name] ([supplier_country])
   ROI: [roi_percent]% | Cost: $[total_cost_usd]
   Savings: $[projected_savings_usd] → [recommendation]
2. [supplier_name] ([supplier_country])
   ROI: [roi_percent]% | Cost: $[total_cost_usd]
   → [recommendation]

After ALL combos present structured summary:
FINANCIAL COMPLETE.
combo: [drug] | [country]
  cost_of_stockout_usd: [amount]
  ranked_suppliers:
    - supplier_id: [id], supplier_name: [name],
      supplier_country: [country], roi_percent: [roi],
      lead_time_days: [days], reliability_score: [score],
      total_cost_usd: [cost], projected_savings_usd: [savings]
[repeat for all combos]

RULES:
- Parse plain text input — do not expect JSON
- Calculate for ALL combos received
- Never call any other agent
- Return complete structured summary to main agent""",
    tools=[
        calculate_financial_impact_per_combo,
    ],
)