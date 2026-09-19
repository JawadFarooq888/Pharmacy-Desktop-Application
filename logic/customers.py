"""Customer business logic."""
from dataclasses import dataclass
from typing import Optional

from database.db_manager import get_connection


@dataclass
class Customer:
    id: int
    name: str
    phone: str


def _row_to_customer(row) -> Customer:
    return Customer(id=row["id"], name=row["name"], phone=row["phone"] or "")


def list_customers(search: str = "") -> list[Customer]:
    conn = get_connection()
    try:
        if search:
            rows = conn.execute(
                "SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY name",
                (f"%{search}%", f"%{search}%"),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM customers ORDER BY name").fetchall()
        return [_row_to_customer(r) for r in rows]
    finally:
        conn.close()


def get_customer(customer_id: int) -> Optional[Customer]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
        return _row_to_customer(row) if row else None
    finally:
        conn.close()


def add_customer(name: str, phone: str) -> Customer:
    if not name or not name.strip():
        raise ValueError("Customer name is required.")
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO customers (name, phone) VALUES (?, ?)", (name.strip(), phone.strip())
        )
        conn.commit()
        new_id = cur.lastrowid
    finally:
        conn.close()
    return get_customer(new_id)


def update_customer(customer_id: int, name: str, phone: str) -> Customer:
    if not name or not name.strip():
        raise ValueError("Customer name is required.")
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE customers SET name=?, phone=? WHERE id=?", (name.strip(), phone.strip(), customer_id)
        )
        conn.commit()
    finally:
        conn.close()
    return get_customer(customer_id)


def delete_customer(customer_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute("UPDATE sales SET customer_id = NULL WHERE customer_id = ?", (customer_id,))
        conn.execute("DELETE FROM customers WHERE id=?", (customer_id,))
        conn.commit()
    finally:
        conn.close()


def sales_history(customer_id: int) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, invoice_no, date, total_amount FROM sales WHERE customer_id=? ORDER BY date DESC",
            (customer_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
