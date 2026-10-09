"""
FreshGuard AI - Stockout Risk Agent
------------------------------------
This agent evaluates inventory depletion and stockout threats by comparing
safe, non-expired inventory against projected demand over a near-term horizon.

Notice: Read-only access to synthetic data. Never writes to data/.
"""

import sys
from pathlib import Path
import pandas as pd

# Add project root to sys.path so utils and agents can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils import load_inventory
from agents.demand_forecast_agent import forecast_demand, avg_daily_demand


def assess_stockout_risk(horizon_days: int = 3) -> pd.DataFrame:
    """
    Evaluates stockout risk for each store_id + product_id.
    
    Logic:
      - safe_stock: Sum of quantity_on_hand for non-expired batches only.
      - demand_next_n_days: Sum of forecast_units over the next horizon_days.
      - days_of_cover: safe_stock / avg daily forecast units.
      - stockout_risk:
          * 'HIGH' if safe_stock < demand_next_n_days
          * 'MEDIUM' if safe_stock < 1.5 * demand_next_n_days
          * 'LOW' otherwise
    
    Output columns:
      store_id, product_id, product_name, safe_stock, demand_next_n_days,
      days_of_cover, stockout_risk
    """
    inv_df = load_inventory()
    fc_df = forecast_demand(horizon_days=horizon_days)
    avg_demand_df = avg_daily_demand(horizon_days=7)

    # 1. Calculate safe on-hand stock (strictly excluding expired lots)
    safe_lots = inv_df[
        (inv_df["days_remaining_at_ref_date"] >= 0) &
        (inv_df["safety_status"] != "EXPIRED_UNSAFE")
    ]
    safe_stock_summary = (
        safe_lots.groupby(["store_id", "product_id"], as_index=False)["quantity_on_hand"]
        .sum()
        .rename(columns={"quantity_on_hand": "safe_stock"})
    )

    # 2. Sum forecasted demand over the next horizon_days
    near_term_demand = (
        fc_df.groupby(["store_id", "product_id", "product_name"], as_index=False)["forecast_units"]
        .sum()
        .rename(columns={"forecast_units": "demand_next_n_days"})
    )

    # 3. Combine stock, demand, and daily burn rate
    merged = near_term_demand.merge(safe_stock_summary, on=["store_id", "product_id"], how="left")
    merged["safe_stock"] = merged["safe_stock"].fillna(0).astype(int)

    merged = merged.merge(avg_demand_df, on=["store_id", "product_id"], how="left")
    merged["avg_daily_units"] = merged["avg_daily_units"].fillna(1.0)

    # 4. Compute days of cover & stockout risk categories
    def calculate_risk_row(row):
        safe_qty = float(row["safe_stock"])
        n_demand = float(row["demand_next_n_days"])
        avg_daily = float(row["avg_daily_units"])

        # Days of cover calculation
        doc = round(safe_qty / avg_daily, 1) if avg_daily > 0 else 99.0

        # Risk classification
        if safe_qty < n_demand:
            risk = "HIGH"
        elif safe_qty < 1.5 * n_demand:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        return pd.Series([doc, risk], index=["days_of_cover", "stockout_risk"])

    risk_metrics = merged.apply(calculate_risk_row, axis=1)
    merged["days_of_cover"] = risk_metrics["days_of_cover"]
    merged["stockout_risk"] = risk_metrics["stockout_risk"]
    merged["demand_next_n_days"] = merged["demand_next_n_days"].round(1)

    # 5. Format output columns in required order
    output_cols = [
        "store_id",
        "product_id",
        "product_name",
        "safe_stock",
        "demand_next_n_days",
        "days_of_cover",
        "stockout_risk",
    ]
    return merged[output_cols].sort_values(["store_id", "product_id"]).reset_index(drop=True)


if __name__ == "__main__":
    print("--- FreshGuard AI: Stockout Risk Agent ---")
    stockout_df = assess_stockout_risk(horizon_days=3)

    print(f"\nTotal Store-Product Combinations Analyzed: {len(stockout_df)}")
    print("\nStockout Risk Assessment Table (3-Day Horizon):")
    print(stockout_df.to_string(index=False))

    print("\nSummary by Stockout Risk Level:")
    print(stockout_df["stockout_risk"].value_counts().to_string())
