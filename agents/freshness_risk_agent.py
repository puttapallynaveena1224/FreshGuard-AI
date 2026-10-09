"""
FreshGuard AI - Freshness & Spoilage Risk Agent
------------------------------------------------
This agent evaluates batch-level expiration risks by comparing on-hand inventory
against projected demand velocity using First-In-First-Out (FIFO) allocation.

Safety Guardrail:
- Expired lots are marked EXPIRED with action DISPOSE.
- NEVER recommends markdowns on expired food.

Notice: Read-only access to synthetic data. Never writes to data/.
"""

import sys
from pathlib import Path
import pandas as pd

# Add project root to sys.path so utils and agents can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils import load_inventory, REF_DATE
from agents.demand_forecast_agent import forecast_demand


def assess_freshness_risk() -> pd.DataFrame:
    """
    Evaluates expiration risk for every inventory lot in inventory_batches.csv.
    Allocates demand FIFO: lots expiring earlier consume projected customer demand first.
    
    Output columns:
      batch_id, store_id, product_id, product_name, expiry_date, days_remaining,
      quantity_on_hand, expected_sold_before_expiry, at_risk_units, risk_level,
      action ("DISPOSE" / "CONSIDER_MARKDOWN" / "NONE"), reason
    """
    inv_df = load_inventory()
    # 21-day forecast covers all batch expiration dates in our catalog
    fc_df = forecast_demand(horizon_days=21)

    results = []

    # Process inventory grouped by store and product
    grouped = inv_df.groupby(["store_id", "product_id"])

    for (s_id, p_id), group in grouped:
        # Get demand forecast for this store and product
        item_fc = fc_df[
            (fc_df["store_id"] == s_id) & (fc_df["product_id"] == p_id)
        ].sort_values("forecast_date")

        # Separate expired lots from safe lots
        expired_lots = group[
            (group["days_remaining_at_ref_date"] < 0) |
            (group["safety_status"] == "EXPIRED_UNSAFE")
        ]
        safe_lots = group[
            (group["days_remaining_at_ref_date"] >= 0) &
            (group["safety_status"] != "EXPIRED_UNSAFE")
        ].sort_values("expiry_date")  # FIFO: earliest expiry first

        # 1. Handle expired lots strictly
        for _, lot in expired_lots.iterrows():
            qty = int(lot["quantity_on_hand"])
            results.append({
                "batch_id": lot["batch_id"],
                "store_id": lot["store_id"],
                "product_id": lot["product_id"],
                "product_name": lot["product_name"],
                "expiry_date": lot["expiry_date"],
                "days_remaining": int(lot["days_remaining_at_ref_date"]),
                "quantity_on_hand": qty,
                "expected_sold_before_expiry": 0.0,
                "at_risk_units": float(qty),
                "risk_level": "EXPIRED",
                "action": "DISPOSE",
                "reason": "Lot is past expiration date. Strict food safety policy: dispose immediately, never sell.",
            })

        # 2. FIFO Demand Allocation for safe lots
        # Track daily unconsumed demand so earliest expiring lots consume it first
        daily_demand_pool = {
            row["forecast_date"]: float(row["forecast_units"])
            for _, row in item_fc.iterrows()
        }

        for _, lot in safe_lots.iterrows():
            qty = float(lot["quantity_on_hand"])
            lot_expiry = lot["expiry_date"]
            days_left = int(lot["days_remaining_at_ref_date"])

            # Lot can only absorb demand for dates strictly before expiry (forecast_date < expiry_date)
            allocated_demand = 0.0
            needed = qty

            for fc_date in sorted(daily_demand_pool.keys()):
                if fc_date >= lot_expiry:
                    # Past this lot's expiry date; cannot sell this lot on or after expiry
                    break
                
                avail = daily_demand_pool[fc_date]
                if avail > 0 and needed > 0:
                    absorbed = min(avail, needed)
                    allocated_demand += absorbed
                    daily_demand_pool[fc_date] -= absorbed
                    needed -= absorbed

            allocated_demand = round(allocated_demand, 1)
            at_risk = round(max(0.0, qty - allocated_demand), 1)
            risk_ratio = at_risk / qty if qty > 0 else 0.0

            # Determine risk level
            if risk_ratio >= 0.5:
                risk_level = "HIGH"
            elif risk_ratio >= 0.2:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"

            # Action rule: CONSIDER_MARKDOWN only when risk is MEDIUM or HIGH and lot is safe
            if risk_level in ["HIGH", "MEDIUM"]:
                action = "CONSIDER_MARKDOWN"
                reason = (
                    f"{at_risk:.0f} units projected unsold before expiry ({risk_ratio:.0%} risk). "
                    "Recommend proactive markdown to accelerate sell-through."
                )
            else:
                action = "NONE"
                reason = "Demand velocity is sufficient. Expected full sell-through before expiration."

            results.append({
                "batch_id": lot["batch_id"],
                "store_id": lot["store_id"],
                "product_id": lot["product_id"],
                "product_name": lot["product_name"],
                "expiry_date": lot_expiry,
                "days_remaining": days_left,
                "quantity_on_hand": int(qty),
                "expected_sold_before_expiry": allocated_demand,
                "at_risk_units": at_risk,
                "risk_level": risk_level,
                "action": action,
                "reason": reason,
            })

    out_df = pd.DataFrame(results)
    # Sort for readable presentation: store, product, expiry
    return out_df.sort_values(["store_id", "product_id", "expiry_date"]).reset_index(drop=True)


if __name__ == "__main__":
    print("--- FreshGuard AI: Freshness & Spoilage Risk Agent ---")
    risk_df = assess_freshness_risk()

    print(f"\nTotal Batches Assessed: {len(risk_df)}")
    print("\nBatch Freshness Risk Assessment (All Lots):")
    print(risk_df.to_string(index=False))

    print("\nSummary by Risk Level:")
    print(risk_df["risk_level"].value_counts().to_string())

    print("\nSummary by Recommended Action:")
    print(risk_df["action"].value_counts().to_string())
