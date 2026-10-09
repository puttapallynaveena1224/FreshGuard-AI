"""
FreshGuard AI - Demand Forecast Agent
--------------------------------------
This agent forecasts future customer demand for perishable products.
It uses historical sales data to capture distinct weekday vs weekend
demand patterns, and provides a simple 7-day moving average baseline
for comparison.

Notice: Read-only access to synthetic data. Never writes to data/.
"""

import sys
from pathlib import Path
from datetime import timedelta
import pandas as pd

# Add project root to sys.path so utils can be imported reliably
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils import load_sales, REF_DATE

__all__ = [
    "forecast_demand",
    "baseline_forecast",
    "avg_daily_demand",
    "calculate_demand_intelligence",
]


def forecast_demand(horizon_days: int = 7) -> pd.DataFrame:
    """
    Forecasts demand for the next horizon_days starting from REF_DATE.
    Differentiates between weekday and weekend sales velocity per store and product.
    Output columns: store_id, product_id, product_name, forecast_date, is_weekend,
                    forecast_units, std_dev, method ("weekday_weekend_avg")
    """
    sales_df = load_sales()
    ref_dt = pd.to_datetime(REF_DATE).date()

    # Calculate weekday and weekend average units sold per store + product
    weekday_sales = sales_df[~sales_df["is_weekend"]].groupby(
        ["store_id", "product_id", "product_name"], as_index=False
    )["units_sold"].mean().rename(columns={"units_sold": "weekday_avg"})

    weekend_sales = sales_df[sales_df["is_weekend"]].groupby(
        ["store_id", "product_id", "product_name"], as_index=False
    )["units_sold"].mean().rename(columns={"units_sold": "weekend_avg"})

    # Compute overall standard deviation of daily units
    overall_std = sales_df.groupby(
        ["store_id", "product_id", "product_name"], as_index=False
    )["units_sold"].std().rename(columns={"units_sold": "std_dev"})

    # Combine historical metrics
    stats_df = weekday_sales.merge(
        weekend_sales, on=["store_id", "product_id", "product_name"], how="left"
    ).merge(
        overall_std, on=["store_id", "product_id", "product_name"], how="left"
    )

    stats_df["std_dev"] = stats_df["std_dev"].fillna(0.0).round(1)

    # Build forecast rows for each future date in horizon
    rows = []
    for day_offset in range(horizon_days):
        fc_date = ref_dt + timedelta(days=day_offset)
        # Saturday (5) and Sunday (6) are weekend days
        is_wknd = fc_date.weekday() >= 5

        for _, item in stats_df.iterrows():
            avg_units = item["weekend_avg"] if is_wknd else item["weekday_avg"]
            rows.append({
                "store_id": item["store_id"],
                "product_id": item["product_id"],
                "product_name": item["product_name"],
                "forecast_date": fc_date,
                "is_weekend": is_wknd,
                "forecast_units": round(float(avg_units), 1),
                "std_dev": round(float(item["std_dev"]), 1),
                "method": "weekday_weekend_avg",
            })

    return pd.DataFrame(rows)


def baseline_forecast(horizon_days: int = 7) -> pd.DataFrame:
    """
    Simple rule-based baseline forecast using the 7-day moving average.
    Projects a flat daily demand across the horizon.
    Output columns: same as forecast_demand(), method = "moving_avg_7d"
    """
    sales_df = load_sales()
    ref_dt = pd.to_datetime(REF_DATE).date()

    # Identify the last 7 calendar days in historical data
    max_history_date = sales_df["date"].max()
    start_7d = max_history_date - timedelta(days=6)
    last_7d_df = sales_df[sales_df["date"] >= start_7d]

    # Compute 7-day average and standard deviation
    baseline_stats = last_7d_df.groupby(
        ["store_id", "product_id", "product_name"], as_index=False
    ).agg(
        baseline_units=("units_sold", "mean"),
        std_dev=("units_sold", "std")
    )
    baseline_stats["std_dev"] = baseline_stats["std_dev"].fillna(0.0).round(1)

    # Project the flat baseline across the horizon
    rows = []
    for day_offset in range(horizon_days):
        fc_date = ref_dt + timedelta(days=day_offset)
        is_wknd = fc_date.weekday() >= 5

        for _, item in baseline_stats.iterrows():
            rows.append({
                "store_id": item["store_id"],
                "product_id": item["product_id"],
                "product_name": item["product_name"],
                "forecast_date": fc_date,
                "is_weekend": is_wknd,
                "forecast_units": round(float(item["baseline_units"]), 1),
                "std_dev": round(float(item["std_dev"]), 1),
                "method": "moving_avg_7d",
            })

    return pd.DataFrame(rows)


def avg_daily_demand(horizon_days: int = 7) -> pd.DataFrame:
    """
    Returns average daily demand per store and product across the forecast horizon.
    Used by other agents (replenishment, spoilage, stockout) for quick velocity checks.
    Output columns: store_id, product_id, avg_daily_units
    """
    fc_df = forecast_demand(horizon_days=horizon_days)
    avg_df = (
        fc_df.groupby(["store_id", "product_id"], as_index=False)["forecast_units"]
        .mean()
        .rename(columns={"forecast_units": "avg_daily_units"})
    )
    avg_df["avg_daily_units"] = avg_df["avg_daily_units"].round(1)
    return avg_df


def calculate_demand_intelligence(
    store_id: str = "STR-001",
    inv_df: pd.DataFrame = None,
    sales_df: pd.DataFrame = None,
    custom_products_df: pd.DataFrame = None,
    ref_date: str = REF_DATE,
) -> pd.DataFrame:
    """
    Computes Demand Intelligence and Next-Week Stock Estimation for every product
    in the specified shop.

    Guarantees:
    - Expiry Safety: Expired inventory is strictly excluded from usable stock.
    - Data Transparency: Distinguishes between VERIFIED POS history and INSUFFICIENT DATA.
    - Transparent Formulas:
        Predicted Next 7D Demand = forecast_demand(7)
        Safety Stock = 2 days of average daily demand buffer
        Recommended Stock Level = Predicted Next 7D Demand + Safety Stock
        Suggested Purchase = max(0, Recommended Stock Level - Usable Inventory)
    """
    ref_dt = pd.to_datetime(ref_date).date()

    if sales_df is None:
        sales_df = load_sales()
    if inv_df is None:
        from utils import load_inventory
        inv_df = load_inventory()

    # Load custom SQLite products if not passed
    if custom_products_df is None:
        try:
            from database import get_store_products
            custom_products_df = get_store_products(store_id)
        except Exception:
            custom_products_df = pd.DataFrame()

    fc_df = forecast_demand(horizon_days=7)

    # 1. Collect all products in this shop
    products = []
    seen_products = set()

    # Custom SQLite products
    if custom_products_df is not None and not custom_products_df.empty:
        for _, cp in custom_products_df.iterrows():
            p_name = str(cp.get("product_name", "")).strip()
            if not p_name:
                continue
            cat = str(cp.get("category", "General")).strip()
            qty = float(cp.get("quantity_on_hand", 0.0))
            unit = str(cp.get("unit", "Units")).strip()
            exp_str = cp.get("expiry_date")
            try:
                exp_dt = pd.to_datetime(exp_str).date()
                is_usable = exp_dt > ref_dt
            except Exception:
                is_usable = True

            p_key = p_name.lower()
            if p_key not in seen_products:
                seen_products.add(p_key)
                products.append({
                    "product_id": cp.get("batch_id", "CUSTOM"),
                    "product_name": p_name,
                    "category": cat,
                    "usable_stock": qty if is_usable else 0.0,
                    "expired_stock": qty if not is_usable else 0.0,
                    "unit": unit,
                    "source": "custom_db",
                })
            else:
                for p in products:
                    if p["product_name"].lower() == p_key:
                        if is_usable:
                            p["usable_stock"] += qty
                        else:
                            p["expired_stock"] += qty

    # CSV inventory products (for demo stores or consolidated view)
    if store_id in ["STR-001", "STR-002", "STR-003", "All Stores"]:
        if store_id == "All Stores":
            s_inv = inv_df
        else:
            s_inv = inv_df[inv_df["store_id"] == store_id]

        if not s_inv.empty:
            for p_id, grp in s_inv.groupby("product_id"):
                p_name = grp.iloc[0]["product_name"]
                cat = "Perishable"
                if "days_remaining_at_ref_date" in grp.columns:
                    safe_qty = grp[grp["days_remaining_at_ref_date"] >= 0]["quantity_on_hand"].sum()
                    exp_qty = grp[grp["days_remaining_at_ref_date"] < 0]["quantity_on_hand"].sum()
                elif "days_remaining" in grp.columns:
                    safe_qty = grp[grp["days_remaining"] >= 0]["quantity_on_hand"].sum()
                    exp_qty = grp[grp["days_remaining"] < 0]["quantity_on_hand"].sum()
                else:
                    safe_qty = grp["quantity_on_hand"].sum()
                    exp_qty = 0

                p_key = p_name.lower()
                if p_key not in seen_products:
                    seen_products.add(p_key)
                    products.append({
                        "product_id": p_id,
                        "product_name": p_name,
                        "category": cat,
                        "usable_stock": float(safe_qty),
                        "expired_stock": float(exp_qty),
                        "unit": "Units",
                        "source": "csv_inventory",
                    })
                else:
                    for p in products:
                        if p["product_name"].lower() == p_key:
                            p["usable_stock"] += float(safe_qty)
                            p["expired_stock"] += float(exp_qty)
                            p["product_id"] = p_id

    # 2. Analyze sales history for each product
    store_sales = sales_df if store_id == "All Stores" else sales_df[sales_df["store_id"] == store_id]

    rows = []
    for prod in products:
        p_name = prod["product_name"]
        p_id = prod["product_id"]
        usable_stk = prod["usable_stock"]
        exp_stk = prod["expired_stock"]

        # Check for verified POS transactions
        p_sales = store_sales[
            (store_sales["product_id"] == p_id) |
            (store_sales["product_name"].str.lower() == p_name.lower())
        ]

        if p_sales.empty:
            rows.append({
                "product_id": p_id,
                "product_name": p_name,
                "category": prod["category"],
                "usable_stock": usable_stk,
                "expired_stock": exp_stk,
                "total_historical_sold": None,
                "last_7d_sold": None,
                "avg_daily_demand": None,
                "demand_status": "NO VERIFIED DEMAND DATA",
                "sales_trend": "No POS history",
                "days_of_stock": None,
                "predicted_next_7d_demand": None,
                "safety_stock": None,
                "recommended_stock_level": None,
                "suggested_purchase": None,
                "stock_warning": "AWAITING POS DATA",
                "warning_explanation": (
                    "No historical POS transactions recorded for this shop. "
                    "The system requires verified sales data before making a next-week quantity recommendation. "
                    "Purchasing is paused to prevent overstocking."
                ),
                "data_transparency": "INSUFFICIENT DATA — not enough historical sales data",
            })
        else:
            total_sold = int(p_sales["units_sold"].sum())
            max_dt = p_sales["date"].max()
            last_7d = p_sales[p_sales["date"] >= max_dt - timedelta(days=6)]
            prior_7d = p_sales[(p_sales["date"] < max_dt - timedelta(days=6)) & (p_sales["date"] >= max_dt - timedelta(days=13))]

            l7_sold = int(last_7d["units_sold"].sum())
            avg_daily = round(float(last_7d["units_sold"].mean()), 1)

            p7_sold = float(prior_7d["units_sold"].sum())
            if p7_sold > 0:
                pct = round((l7_sold - p7_sold) / p7_sold * 100, 1)
                trend = f"📈 Rising (+{pct}%)" if pct >= 5.0 else (f"📉 Declining ({pct}%)" if pct <= -5.0 else f"➡️ Stable ({pct:+.1f}%)")
            else:
                trend = "➡️ Stable"

            # Demand velocity status
            if avg_daily >= 25.0:
                d_status = "HIGH DEMAND"
            elif avg_daily >= 15.0:
                d_status = "MEDIUM DEMAND"
            else:
                d_status = "LOW DEMAND"

            # Days of stock cover based on demand
            days_cover = round(usable_stk / avg_daily, 1) if avg_daily > 0 else 999.0

            # Predicted next-week demand
            s_fc = fc_df[
                ((fc_df["store_id"] == store_id) | (store_id == "All Stores")) &
                ((fc_df["product_id"] == p_id) | (fc_df["product_name"].str.lower() == p_name.lower()))
            ]
            pred_7d = round(float(s_fc["forecast_units"].sum()), 1) if not s_fc.empty else round(avg_daily * 7.0, 1)

            # Safety stock: 2 days average daily demand buffer
            safety = round(avg_daily * 2.0, 1)

            # Recommended stock level
            rec_stock = round(pred_7d + safety, 1)

            # Suggested purchase quantity
            po_qty = max(0, int(round(rec_stock - usable_stk)))

            # Stockout vs Overstock Warning
            if usable_stk < pred_7d:
                alert = "URGENT REORDER"
                expl = "Current stock may not cover the predicted next 7 days."
            elif usable_stk > pred_7d * 1.5:
                alert = "OVERSTOCK RISK"
                expl = f"Current stock ({usable_stk:.0f} units, {days_cover} days cover) significantly exceeds 7-day demand. Avoid unnecessary purchasing to prevent spoilage."
            else:
                alert = "OPTIMAL STOCK"
                expl = "Current stock is adequate to cover predicted 7-day demand with safety buffer."

            rows.append({
                "product_id": p_id,
                "product_name": p_name,
                "category": prod["category"],
                "usable_stock": usable_stk,
                "expired_stock": exp_stk,
                "total_historical_sold": total_sold,
                "last_7d_sold": l7_sold,
                "avg_daily_demand": avg_daily,
                "demand_status": d_status,
                "sales_trend": trend,
                "days_of_stock": days_cover,
                "predicted_next_7d_demand": pred_7d,
                "safety_stock": safety,
                "recommended_stock_level": rec_stock,
                "suggested_purchase": po_qty,
                "stock_warning": alert,
                "warning_explanation": expl,
                "data_transparency": "VERIFIED — based on actual POS history",
            })

    out_df = pd.DataFrame(rows)
    return out_df


if __name__ == "__main__":
    print("--- FreshGuard AI: Demand Forecast Agent Test ---")

    # Generate 7-day forecast
    df_fc = forecast_demand(horizon_days=7)

    print("\nFirst 10 rows of forecast_demand():")
    print(df_fc.head(10).to_string(index=False))

    # Calculate total forecast units for STR-001 and PRD-AVO-01 over 7 days
    sample_item = df_fc[
        (df_fc["store_id"] == "STR-001") & (df_fc["product_id"] == "PRD-AVO-01")
    ]
    total_7d_units = sample_item["forecast_units"].sum()
    print(f"\nTotal forecast units for STR-001 PRD-AVO-01 (7 days): {total_7d_units:.1f} units")

    # Test Demand Intelligence for Lakshmi General Store (STR-USR-004)
    print("\n--- Demand Intelligence: Lakshmi General Store (STR-USR-004) ---")
    df_lakshmi = calculate_demand_intelligence(store_id="STR-USR-004")
    print(df_lakshmi.to_string(index=False))

    # Test Demand Intelligence for Downtown Metro Fresh (STR-001)
    print("\n--- Demand Intelligence: Downtown Metro Fresh (STR-001) ---")
    df_metro = calculate_demand_intelligence(store_id="STR-001")
    print(df_metro[["product_name", "usable_stock", "last_7d_sold", "avg_daily_demand", "demand_status", "predicted_next_7d_demand", "safety_stock", "recommended_stock_level", "suggested_purchase", "stock_warning", "data_transparency"]].head(5).to_string(index=False))

