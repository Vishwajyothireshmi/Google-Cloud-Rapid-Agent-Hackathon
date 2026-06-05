# ══════════════════════════════════════════════════════
# PROCUREMENT AGENT (FIXED + STRUCTURED OUTPUT)
# ══════════════════════════════════════════════════════

import os
import datetime
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types

from integrations.mongodb_client import get_db
from integrations.arize_client import trace_step


# ══════════════════════════════════════════════════════
# TOOL: CREATE PURCHASE ORDER
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

    trace_step("file_order", {
        "drug": drug_name,
        "country": destination_country
    })

    db = get_db()

    # ─────────────────────────────
    # Quantity calculation logic
    # ─────────────────────────────
    patients_at_risk = population_served
    daily_consumption = max(1, patients_at_risk // 365)
    days_needed = 90

    inventory = db.inventory.find_one(
        {"drug_name": drug_name},
        {"_id": 0}
    )

    current_stock = inventory.get("current_stock", 0) if inventory else 0

    base_quantity = max(
        0,
        (daily_consumption * days_needed) - current_stock
    )

    final_quantity = int(base_quantity * 1.15)  # 15% safety buffer

    total_cost = final_quantity * unit_cost_usd

    expected_delivery = (
        datetime.datetime.utcnow() +
        datetime.timedelta(days=lead_time_days)
    ).strftime("%Y-%m-%d")

    # ─────────────────────────────
    # MongoDB order object
    # ─────────────────────────────
    order = {
        "order_type": "draft_purchase_order",
        "drug_name": drug_name,
        "api_name": api_name,
        "destination_country": destination_country,

        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "supplier_country": supplier_country,

        "patients_at_risk": patients_at_risk,
        "daily_consumption": daily_consumption,

        "base_quantity": base_quantity,
        "final_quantity_units": final_quantity,

        "unit_cost_usd": round(unit_cost_usd, 2),
        "total_cost_usd": round(total_cost, 2),

        "lead_time_days": lead_time_days,
        "expected_delivery": expected_delivery,

        "roi_percent": roi_percent,
        "combined_score": combined_score,
        "stockout_probability_percent": stockout_probability_percent,

        "status": "draft",
        "requires_human_approval": True,
        "created_at": datetime.datetime.utcnow()
    }

    result = db.procurement_orders.insert_one(order)
    order_id = str(result.inserted_id)

    # ─────────────────────────────
    # IMPORTANT: return structured data ONLY
    # ─────────────────────────────
    return {
        "order_id": order_id,
        "drug_name": drug_name,
        "api_name": api_name,
        "destination_country": destination_country,

        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "supplier_country": supplier_country,

        "quantity": final_quantity,
        "unit_cost_usd": round(unit_cost_usd, 2),
        "total_cost_usd": round(total_cost, 2),

        "lead_time_days": lead_time_days,
        "expected_delivery": expected_delivery,

        "roi_percent": roi_percent,
        "combined_score": combined_score,
        "stockout_probability_percent": stockout_probability_percent
    }


# ══════════════════════════════════════════════════════
# PROCUREMENT AGENT
# ══════════════════════════════════════════════════════

procurement_agent = Agent(
    name="procurement_agent",
    description="Creates procurement orders and returns structured JSON output for all drug-country combos",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),

    instruction="""
You are a Procurement Agent.

You receive multiple drug×country combos with selected suppliers.

────────────────────────────────────────
YOUR TASK
────────────────────────────────────────

For EACH combo:
→ Call file_purchase_order_per_combo()

Collect ALL results.

────────────────────────────────────────
CRITICAL RULES
────────────────────────────────────────
- DO NOT generate long formatted text
- DO NOT summarize manually
- DO NOT output Markdown tables
- ONLY use tool outputs
- ALWAYS collect every tool response

────────────────────────────────────────
FINAL OUTPUT FORMAT (MANDATORY)
────────────────────────────────────────

Return ONLY this JSON:

{
  "orders": [
    {
      "drug_name": "",
      "destination_country": "",
      "supplier_name": "",
      "order_id": "",
      "quantity": 0,
      "total_cost_usd": 0,
      "lead_time_days": 0,
      "combined_score": 0
    }
  ]
}

────────────────────────────────────────
END RULE
────────────────────────────────────────
After all tool calls:
→ Combine results into "orders"
→ Return ONLY JSON (no text)
""",

    tools=[
        file_purchase_order_per_combo,
    ],
)