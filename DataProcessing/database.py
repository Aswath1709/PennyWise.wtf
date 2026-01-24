# DataProcessing/database.py

"""
SQLite Database Storage for Transactions
"""

import sqlite3
import hashlib
import pandas as pd
from pathlib import Path

import sys

sys.path.append(str(Path(__file__).parent.parent))
from config import DB_PATH, DATA_DIR


# ========== INITIALIZATION ==========

def init_db():
    """Create database tables if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)

    # Transactions table with unique hash to prevent duplicates
    conn.execute("""
                 CREATE TABLE IF NOT EXISTS transactions
                 (
                     id
                     INTEGER
                     PRIMARY
                     KEY
                     AUTOINCREMENT,
                     date
                     TEXT,
                     description
                     TEXT,
                     amount
                     REAL,
                     category
                     TEXT,
                     card_type
                     TEXT,
                     bank
                     TEXT,
                     txn_hash
                     TEXT
                     UNIQUE,
                     source_file
                     TEXT,
                     created_at
                     TIMESTAMP
                     DEFAULT
                     CURRENT_TIMESTAMP
                 )
                 """)

    # Track imported files
    conn.execute("""
                 CREATE TABLE IF NOT EXISTS imported_files
                 (
                     id
                     INTEGER
                     PRIMARY
                     KEY
                     AUTOINCREMENT,
                     filename
                     TEXT
                     UNIQUE,
                     filepath
                     TEXT,
                     transaction_count
                     INTEGER,
                     imported_at
                     TIMESTAMP
                     DEFAULT
                     CURRENT_TIMESTAMP
                 )
                 """)

    # Migration: Add card_type and bank columns if they don't exist
    _migrate_add_columns(conn)

    conn.commit()
    conn.close()


def _migrate_add_columns(conn):
    """Add new columns to existing database if they don't exist."""
    cursor = conn.execute("PRAGMA table_info(transactions)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'card_type' not in columns:
        conn.execute("ALTER TABLE transactions ADD COLUMN card_type TEXT")

    if 'bank' not in columns:
        conn.execute("ALTER TABLE transactions ADD COLUMN bank TEXT")


# ========== HELPER FUNCTIONS ==========

def _generate_txn_hash(date: str, description: str, amount: float) -> str:
    """Generate unique hash for a transaction to detect duplicates."""
    unique_string = f"{date}|{description}|{amount}"
    return hashlib.md5(unique_string.encode()).hexdigest()


def is_file_imported(filename: str) -> bool:
    """Check if a file has already been imported."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        "SELECT 1 FROM imported_files WHERE filename = ?",
        (filename,)
    )
    result = cursor.fetchone() is not None
    conn.close()
    return result


def get_imported_files() -> pd.DataFrame:
    """Get list of all imported files."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT filename, transaction_count, imported_at FROM imported_files ORDER BY imported_at DESC",
                     conn)
    conn.close()
    return df


# ========== SAVE ==========

def save_transactions(df: pd.DataFrame, source_file: str = None, card_type: str = None, bank: str = None) -> dict:
    """
    Save transactions to database, skipping duplicates.

    Args:
        df: DataFrame with Date, Description, Amount, Category columns
        source_file: Optional filename for tracking
        card_type: "credit" or "debit"
        bank: Bank name (e.g., "Chase")

    Returns:
        Dict with saved_count, skipped_count, already_imported
    """
    init_db()

    # Check if file already imported
    if source_file and is_file_imported(source_file):
        print(f"⚠️  File '{source_file}' already imported. Skipping.")
        return {"saved_count": 0, "skipped_count": 0, "already_imported": True}

    conn = sqlite3.connect(DB_PATH)

    # Prepare data
    df_save = df.copy()
    df_save['date'] = df_save['Date'].dt.strftime('%Y-%m-%d')

    saved_count = 0
    skipped_count = 0

    for _, row in df_save.iterrows():
        date = row['date']
        description = row['Description']
        amount = row['Amount']
        category = row['Category']
        txn_hash = _generate_txn_hash(date, description, amount)

        try:
            conn.execute(
                """INSERT INTO transactions (date, description, amount, category, card_type, bank, txn_hash,
                                             source_file)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (date, description, amount, category, card_type, bank, txn_hash, source_file)
            )
            saved_count += 1
        except sqlite3.IntegrityError:
            # Duplicate transaction (same hash)
            skipped_count += 1

    # Track imported file
    if source_file:
        conn.execute(
            "INSERT OR REPLACE INTO imported_files (filename, filepath, transaction_count) VALUES (?, ?, ?)",
            (source_file, source_file, saved_count)
        )

    conn.commit()
    conn.close()

    print(f"✓ Saved {saved_count} new transactions")
    if skipped_count > 0:
        print(f"⚠️  Skipped {skipped_count} duplicate transactions")

    return {"saved_count": saved_count, "skipped_count": skipped_count, "already_imported": False}


# ========== LOAD ==========

def load_transactions() -> pd.DataFrame:
    """Load all transactions from database."""
    init_db()

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT * FROM transactions", conn)
    conn.close()

    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])

    return df


# ========== QUERY ==========

def run_query(sql: str) -> pd.DataFrame:
    """
    Run a SELECT query.
    Only allows SELECT for safety.
    """
    sql_lower = sql.strip().lower()

    if not sql_lower.startswith("select"):
        raise ValueError("Only SELECT queries allowed")

    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(sql, conn)
    conn.close()

    return df


# ========== SUMMARY ==========

def get_summary() -> dict:
    """Get database summary."""
    df = load_transactions()

    if df.empty:
        return {"status": "Database is empty"}

    return {
        "total_transactions": len(df),
        "date_range": f"{df['date'].min().date()} to {df['date'].max().date()}",
        "categories": df['category'].unique().tolist(),
        "total_income": float(df[df['amount'] > 0]['amount'].sum()),
        "total_expenses": float(abs(df[df['amount'] < 0]['amount'].sum()))
    }


# ========== CLEAR ==========

def clear_transactions():
    """Delete all transactions. Use with caution."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM transactions")
    conn.commit()
    conn.close()
    print("All transactions deleted")


# ========== CLI ==========

if __name__ == "__main__":
    summary = get_summary()
    print("Database Summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")