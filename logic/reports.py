"""Reporting business logic: daily/monthly sales, profit/loss, expiry-wise stock.

Profit/loss note: sale_items stores the sale price at time of sale but not a
historical cost price, so profit is computed using each medicine's *current*
purchase_price. This matches the fixed schema in the spec; if precise historical
costing is ever needed, sale_items would need its own cost_price column.
"""
from datetime import date, timedelta

from database.db_manager import get_connection


def daily_sales_report(report_date: str) -> dict:
    """report_date: 'YYYY-MM-DD'."""
    conn = get_connection()
    try:
        sales = conn.execute(
            """
            SELECT s.id, s.invoice_no, s.date, s.total_amount, s.discount, s.tax,
                   COALESCE(c.name, 'Walk-in') AS customer_name, u.username AS cashier_name
            FROM sales s
            LEFT JOIN customers c ON c.id = s.customer_id
            LEFT JOIN users u ON u.id = s.cashier_id
            WHERE date(s.date) = ?
            ORDER BY s.date
            """,
            (report_date,),
        ).fetchall()
        rows = [dict(r) for r in sales]
        totals = {
            "count": len(rows),
            "total_amount": round(sum(r["total_amount"] for r in rows), 2),
            "total_discount": round(sum(r["discount"] for r in rows), 2),
            "total_tax": round(sum(r["tax"] for r in rows), 2),
        }
        return {"date": report_date, "sales": rows, "totals": totals}
    finally:
        conn.close()


def monthly_sales_report(year: int, month: int) -> dict:
    month_str = f"{year:04d}-{month:02d}"
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT date(date) AS day, COUNT(*) AS count, SUM(total_amount) AS total,
                   SUM(discount) AS discount, SUM(tax) AS tax
            FROM sales
            WHERE strftime('%Y-%m', date) = ?
            GROUP BY date(date)
            ORDER BY day
            """,
            (month_str,),
        ).fetchall()
        daily_breakdown = [dict(r) for r in rows]
        totals = {
            "count": sum(r["count"] for r in daily_breakdown),
            "total_amount": round(sum(r["total"] or 0 for r in daily_breakdown), 2),
            "total_discount": round(sum(r["discount"] or 0 for r in daily_breakdown), 2),
            "total_tax": round(sum(r["tax"] or 0 for r in daily_breakdown), 2),
        }
        return {"month": month_str, "daily_breakdown": daily_breakdown, "totals": totals}
    finally:
        conn.close()


def profit_loss_summary(start_date: str, end_date: str) -> dict:
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT si.quantity, si.unit_price, si.subtotal, m.purchase_price, m.name
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            JOIN medicines m ON m.id = si.medicine_id
            WHERE date(s.date) BETWEEN ? AND ?
            """,
            (start_date, end_date),
        ).fetchall()

        revenue = 0.0
        cost = 0.0
        per_medicine: dict[str, dict] = {}
        for r in rows:
            revenue += r["subtotal"]
            item_cost = r["purchase_price"] * r["quantity"]
            cost += item_cost
            entry = per_medicine.setdefault(r["name"], {"quantity": 0, "revenue": 0.0, "cost": 0.0})
            entry["quantity"] += r["quantity"]
            entry["revenue"] += r["subtotal"]
            entry["cost"] += item_cost

        revenue = round(revenue, 2)
        cost = round(cost, 2)
        profit = round(revenue - cost, 2)

        breakdown = [
            {"medicine": name, "quantity": v["quantity"], "revenue": round(v["revenue"], 2),
             "cost": round(v["cost"], 2), "profit": round(v["revenue"] - v["cost"], 2)}
            for name, v in sorted(per_medicine.items())
        ]

        return {
            "start_date": start_date,
            "end_date": end_date,
            "revenue": revenue,
            "cost": cost,
            "profit": profit,
            "breakdown": breakdown,
        }
    finally:
        conn.close()


def expiry_stock_report(within_days: int = 90) -> list[dict]:
    cutoff = (date.today() + timedelta(days=within_days)).isoformat()
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT m.name, m.batch_no, m.expiry_date, m.quantity, s.name AS supplier_name,
                   CAST(julianday(m.expiry_date) - julianday('now') AS INTEGER) AS days_to_expiry
            FROM medicines m
            LEFT JOIN suppliers s ON s.id = m.supplier_id
            WHERE m.is_active = 1 AND m.expiry_date IS NOT NULL AND m.expiry_date != ''
              AND m.expiry_date <= ?
            ORDER BY m.expiry_date
            """,
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
