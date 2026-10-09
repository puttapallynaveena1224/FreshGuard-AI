"""
FreshGuard AI - Final Store ID & Store Isolation Migration Script
-----------------------------------------------------------------
Migrates Lakshmi General Store to final Store ID 'STR-001',
re-tags old benchmark STR-001 data to 'STR-LEGACY-001' across SQLite
and CSV datasets, and ensures complete isolation.
"""

import os
import shutil
import sqlite3
import hashlib
import datetime
from pathlib import Path
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent

def run_migration():
    print("=== FreshGuard AI: Store Isolation Migration ===")
    backup_dir = ROOT_DIR / "data" / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # 1. Back up files
    db_file = ROOT_DIR / "freshguard.db"
    stores_file = ROOT_DIR / "data" / "stores.csv"
    inv_file = ROOT_DIR / "data" / "inventory_batches.csv"
    sales_file = ROOT_DIR / "data" / "sales_history.csv"

    if db_file.exists():
        shutil.copy(db_file, backup_dir / "freshguard.db.bak")
    if stores_file.exists():
        shutil.copy(stores_file, backup_dir / "stores.csv.bak")
    if inv_file.exists():
        shutil.copy(inv_file, backup_dir / "inventory_batches.csv.bak")
    if sales_file.exists():
        shutil.copy(sales_file, backup_dir / "sales_history.csv.bak")
    print("Backups safely preserved in data/backup/")

    # 2. SQLite Database Migration
    conn = sqlite3.connect(str(db_file))
    c = conn.cursor()

    # Re-tag legacy demo account to STR-LEGACY-001
    c.execute(
        "UPDATE users SET store_id = 'STR-LEGACY-001' WHERE email = 'metro@freshguard.ai' OR store_id = 'STR-001'"
    )

    # Re-tag Lakshmi General Store to STR-001
    c.execute(
        """UPDATE users 
           SET store_id = 'STR-001', shop_name = 'Lakshmi General Store', shopkeeper_name = 'Lakshmi' 
           WHERE email = 'puttapallynaveena1224@gmail.com' OR store_id = 'STR-USR-004'"""
    )

    # Seed/ensure lakshmi@freshguard.ai as quick demo user for STR-001
    c.execute("SELECT id FROM users WHERE email = 'lakshmi@freshguard.ai'")
    if not c.fetchone():
        salt = os.urandom(16)
        p_hash = hashlib.pbkdf2_hmac("sha256", "freshguard123".encode("utf-8"), salt, 100000).hex()
        now_str = datetime.datetime.now().isoformat()
        c.execute(
            """INSERT INTO users (email, password_hash, salt, shopkeeper_name, shop_name, store_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("lakshmi@freshguard.ai", p_hash, salt.hex(), "Lakshmi", "Lakshmi General Store", "STR-001", now_str),
        )

    # Move old demo product (Artisan Butter Croissant) to STR-LEGACY-001
    c.execute(
        "UPDATE custom_products SET store_id = 'STR-LEGACY-001' WHERE batch_id = 'LOT-TEST-999'"
    )

    # Move Lakshmi's actual inventory products to STR-001
    c.execute(
        "UPDATE custom_products SET store_id = 'STR-001' WHERE store_id = 'STR-USR-004'"
    )

    conn.commit()

    print("\n--- Users Table After Migration ---")
    for r in c.execute("SELECT id, email, shopkeeper_name, shop_name, store_id FROM users").fetchall():
        print(f"ID {r[0]}: {r[1]} | {r[2]} | {r[3]} | Store ID: {r[4]}")

    print("\n--- Custom Products After Migration ---")
    for r in c.execute("SELECT id, store_id, product_name, quantity_on_hand, unit, batch_id, expiry_date FROM custom_products").fetchall():
        print(f"ID {r[0]}: Store: {r[1]} | Product: {r[2]} | Qty: {r[3]} {r[4]} | Batch: {r[5]} | Expiry: {r[6]}")

    conn.close()

    # 3. Migrate CSV datasets
    # Stores CSV
    stores_df = pd.read_csv(stores_file)
    stores_df.loc[stores_df["store_id"] == "STR-001", "store_id"] = "STR-LEGACY-001"
    # Ensure Lakshmi General Store is row 1
    if "STR-001" not in stores_df["store_id"].values:
        lakshmi_row = pd.DataFrame([{
            "store_id": "STR-001",
            "store_name": "Lakshmi General Store",
            "store_type": "Grocery & Fresh Foods",
            "city": "Hyderabad",
            "daily_foot_traffic": 850,
            "cooling_capacity_status": "Optimal",
            "data_notice": "ACTIVE_STORE",
        }])
        stores_df = pd.concat([lakshmi_row, stores_df], ignore_index=True)
    stores_df.to_csv(stores_file, index=False)
    print(f"\nUpdated stores.csv ({len(stores_df)} total stores). STR-001 is now Lakshmi General Store.")

    # Inventory CSV
    inv_df = pd.read_csv(inv_file)
    inv_str1_cnt = len(inv_df[inv_df["store_id"] == "STR-001"])
    inv_df.loc[inv_df["store_id"] == "STR-001", "store_id"] = "STR-LEGACY-001"
    inv_df.to_csv(inv_file, index=False)
    print(f"Updated inventory_batches.csv. Re-tagged {inv_str1_cnt} batches from STR-001 to STR-LEGACY-001.")

    # Sales history CSV
    sales_df = pd.read_csv(sales_file)
    sales_str1_cnt = len(sales_df[sales_df["store_id"] == "STR-001"])
    sales_df.loc[sales_df["store_id"] == "STR-001", "store_id"] = "STR-LEGACY-001"
    sales_df.to_csv(sales_file, index=False)
    print(f"Updated sales_history.csv. Re-tagged {sales_str1_cnt} sales records from STR-001 to STR-LEGACY-001.")

    print("\nMigration finished successfully!")


if __name__ == "__main__":
    run_migration()
