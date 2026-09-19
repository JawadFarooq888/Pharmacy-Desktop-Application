"""Settings screen (admin only): configurable alert thresholds + user management,
matching the 'Settings' item in the sidebar spec."""
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from logic import auth, settings
from ui.users_view import UsersView


class GeneralSettingsTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QFormLayout()

        self.low_stock_input = QSpinBox()
        self.low_stock_input.setRange(0, 100_000)
        self.low_stock_input.setValue(settings.get_low_stock_threshold())
        layout.addRow("Default low-stock threshold (units)", self.low_stock_input)

        self.expiry_days_input = QSpinBox()
        self.expiry_days_input.setRange(1, 3650)
        self.expiry_days_input.setValue(settings.get_expiry_alert_days())
        layout.addRow("Expiry alert window (days)", self.expiry_days_input)

        save_btn = QPushButton("💾  Save Settings")
        save_btn.setProperty("success", True)
        save_btn.clicked.connect(self._save)
        layout.addRow(save_btn)

        note = QLabel(
            "The low-stock threshold applies to newly added medicines by default; "
            "each medicine's own threshold can still be adjusted individually in Inventory."
        )
        note.setProperty("subheading", True)
        note.setWordWrap(True)
        layout.addRow(note)

        self.setLayout(layout)

    def _save(self):
        settings.set_setting("low_stock_threshold", str(self.low_stock_input.value()))
        settings.set_setting("expiry_alert_days", str(self.expiry_days_input.value()))
        QMessageBox.information(self, "Saved", "Settings saved successfully.")


class SettingsView(QWidget):
    def __init__(self, current_user: auth.User):
        super().__init__()
        layout = QVBoxLayout()
        title = QLabel("Settings")
        title.setProperty("heading", True)
        layout.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(GeneralSettingsTab(), "General")
        tabs.addTab(UsersView(current_user), "User Management")
        layout.addWidget(tabs)

        self.setLayout(layout)
