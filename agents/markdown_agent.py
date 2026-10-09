"""
FreshGuard AI - Dynamic Markdown Agent
---------------------------------------
This agent recommends safe, proactive discounts on wholesome food lots
approaching their expiration date to accelerate sell-through and prevent waste.

Food Safety Guardrail:
- Expired food is NEVER discounted or sold.
- Margin floor protection: Discounts will never breach min_allowed_price.

Notice: Read-only access to synthetic data. Simulated recommendations only.
"""

import sys
from pathlib import Path
import pandas as pd

# Add project root to sys.path so utils and agents can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils import load_suppliers, min_allowed_price
from agents.freshness_risk_agent import assess_freshness_risk


def generate_markdown_recommendations() -> pd.DataFrame:
    """
    Evaluates at-risk wholesome inventory lots and generates dynamic discount recommendations.
    
    Logic:
      - Filters lots with action == "CONSIDER_MARKDOWN".
      - Strictly excludes any lot with risk_level == "EXPIRED" or action == "DISPOSE".
      - Assigns discount based on days remaining:
          * 1 day remaining: 35% discount
          * 2 days remaining: 25% discount
          * 3+ days remaining: 15% discount
      - Ensures discounted_price >= min_allowed_price(unit_cost, margin_floor_pct).
      - Default status: PENDING_APPROVAL for Human-in-the-Loop review.
      
    Output columns:
      markdown_id, batch_id, store_id, product_id, product_name, expiry_date,
      days_remaining, at_risk_units, original_price, suggested_discount_pct,
      discounted_price, floor_price, projected_revenue_recovered, status, rationale
    """
    freshness_df = assess_freshness_risk()
    suppliers_df = load_suppliers()

    # Filter strictly for safe approaching-expiry lots
    candidates = freshness_df[freshness_df["action"] == "CONSIDER_MARKDOWN"].copy()

    merged = candidates.merge(
        suppliers_df[[
            "product_id", "unit_cost", "retail_price", "margin_floor_pct"
        ]],
        on="product_id",
        how="left"
    )

    markdowns = []
    mk_counter = 7000

    for _, row in merged.iterrows():
        mk_counter += 1
        mk_id = f"REC-MKD-{mk_counter}"
        days_left = int(row["days_remaining"])
        at_risk = float(row["at_risk_units"])
        unit_cost = float(row["unit_cost"])
        orig_price = float(row["retail_price"])
        margin_floor = float(row["margin_floor_pct"])

        floor_price = min_allowed_price(unit_cost, margin_floor)

        # Tiered discount strategy based on urgency
        if days_left <= 1:
            raw_discount = 0.35
        elif days_left == 2:
            raw_discount = 0.25
        else:
            raw_discount = 0.15

        target_price = round(orig_price * (1.0 - raw_discount), 2)

        # Margin protection floor guardrail
        if target_price < floor_price:
            discounted_price = floor_price
            effective_discount = round((1.0 - (floor_price / orig_price)) * 100, 0)
            note = f"Discount capped at floor price (₹{floor_price:.2f}) to protect minimum margin."
        else:
            discounted_price = target_price
            effective_discount = round(raw_discount * 100, 0)
            note = f"Dynamic {int(effective_discount)}% markdown to accelerate pre-expiry sell-through."

        proj_revenue = round(at_risk * discounted_price, 2)

        markdowns.append({
            "markdown_id": mk_id,
            "batch_id": row["batch_id"],
            "store_id": row["store_id"],
            "product_id": row["product_id"],
            "product_name": row["product_name"],
            "expiry_date": row["expiry_date"],
            "days_remaining": days_left,
            "at_risk_units": at_risk,
            "original_price": orig_price,
            "suggested_discount_pct": int(effective_discount),
            "discounted_price": discounted_price,
            "floor_price": floor_price,
            "projected_revenue_recovered": proj_revenue,
            "status": "PENDING_APPROVAL",
            "rationale": note,
        })

    return pd.DataFrame(markdowns)


if __name__ == "__main__":
    print("--- FreshGuard AI: Dynamic Markdown Agent ---")
    mk_df = generate_markdown_recommendations()
    print(f"\nTotal Markdown Recommendations Generated: {len(mk_df)}")
    print(mk_df.to_string(index=False))
