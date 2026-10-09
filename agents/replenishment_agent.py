"""
FreshGuard AI - Replenishment Agent
------------------------------------
This agent calculates intelligent purchase orders for perishable products.
It accounts for supplier lead times, Minimum Order Quantities (MOQ),
and imposes perishable shelf-life caps to prevent over-ordering.

Notice: Read-only access to synthetic data. Generates simulated POs only.
Never places real commercial orders.
"""

import sys
from pathlib import Path
import pandas as pd

# Add project root to sys.path so utils and agents can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils import load_suppliers
from agents.demand_forecast_agent import avg_daily_demand
from agents.stockout_risk_agent import assess_stockout_risk


def generate_replenishment_recommendations() -> pd.DataFrame:
    """
    Generates recommended replenishment purchase orders for all store_id + product_id pairs.
    
    Logic:
      - Uses stockout risk (HIGH, MEDIUM, LOW) and supplier constraints (lead_time_days, moq, unit_cost).
      - Target stock = projected demand during lead time + safety buffer.
      - Imposes perishable cap: order cannot exceed product's shelf-life demand capacity.
      - Status defaults to PENDING_APPROVAL for Human-in-the-Loop review.
      
    Output columns:
      recommendation_id, store_id, product_id, product_name, supplier_name,
      safe_stock, stockout_risk, lead_time_days, moq, unit_cost,
      recommended_order_units, estimated_order_cost, priority, status, rationale
    """
    stockout_df = assess_stockout_risk(horizon_days=3)
    suppliers_df = load_suppliers()
    avg_demand_df = avg_daily_demand(horizon_days=7)

    # Merge stockout status with supplier catalog
    merged = stockout_df.merge(
        suppliers_df[[
            "product_id", "supplier_name", "lead_time_days",
            "moq", "unit_cost", "retail_price", "shelf_life_days"
        ]],
        on="product_id",
        how="left"
    )

    merged = merged.merge(
        avg_demand_df[["store_id", "product_id", "avg_daily_units"]],
        on=["store_id", "product_id"],
        how="left"
    )

    orders = []
    order_counter = 5000

    for _, row in merged.iterrows():
        order_counter += 1
        rec_id = f"REC-PO-{order_counter}"
        risk = row["stockout_risk"]
        safe_stock = int(row["safe_stock"])
        lead_time = int(row["lead_time_days"])
        moq = int(row["moq"])
        unit_cost = float(row["unit_cost"])
        shelf_life = int(row["shelf_life_days"])
        avg_daily = float(row["avg_daily_units"])

        lead_time_demand = avg_daily * lead_time

        if risk == "HIGH":
            # Target 3 days buffer plus lead time
            target_stock = lead_time_demand + (avg_daily * 3.0)
            net_need = target_stock - safe_stock
            order_qty = max(moq, int(round(net_need)))
            priority = "URGENT"
            rationale = (
                f"High stockout risk ({safe_stock} safe units vs {lead_time_demand:.1f} lead-time demand). "
                f"Order size respects supplier MOQ ({moq})."
            )
        elif risk == "MEDIUM":
            # Target 2 days buffer plus lead time
            target_stock = lead_time_demand + (avg_daily * 2.0)
            net_need = target_stock - safe_stock
            order_qty = max(moq, int(round(net_need)))
            priority = "MEDIUM"
            rationale = (
                f"Medium stockout risk. Preemptive reorder to sustain buffer over {lead_time}d lead time."
            )
        else:
            order_qty = 0
            priority = "LOW"
            rationale = "Adequate inventory on hand. No reorder needed at this time."

        # Perishable Guardrail Cap: Never order more units than can be sold within shelf life
        max_shelf_life_capacity = int(round(avg_daily * min(shelf_life, 6)))
        if order_qty > max_shelf_life_capacity:
            order_qty = max(moq, max_shelf_life_capacity)
            rationale += f" Capped by {shelf_life}d perishable shelf life."

        est_cost = round(order_qty * unit_cost, 2)
        status = "PENDING_APPROVAL" if order_qty > 0 else "NO_ORDER_NEEDED"

        orders.append({
            "recommendation_id": rec_id,
            "store_id": row["store_id"],
            "product_id": row["product_id"],
            "product_name": row["product_name"],
            "supplier_name": row["supplier_name"],
            "safe_stock": safe_stock,
            "stockout_risk": risk,
            "lead_time_days": lead_time,
            "moq": moq,
            "unit_cost": unit_cost,
            "recommended_order_units": order_qty,
            "estimated_order_cost": est_cost,
            "priority": priority,
            "status": status,
            "rationale": rationale,
        })

    return pd.DataFrame(orders).sort_values(
        ["priority", "store_id"], ascending=[True, True]
    ).reset_index(drop=True)


if __name__ == "__main__":
    print("--- FreshGuard AI: Replenishment Agent ---")
    po_df = generate_replenishment_recommendations()
    print(f"\nTotal Recommendations Generated: {len(po_df)}")
    active_pos = po_df[po_df["recommended_order_units"] > 0]
    print(f"Active Replenishment POs: {len(active_pos)}")
    print("\nSample Active Purchase Orders (First 8):")
    print(active_pos.head(8).to_string(index=False))
