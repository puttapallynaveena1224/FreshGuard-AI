"""
FreshGuard AI - Utility Data Loaders & Helpers
-----------------------------------------------
This module provides clean functions to load, validate, and parse
the synthetic datasets used across FreshGuard AI agents and dashboard.

Notice: Synthetic sample data only. Not connected to real retail systems.
"""

from pathlib import Path
import pandas as pd

# Fixed Reference Date for reproducible simulation
REF_DATE = "2026-10-09"

# Directory where CSV data files are located (relative to utils.py)
DATA_DIR = Path(__file__).resolve().parent / "data"


def _validate_file_and_columns(filepath: Path, required_columns: list[str]) -> pd.DataFrame:
    """Helper function to verify file existence and required schema."""
    if not filepath.exists():
        raise FileNotFoundError(
            f"Missing required data file: '{filepath.name}' at path '{filepath}'. "
            "Please ensure data files are present in the data/ directory."
        )

    df = pd.read_csv(filepath)

    missing_cols = [col for col in required_columns if col not in df.columns]
    if missing_cols:
        raise ValueError(
            f"File '{filepath.name}' is missing required column(s): {missing_cols}. "
            f"Found columns: {list(df.columns)}"
        )

    return df


def load_inventory() -> pd.DataFrame:
    """
    Loads data/inventory_batches.csv.
    Parses received_date and expiry_date into date objects.
    """
    required_cols = [
        "batch_id",
        "store_id",
        "product_id",
        "product_name",
        "received_date",
        "expiry_date",
        "quantity_on_hand",
        "days_remaining_at_ref_date",
        "safety_status",
        "markdown_eligible",
        "recommended_action_default",
        "data_notice",
    ]
    filepath = DATA_DIR / "inventory_batches.csv"
    df = _validate_file_and_columns(filepath, required_cols)

    # Parse date strings into Python date objects
    df["received_date"] = pd.to_datetime(df["received_date"]).dt.date
    df["expiry_date"] = pd.to_datetime(df["expiry_date"]).dt.date

    return df


def load_sales() -> pd.DataFrame:
    """
    Loads data/sales_history.csv.
    Parses date into date objects and converts is_weekend from 'YES'/'NO' to boolean True/False.
    """
    required_cols = [
        "date",
        "store_id",
        "product_id",
        "product_name",
        "category",
        "units_sold",
        "unit_retail_price_usd",
        "total_revenue_usd",
        "is_weekend",
        "data_notice",
    ]
    filepath = DATA_DIR / "sales_history.csv"
    df = _validate_file_and_columns(filepath, required_cols)

    # Parse date string into Python date object
    df["date"] = pd.to_datetime(df["date"]).dt.date

    # Convert YES/NO string values to boolean True/False
    df["is_weekend"] = df["is_weekend"].astype(str).str.strip().str.upper() == "YES"

    return df


def load_suppliers() -> pd.DataFrame:
    """Loads data/suppliers.csv with lead times, MOQ, costs, and shelf life."""
    required_cols = [
        "supplier_id",
        "supplier_name",
        "product_id",
        "lead_time_days",
        "moq",
        "unit_cost",
        "retail_price",
        "margin_floor_pct",
        "shelf_life_days",
        "data_notice",
    ]
    filepath = DATA_DIR / "suppliers.csv"
    return _validate_file_and_columns(filepath, required_cols)


def load_stores() -> pd.DataFrame:
    """Loads data/stores.csv with retail store profiles."""
    required_cols = [
        "store_id",
        "store_name",
        "store_type",
        "city",
        "daily_foot_traffic",
        "cooling_capacity_status",
        "data_notice",
    ]
    filepath = DATA_DIR / "stores.csv"
    return _validate_file_and_columns(filepath, required_cols)


def min_allowed_price(unit_cost: float, margin_floor_pct: float) -> float:
    """
    Calculates the minimum allowable retail price to protect the business margin floor.
    Formula: unit_cost / (1 - margin_floor_pct / 100)
    """
    if margin_floor_pct >= 100:
        raise ValueError("margin_floor_pct must be less than 100")
    return round(unit_cost / (1.0 - margin_floor_pct / 100.0), 2)


def format_inr(amount: float, decimals: int = 2) -> str:
    """
    Formats a numeric amount into standard Indian Rupee notation (₹).
    Supports Indian number grouping (lakhs, crores), e.g.:
    120000.00 -> ₹1,20,000.00
    45.50 -> ₹45.50
    """
    if amount is None or pd.isna(amount):
        return f"₹0.{'0' * decimals}" if decimals > 0 else "₹0"
    try:
        val = float(amount)
    except (ValueError, TypeError):
        return f"₹{amount}"

    is_neg = val < 0
    val = abs(val)
    parts = f"{val:.{decimals}f}".split(".")
    int_part = parts[0]
    dec_part = parts[1] if len(parts) > 1 else ""

    if len(int_part) <= 3:
        formatted_int = int_part
    else:
        last3 = int_part[-3:]
        rem = int_part[:-3]
        groups = []
        while len(rem) > 2:
            groups.insert(0, rem[-2:])
            rem = rem[:-2]
        if rem:
            groups.insert(0, rem)
        formatted_int = ",".join(groups) + "," + last3

    res = f"₹{formatted_int}" + (f".{dec_part}" if decimals > 0 else "")
    return f"-{res}" if is_neg else res


if __name__ == "__main__":
    print("Testing FreshGuard AI data loaders...")

    # Load all four datasets
    inv_df = load_inventory()
    sales_df = load_sales()
    suppliers_df = load_suppliers()
    stores_df = load_stores()

    # Print summary row counts
    print(f"Inventory batches loaded: {len(inv_df)} rows (expected: 50)")
    print(f"Sales history loaded:     {len(sales_df)} rows (expected: 336)")
    print(f"Suppliers loaded:         {len(suppliers_df)} rows (expected: 8)")
    print(f"Stores loaded:            {len(stores_df)} rows (expected: 3)")

    # Test the min_allowed_price helper
    test_min_price = min_allowed_price(unit_cost=2.00, margin_floor_pct=15)
    print(f"Sample min_allowed_price(cost=₹2.00, floor=15%): ₹{test_min_price:.2f}")
    print(f"Sample format_inr(120000): {format_inr(120000)}")
