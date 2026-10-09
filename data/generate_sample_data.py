"""
FreshGuard AI - Synthetic Sample Data Generator
-----------------------------------------------
Notice: All datasets produced by this script are entirely synthetic and simulated
for demonstration and educational hackathon purposes.
Estimated savings or waste reduction metrics simulated in FreshGuard AI
are model projections, not guaranteed commercial outcomes.

Safety Rule: Batches past their expiration date are strictly flagged as EXPIRED_UNSAFE
and must never be marked down or sold. Only safe, pre-expiration food is eligible
for dynamic sell-through discounts.
"""

import csv
import datetime
import random
from pathlib import Path

# Base output directory
DATA_DIR = Path(__file__).resolve().parent

# Ensure output directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Fixed Reference Date for reproducible simulation (October 9, 2026)
REFERENCE_DATE = datetime.date(2026, 10, 9)

# 1. Retail Store Definitions
STORES = [
    {
        "store_id": "STR-001",
        "store_name": "Downtown Metro Fresh",
        "store_type": "Urban Supermarket",
        "city": "Metropolis",
        "daily_foot_traffic": 3400,
        "cooling_capacity_status": "Optimal",
        "data_notice": "SYNTHETIC_SAMPLE_DATA",
    },
    {
        "store_id": "STR-002",
        "store_name": "Suburban Center Grocers",
        "store_type": "Suburban Supercenter",
        "city": "Westfield",
        "daily_foot_traffic": 5200,
        "cooling_capacity_status": "Optimal",
        "data_notice": "SYNTHETIC_SAMPLE_DATA",
    },
    {
        "store_id": "STR-003",
        "store_name": "Express Transit Mart",
        "store_type": "Convenience Fresh",
        "city": "Metropolis Station",
        "daily_foot_traffic": 1800,
        "cooling_capacity_status": "Near Capacity",
        "data_notice": "SYNTHETIC_SAMPLE_DATA",
    },
]

# 2. Supplier & Perishable Product Catalog
PRODUCTS = [
    {
        "product_id": "PRD-AVO-01",
        "product_name": "Hass Avocados (4-Pack)",
        "category": "Produce",
        "supplier_id": "SUP-AGRI-01",
        "supplier_name": "Valley Green Farms",
        "lead_time_days": 2,
        "moq_units": 20,
        "unit_cost_usd": 2.10,
        "base_retail_price_usd": 4.99,
        "min_margin_floor_usd": 2.30,  # Floor price below which items cannot be discounted
        "nominal_shelf_life_days": 7,
        "storage_condition": "Ambient / Chilled (10°C)",
    },
    {
        "product_id": "PRD-BER-02",
        "product_name": "Fresh Strawberries (1 lb)",
        "category": "Produce",
        "supplier_id": "SUP-AGRI-01",
        "supplier_name": "Valley Green Farms",
        "lead_time_days": 1,
        "moq_units": 24,
        "unit_cost_usd": 1.80,
        "base_retail_price_usd": 4.49,
        "min_margin_floor_usd": 2.00,
        "nominal_shelf_life_days": 5,
        "storage_condition": "Refrigerated (2°C)",
    },
    {
        "product_id": "PRD-SPN-03",
        "product_name": "Organic Baby Spinach (5 oz)",
        "category": "Produce",
        "supplier_id": "SUP-AGRI-02",
        "supplier_name": "FreshLeaf Organics",
        "lead_time_days": 2,
        "moq_units": 15,
        "unit_cost_usd": 1.40,
        "base_retail_price_usd": 3.79,
        "min_margin_floor_usd": 1.60,
        "nominal_shelf_life_days": 6,
        "storage_condition": "Refrigerated (3°C)",
    },
    {
        "product_id": "PRD-MLK-04",
        "product_name": "Whole Organic Milk (1 Gallon)",
        "category": "Dairy",
        "supplier_id": "SUP-DAIR-01",
        "supplier_name": "Meadowland Dairy Co.",
        "lead_time_days": 2,
        "moq_units": 30,
        "unit_cost_usd": 2.80,
        "base_retail_price_usd": 5.89,
        "min_margin_floor_usd": 3.00,
        "nominal_shelf_life_days": 12,
        "storage_condition": "Refrigerated (2°C)",
    },
    {
        "product_id": "PRD-YOG-05",
        "product_name": "Greek Yogurt Plain (32 oz)",
        "category": "Dairy",
        "supplier_id": "SUP-DAIR-01",
        "supplier_name": "Meadowland Dairy Co.",
        "lead_time_days": 3,
        "moq_units": 20,
        "unit_cost_usd": 2.40,
        "base_retail_price_usd": 5.29,
        "min_margin_floor_usd": 2.60,
        "nominal_shelf_life_days": 14,
        "storage_condition": "Refrigerated (2°C)",
    },
    {
        "product_id": "PRD-BRD-06",
        "product_name": "Artisan Sourdough Loaf",
        "category": "Bakery",
        "supplier_id": "SUP-BAKE-01",
        "supplier_name": "Golden Crust Bakery",
        "lead_time_days": 1,
        "moq_units": 12,
        "unit_cost_usd": 1.75,
        "base_retail_price_usd": 4.99,
        "min_margin_floor_usd": 1.95,
        "nominal_shelf_life_days": 4,
        "storage_condition": "Dry Ambient (20°C)",
    },
    {
        "product_id": "PRD-CHK-07",
        "product_name": "Free-Range Chicken Breast (1 lb)",
        "category": "Meat & Poultry",
        "supplier_id": "SUP-MEAT-01",
        "supplier_name": "Highland Pastures Meat",
        "lead_time_days": 1,
        "moq_units": 18,
        "unit_cost_usd": 3.50,
        "base_retail_price_usd": 7.49,
        "min_margin_floor_usd": 3.90,
        "nominal_shelf_life_days": 5,
        "storage_condition": "Refrigerated (0-2°C)",
    },
    {
        "product_id": "PRD-BEE-08",
        "product_name": "Lean Ground Beef 85/15 (1 lb)",
        "category": "Meat & Poultry",
        "supplier_id": "SUP-MEAT-01",
        "supplier_name": "Highland Pastures Meat",
        "lead_time_days": 1,
        "moq_units": 16,
        "unit_cost_usd": 3.20,
        "base_retail_price_usd": 6.99,
        "min_margin_floor_usd": 3.50,
        "nominal_shelf_life_days": 5,
        "storage_condition": "Refrigerated (0-2°C)",
    },
]


def generate_stores_csv(filepath: Path):
    """Generates stores.csv with synthetic retail outlet profiles."""
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(STORES[0].keys()))
        writer.writeheader()
        writer.writerows(STORES)


def generate_suppliers_csv(filepath: Path):
    """Generates suppliers.csv containing lead times, MOQ, costs, and retail price."""
    fields = [
        "product_id",
        "product_name",
        "category",
        "supplier_id",
        "supplier_name",
        "lead_time_days",
        "moq_units",
        "unit_cost_usd",
        "base_retail_price_usd",
        "min_margin_floor_usd",
        "nominal_shelf_life_days",
        "storage_condition",
        "data_notice",
    ]
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for prod in PRODUCTS:
            row = dict(prod)
            row["data_notice"] = "SYNTHETIC_SAMPLE_DATA"
            writer.writerow(row)


def generate_inventory_batches_csv(filepath: Path):
    """
    Generates inventory_batches.csv representing live batches in store refrigerators/shelves.
    Strict Food Safety Classification:
      - SAFE_FRESH: >= 4 days shelf life remaining.
      - SAFE_APPROACHING_EXPIRY: 1 to 3 days remaining (eligible for dynamic markdown).
      - EXPIRED_UNSAFE: <= 0 days remaining (MANDATORY DISPOSAL - NEVER MARKED DOWN OR SOLD).
    """
    batches = []
    batch_counter = 1000

    # For each store and product, create realistic batches at various points in their shelf life
    for store in STORES:
        s_id = store["store_id"]
        for prod in PRODUCTS:
            p_id = prod["product_id"]
            nominal_shelf = prod["nominal_shelf_life_days"]

            # Scenario 1: Fresh Batch (plenty of time left)
            days_fresh = nominal_shelf - 1
            exp_fresh = REFERENCE_DATE + datetime.timedelta(days=max(4, days_fresh))
            rec_fresh = exp_fresh - datetime.timedelta(days=nominal_shelf)
            qty_fresh = random.randint(25, 60)
            batch_counter += 1
            batches.append({
                "batch_id": f"LOT-{batch_counter}",
                "store_id": s_id,
                "product_id": p_id,
                "product_name": prod["product_name"],
                "received_date": rec_fresh.isoformat(),
                "expiry_date": exp_fresh.isoformat(),
                "quantity_on_hand": qty_fresh,
                "days_remaining_at_ref_date": (exp_fresh - REFERENCE_DATE).days,
                "safety_status": "SAFE_FRESH",
                "markdown_eligible": "NO",
                "recommended_action_default": "Normal Rotation (FIFO)",
                "data_notice": "SYNTHETIC_SAMPLE_DATA",
            })

            # Scenario 2: Safe Approaching Expiry Batch (1-3 days left)
            # Perfect candidate for proactive discount to avoid waste while 100% wholesome
            days_near = random.choice([1, 2, 3])
            exp_near = REFERENCE_DATE + datetime.timedelta(days=days_near)
            rec_near = exp_near - datetime.timedelta(days=nominal_shelf)
            qty_near = random.randint(8, 22)
            batch_counter += 1
            batches.append({
                "batch_id": f"LOT-{batch_counter}",
                "store_id": s_id,
                "product_id": p_id,
                "product_name": prod["product_name"],
                "received_date": rec_near.isoformat(),
                "expiry_date": exp_near.isoformat(),
                "quantity_on_hand": qty_near,
                "days_remaining_at_ref_date": days_near,
                "safety_status": "SAFE_APPROACHING_EXPIRY",
                "markdown_eligible": "YES_SAFE_PRE_EXPIRY",
                "recommended_action_default": "Evaluate Dynamic Markdown",
                "data_notice": "SYNTHETIC_SAMPLE_DATA",
            })

            # Scenario 3: Occasional Expired Batch (Testing our safety guardrail)
            # Only generate for some items to verify system halts sales and flags safe disposal
            if p_id in ["PRD-BRD-06", "PRD-BER-02"] and s_id == "STR-001":
                exp_expired = REFERENCE_DATE - datetime.timedelta(days=1)
                rec_expired = exp_expired - datetime.timedelta(days=nominal_shelf)
                batch_counter += 1
                batches.append({
                    "batch_id": f"LOT-{batch_counter}",
                    "store_id": s_id,
                    "product_id": p_id,
                    "product_name": prod["product_name"],
                    "received_date": rec_expired.isoformat(),
                    "expiry_date": exp_expired.isoformat(),
                    "quantity_on_hand": 4,
                    "days_remaining_at_ref_date": -1,
                    "safety_status": "EXPIRED_UNSAFE",
                    "markdown_eligible": "STRICT_NO_EXPIRED_FOOD",
                    "recommended_action_default": "MANDATORY RECYCLING / DISPOSAL",
                    "data_notice": "SYNTHETIC_SAMPLE_DATA",
                })

    fields = [
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
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(batches)


def generate_sales_history_csv(filepath: Path):
    """
    Generates 14 days of realistic historical daily sales for each store and product.
    Incorporates weekend demand lift and baseline sales velocity.
    """
    sales_rows = []
    # Seed for deterministic reproducible synthetic data
    random.seed(42)

    # 14 days leading up to reference date
    start_date = REFERENCE_DATE - datetime.timedelta(days=14)

    base_velocities = {
        "PRD-AVO-01": 18,
        "PRD-BER-02": 22,
        "PRD-SPN-03": 14,
        "PRD-MLK-04": 26,
        "PRD-YOG-05": 16,
        "PRD-BRD-06": 20,
        "PRD-CHK-07": 19,
        "PRD-BEE-08": 17,
    }

    store_traffic_multipliers = {
        "STR-001": 1.15,  # Downtown Metro
        "STR-002": 1.30,  # Suburban Supercenter (larger volume)
        "STR-003": 0.70,  # Express Transit
    }

    for day_offset in range(14):
        curr_date = start_date + datetime.timedelta(days=day_offset)
        # Saturday (5) & Sunday (6) see +35% to +50% grocery bump
        is_weekend = curr_date.weekday() >= 5
        weekend_mult = 1.40 if is_weekend else 1.0

        for store in STORES:
            s_id = store["store_id"]
            store_mult = store_traffic_multipliers[s_id]

            for prod in PRODUCTS:
                p_id = prod["product_id"]
                base_v = base_velocities[p_id]

                # Random noise factor +/- 15%
                noise = random.uniform(0.85, 1.15)
                simulated_units_sold = int(round(base_v * store_mult * weekend_mult * noise))
                revenue_usd = round(simulated_units_sold * prod["base_retail_price_usd"], 2)

                sales_rows.append({
                    "date": curr_date.isoformat(),
                    "store_id": s_id,
                    "product_id": p_id,
                    "product_name": prod["product_name"],
                    "category": prod["category"],
                    "units_sold": simulated_units_sold,
                    "unit_retail_price_usd": prod["base_retail_price_usd"],
                    "total_revenue_usd": revenue_usd,
                    "is_weekend": "YES" if is_weekend else "NO",
                    "data_notice": "SYNTHETIC_SAMPLE_DATA",
                })

    fields = [
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
    with open(filepath, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sales_rows)


def main():
    print(f"Generating synthetic datasets in: {DATA_DIR}")
    generate_stores_csv(DATA_DIR / "stores.csv")
    print("  -> Created stores.csv")
    generate_suppliers_csv(DATA_DIR / "suppliers.csv")
    print("  -> Created suppliers.csv")
    generate_inventory_batches_csv(DATA_DIR / "inventory_batches.csv")
    print("  -> Created inventory_batches.csv")
    generate_sales_history_csv(DATA_DIR / "sales_history.csv")
    print("  -> Created sales_history.csv")
    print("All sample datasets generated successfully (100% Synthetic Sample Data).")


if __name__ == "__main__":
    main()
