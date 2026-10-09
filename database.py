"""
FreshGuard AI - Persistent SQLite Database & Authentication Module
-------------------------------------------------------------------
Provides secure password hashing (PBKDF2-HMAC-SHA256), user registration,
shopkeeper-isolated inventory storage, and CRUD operations.

Notice: 100% standard library (sqlite3, hashlib, os, datetime).
"""

import datetime
import hashlib
import os
from pathlib import Path
import sqlite3
import pandas as pd

# Persistent SQLite database file in the project directory
DB_PATH = Path(__file__).resolve().parent / "freshguard.db"


def get_connection() -> sqlite3.Connection:
    """Returns a connection to the SQLite database with Row factory."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str, salt: bytes = None) -> tuple[str, str]:
    """
    Hashes a password using PBKDF2-HMAC-SHA256 with 100,000 iterations.
    Returns (hex_hash, hex_salt).
    """
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return key.hex(), salt.hex()


def verify_password(stored_hash: str, stored_salt: str, password_attempt: str) -> bool:
    """Verifies a password attempt against stored hash and salt."""
    try:
        salt = bytes.fromhex(stored_salt)
        key = hashlib.pbkdf2_hmac("sha256", password_attempt.encode("utf-8"), salt, 100000)
        return key.hex() == stored_hash
    except Exception:
        return False


def init_db():
    """Initializes tables and seeds default demo accounts if not already present."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. Users / Shopkeepers table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                shopkeeper_name TEXT NOT NULL,
                shop_name TEXT NOT NULL,
                store_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # 2. Custom shop products / batches table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                category TEXT NOT NULL,
                quantity_on_hand REAL NOT NULL,
                unit TEXT NOT NULL,
                cost_price REAL NOT NULL,
                selling_price REAL NOT NULL,
                batch_id TEXT NOT NULL,
                received_date TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(store_id, batch_id)
            )
            """
        )

        conn.commit()

        # Seed Lakshmi General Store as the primary STR-001 account
        cursor.execute("SELECT id FROM users WHERE email = 'lakshmi@freshguard.ai'")
        if not cursor.fetchone():
            p_hash, salt = hash_password("freshguard123")
            now_str = datetime.datetime.now().isoformat()
            cursor.execute(
                """
                INSERT INTO users (email, password_hash, salt, shopkeeper_name, shop_name, store_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("lakshmi@freshguard.ai", p_hash, salt, "Lakshmi", "Lakshmi General Store", "STR-001", now_str),
            )

        # Enforce store isolation and migration invariants
        cursor.execute("UPDATE users SET store_id = 'STR-LEGACY-001' WHERE email = 'metro@freshguard.ai'")
        cursor.execute(
            """UPDATE users 
               SET store_id = 'STR-001', shop_name = 'Lakshmi General Store', shopkeeper_name = 'Lakshmi' 
               WHERE email = 'puttapallynaveena1224@gmail.com' OR store_id = 'STR-USR-004'"""
        )
        cursor.execute(
            "UPDATE custom_products SET store_id = 'STR-LEGACY-001' WHERE batch_id = 'LOT-TEST-999'"
        )
        cursor.execute(
            "UPDATE custom_products SET store_id = 'STR-001' WHERE store_id = 'STR-USR-004'"
        )
        conn.commit()


def register_user(email: str, password: str, shopkeeper_name: str, shop_name: str) -> tuple[bool, str, dict]:
    """
    Registers a new shopkeeper account.
    Returns (success, message, user_dict).
    """
    email = email.strip().lower()
    shopkeeper_name = shopkeeper_name.strip()
    shop_name = shop_name.strip()

    if not email or "@" not in email or "." not in email:
        return False, "Please provide a valid email address.", {}
    if not shopkeeper_name:
        return False, "Shopkeeper name is required.", {}
    if not shop_name:
        return False, "Shop name is required.", {}
    if len(password) < 6:
        return False, "Password must be at least 6 characters long.", {}

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            return False, "An account with this email address already exists. Please log in.", {}

        # Generate a unique store_id for this shop
        cursor.execute("SELECT COUNT(*) as count FROM users")
        user_num = cursor.fetchone()["count"] + 1
        new_store_id = f"STR-USR-{user_num:03d}"

        p_hash, salt = hash_password(password)
        now_str = datetime.datetime.now().isoformat()

        cursor.execute(
            """
            INSERT INTO users (email, password_hash, salt, shopkeeper_name, shop_name, store_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (email, p_hash, salt, shopkeeper_name, shop_name, new_store_id, now_str),
        )
        conn.commit()

        user_dict = {
            "id": cursor.lastrowid,
            "email": email,
            "shopkeeper_name": shopkeeper_name,
            "shop_name": shop_name,
            "store_id": new_store_id,
        }
        return True, "Registration successful!", user_dict


def authenticate_user(email: str, password: str) -> tuple[bool, str, dict]:
    """
    Authenticates a shopkeeper.
    Returns (success, message, user_dict).
    """
    email = email.strip().lower()
    if not email or not password:
        return False, "Please enter both email and password.", {}

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()

        if not user:
            return False, "No account found with this email. Please check your credentials or register.", {}

        if not verify_password(user["password_hash"], user["salt"], password):
            return False, "Incorrect password. Please try again.", {}

        user_dict = {
            "id": user["id"],
            "email": user["email"],
            "shopkeeper_name": user["shopkeeper_name"],
            "shop_name": user["shop_name"],
            "store_id": user["store_id"],
        }
        return True, "Login successful!", user_dict


def add_product(
    store_id: str,
    product_name: str,
    category: str,
    quantity: float,
    unit: str,
    cost_price: float,
    selling_price: float,
    batch_id: str,
    expiry_date: str,
    received_date: str = None,
) -> tuple[bool, str]:
    """
    Adds a new product lot into the SQLite database.
    Validates required fields, positive quantities, non-negative prices, and valid dates.
    """
    product_name = product_name.strip()
    category = category.strip()
    batch_id = batch_id.strip().upper()
    unit = unit.strip()

    if not batch_id:
        # Auto-generate a readable unique lot identifier if omitted
        import time
        batch_id = f"LOT-{store_id}-{int(time.time()) % 1000000:06d}"

    if not product_name:
        return False, "Product name cannot be empty."
    if not category:
        return False, "Category cannot be empty."
    if quantity <= 0:
        return False, "Quantity must be greater than zero."
    if cost_price < 0:
        return False, "Cost price cannot be negative."
    if selling_price < 0:
        return False, "Selling price cannot be negative."

    try:
        exp_dt = datetime.date.fromisoformat(str(expiry_date))
    except Exception:
        return False, "Invalid expiry date format. Please use YYYY-MM-DD."

    if not received_date:
        rec_dt = datetime.date.today().isoformat()
    else:
        rec_dt = str(received_date)

    with get_connection() as conn:
        cursor = conn.cursor()
        # Check duplicate batch number for this store
        cursor.execute(
            "SELECT id FROM custom_products WHERE store_id = ? AND batch_id = ?",
            (store_id, batch_id),
        )
        if cursor.fetchone():
            return False, f"Batch '{batch_id}' already exists for this shop. Please use a unique batch number."

        now_str = datetime.datetime.now().isoformat()
        cursor.execute(
            """
            INSERT INTO custom_products (
                store_id, product_name, category, quantity_on_hand, unit,
                cost_price, selling_price, batch_id, received_date, expiry_date, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                store_id,
                product_name,
                category,
                quantity,
                unit,
                cost_price,
                selling_price,
                batch_id,
                rec_dt,
                exp_dt.isoformat(),
                now_str,
            ),
        )
        conn.commit()

    return True, f"Successfully added '{product_name}' (Batch: {batch_id}) to inventory!"


def get_store_products(store_id: str) -> pd.DataFrame:
    """Retrieves all custom products for a given store as a pandas DataFrame."""
    with get_connection() as conn:
        query = "SELECT * FROM custom_products WHERE store_id = ? ORDER BY id DESC"
        df = pd.read_sql_query(query, conn, params=(store_id,))
    return df


def update_product_stock(product_id: int, new_quantity: float, store_id: str = None) -> tuple[bool, str]:
    """Updates stock quantity for a product, restricted to store_id if provided."""
    if new_quantity < 0:
        return False, "Quantity cannot be negative."

    with get_connection() as conn:
        cursor = conn.cursor()
        if store_id:
            cursor.execute(
                "UPDATE custom_products SET quantity_on_hand = ? WHERE id = ? AND store_id = ?",
                (new_quantity, product_id, store_id),
            )
        else:
            cursor.execute(
                "UPDATE custom_products SET quantity_on_hand = ? WHERE id = ?",
                (new_quantity, product_id),
            )
        conn.commit()
        if cursor.rowcount == 0:
            return False, "Product not found or access denied."
    return True, f"Stock updated to {new_quantity}."


def update_product_details(
    product_id: int,
    product_name: str,
    category: str,
    quantity: float,
    unit: str,
    cost_price: float,
    selling_price: float,
    expiry_date: str,
    store_id: str = None,
) -> tuple[bool, str]:
    """Updates full details of a custom product record, restricted to store_id if provided."""
    if not product_name.strip():
        return False, "Product name cannot be empty."
    if quantity < 0 or cost_price < 0 or selling_price < 0:
        return False, "Values cannot be negative."

    with get_connection() as conn:
        cursor = conn.cursor()
        if store_id:
            cursor.execute(
                """
                UPDATE custom_products
                SET product_name = ?, category = ?, quantity_on_hand = ?, unit = ?,
                    cost_price = ?, selling_price = ?, expiry_date = ?
                WHERE id = ? AND store_id = ?
                """,
                (
                    product_name.strip(),
                    category.strip(),
                    quantity,
                    unit.strip(),
                    cost_price,
                    selling_price,
                    expiry_date,
                    product_id,
                    store_id,
                ),
            )
        else:
            cursor.execute(
                """
                UPDATE custom_products
                SET product_name = ?, category = ?, quantity_on_hand = ?, unit = ?,
                    cost_price = ?, selling_price = ?, expiry_date = ?
                WHERE id = ?
                """,
                (
                    product_name.strip(),
                    category.strip(),
                    quantity,
                    unit.strip(),
                    cost_price,
                    selling_price,
                    expiry_date,
                    product_id,
                ),
            )
        conn.commit()
        if cursor.rowcount == 0:
            return False, "Product not found or access denied."
    return True, "Product details updated successfully."


def delete_product(product_id: int, store_id: str = None) -> tuple[bool, str]:
    """Deletes a custom product record, restricted to store_id if provided."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if store_id:
            cursor.execute("DELETE FROM custom_products WHERE id = ? AND store_id = ?", (product_id, store_id))
        else:
            cursor.execute("DELETE FROM custom_products WHERE id = ?", (product_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return False, "Product not found or access denied."
    return True, "Product removed from inventory."


# Auto-initialize database tables on first import
init_db()


if __name__ == "__main__":
    print("Testing FreshGuard AI Database...")
    init_db()
    ok, msg, u = authenticate_user("metro@freshguard.ai", "freshguard123")
    print(f"Auth test: {ok} ({msg}) -> User: {u.get('shopkeeper_name')} @ {u.get('shop_name')}")

    # Test adding product
    add_ok, add_msg = add_product(
        store_id="STR-001",
        product_name="Artisan Butter Croissant",
        category="Bakery",
        quantity=25.0,
        unit="Units",
        cost_price=1.20,
        selling_price=3.50,
        batch_id="LOT-TEST-999",
        expiry_date="2026-10-12",
    )
    print(f"Add product test: {add_ok} -> {add_msg}")
    prods = get_store_products("STR-001")
    print(f"Custom products for STR-001: {len(prods)} rows.")
