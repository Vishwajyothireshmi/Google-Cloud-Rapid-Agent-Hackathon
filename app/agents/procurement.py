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

# ── MongoDB MCP for Procurement Agent ─────────────────────────────────────────
procurement_mongodb_toolset = McpToolset(
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
    Calculates quantity using (patients / 365) × 90 days.
    Note: population_served passed here is already patients_at_risk.
    Args:
        drug_name: Drug being ordered
        api_name: Active ingredient
        destination_country: Country receiving the order
        population_served: Patients at risk (already 15% of population)
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

    patients_at_risk = population_served
    daily_consumption = max(1, patients_at_risk // 365)
    days_needed = 90

    inventory = db.inventory.find_one(
        {"drug_name": drug_name},
        {"_id": 0}
    )
    current_stock = inventory.get(
        "current_stock", 0
    ) if inventory else 0

    base_quantity = max(
        0, (daily_consumption * days_needed) - current_stock
    )
    final_quantity = int(base_quantity * 1.15)

    total_cost = final_quantity * unit_cost_usd
    expected_delivery = (
        datetime.datetime.utcnow() +
        datetime.timedelta(days=lead_time_days)
    ).strftime("%Y-%m-%d")

    order = {
        "order_type":                   "draft_purchase_order",
        "drug_name":                    drug_name,
        "api_name":                     api_name,
        "destination_country":          destination_country,
        "supplier_id":                  supplier_id,
        "supplier_name":                supplier_name,
        "supplier_country":             supplier_country,
        "patients_at_risk":             patients_at_risk,
        "daily_consumption":            daily_consumption,
        "base_quantity":                base_quantity,
        "safety_buffer_15pct":          int(base_quantity * 0.15),
        "final_quantity_units":         final_quantity,
        "unit_cost_usd":                round(unit_cost_usd, 2),
        "total_cost_usd":               round(total_cost, 2),
        "lead_time_days":               lead_time_days,
        "expected_delivery":            expected_delivery,
        "roi_percent":                  roi_percent,
        "stockout_probability_avoided": stockout_probability_percent,
        "combined_decision_score":      combined_score,
        "formula_used": (
            f"({patients_at_risk} patients) / 365 × {days_needed} days"
            f" = {base_quantity} + 15% buffer = {final_quantity} units"
        ),
        "status":                       "draft",
        "requires_human_approval":      True,
        "created_at":                   datetime.datetime.utcnow(),
        "created_by":                   "procurement_agent"
    }

    result = db.procurement_orders.insert_one(order)
    order_id = str(result.inserted_id)

    return {
        "order_id":            order_id,
        "drug_name":           drug_name,
        "api_name":            api_name,
        "destination_country": destination_country,
        "supplier_name":       supplier_name,
        "supplier_country":    supplier_country,
        "quantity":            final_quantity,
        "unit_cost_usd":       round(unit_cost_usd, 2),
        "total_cost_usd":      round(total_cost, 2),
        "lead_time_days":      lead_time_days,
        "expected_delivery":   expected_delivery,
        "roi_percent":         roi_percent,
        "combined_score":      combined_score
    }


# ══════════════════════════════════════════════════════
# PROCUREMENT AGENT
# ══════════════════════════════════════════════════════

procurement_agent = Agent(
    name="procurement_agent",
    description="Files draft purchase orders to MongoDB for each drug×country combo. Has direct MongoDB MCP access for order verification and ad-hoc queries.",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are a Procurement Agent responsible for
filing purchase orders — one per drug×country combo.

You receive drug×country combos with chosen suppliers.
Use the custom tool to file orders.
Use MongoDB MCP tools if you need to verify orders
or run additional database queries.

For EACH combo:
→ Call file_purchase_order_per_combo() with all details

After ALL orders are filed return a JSON summary:

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
      "expected_delivery": "",
      "roi_percent": 0,
      "combined_score": 0
    }
  ]
}

RULES:
- Call the tool for EVERY combo
- Collect ALL order_ids from tool responses
- Return ONLY the JSON summary after all calls complete
- Do not skip any combo""",
    tools=[
        file_purchase_order_per_combo,
        procurement_mongodb_toolset,
    ],
)