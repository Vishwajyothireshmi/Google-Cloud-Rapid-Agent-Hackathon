# ruff: noqa
import os
import datetime
from google.adk.agents import Agent
from google.adk.models import Gemini
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.genai import types
from mcp import StdioServerParameters
from app.integrations.mongodb_client import get_db
from app.integrations.arize_client import trace_step

procurement_mongodb_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=["-y", "mongodb-mcp-server"],
            env={"MDB_MCP_CONNECTION_STRING": os.getenv("MONGODB_URI")},
        ),
        timeout=30,
    ),
)


def file_purchase_order_per_combo(
        drug_name: str,
        api_name: str,
        destination_country: str,
        population_served: int,
        supplier_id: str,
        supplier_name: str,
        supplier_country: str,
        lead_time_days: int,
        roi_percent: float,
        stockout_probability_percent: int,
        combined_score: float) -> dict:
    """File a draft purchase order for one drug×country combo.
    Calculates unit cost from supplier country — never trusts LLM value.
    Args:
        drug_name: Drug being ordered
        api_name: Active ingredient
        destination_country: Country receiving the order
        population_served: Patients at risk
        supplier_id: ID of chosen supplier
        supplier_name: Name of chosen supplier
        supplier_country: Country of chosen supplier
        lead_time_days: Expected delivery time in days
        roi_percent: ROI of this intervention
        stockout_probability_percent: Stockout probability
        combined_score: Final combined decision score
    Returns:
        Purchase order confirmation with order ID
    """
    trace_step("file_order", {"drug": drug_name, "country": destination_country})
    db = get_db()

    # Always calculate unit cost from supplier country
    country_cost_factor = {
        "Germany": 1.15, "Switzerland": 1.20,
        "Netherlands": 1.12, "Italy": 1.08,
        "Spain": 1.05, "Japan": 1.18,
        "USA": 1.25, "South Korea": 1.10,
        "China": 0.85, "India": 0.80,
    }
    base_cost = 2.50
    factor = country_cost_factor.get(supplier_country, 1.0)
    unit_cost_usd = base_cost * factor
    if lead_time_days < 20:
        unit_cost_usd *= 1.10

    inventory = db.inventory.find_one(
        {"drug_name": drug_name},
        {"_id": 0, "daily_consumption": 1, "current_stock": 1}
    )
    daily_consumption = inventory.get(
        "daily_consumption", 100
    ) if inventory else 100
    current_stock = inventory.get(
        "current_stock", 0
    ) if inventory else 0

    days_needed = 90
    base_quantity = max(
        0, (daily_consumption * days_needed) - current_stock
    )
    final_quantity = int(base_quantity * 1.15)
    total_cost = round(final_quantity * unit_cost_usd, 2)

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
        "patients_at_risk":             population_served,
        "daily_consumption":            daily_consumption,
        "current_stock":                current_stock,
        "base_quantity":                base_quantity,
        "safety_buffer_15pct":          int(base_quantity * 0.15),
        "final_quantity_units":         final_quantity,
        "unit_cost_usd":                round(unit_cost_usd, 2),
        "total_cost_usd":               total_cost,
        "lead_time_days":               lead_time_days,
        "expected_delivery":            expected_delivery,
        "roi_percent":                  roi_percent,
        "stockout_probability_avoided": stockout_probability_percent,
        "combined_decision_score":      combined_score,
        "formula_used": (
            f"daily_consumption({daily_consumption}) × {days_needed} days"
            f" - current_stock({current_stock})"
            f" = {base_quantity} + 15% buffer = {final_quantity} units"
            f" × ${unit_cost_usd:.2f} = ${total_cost}"
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
        "destination_country": destination_country,
        "supplier_name":       supplier_name,
        "supplier_country":    supplier_country,
        "quantity":            final_quantity,
        "unit_cost_usd":       round(unit_cost_usd, 2),
        "total_cost_usd":      total_cost,
        "lead_time_days":      lead_time_days,
        "expected_delivery":   expected_delivery,
        "roi_percent":         roi_percent,
        "combined_score":      combined_score
    }


procurement_agent = Agent(
    name="procurement_agent",
    description="Files draft purchase orders to MongoDB for each drug×country combo selected by main agent.",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the Procurement Agent.
File one purchase order per drug×country combo.
Use file_purchase_order_per_combo() for all order filing.
Use MongoDB MCP tools only to verify orders after filing.

For EACH combo:
→ Call file_purchase_order_per_combo() with all details

After ALL orders filed return JSON summary:
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
      "expected_delivery": ""
    }
  ]
}

RULES:
- ALWAYS use file_purchase_order_per_combo() for filing
- Use MCP only for verification after filing
- Call tool for EVERY combo — never skip
- Return ONLY JSON after all calls complete""",
    tools=[
        file_purchase_order_per_combo,
        procurement_mongodb_toolset,
    ],
)