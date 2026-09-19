"""App-wide configurable settings (key/value store)."""
from database.db_manager import get_connection


def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def get_low_stock_threshold() -> int:
    return int(get_setting("low_stock_threshold", "10"))


def get_expiry_alert_days() -> int:
    return int(get_setting("expiry_alert_days", "30"))
