"""SQLite connection management and schema initialization.

Resolves paths relative to the project root during normal development, so
`python main.py` reads/writes files right there in the repo. When frozen by
PyInstaller, data instead lives under the current user's %LOCALAPPDATA%
(NOT next to the .exe): the installer may place the executable in
Program Files, which a normal (non-elevated) running process cannot write
to, so storing data there would break saving on first use.
"""
import os
import sqlite3
import sys
from pathlib import Path

from logic.security import hash_password


def get_app_dir() -> Path:
    """Directory that holds data/, backups/, and invoices/."""
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "PharmacyManagementSystem"
    return Path(__file__).resolve().parent.parent


APP_DIR = get_app_dir()
DATA_DIR = APP_DIR / "data"
BACKUP_DIR = APP_DIR / "backups"
DB_PATH = DATA_DIR / "pharmacy.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"


def get_connection() -> sqlite3.Connection:
    """Open a new connection with sane defaults (foreign keys, dict-like rows)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """ALTER TABLE ... ADD COLUMN if it's not already there. CREATE TABLE IF
    NOT EXISTS in schema.sql is a no-op on an already-existing table, so
    every column added to an existing table after its first release needs
    an explicit migration step like this one for older installs to pick it
    up without losing their data."""
    columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        conn.commit()


def _run_migrations(conn: sqlite3.Connection) -> None:
    _add_column_if_missing(conn, "medicines", "barcode", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_medicines_barcode ON medicines(barcode)")

    _add_column_if_missing(conn, "medicines", "is_controlled_substance", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "customers", "credit_balance", "REAL NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "sales", "payment_method", "TEXT NOT NULL DEFAULT 'cash'")
    _add_column_if_missing(conn, "sales", "amount_paid", "REAL NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "sales", "doctor_name", "TEXT")
    _add_column_if_missing(conn, "sales", "is_refunded", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "sale_items", "returned_qty", "INTEGER NOT NULL DEFAULT 0")
    conn.commit()

    # Older sales predate amount_paid tracking (it defaults to 0). Backfill
    # them as fully paid in cash exactly once -- this must NOT re-run on
    # every startup, since a legitimate 100%-credit sale also has
    # amount_paid=0 by design and would otherwise get silently "paid off"
    # the next time the app starts.
    already_backfilled = conn.execute(
        "SELECT 1 FROM settings WHERE key='amount_paid_backfilled'"
    ).fetchone()
    if not already_backfilled:
        conn.execute(
            "UPDATE sales SET amount_paid = total_amount, payment_method = 'cash' "
            "WHERE amount_paid = 0 AND payment_method = 'cash'"
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('amount_paid_backfilled', '1')"
        )
        conn.commit()


def init_db() -> None:
    """Create tables if missing and seed a default admin user on first run."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_connection()
    try:
        conn.executescript(schema_sql)
        conn.commit()

        _run_migrations(conn)

        cur = conn.execute("SELECT COUNT(*) AS c FROM users")
        if cur.fetchone()["c"] == 0:
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role) "
                "VALUES (?, ?, ?, 'admin')",
                (
                    DEFAULT_ADMIN_USERNAME,
                    hash_password(DEFAULT_ADMIN_PASSWORD),
                    "Administrator",
                ),
            )
            conn.commit()

        # Seed default configurable settings if absent.
        defaults = {
            "low_stock_threshold": "10",
            "expiry_alert_days": "30",
        }
        for key, value in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        conn.commit()
    finally:
        conn.close()
