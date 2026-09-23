"""Billing / POS business logic: build a cart, compute totals, commit a sale
(insert sale + sale_items, deduct stock, track udhaar/credit) as one atomic
transaction, and process returns/refunds against a past sale."""
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from database.db_manager import get_connection
from logic import inventory

VALID_PAYMENT_METHODS = ("cash", "card", "easypaisa", "jazzcash", "bank", "udhaar")

PAYMENT_METHOD_LABELS = {
    "cash": "💵 Cash",
    "card": "💳 Card",
    "easypaisa": "📱 EasyPaisa",
    "jazzcash": "📱 JazzCash",
    "bank": "🏦 Bank Transfer",
    "udhaar": "📒 Udhaar (Credit)",
}


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


def checkout(
    cart: Cart,
    cashier_id: int,
    customer_id: int = None,
    payment_method: str = "cash",
    amount_paid: float = None,
    doctor_name: str = "",
) -> dict:
    """Commit the cart as a sale: creates sales + sale_items rows, deducts
    stock, and (if `amount_paid` is less than the total) adds the remainder
    to the selected customer's udhaar balance -- all inside one transaction.
    Returns a receipt dict for printing.

    `amount_paid=None` means "paid in full" (the whole total), except when
    payment_method is "udhaar", where it means "nothing paid now" (0) --
    matching what a cashier picking that method from a dropdown expects.
    """
    if not cart.items:
        raise ValueError("Cannot checkout an empty cart.")
    if cart.discount < 0:
        raise ValueError("Discount cannot be negative.")
    if cart.discount > cart.subtotal:
        raise ValueError("Discount cannot exceed the subtotal.")
    if payment_method not in VALID_PAYMENT_METHODS:
        raise ValueError(f"Unknown payment method '{payment_method}'.")

    total = cart.total
    if amount_paid is None:
        amount_paid = 0.0 if payment_method == "udhaar" else total
    if amount_paid < 0:
        raise ValueError("Amount paid cannot be negative.")
    if amount_paid > total + 0.005:
        raise ValueError("Amount paid cannot be more than the sale total.")

    credit_amount = round(total - amount_paid, 2)
    if credit_amount > 0.005 and customer_id is None:
        raise ValueError(
            "A walk-in sale must be paid in full -- select a customer to extend udhaar (credit)."
        )

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
                    "INSERT INTO sales (invoice_no, customer_id, cashier_id, total_amount, discount, "
                    "tax, payment_method, amount_paid, doctor_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        invoice_no, customer_id, cashier_id, total, cart.discount,
                        cart.tax_amount, payment_method, amount_paid, doctor_name.strip() or None,
                    ),
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

        if credit_amount > 0.005:
            conn.execute(
                "UPDATE customers SET credit_balance = credit_balance + ? WHERE id = ?",
                (credit_amount, customer_id),
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
        "total": total,
        "customer_id": customer_id,
        "cashier_id": cashier_id,
        "payment_method": payment_method,
        "amount_paid": amount_paid,
        "credit_amount": credit_amount,
        "doctor_name": doctor_name.strip(),
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


def process_return(sale_item_id: int, quantity: int, reason: str, processed_by: int) -> dict:
    """Return `quantity` units of one sale line item: restocks inventory and
    logs the refund. If the original sale still has an unpaid (udhaar)
    balance, the refund reduces that balance first rather than handing back
    cash that was never actually collected; any amount beyond what's still
    owed is a cash refund. Returns how much of each so the cashier knows
    what to actually hand back."""
    if quantity <= 0:
        raise ValueError("Return quantity must be positive.")

    conn = get_connection()
    try:
        item = conn.execute("SELECT * FROM sale_items WHERE id=?", (sale_item_id,)).fetchone()
        if item is None:
            raise ValueError("Sale item not found.")
        remaining = item["quantity"] - item["returned_qty"]
        if quantity > remaining:
            raise ValueError(f"Only {remaining} unit(s) can still be returned from this line.")

        sale = conn.execute("SELECT * FROM sales WHERE id=?", (item["sale_id"],)).fetchone()
        refund_amount = round(item["unit_price"] * quantity, 2)

        conn.execute(
            "UPDATE sale_items SET returned_qty = returned_qty + ? WHERE id=?", (quantity, sale_item_id)
        )
        conn.execute(
            "UPDATE medicines SET quantity = quantity + ?, updated_at=datetime('now','localtime') WHERE id=?",
            (quantity, item["medicine_id"]),
        )
        conn.execute(
            "INSERT INTO sale_returns (sale_id, sale_item_id, medicine_id, quantity, refund_amount, "
            "reason, processed_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (item["sale_id"], sale_item_id, item["medicine_id"], quantity, refund_amount,
             reason.strip(), processed_by),
        )

        credit_reduction = 0.0
        if sale["customer_id"] is not None:
            outstanding = round(sale["total_amount"] - sale["amount_paid"], 2)
            if outstanding > 0.005:
                credit_reduction = min(refund_amount, outstanding)
                conn.execute(
                    "UPDATE customers SET credit_balance = credit_balance - ? WHERE id=?",
                    (credit_reduction, sale["customer_id"]),
                )
                conn.execute(
                    "UPDATE sales SET amount_paid = amount_paid + ? WHERE id=?",
                    (credit_reduction, sale["id"]),
                )

        all_items = conn.execute(
            "SELECT quantity, returned_qty FROM sale_items WHERE sale_id=?", (sale["id"],)
        ).fetchall()
        if all(r["quantity"] == r["returned_qty"] for r in all_items):
            conn.execute("UPDATE sales SET is_refunded=1 WHERE id=?", (sale["id"],))

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "refund_amount": refund_amount,
        "credit_reduction": credit_reduction,
        "cash_refund": round(refund_amount - credit_reduction, 2),
    }


def returnable_sales(search: str = "", limit: int = 100) -> list[dict]:
    """Recent sales that still have at least one unreturned unit, for the
    Returns screen to search against."""
    conn = get_connection()
    try:
        query = """
            SELECT s.id, s.invoice_no, s.date, s.total_amount,
                   COALESCE(c.name, 'Walk-in') AS customer_name
            FROM sales s
            LEFT JOIN customers c ON c.id = s.customer_id
            WHERE EXISTS (
                SELECT 1 FROM sale_items si WHERE si.sale_id = s.id AND si.quantity > si.returned_qty
            )
        """
        params: list = []
        if search:
            query += " AND s.invoice_no LIKE ?"
            params.append(f"%{search}%")
        query += " ORDER BY s.date DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
