"""Billing / POS business logic: build a cart, compute totals, and commit a sale
as one atomic transaction (insert sale + sale_items, deduct stock)."""
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from database.db_manager import get_connection
from logic import inventory


@dataclass
class CartItem:
    medicine_id: int
    name: str
    unit_price: float
    quantity: int
    available_stock: int

    @property
    def subtotal(self) -> float:
        return round(self.unit_price * self.quantity, 2)


@dataclass
class Cart:
    items: list = field(default_factory=list)
    discount: float = 0.0
    tax_percent: float = 0.0

    def add(self, medicine: inventory.Medicine, quantity: int):
        if quantity <= 0:
            raise ValueError("Quantity must be positive.")
        for item in self.items:
            if item.medicine_id == medicine.id:
                new_qty = item.quantity + quantity
                if new_qty > medicine.quantity:
                    raise ValueError(
                        f"Only {medicine.quantity} unit(s) of '{medicine.name}' in stock."
                    )
                item.quantity = new_qty
                return
        if quantity > medicine.quantity:
            raise ValueError(f"Only {medicine.quantity} unit(s) of '{medicine.name}' in stock.")
        self.items.append(
            CartItem(
                medicine_id=medicine.id,
                name=medicine.name,
                unit_price=medicine.sale_price,
                quantity=quantity,
                available_stock=medicine.quantity,
            )
        )

    def update_quantity(self, medicine_id: int, quantity: int):
        for item in self.items:
            if item.medicine_id == medicine_id:
                if quantity <= 0:
                    self.remove(medicine_id)
                    return
                if quantity > item.available_stock:
                    raise ValueError(f"Only {item.available_stock} unit(s) of '{item.name}' in stock.")
                item.quantity = quantity
                return

    def remove(self, medicine_id: int):
        self.items = [i for i in self.items if i.medicine_id != medicine_id]

    def clear(self):
        self.items = []
        self.discount = 0.0
        self.tax_percent = 0.0

    @property
    def subtotal(self) -> float:
        return round(sum(i.subtotal for i in self.items), 2)

    @property
    def tax_amount(self) -> float:
        return round((self.subtotal - self.discount) * (self.tax_percent / 100), 2)

    @property
    def total(self) -> float:
        return round(self.subtotal - self.discount + self.tax_amount, 2)


def _generate_invoice_no(conn) -> str:
    today = datetime.now().strftime("%Y%m%d")
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM sales WHERE invoice_no LIKE ?", (f"INV-{today}-%",)
    ).fetchone()
    seq = row["c"] + 1
    return f"INV-{today}-{seq:04d}"


def checkout(cart: Cart, cashier_id: int, customer_id: int = None) -> dict:
    """Commit the cart as a sale: creates sales + sale_items rows and deducts
    stock, all inside one transaction. Returns a receipt dict for printing."""
    if not cart.items:
        raise ValueError("Cannot checkout an empty cart.")
    if cart.discount < 0:
        raise ValueError("Discount cannot be negative.")
    if cart.discount > cart.subtotal:
        raise ValueError("Discount cannot exceed the subtotal.")

    conn = get_connection()
    try:
        # Re-check stock against the live DB right before committing, in case
        # another sale happened concurrently.
        for item in cart.items:
            row = conn.execute(
                "SELECT quantity, name FROM medicines WHERE id=? AND is_active=1", (item.medicine_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Medicine '{item.name}' no longer exists.")
            if row["quantity"] < item.quantity:
                raise ValueError(
                    f"Only {row['quantity']} unit(s) of '{row['name']}' available now."
                )

        # Two checkouts landing in the same instant (e.g. the app open in two
        # windows at once) could both compute the same next invoice number;
        # retry with a freshly regenerated one rather than losing the sale.
        max_attempts = 5
        for attempt in range(max_attempts):
            invoice_no = _generate_invoice_no(conn)
            try:
                cur = conn.execute(
                    "INSERT INTO sales (invoice_no, customer_id, cashier_id, total_amount, discount, tax) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (invoice_no, customer_id, cashier_id, cart.total, cart.discount, cart.tax_amount),
                )
                sale_id = cur.lastrowid
                break
            except sqlite3.IntegrityError:
                if attempt == max_attempts - 1:
                    raise
                continue

        for item in cart.items:
            conn.execute(
                "INSERT INTO sale_items (sale_id, medicine_id, quantity, unit_price, subtotal) "
                "VALUES (?, ?, ?, ?, ?)",
                (sale_id, item.medicine_id, item.quantity, item.unit_price, item.subtotal),
            )
            conn.execute(
                "UPDATE medicines SET quantity = quantity - ?, updated_at=datetime('now','localtime') "
                "WHERE id = ?",
                (item.quantity, item.medicine_id),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "invoice_no": invoice_no,
        "sale_id": sale_id,
        "items": list(cart.items),
        "subtotal": cart.subtotal,
        "discount": cart.discount,
        "tax": cart.tax_amount,
        "total": cart.total,
        "customer_id": customer_id,
        "cashier_id": cashier_id,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_sale_with_items(sale_id: int) -> dict:
    conn = get_connection()
    try:
        sale = conn.execute(
            """
            SELECT s.*, c.name AS customer_name, u.username AS cashier_name
            FROM sales s
            LEFT JOIN customers c ON c.id = s.customer_id
            LEFT JOIN users u ON u.id = s.cashier_id
            WHERE s.id = ?
            """,
            (sale_id,),
        ).fetchone()
        if sale is None:
            return None
        items = conn.execute(
            """
            SELECT si.*, m.name AS medicine_name
            FROM sale_items si
            JOIN medicines m ON m.id = si.medicine_id
            WHERE si.sale_id = ?
            """,
            (sale_id,),
        ).fetchall()
        return {"sale": dict(sale), "items": [dict(i) for i in items]}
    finally:
        conn.close()
