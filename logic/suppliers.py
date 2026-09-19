"""Supplier business logic (basic CRUD + purchase-order stock intake)."""
from dataclasses import dataclass
from typing import Optional

from database.db_manager import get_connection


@dataclass
class Supplier:
    id: int
    name: str
    contact: str
    address: str


def _row_to_supplier(row) -> Supplier:
    return Supplier(id=row["id"], name=row["name"], contact=row["contact"] or "", address=row["address"] or "")


def list_suppliers() -> list[Supplier]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
        return [_row_to_supplier(r) for r in rows]
    finally:
        conn.close()


def get_supplier(supplier_id: int) -> Optional[Supplier]:
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM suppliers WHERE id=?", (supplier_id,)).fetchone()
        return _row_to_supplier(row) if row else None
    finally:
        conn.close()


def add_supplier(name: str, contact: str, address: str) -> Supplier:
    if not name or not name.strip():
        raise ValueError("Supplier name is required.")
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO suppliers (name, contact, address) VALUES (?, ?, ?)",
            (name.strip(), contact.strip(), address.strip()),
        )
        conn.commit()
        new_id = cur.lastrowid
    finally:
        conn.close()
    return get_supplier(new_id)


def update_supplier(supplier_id: int, name: str, contact: str, address: str) -> Supplier:
    if not name or not name.strip():
        raise ValueError("Supplier name is required.")
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE suppliers SET name=?, contact=?, address=? WHERE id=?",
            (name.strip(), contact.strip(), address.strip(), supplier_id),
        )
        conn.commit()
    finally:
        conn.close()
    return get_supplier(supplier_id)


def delete_supplier(supplier_id: int) -> None:
    conn = get_connection()
    try:
        in_use = conn.execute(
            "SELECT COUNT(*) AS c FROM medicines WHERE supplier_id=? AND is_active=1", (supplier_id,)
        ).fetchone()["c"]
        if in_use:
            raise ValueError(
                f"Cannot delete: {in_use} medicine(s) still reference this supplier."
            )
        conn.execute("DELETE FROM suppliers WHERE id=?", (supplier_id,))
        conn.commit()
    finally:
        conn.close()


def record_purchase_order(medicine_id: int, quantity: int, new_batch_no: str, new_expiry_date: str, new_purchase_price: Optional[float] = None) -> None:
    """Receive new stock from a supplier: bump quantity and update batch/expiry.

    Simplification note: this project tracks one batch/expiry per medicine row
    (matching the fixed `medicines` schema in the spec) rather than per-batch
    lots, so receiving stock overwrites batch_no/expiry_date with the newest.
    """
    if quantity <= 0:
        raise ValueError("Received quantity must be positive.")
    from logic import inventory

    conn = get_connection()
    try:
        row = conn.execute("SELECT quantity FROM medicines WHERE id=?", (medicine_id,)).fetchone()
        if row is None:
            raise ValueError("Medicine not found.")
        new_qty = row["quantity"] + quantity
        if new_purchase_price is not None:
            conn.execute(
                "UPDATE medicines SET quantity=?, batch_no=?, expiry_date=?, purchase_price=?, "
                "updated_at=datetime('now','localtime') WHERE id=?",
                (new_qty, new_batch_no.strip(), new_expiry_date, new_purchase_price, medicine_id),
            )
        else:
            conn.execute(
                "UPDATE medicines SET quantity=?, batch_no=?, expiry_date=?, "
                "updated_at=datetime('now','localtime') WHERE id=?",
                (new_qty, new_batch_no.strip(), new_expiry_date, medicine_id),
            )
        conn.commit()
    finally:
        conn.close()
