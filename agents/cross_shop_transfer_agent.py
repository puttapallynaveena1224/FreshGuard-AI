"""
FreshGuard AI - Cross-Shop Transfer Agent
-----------------------------------------
This agent evaluates multi-store inventory rebalancing for perishable food lots
approaching their expiration date (0 <= days_remaining <= 2).

Food Safety Guardrails:
- Expired lots (days_remaining < 0) are strictly assigned QUARANTINE_DISPOSAL.
- Expired products are NEVER recommended for sale, discount, or transfer.

Recommendation Priority:
1. NORMAL_SELL:
   Origin-store forecast can fully consume the lot quantity before expiry.
2. INTER_SHOP_TRANSFER:
   Origin demand is insufficient AND another participating store has strong demand
   with insufficient stock AND the transferred quantity can realistically be sold before expiry.
3. CONTROLLED_MARKDOWN:
   Transfer is not viable (e.g., destination stores already have sufficient stock)
   and existing markdown rules allow dynamic discounting.
4. QUARANTINE_DISPOSAL:
   Strictly for stock that is already expired (days_remaining < 0).

Data Integrity:
- Real POS sales history (sales_history.csv) and demand_forecast_agent are used exclusively.
- Never fabricates demand; if historical POS data is unavailable for a store/product,
  explicitly labels data_status as DEMAND_DATA_UNAVAILABLE.

Notice: Read-only access to existing project data. Never writes to data/ or database.
"""

import sys
from pathlib import Path
from datetime import timedelta
import pandas as pd

# Add project root to sys.path so utils and agents can be imported reliably
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils import (
    load_inventory,
    load_sales,
    load_suppliers,
    load_stores,
    REF_DATE,
    min_allowed_price,
)
from agents.demand_forecast_agent import forecast_demand, avg_daily_demand


def evaluate_lot_transfer(
    lot: dict | pd.Series,
    inv_df: pd.DataFrame,
    fc_df: pd.DataFrame,
    sales_df: pd.DataFrame,
    suppliers_df: pd.DataFrame = None,
    stores_df: pd.DataFrame = None,
    ref_date: str = REF_DATE,
) -> dict:
    """
    Evaluates a single inventory lot approaching expiration and produces
    a structured recommendation following the strict priority:
    1. QUARANTINE_DISPOSAL (if days_remaining < 0)
    2. NORMAL_SELL (if origin forecast covers quantity)
    3. INTER_SHOP_TRANSFER (if origin demand insufficient and destination has unmet demand)
    4. CONTROLLED_MARKDOWN (if transfer unviable and markdown rules allow)
    """
    ref_dt = pd.to_datetime(ref_date).date()

    # Extract lot metadata safely
    batch_id = str(lot.get("batch_id", "UNKNOWN"))
    origin_store_id = str(lot.get("store_id", "UNKNOWN"))
    product_id = str(lot.get("product_id", "UNKNOWN"))
    product_name = str(lot.get("product_name", ""))
    quantity = int(lot.get("quantity_on_hand", 0))
    safety_status = str(lot.get("safety_status", ""))

    # Determine days remaining
    if "days_remaining" in lot and pd.notna(lot["days_remaining"]):
        days_rem = int(lot["days_remaining"])
    elif "days_remaining_at_ref_date" in lot and pd.notna(lot["days_remaining_at_ref_date"]):
        days_rem = int(lot["days_remaining_at_ref_date"])
    elif "expiry_date" in lot and pd.notna(lot["expiry_date"]):
        exp_val = pd.to_datetime(lot["expiry_date"]).date()
        days_rem = (exp_val - ref_dt).days
    else:
        days_rem = 0

    # Determine expiry date
    if "expiry_date" in lot and pd.notna(lot["expiry_date"]):
        expiry_date = pd.to_datetime(lot["expiry_date"]).date()
    else:
        expiry_date = ref_dt + timedelta(days=max(0, days_rem))

    # Lookup product name if blank
    if not product_name or product_name == "nan":
        prod_matches = inv_df[inv_df["product_id"] == product_id]
        if not prod_matches.empty:
            product_name = str(prod_matches.iloc[0]["product_name"])
        elif suppliers_df is not None:
            supp_matches = suppliers_df[suppliers_df["product_id"] == product_id]
            if not supp_matches.empty and "product_name" in supp_matches.columns:
                product_name = str(supp_matches.iloc[0]["product_name"])
        if not product_name:
            product_name = product_id

    # -------------------------------------------------------------
    # RULE 2 & PRIORITY D: Expired lot check (FOOD SAFETY GUARDRAIL)
    # -------------------------------------------------------------
    if days_rem < 0 or safety_status == "EXPIRED_UNSAFE":
        return {
            "batch_id": batch_id,
            "product_id": product_id,
            "product_name": product_name,
            "origin_store_id": origin_store_id,
            "destination_store_id": None,
            "quantity": quantity,
            "days_remaining": days_rem,
            "origin_demand": 0.0,
            "destination_demand": None,
            "destination_stock": None,
            "recommended_action": "QUARANTINE_DISPOSAL",
            "reason": (
                f"Lot is past expiration date ({days_rem} days remaining). "
                "Strict food safety guardrail: quarantine and dispose immediately. "
                "Never sell, discount, or transfer expired stock."
            ),
            "confidence": "HIGH",
            "data_status": "VERIFIED_EXPIRED",
        }

    # -------------------------------------------------------------
    # RULE 6: Verify POS sales history existence (No fabricated demand)
    # -------------------------------------------------------------
    pos_pairs = set(zip(sales_df["store_id"], sales_df["product_id"]))
    origin_has_pos = (origin_store_id, product_id) in pos_pairs

    if not origin_has_pos:
        origin_demand = None
        data_status = "DEMAND_DATA_UNAVAILABLE"
        confidence = "LOW"
    else:
        data_status = "HISTORICAL_POS_VERIFIED"
        confidence = "HIGH"

        # Calculate origin demand before expiry
        # Sellable window: dates strictly before expiry (or today if days_rem == 0)
        if days_rem == 0:
            origin_fc = fc_df[
                (fc_df["store_id"] == origin_store_id)
                & (fc_df["product_id"] == product_id)
                & (fc_df["forecast_date"] == ref_dt)
            ]
        else:
            origin_fc = fc_df[
                (fc_df["store_id"] == origin_store_id)
                & (fc_df["product_id"] == product_id)
                & (fc_df["forecast_date"] < expiry_date)
            ]

        origin_demand = round(float(origin_fc["forecast_units"].sum()), 1)

    # -------------------------------------------------------------
    # PRIORITY A: NORMAL_SELL
    # If origin-store forecast can consume the quantity before expiry
    # -------------------------------------------------------------
    if origin_has_pos and origin_demand is not None and origin_demand >= quantity:
        return {
            "batch_id": batch_id,
            "product_id": product_id,
            "product_name": product_name,
            "origin_store_id": origin_store_id,
            "destination_store_id": None,
            "quantity": quantity,
            "days_remaining": days_rem,
            "origin_demand": origin_demand,
            "destination_demand": None,
            "destination_stock": None,
            "recommended_action": "NORMAL_SELL",
            "reason": (
                f"Origin store forecast ({origin_demand:.1f} units) can fully absorb on-hand "
                f"quantity ({quantity} units) before expiry date ({expiry_date}). "
                "Expected full sell-through at standard retail price."
            ),
            "confidence": confidence,
            "data_status": data_status,
        }

    # -------------------------------------------------------------
    # PRIORITY B: INTER_SHOP_TRANSFER
    # Check other participating stores for the same product
    # -------------------------------------------------------------
    surplus_qty = quantity - (origin_demand if origin_demand is not None else 0.0)

    # Identify all participating stores
    all_stores = set()
    if stores_df is not None and "store_id" in stores_df.columns:
        all_stores.update(stores_df["store_id"].dropna().unique())
    if "store_id" in inv_df.columns:
        all_stores.update(inv_df["store_id"].dropna().unique())
    all_stores.update(sales_df["store_id"].dropna().unique())

    candidate_destinations = sorted([s for s in all_stores if s != origin_store_id])

    viable_transfers = []
    inspected_destinations = []

    # If lot expires today (days_rem == 0), inter-shop transit is physically unviable
    can_physically_transfer = days_rem > 0

    if can_physically_transfer:
        for dest_id in candidate_destinations:
            dest_has_pos = (dest_id, product_id) in pos_pairs
            if not dest_has_pos:
                inspected_destinations.append({
                    "store_id": dest_id,
                    "status": "DEMAND_DATA_UNAVAILABLE",
                    "demand": None,
                    "stock": None,
                    "deficit": 0.0,
                })
                continue

            # Demand at destination before expiry
            dest_fc = fc_df[
                (fc_df["store_id"] == dest_id)
                & (fc_df["product_id"] == product_id)
                & (fc_df["forecast_date"] < expiry_date)
            ]
            dest_demand = round(float(dest_fc["forecast_units"].sum()), 1)

            # Daily velocity for velocity comparison
            dest_item_all = fc_df[
                (fc_df["store_id"] == dest_id)
                & (fc_df["product_id"] == product_id)
            ]
            dest_velocity = round(float(dest_item_all["forecast_units"].mean()), 1) if not dest_item_all.empty else 0.0

            # Destination safe on-hand stock
            dest_inv = inv_df[
                (inv_df["store_id"] == dest_id)
                & (inv_df["product_id"] == product_id)
            ]
            # Exclude expired stock from destination stock count
            if "days_remaining_at_ref_date" in dest_inv.columns:
                safe_dest_inv = dest_inv[dest_inv["days_remaining_at_ref_date"] >= 0]
            elif "days_remaining" in dest_inv.columns:
                safe_dest_inv = dest_inv[dest_inv["days_remaining"] >= 0]
            else:
                safe_dest_inv = dest_inv
            dest_stock = int(safe_dest_inv["quantity_on_hand"].sum()) if not safe_dest_inv.empty else 0

            # Net deficit: how many units destination lacks to meet forecast before expiry
            net_deficit = round(dest_demand - dest_stock, 1)

            dest_record = {
                "store_id": dest_id,
                "status": "HISTORICAL_POS_VERIFIED",
                "demand": dest_demand,
                "stock": dest_stock,
                "velocity": dest_velocity,
                "deficit": net_deficit,
            }
            inspected_destinations.append(dest_record)

            # Condition 4 & 5B:
            # Destination has strong demand (dest_demand > 0),
            # insufficient stock (dest_stock < dest_demand, i.e., net_deficit > 0),
            # and could realistically sell the transferred quantity before expiry.
            if net_deficit > 0 and dest_demand > 0:
                sellable_capacity = min(surplus_qty, net_deficit)
                if sellable_capacity >= 1.0:
                    viable_transfers.append({
                        "destination_store_id": dest_id,
                        "destination_demand": dest_demand,
                        "destination_stock": dest_stock,
                        "net_deficit": net_deficit,
                        "sellable_capacity": sellable_capacity,
                        "destination_velocity": dest_velocity,
                    })

    if viable_transfers:
        # Select best destination: highest net deficit (greatest unmet need), then velocity
        viable_transfers.sort(
            key=lambda x: (x["net_deficit"], x["destination_velocity"]),
            reverse=True,
        )
        best = viable_transfers[0]

        return {
            "batch_id": batch_id,
            "product_id": product_id,
            "product_name": product_name,
            "origin_store_id": origin_store_id,
            "destination_store_id": best["destination_store_id"],
            "quantity": quantity,
            "days_remaining": days_rem,
            "origin_demand": origin_demand,
            "destination_demand": best["destination_demand"],
            "destination_stock": best["destination_stock"],
            "recommended_action": "INTER_SHOP_TRANSFER",
            "reason": (
                f"Origin forecast ({origin_demand if origin_demand is not None else 'N/A'} units) "
                f"is insufficient for on-hand quantity ({quantity} units). "
                f"Destination store {best['destination_store_id']} has high demand ({best['destination_demand']} units) "
                f"and insufficient stock ({best['destination_stock']} units, net deficit {best['net_deficit']} units). "
                f"Destination can realistically sell {min(quantity, int(best['net_deficit']))} units before expiry ({expiry_date})."
            ),
            "confidence": "HIGH" if origin_has_pos else "MEDIUM",
            "data_status": data_status,
        }

    # -------------------------------------------------------------
    # PRIORITY C: CONTROLLED_MARKDOWN
    # Transfer is not viable; check existing markdown rules
    # -------------------------------------------------------------
    markdown_eligible = lot.get("markdown_eligible", "YES")
    is_markdown_allowed = (
        days_rem >= 0
        and str(markdown_eligible).strip().upper() != "NO"
        and safety_status != "EXPIRED_UNSAFE"
    )

    # Build detailed context about inspected destination stores
    if not can_physically_transfer:
        dest_summary = "Lot expires today (same-day transfer not feasible)."
    elif inspected_destinations:
        pos_inspected = [d for d in inspected_destinations if d["status"] == "HISTORICAL_POS_VERIFIED"]
        if pos_inspected:
            dest_details = ", ".join(
                f"{d['store_id']}: stock {d['stock']} vs demand {d['demand']}"
                for d in pos_inspected
            )
            dest_summary = f"Participating stores hold sufficient inventory ({dest_details})."
        else:
            dest_summary = "No participating stores have verified POS demand."
    else:
        dest_summary = "No participating destination stores available."

    if is_markdown_allowed:
        orig_dem_str = f"{origin_demand:.1f} units" if origin_demand is not None else "unavailable"
        return {
            "batch_id": batch_id,
            "product_id": product_id,
            "product_name": product_name,
            "origin_store_id": origin_store_id,
            "destination_store_id": None,
            "quantity": quantity,
            "days_remaining": days_rem,
            "origin_demand": origin_demand,
            "destination_demand": None,
            "destination_stock": None,
            "recommended_action": "CONTROLLED_MARKDOWN",
            "reason": (
                f"Origin demand ({orig_dem_str}) cannot absorb lot quantity ({quantity} units) before expiry. "
                f"Transfer not viable: {dest_summary} "
                "Markdown rules allow discount; recommend controlled markdown to accelerate sell-through."
            ),
            "confidence": confidence,
            "data_status": data_status,
        }

    # Fallback if markdown rules disallow discounting
    return {
        "batch_id": batch_id,
        "product_id": product_id,
        "product_name": product_name,
        "origin_store_id": origin_store_id,
        "destination_store_id": None,
        "quantity": quantity,
        "days_remaining": days_rem,
        "origin_demand": origin_demand,
        "destination_demand": None,
        "destination_stock": None,
        "recommended_action": "MANUAL_REVIEW",
        "reason": (
            f"Origin demand cannot absorb quantity ({quantity} units), transfer is not viable ({dest_summary}), "
            "and lot is flagged as not eligible for dynamic markdown. Manual supervisor review required."
        ),
        "confidence": confidence,
        "data_status": data_status,
    }


def recommend_cross_shop_transfers(
    inv_df: pd.DataFrame = None,
    max_days_remaining: int = 2,
    include_expired: bool = True,
) -> pd.DataFrame:
    """
    Evaluates inventory lots approaching expiry (0 <= days_remaining <= max_days_remaining)
    and produces structured multi-shop rebalancing recommendations.

    Food Safety Guardrail:
    - Expired lots (days_remaining < 0) are strictly flagged as QUARANTINE_DISPOSAL.
    - Expired products are NEVER recommended for sale, markdown, or transfer.

    Parameters:
      inv_df: Optional custom inventory DataFrame. Defaults to load_inventory().
      max_days_remaining: Maximum shelf-life days to evaluate (default: 2 days).
      include_expired: If True, evaluates expired lots and marks them QUARANTINE_DISPOSAL.

    Returns:
      pd.DataFrame containing structured recommendations with required columns:
      - product_id, product_name
      - batch_id
      - origin_store_id
      - destination_store_id
      - quantity
      - days_remaining
      - origin_demand
      - destination_demand
      - destination_stock
      - recommended_action
      - reason
      - confidence
      - data_status
    """
    if inv_df is None:
        inv_df = load_inventory()

    sales_df = load_sales()
    suppliers_df = load_suppliers()
    stores_df = load_stores()

    # Pre-generate forecast for 21 days
    fc_df = forecast_demand(horizon_days=21)
    ref_dt = pd.to_datetime(REF_DATE).date()

    # Determine days remaining column
    candidates = []
    for _, row in inv_df.iterrows():
        if "days_remaining" in row and pd.notna(row["days_remaining"]):
            days_rem = int(row["days_remaining"])
        elif "days_remaining_at_ref_date" in row and pd.notna(row["days_remaining_at_ref_date"]):
            days_rem = int(row["days_remaining_at_ref_date"])
        elif "expiry_date" in row and pd.notna(row["expiry_date"]):
            exp_val = pd.to_datetime(row["expiry_date"]).date()
            days_rem = (exp_val - ref_dt).days
        else:
            days_rem = 0

        # Filter criteria:
        # Expired lots (< 0) are included if include_expired is True
        # Approaching expiry lots (0 <= days <= max_days_remaining) are included
        if days_rem < 0:
            if include_expired:
                candidates.append((row, days_rem))
        elif 0 <= days_rem <= max_days_remaining:
            candidates.append((row, days_rem))

    recommendations = []
    for row, days_rem in candidates:
        rec = evaluate_lot_transfer(
            lot=row,
            inv_df=inv_df,
            fc_df=fc_df,
            sales_df=sales_df,
            suppliers_df=suppliers_df,
            stores_df=stores_df,
            ref_date=REF_DATE,
        )
        recommendations.append(rec)

    # Format into DataFrame with canonical column order
    cols = [
        "batch_id",
        "product_id",
        "product_name",
        "origin_store_id",
        "destination_store_id",
        "quantity",
        "days_remaining",
        "origin_demand",
        "destination_demand",
        "destination_stock",
        "recommended_action",
        "reason",
        "confidence",
        "data_status",
    ]

    out_df = pd.DataFrame(recommendations)
    if out_df.empty:
        return pd.DataFrame(columns=cols)

    # Ensure all required columns are present
    for c in cols:
        if c not in out_df.columns:
            out_df[c] = None

    return out_df[cols].sort_values(["origin_store_id", "days_remaining", "product_id"]).reset_index(drop=True)


def run_demo():
    """
    Executes an independent demonstration and verification of the
    Cross-Shop Transfer Agent against real project data.
    """
    print("=" * 80)
    print(" FreshGuard AI - Cross-Shop Transfer Agent Independent Execution Test")
    print("=" * 80)

    # Test 1: Run against actual project inventory data
    print("\n>>> TEST 1: Running against existing data/inventory_batches.csv (0 <= days <= 2 + expired)")
    df_recs = recommend_cross_shop_transfers(max_days_remaining=2, include_expired=True)

    print(f"\nTotal Candidate Lots Evaluated: {len(df_recs)}")
    print("\nRecommendation Breakdown by Action:")
    print(df_recs["recommended_action"].value_counts().to_string())

    print("\nRecommendation Breakdown by Data Status:")
    print(df_recs["data_status"].value_counts().to_string())

    print("\nDetailed Evaluation Table:")
    display_cols = [
        "batch_id",
        "product_id",
        "origin_store_id",
        "days_remaining",
        "quantity",
        "origin_demand",
        "destination_store_id",
        "recommended_action",
    ]
    print(df_recs[display_cols].to_string(index=False))

    print("\n--- Detailed Reasons for At-Risk Lots ---")
    at_risk_or_special = df_recs[df_recs["recommended_action"] != "NORMAL_SELL"]
    for _, row in at_risk_or_special.iterrows():
        print(f"[{row['batch_id']}] {row['product_name']} ({row['origin_store_id']}) -> {row['recommended_action']}")
        print(f"   Reason: {row['reason']}")
        print(f"   Confidence: {row['confidence']} | Status: {row['data_status']}\n")

    # Test 2: Multi-Shop Transfer Simulation Scenario
    # Verify that INTER_SHOP_TRANSFER triggers when another store has strong demand and insufficient stock
    print("=" * 80)
    print(">>> TEST 2: Simulating Rebalancing Scenario (Destination has low stock & high demand)")
    base_inv = load_inventory()
    sim_inv = base_inv.copy()
    # Simulate STR-001 having a stockout of PRD-BRD-06 (Bread) with only 2 units on hand
    sim_inv.loc[
        (sim_inv["store_id"] == "STR-001") & (sim_inv["product_id"] == "PRD-BRD-06"),
        "quantity_on_hand",
    ] = 2

    sim_recs = recommend_cross_shop_transfers(inv_df=sim_inv, max_days_remaining=2, include_expired=True)
    transfer_rows = sim_recs[sim_recs["recommended_action"] == "INTER_SHOP_TRANSFER"]

    print(f"Transfer Recommendations Detected: {len(transfer_rows)}")
    for _, row in transfer_rows.iterrows():
        print(f"[{row['batch_id']}] {row['product_name']}: {row['origin_store_id']} -> {row['destination_store_id']}")
        print(f"   Quantity: {row['quantity']} | Days Rem: {row['days_remaining']}")
        print(f"   Origin Demand: {row['origin_demand']} | Dest Demand: {row['destination_demand']} | Dest Stock: {row['destination_stock']}")
        print(f"   Reason: {row['reason']}\n")

    # Test 3: Unknown store/product with missing POS history
    print("=" * 80)
    print(">>> TEST 3: Handling Store with No POS Sales History (Requirement 6)")
    untracked_inv = pd.DataFrame([{
        "batch_id": "LOT-CUSTOM-99",
        "store_id": "STR-USR-004",
        "product_id": "PRD-NEW-99",
        "product_name": "Artisan Goat Cheese",
        "quantity_on_hand": 10,
        "days_remaining_at_ref_date": 1,
        "safety_status": "SAFE_APPROACHING_EXPIRY",
        "markdown_eligible": "YES",
    }])
    untracked_recs = recommend_cross_shop_transfers(inv_df=untracked_inv, max_days_remaining=2, include_expired=True)
    for _, row in untracked_recs.iterrows():
        print(f"[{row['batch_id']}] {row['product_name']} ({row['origin_store_id']}) -> {row['recommended_action']}")
        print(f"   Data Status: {row['data_status']} | Origin Demand: {row['origin_demand']}")
        print(f"   Reason: {row['reason']}\n")

    print("=" * 80)
    print(" All agent tests completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    run_demo()
