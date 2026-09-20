"""Customer management screen: add/edit/delete + view a customer's sales history."""
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from logic import customers


class CustomerEditDialog(QDialog):
    def __init__(self, parent=None, customer: customers.Customer = None):
        super().__init__(parent)
        self.customer = customer
        self.setWindowTitle("Edit Customer" if customer else "Add Customer")
        self.setMinimumWidth(320)

        layout = QFormLayout()
        self.name_input = QLineEdit()
        self.phone_input = QLineEdit()
        if customer:
            self.name_input.setText(customer.name)
            self.phone_input.setText(customer.phone)
        layout.addRow("Name *", self.name_input)
        layout.addRow("Phone", self.phone_input)

        buttons = QHBoxLayout()
        save_btn = QPushButton("💾  Save")
        save_btn.setProperty("success", True)
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("✖️  Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        layout.addRow(buttons)
        self.setLayout(layout)

    def _save(self):
        try:
            if self.customer is None:
                customers.add_customer(self.name_input.text(), self.phone_input.text())
            else:
                customers.update_customer(self.customer.id, self.name_input.text(), self.phone_input.text())
            self.accept()
        except ValueError as e:
            QMessageBox.warning(self, "Cannot save", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Cannot save", f"An unexpected error occurred:\n{e}")


class CustomerHistoryDialog(QDialog):
    def __init__(self, parent, customer: customers.Customer):
        super().__init__(parent)
        self.setWindowTitle(f"Sales History — {customer.name}")
        self.setMinimumSize(420, 320)
        layout = QVBoxLayout()

        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["Invoice No.", "Date", "Total"])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)

        history = customers.sales_history(customer.id)
        table.setRowCount(len(history))
        for row, sale in enumerate(history):
            table.setItem(row, 0, QTableWidgetItem(sale["invoice_no"]))
            table.setItem(row, 1, QTableWidgetItem(sale["date"]))
            table.setItem(row, 2, QTableWidgetItem(f"{sale['total_amount']:.2f}"))

        layout.addWidget(table)
        if not history:
            layout.addWidget(QLabel("No sales recorded for this customer yet."))
        self.setLayout(layout)


class CustomersView(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        # current_user is optional so this view still works if constructed
        # without one; when given, edit/delete are restricted to admins
        # (cashiers may still register walk-in customers during billing).
        self.current_user = current_user
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout()

        header = QHBoxLayout()
        title = QLabel("Customer Management")
        title.setProperty("heading", True)
        header.addWidget(title)
        header.addStretch()
        add_btn = QPushButton("➕  Add Customer")
        add_btn.setProperty("success", True)
        add_btn.clicked.connect(self._add_customer)
        header.addWidget(add_btn)
        layout.addLayout(header)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍  Search by name or phone...")
        self.search_input.textChanged.connect(self.refresh)
        layout.addWidget(self.search_input)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Phone", "", "Actions"])
        self.table.setColumnWidth(1, 140)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnHidden(2, True)
        layout.addWidget(self.table)

        self.setLayout(layout)

    def refresh(self):
        self.table.setUpdatesEnabled(False)
        try:
            self._refresh_impl()
        finally:
            self.table.setUpdatesEnabled(True)

    def _refresh_impl(self):
        rows = customers.list_customers(search=self.search_input.text().strip())
        self.table.setRowCount(len(rows))
        for row, c in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(c.name))
            self.table.setItem(row, 1, QTableWidgetItem(c.phone))

            actions = QWidget()
            actions_layout = QHBoxLayout()
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(6)
            history_btn = QPushButton("📜  History")
            history_btn.setProperty("compact", True)
            history_btn.clicked.connect(lambda _, cust=c: self._show_history(cust))
            actions_layout.addWidget(history_btn)

            is_admin = self.current_user is None or self.current_user.is_admin
            if is_admin:
                edit_btn = QPushButton("✏️  Edit")
                edit_btn.setProperty("compact", True)
                edit_btn.clicked.connect(lambda _, cust=c: self._edit_customer(cust))
                delete_btn = QPushButton("🗑️  Delete")
                delete_btn.setProperty("compact", True)
                delete_btn.setProperty("danger", True)
                delete_btn.clicked.connect(lambda _, cust=c: self._delete_customer(cust))
                actions_layout.addWidget(edit_btn)
                actions_layout.addWidget(delete_btn)
            actions.setLayout(actions_layout)
            self.table.setCellWidget(row, 3, actions)

    def _add_customer(self):
        dialog = CustomerEditDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _edit_customer(self, customer: customers.Customer):
        dialog = CustomerEditDialog(self, customer=customer)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _show_history(self, customer: customers.Customer):
        CustomerHistoryDialog(self, customer).exec()

    def _delete_customer(self, customer: customers.Customer):
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete customer '{customer.name}'? Their past sales records will be kept but unlinked.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        customers.delete_customer(customer.id)
        self.refresh()
