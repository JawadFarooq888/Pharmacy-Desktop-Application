"""Billing / POS screen: search medicine -> add to cart -> checkout -> print invoice."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from logic import audit, auth, customers, inventory, invoice_pdf, printing, sales, settings, thermal_receipt
from logic.sales import PAYMENT_METHOD_LABELS


class BillingView(QWidget):
    def __init__(self, current_user: auth.User):
        super().__init__()
        self.current_user = current_user
        self.cart = sales.Cart()
        self._search_results: list[inventory.Medicine] = []
        self._build_ui()
        self.refresh_search()

    def _build_ui(self):
        root = QHBoxLayout()

        # ---- Left: medicine search + results ----
        left = QVBoxLayout()
        title = QLabel("New Sale")
        title.setProperty("heading", True)
        left.addWidget(title)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍📷  Scan barcode or type medicine name...")
        self.search_input.textChanged.connect(self.refresh_search)
        self.search_input.returnPressed.connect(self._handle_scan_or_enter)
        left.addWidget(self.search_input)

        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self._add_selected_to_cart)
        left.addWidget(self.results_list)

        add_row = QHBoxLayout()
        self.qty_input = QSpinBox()
        self.qty_input.setRange(1, 100_000)
        self.qty_input.setValue(1)
        add_row.addWidget(QLabel("Qty:"))
        add_row.addWidget(self.qty_input)
        add_btn = QPushButton("🛒  Add to Cart")
        add_btn.setProperty("success", True)
        add_btn.clicked.connect(self._add_selected_to_cart)
        add_row.addWidget(add_btn)
        left.addLayout(add_row)

        root.addLayout(left, 2)

        # ---- Right: cart + checkout ----
        right = QVBoxLayout()
        cart_title = QLabel("Cart")
        cart_title.setProperty("heading", True)
        right.addWidget(cart_title)

        self.cart_table = QTableWidget(0, 5)
        self.cart_table.setHorizontalHeaderLabels(["Medicine", "Qty", "Unit Price", "Subtotal", ""])
        self.cart_table.setColumnWidth(1, 60)
        self.cart_table.setColumnWidth(2, 90)
        self.cart_table.setColumnWidth(3, 90)
        self.cart_table.setColumnWidth(4, 110)
        self.cart_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.cart_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cart_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.cart_table.verticalHeader().setVisible(False)
        right.addWidget(self.cart_table)

        customer_row = QHBoxLayout()
        customer_row.addWidget(QLabel("Customer:"))
        self.customer_input = QComboBox()
        self.customer_input.currentIndexChanged.connect(self._on_customer_changed)
        customer_row.addWidget(self.customer_input)
        refresh_cust_btn = QPushButton("🔄  Refresh")
        refresh_cust_btn.clicked.connect(self._reload_customers)
        customer_row.addWidget(refresh_cust_btn)
        right.addLayout(customer_row)

        self.credit_label = QLabel("")
        self.credit_label.setProperty("warning", True)
        right.addWidget(self.credit_label)

        doctor_row = QHBoxLayout()
        doctor_row.addWidget(QLabel("Doctor (optional):"))
        self.doctor_input = QLineEdit()
        self.doctor_input.setPlaceholderText("For prescription medicines")
        doctor_row.addWidget(self.doctor_input)
        right.addLayout(doctor_row)

        discount_row = QHBoxLayout()
        discount_row.addWidget(QLabel("Discount:"))
        self.discount_input = QDoubleSpinBox()
        self.discount_input.setRange(0, 1_000_000)
        self.discount_input.setDecimals(2)
        self.discount_input.valueChanged.connect(self._recalculate)
        discount_row.addWidget(self.discount_input)

        discount_row.addWidget(QLabel("Tax %:"))
        self.tax_input = QDoubleSpinBox()
        self.tax_input.setRange(0, 100)
        self.tax_input.setDecimals(2)
        self.tax_input.valueChanged.connect(self._recalculate)
        discount_row.addWidget(self.tax_input)
        right.addLayout(discount_row)

        payment_row = QHBoxLayout()
        payment_row.addWidget(QLabel("Payment:"))
        self.payment_method_input = QComboBox()
        for value, label in PAYMENT_METHOD_LABELS.items():
            self.payment_method_input.addItem(label, value)
        self.payment_method_input.currentIndexChanged.connect(self._on_payment_method_changed)
        payment_row.addWidget(self.payment_method_input)

        payment_row.addWidget(QLabel("Amount Paid Now:"))
        self.amount_paid_input = QDoubleSpinBox()
        self.amount_paid_input.setRange(0, 10_000_000)
        self.amount_paid_input.setDecimals(2)
        self.amount_paid_input.valueChanged.connect(self._recalculate)
        payment_row.addWidget(self.amount_paid_input)
        right.addLayout(payment_row)

        self.credit_preview_label = QLabel("")
        self.credit_preview_label.setProperty("warning", True)
        right.addWidget(self.credit_preview_label)

        self.totals_label = QLabel("Subtotal: 0.00   Total: 0.00")
        self.totals_label.setProperty("heading", True)
        right.addWidget(self.totals_label)

        checkout_row = QHBoxLayout()
        clear_btn = QPushButton("🗑️  Clear Cart")
        clear_btn.setProperty("danger", True)
        clear_btn.clicked.connect(self._clear_cart)
        checkout_row.addWidget(clear_btn)
        checkout_btn = QPushButton("🧾  Checkout && Print Invoice")
        checkout_btn.setProperty("success", True)
        checkout_btn.clicked.connect(self._checkout)
        checkout_row.addWidget(checkout_btn)
        right.addLayout(checkout_row)

        root.addLayout(right, 3)
        self.setLayout(root)

        self._reload_customers()

    def refresh(self):
        """Called whenever this screen becomes visible (e.g. switching to it
        from another tab) so a customer/medicine added, edited or deleted
        elsewhere -- while this screen sat idle in the background -- shows up
        immediately instead of only after manually pressing 🔄 Refresh."""
        self._reload_customers()
        self.refresh_search()

    def _reload_customers(self):
        current = self.customer_input.currentData()
        self.customer_input.blockSignals(True)
        self.customer_input.clear()
        self.customer_input.addItem("Walk-in Customer", None)
        for c in customers.list_customers():
            self.customer_input.addItem(f"{c.name} ({c.phone})", c.id)
        idx = self.customer_input.findData(current)
        self.customer_input.setCurrentIndex(idx if idx >= 0 else 0)
        self.customer_input.blockSignals(False)
        self._on_customer_changed()

    def _update_credit_label(self):
        customer_id = self.customer_input.currentData()
        if customer_id is None:
            self.credit_label.setText("")
            return
        cust = customers.get_customer(customer_id)
        if cust and cust.has_credit:
            self.credit_label.setText(f"⚠️  This customer already owes {cust.credit_balance:.2f} in udhaar.")
        else:
            self.credit_label.setText("")

    def _on_customer_changed(self):
        self._update_credit_label()
        # Re-apply the payment method's default now that udhaar may have
        # just become usable again (a walk-in always forces "paid in full"
        # below, overriding this back if we've switched TO walk-in) --
        # otherwise switching from Walk-in to a real customer while "Udhaar"
        # is already selected would silently leave "Amount Paid" at the
        # walk-in-forced full total, recording the sale as fully paid
        # instead of the credit sale the cashier picked "Udhaar" for.
        self._apply_default_amount_paid()
        self._enforce_walkin_full_payment()

    def _apply_default_amount_paid(self):
        method = self.payment_method_input.currentData()
        if method == "udhaar":
            self.amount_paid_input.setValue(0.0)
        else:
            self.amount_paid_input.setValue(self.cart.total)

    def _enforce_walkin_full_payment(self):
        """A walk-in sale can never be on udhaar (checkout() rejects it), so
        the "amount paid" field is locked to the full total -- and disabled
        entirely -- whenever no customer is selected. Without this, a
        cashier could select Walk-in + Udhaar (or just hand-type a lower
        amount) and see a "will be added to udhaar" preview for a sale
        that's guaranteed to fail at checkout with no customer to bill it to."""
        is_walkin = self.customer_input.currentData() is None
        self.amount_paid_input.setEnabled(not is_walkin)
        if is_walkin:
            self.amount_paid_input.setValue(self.cart.total)
            self._update_totals_label()

    def _on_payment_method_changed(self):
        self._apply_default_amount_paid()
        self._enforce_walkin_full_payment()

    def refresh_search(self):
        text = self.search_input.text().strip()
        self._search_results = inventory.list_medicines(search=text) if text else []
        self.results_list.clear()
        for m in self._search_results:
            label = f"{m.name}  |  Stock: {m.quantity}  |  Price: {m.sale_price:.2f}"
            item = QListWidgetItem(label)
            if m.quantity <= 0:
                item.setFlags(Qt.NoItemFlags)
            self.results_list.addItem(item)

    def _add_selected_to_cart(self):
        row = self.results_list.currentRow()
        if row < 0 or row >= len(self._search_results):
            QMessageBox.information(self, "No selection", "Please select a medicine from the search results.")
            return
        self._add_medicine_to_cart(self._search_results[row])

    def _add_medicine_to_cart(self, medicine: inventory.Medicine):
        if medicine.quantity <= 0:
            QMessageBox.warning(self, "Out of stock", f"'{medicine.name}' has no stock available.")
            return
        try:
            self.cart.add(medicine, self.qty_input.value())
            self._render_cart()
        except ValueError as e:
            QMessageBox.warning(self, "Cannot add to cart", str(e))

    def _handle_scan_or_enter(self):
        """Fired when Enter is pressed in the search box -- which is exactly
        what a barcode scanner does after "typing" a scanned code. Tries an
        exact barcode match first (the scan case); if that fails, falls back
        to auto-adding when the typed text narrowed the list to one medicine
        (a convenience for manually typed searches too)."""
        text = self.search_input.text().strip()
        if not text:
            return

        medicine = inventory.get_medicine_by_barcode(text)
        if medicine is not None:
            self._add_medicine_to_cart(medicine)
            self.search_input.clear()
            self.qty_input.setValue(1)
            return

        if len(self._search_results) == 1:
            self._add_medicine_to_cart(self._search_results[0])
            self.search_input.clear()
            self.qty_input.setValue(1)
            return

        if not self._search_results:
            QMessageBox.information(
                self, "Not found", f"No medicine matches '{text}' (checked by name and barcode)."
            )

    def _render_cart(self):
        self.cart_table.setRowCount(len(self.cart.items))
        for row, item in enumerate(self.cart.items):
            self.cart_table.setItem(row, 0, QTableWidgetItem(item.name))
            self.cart_table.setItem(row, 1, QTableWidgetItem(str(item.quantity)))
            self.cart_table.setItem(row, 2, QTableWidgetItem(f"{item.unit_price:.2f}"))
            self.cart_table.setItem(row, 3, QTableWidgetItem(f"{item.subtotal:.2f}"))
            remove_btn = QPushButton("🗑️  Remove")
            remove_btn.setProperty("compact", True)
            remove_btn.setProperty("danger", True)
            remove_btn.clicked.connect(lambda _, mid=item.medicine_id: self._remove_from_cart(mid))
            self.cart_table.setCellWidget(row, 4, remove_btn)
        self._recalculate()
        if self.payment_method_input.currentData() != "udhaar":
            self.amount_paid_input.blockSignals(True)
            self.amount_paid_input.setValue(self.cart.total)
            self.amount_paid_input.blockSignals(False)
            self._update_totals_label()
        self._enforce_walkin_full_payment()

    def _remove_from_cart(self, medicine_id: int):
        self.cart.remove(medicine_id)
        self._render_cart()

    def _clear_cart(self):
        self.cart.clear()
        self.discount_input.setValue(0)
        self.tax_input.setValue(0)
        self.payment_method_input.setCurrentIndex(0)
        self.doctor_input.clear()
        self._render_cart()

    def _recalculate(self):
        # Discount can never exceed the subtotal (would otherwise produce a
        # negative total); cap the spinbox itself so it's not even possible
        # to type an invalid value.
        self.discount_input.setMaximum(max(self.cart.subtotal, 0.0))

        self.cart.discount = self.discount_input.value()
        self.cart.tax_percent = self.tax_input.value()
        # Amount paid can never exceed the total -- clamp rather than allow
        # a value that checkout() would just reject anyway.
        self.amount_paid_input.setMaximum(max(self.cart.total, 0.0))
        self._update_totals_label()

    def _update_totals_label(self):
        self.totals_label.setText(
            f"Subtotal: {self.cart.subtotal:.2f}   Discount: {self.cart.discount:.2f}   "
            f"Tax: {self.cart.tax_amount:.2f}   Total: {self.cart.total:.2f}"
        )
        remaining = round(self.cart.total - self.amount_paid_input.value(), 2)
        if remaining > 0.005:
            self.credit_preview_label.setText(
                f"📒  {remaining:.2f} will be added to the selected customer's udhaar balance."
            )
        else:
            self.credit_preview_label.setText("")

    def _checkout(self):
        if not self.cart.items:
            QMessageBox.information(self, "Empty cart", "Add at least one medicine before checking out.")
            return

        amount_paid = self.amount_paid_input.value()
        remaining = round(self.cart.total - amount_paid, 2)
        confirm_msg = f"Complete this sale for a total of {self.cart.total:.2f}?"
        if remaining > 0.005:
            confirm_msg += f"\n\n{remaining:.2f} will be added to the customer's udhaar balance."
        reply = QMessageBox.question(
            self, "Confirm Sale", confirm_msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            customer_id = self.customer_input.currentData()
            receipt = sales.checkout(
                self.cart,
                cashier_id=self.current_user.id,
                customer_id=customer_id,
                payment_method=self.payment_method_input.currentData(),
                amount_paid=amount_paid,
                doctor_name=self.doctor_input.text(),
            )
        except ValueError as e:
            QMessageBox.warning(self, "Checkout failed", str(e))
            return
        except Exception as e:
            # Anything unexpected (e.g. a database-level error) should still
            # surface as a clear message rather than an unhandled crash.
            QMessageBox.critical(self, "Checkout failed", f"The sale could not be completed:\n{e}")
            return

        # Flag anything a shop owner would want visibility into later: a
        # meaningful discount, or a sale that added to a customer's udhaar.
        if receipt["discount"] > 0 and receipt["discount"] >= 0.1 * receipt["subtotal"]:
            audit.log(
                self.current_user.id, self.current_user.username, "large_discount",
                f"invoice {receipt['invoice_no']}: discount {receipt['discount']:.2f} "
                f"on subtotal {receipt['subtotal']:.2f}",
            )
        if receipt["credit_amount"] > 0.005:
            audit.log(
                self.current_user.id, self.current_user.username, "udhaar_sale",
                f"invoice {receipt['invoice_no']}: {receipt['credit_amount']:.2f} added to customer credit",
            )

        customer_name = self.customer_input.currentText()
        receipt_format = settings.get_receipt_format()
        shop_name = settings.get_shop_name()
        try:
            if receipt_format in ("58mm", "80mm"):
                pdf_path = thermal_receipt.generate_thermal_receipt(
                    receipt, width=receipt_format, customer_name=customer_name,
                    cashier_name=self.current_user.username, shop_name=shop_name,
                )
            else:
                pdf_path = invoice_pdf.generate_invoice_pdf(
                    receipt, customer_name=customer_name, cashier_name=self.current_user.username,
                    shop_name=shop_name,
                )
            printed = printing.print_document(pdf_path)
            msg = f"Sale complete!\nInvoice: {receipt['invoice_no']}\nTotal: {receipt['total']:.2f}\n\n"
            msg += f"Sent to printer ({receipt_format}).\n" if printed else ""
            msg += f"Receipt saved to:\n{pdf_path}"
        except Exception as e:
            msg = (
                f"Sale complete!\nInvoice: {receipt['invoice_no']}\nTotal: {receipt['total']:.2f}\n\n"
                f"(Could not generate/print receipt: {e})"
            )
        if receipt["credit_amount"] > 0.005:
            msg += f"\n\n📒 Udhaar added: {receipt['credit_amount']:.2f}"
        QMessageBox.information(self, "Sale Complete", msg)

        self._reload_customers()
        self._clear_cart()
        self.refresh_search()
