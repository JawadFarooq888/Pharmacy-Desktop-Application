"""Supplier management screen: add/edit/delete suppliers + record purchase orders
(receive new stock into an existing medicine's batch/expiry/quantity)."""
from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from logic import inventory, suppliers


class SupplierEditDialog(QDialog):
    def __init__(self, parent=None, supplier: suppliers.Supplier = None):
        super().__init__(parent)
        self.supplier = supplier
        self.setWindowTitle("Edit Supplier" if supplier else "Add Supplier")
        self.setMinimumWidth(360)

        layout = QFormLayout()
        self.name_input = QLineEdit()
        self.contact_input = QLineEdit()
        self.address_input = QLineEdit()
        if supplier:
            self.name_input.setText(supplier.name)
            self.contact_input.setText(supplier.contact)
            self.address_input.setText(supplier.address)
        layout.addRow("Name *", self.name_input)
        layout.addRow("Contact", self.contact_input)
        layout.addRow("Address", self.address_input)

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
            if self.supplier is None:
                suppliers.add_supplier(self.name_input.text(), self.contact_input.text(), self.address_input.text())
            else:
                suppliers.update_supplier(
                    self.supplier.id, self.name_input.text(), self.contact_input.text(), self.address_input.text()
                )
            self.accept()
        except ValueError as e:
            QMessageBox.warning(self, "Cannot save", str(e))


class PurchaseOrderDialog(QDialog):
    """Receive new stock from a supplier into an existing medicine."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Record Purchase Order (Receive Stock)")
        self.setMinimumWidth(400)

        layout = QFormLayout()
        self.medicine_input = QComboBox()
        for m in inventory.list_medicines():
            self.medicine_input.addItem(f"{m.name} (current stock: {m.quantity})", m.id)

        self.quantity_input = QSpinBox()
        self.quantity_input.setRange(1, 1_000_000)

        self.batch_input = QLineEdit()

        self.expiry_input = QDateEdit()
        self.expiry_input.setCalendarPopup(True)
        self.expiry_input.setDisplayFormat("yyyy-MM-dd")
        self.expiry_input.setDate(QDate.currentDate())

        layout.addRow("Medicine *", self.medicine_input)
        layout.addRow("Quantity received *", self.quantity_input)
        layout.addRow("New batch no.", self.batch_input)
        layout.addRow("New expiry date", self.expiry_input)

        buttons = QHBoxLayout()
        save_btn = QPushButton("📥  Receive Stock")
        save_btn.setProperty("success", True)
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("✖️  Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        layout.addRow(buttons)
        self.setLayout(layout)

    def _save(self):
        if self.medicine_input.count() == 0:
            QMessageBox.warning(self, "No medicines", "Add a medicine in Inventory first.")
            return
        try:
            suppliers.record_purchase_order(
                medicine_id=self.medicine_input.currentData(),
                quantity=self.quantity_input.value(),
                new_batch_no=self.batch_input.text(),
                new_expiry_date=self.expiry_input.date().toString("yyyy-MM-dd"),
            )
            self.accept()
        except ValueError as e:
            QMessageBox.warning(self, "Cannot save", str(e))


class SuppliersView(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout()

        header = QHBoxLayout()
        title = QLabel("Supplier Management")
        title.setProperty("heading", True)
        header.addWidget(title)
        header.addStretch()
        po_btn = QPushButton("📦  Purchase Order")
        po_btn.clicked.connect(self._record_purchase_order)
        header.addWidget(po_btn)
        add_btn = QPushButton("➕  Add Supplier")
        add_btn.setProperty("success", True)
        add_btn.clicked.connect(self._add_supplier)
        header.addWidget(add_btn)
        layout.addLayout(header)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Contact", "Address", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        self.setLayout(layout)

    def refresh(self):
        rows = suppliers.list_suppliers()
        self.table.setRowCount(len(rows))
        for row, s in enumerate(rows):
            self.table.setItem(row, 0, QTableWidgetItem(s.name))
            self.table.setItem(row, 1, QTableWidgetItem(s.contact))
            self.table.setItem(row, 2, QTableWidgetItem(s.address))

            actions = QWidget()
            actions_layout = QHBoxLayout()
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(6)
            edit_btn = QPushButton("✏️  Edit")
            edit_btn.setProperty("compact", True)
            edit_btn.clicked.connect(lambda _, sup=s: self._edit_supplier(sup))
            delete_btn = QPushButton("🗑️  Delete")
            delete_btn.setProperty("compact", True)
            delete_btn.setProperty("danger", True)
            delete_btn.clicked.connect(lambda _, sup=s: self._delete_supplier(sup))
            actions_layout.addWidget(edit_btn)
            actions_layout.addWidget(delete_btn)
            actions.setLayout(actions_layout)
            self.table.setCellWidget(row, 3, actions)

    def _add_supplier(self):
        dialog = SupplierEditDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _edit_supplier(self, supplier: suppliers.Supplier):
        dialog = SupplierEditDialog(self, supplier=supplier)
        if dialog.exec() == QDialog.Accepted:
            self.refresh()

    def _delete_supplier(self, supplier: suppliers.Supplier):
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete supplier '{supplier.name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            suppliers.delete_supplier(supplier.id)
            self.refresh()
        except ValueError as e:
            QMessageBox.warning(self, "Cannot delete", str(e))

    def _record_purchase_order(self):
        dialog = PurchaseOrderDialog(self)
        if dialog.exec() == QDialog.Accepted:
            QMessageBox.information(self, "Stock received", "Purchase order recorded and stock updated.")
