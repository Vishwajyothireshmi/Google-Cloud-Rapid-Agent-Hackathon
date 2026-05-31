# ruff: noqa
import os
import datetime
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types
from integrations.arize_client import trace_step


# ══════════════════════════════════════════════════════
# FINANCIAL IMPACT AGENT TOOLS
# ══════════════════════════════════════════════════════

def calculate_financial_impact_per_combo(
        drug_name: str,
        country: str,
        population_served: int,
        disruption_duration_days: int,
        suppliers: list[dict]) -> dict:
    """Calculate full financial impact for a drug×country combo.
    Calculates stockout cost + switching cost + ROI for each supplier.
    Args:
        drug_name: Drug at risk
        country: Affected country
        population_served: Population depending on drug
        disruption_duration_days: How long shortage lasts
        suppliers: List of alternative suppliers to evaluate
    Returns:
        Full financial analysis with ranked suppliers
    """
    trace_step("financial_impact", {
        "drug": drug_name,
        "country": country
    })

    affected_patients = int(population_served * 0.15)
    daily_cost_per_patient = 45

    # Cost of doing nothing
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

    # Cost factors by country
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

        ranked.append({
            "supplier_id": s.get("supplier_id", ""),
            "supplier_name": supplier_name,
            "supplier_country": supplier_country,
            "reliability_score": reliability,
            "lead_time_days": lead_time,
            "quantity_needed": quantity_needed,
            "unit_cost_usd": round(unit_cost, 2),
            "switching_cost_usd": round(switching_cost, 2),
            "logistics_cost_usd": round(logistics_cost, 2),
            "total_cost_usd": round(total_cost, 2),
            "cost_of_inaction_usd": round(total_stockout_cost, 2),
            "projected_savings_usd": round(savings, 2),
            "roi_percent": round(roi, 1),
            "recommendation": (
                "STRONGLY RECOMMENDED" if roi > 200
                else "RECOMMENDED" if roi > 100
                else "CONSIDER" if roi > 0
                else "NOT RECOMMENDED"
            )
        })

    ranked.sort(key=lambda x: x["roi_percent"], reverse=True)

    return {
        "drug_name": drug_name,
        "country": country,
        "population_served": population_served,
        "affected_patients": affected_patients,
        "disruption_duration_days": disruption_duration_days,
        "cost_of_stockout_usd": round(total_stockout_cost, 2),
        "direct_health_cost_usd": round(direct_cost, 2),
        "emergency_care_cost_usd": round(emergency_cost, 2),
        "productivity_loss_usd": round(productivity_loss, 2),
        "ranked_suppliers": ranked,
        "best_supplier_country": (
            ranked[0]["supplier_country"] if ranked else ""
        ),
        "best_roi_percent": (
            ranked[0]["roi_percent"] if ranked else 0
        ),
        "best_savings_usd": (
            ranked[0]["projected_savings_usd"] if ranked else 0
        )
    }


# ══════════════════════════════════════════════════════
# FINANCIAL IMPACT AGENT
# ══════════════════════════════════════════════════════

financial_impact_agent = Agent(
    name="financial_impact_agent",
    description="Calculates financial impact per drug×country combo including stockout cost, switching cost and ROI for each supplier. Returns ranked suppliers to stock forecasting agent.",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are a Financial Impact Agent specializing
in healthcare supply chain economics.

You receive a list of drug×country combos with supplier options
from the stock_forecasting_agent.

For EACH drug×country combo:

STEP 1: Calculate financial impact
→ Call calculate_financial_impact_per_combo(
    drug_name, country, population_served,
    disruption_duration_days=60, suppliers)

STEP 2: Present results in this EXACT format:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FINANCIAL ANALYSIS: [drug_name] | [country]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Cost of doing nothing (stockout):
  Direct health cost:    $[direct_health_cost_usd]
  Emergency care:        $[emergency_care_cost_usd]
  Productivity loss:     $[productivity_loss_usd]
  ─────────────────────────────────────
  TOTAL INACTION COST:   $[cost_of_stockout_usd]

Supplier options ranked by ROI:
  1. [supplier_name] ([supplier_country])
     Switching cost:      $[total_cost_usd]
     Projected savings:   $[projected_savings_usd]
     ROI:                 [roi_percent]%
     → [recommendation]

  2. [supplier_name] ([supplier_country])
     Switching cost:      $[total_cost_usd]
     Projected savings:   $[projected_savings_usd]
     ROI:                 [roi_percent]%
     → [recommendation]

STEP 3: After calculating all combos present
your complete results clearly with all numbers.
The calling agent will automatically receive
your response — do not try to call any other agent.

Never summarize — show full numbers for every combo.""",
    tools=[
        calculate_financial_impact_per_combo,
    ],
)