# ruff: noqa
import os
import datetime
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types
from integrations.mongodb_client import get_db
from integrations.arize_client import trace_step


# ══════════════════════════════════════════════════════
# PROCUREMENT AGENT TOOLS
# ══════════════════════════════════════════════════════

def file_purchase_order_per_combo(
        drug_name: str,
        api_name: str,
        destination_country: str,
        population_served: int,
        supplier_id: str,
        supplier_name: str,
        supplier_country: str,
        unit_cost_usd: float,
        lead_time_days: int,
        roi_percent: float,
        stockout_probability_percent: int,
        combined_score: float) -> dict:
    """File a draft purchase order for one drug×country combo.
    Calculates quantity using (population × 15%) / 365 × 90 days.
    Args:
        drug_name: Drug being ordered
        api_name: Active ingredient
        destination_country: Country receiving the order
        population_served: Population of health system
        supplier_id: ID of chosen supplier
        supplier_name: Name of chosen supplier
        supplier_country: Country of chosen supplier
        unit_cost_usd: Cost per unit in USD
        lead_time_days: Expected delivery time in days
        roi_percent: ROI of this intervention
        stockout_probability_percent: Stockout probability avoided
        combined_score: Combined decision score
    Returns:
        Purchase order confirmation with order ID
    """
    trace_step("file_order", {
        "drug": drug_name,
        "country": destination_country
    })
    db = get_db()

    # Get current stock
    inventory = db.inventory.find_one(
        {"drug_name": drug_name},
        {"_id": 0}
    )
    current_stock = inventory.get(
        "current_stock", 0
    ) if inventory else 0

    # Formula: (population × 15%) / 365 × 90 days
    affected_patients = int(population_served * 0.15)
    daily_consumption = max(1, affected_patients // 365)
    days_needed = 90
    base_quantity = max(
        0, (daily_consumption * days_needed) - current_stock
    )
    # 15% safety buffer
    final_quantity = int(base_quantity * 1.15)

    total_cost = final_quantity * unit_cost_usd
    expected_delivery = (
        datetime.datetime.utcnow() +
        datetime.timedelta(days=lead_time_days)
    ).strftime("%Y-%m-%d")

    order = {
        "order_type":                    "draft_purchase_order",
        "drug_name":                     drug_name,
        "api_name":                      api_name,
        "destination_country":           destination_country,
        "supplier_id":                   supplier_id,
        "supplier_name":                 supplier_name,
        "supplier_country":              supplier_country,
        "population_served":             population_served,
        "affected_patients":             affected_patients,
        "daily_consumption":             daily_consumption,
        "base_quantity":                 base_quantity,
        "safety_buffer_15pct":           int(base_quantity * 0.15),
        "final_quantity_units":          final_quantity,
        "unit_cost_usd":                 round(unit_cost_usd, 2),
        "total_cost_usd":                round(total_cost, 2),
        "lead_time_days":                lead_time_days,
        "expected_delivery":             expected_delivery,
        "roi_percent":                   roi_percent,
        "stockout_probability_avoided":  stockout_probability_percent,
        "combined_decision_score":       combined_score,
        "formula_used": (
            f"({population_served} × 15%) / 365 × {days_needed} days"
            f" = {base_quantity} + 15% buffer = {final_quantity} units"
        ),
        "status":                        "draft",
        "requires_human_approval":       True,
        "created_at":                    datetime.datetime.utcnow(),
        "created_by":                    "procurement_agent"
    }

    result = db.procurement_orders.insert_one(order)

    return {
        "order_id":           str(result.inserted_id),
        "drug_name":          drug_name,
        "api_name":           api_name,
        "destination_country": destination_country,
        "supplier_name":      supplier_name,
        "supplier_country":   supplier_country,
        "population_served":  population_served,
        "affected_patients":  affected_patients,
        "daily_consumption":  daily_consumption,
        "base_quantity":      base_quantity,
        "safety_buffer":      int(base_quantity * 0.15),
        "final_quantity":     final_quantity,
        "formula":            order["formula_used"],
        "unit_cost_usd":      round(unit_cost_usd, 2),
        "total_cost_usd":     round(total_cost, 2),
        "expected_delivery":  expected_delivery,
        "roi_percent":        roi_percent,
        "status":             "draft_filed",
        "message": (
            f"✅ Order {str(result.inserted_id)} filed. "
            f"Requires human approval before execution."
        )
    }


# ══════════════════════════════════════════════════════
# PROCUREMENT AGENT
# ══════════════════════════════════════════════════════

procurement_agent = Agent(
    name="procurement_agent",
    description="Files one draft purchase order per drug×country combo to MongoDB with full quantity calculation shown",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are a Procurement Agent responsible for
filing purchase orders — one per drug×country combo.

You receive a list of drug×country combos with the chosen
best supplier for each from stock_forecasting_agent.

For EACH drug×country combo:

STEP 1: File purchase order
→ Call file_purchase_order_per_combo() with all details

STEP 2: Present confirmation in this EXACT format:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROCUREMENT ORDER: [drug_name] | [destination_country]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Supplier:  [supplier_name] ([supplier_country])
API:       [api_name]

Quantity Calculation:
  Formula:  ([population_served] × 15%) / 365 × 90 days
  Patients: [affected_patients]
  Daily use: [daily_consumption] units/day
  Base qty:  [base_quantity] units
  + 15% buffer: [safety_buffer] units
  ─────────────────────────────────────
  FINAL ORDER: [final_quantity] units

Financials:
  Unit cost:         $[unit_cost_usd]
  Total cost:        $[total_cost_usd]
  ROI of decision:   [roi_percent]%

Delivery:
  Lead time:         [lead_time_days] days
  Expected delivery: [expected_delivery]

⚠️  ORDER ID: [order_id]
⚠️  Status: Draft — requires human approval

After filing all orders present a summary table:
Drug | Country | Supplier | Qty | Cost | Delivery | Order ID""",
    tools=[
        file_purchase_order_per_combo,
    ],
)