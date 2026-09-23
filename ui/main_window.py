"""Main application window: sidebar navigation + stacked pages.

Cashiers see Dashboard / Billing / Inventory (view-only) / Customers / Reports.
Admins additionally see Suppliers, Backup/Restore, and Settings (user management).
"""
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from logic import auth, backup
from ui.backup_view import BackupView
from ui.billing_view import BillingView
from ui.customers_view import CustomersView
from ui.dashboard_view import DashboardView
from ui.inventory_view import InventoryView
from ui.reports_view import ReportsView
from ui.returns_view import ReturnsView
from ui.settings_view import SettingsView
from ui.suppliers_view import SuppliersView


class MainWindow(QMainWindow):
    def __init__(self, user: auth.User):
        super().__init__()
        self.user = user
        self.setWindowTitle("Shani Pharmacy Management System (SPMS)")
        self.resize(1200, 750)
        # Below this, the sidebar and page content start cramming into each
        # other -- shrink-to-broken isn't a state a non-technical user should
        # be able to reach by just dragging a window edge.
        self.setMinimumSize(1100, 650)

        self.nav_buttons = []
        self._build_ui()
        backup.run_daily_auto_backup_if_needed()

    def _build_ui(self):
        central = QWidget()
        root_layout = QHBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Sidebar ---
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout()
        sidebar_layout.setContentsMargins(0, 20, 0, 20)
        sidebar_layout.setSpacing(2)

        app_title = QLabel("  Pharmacy MS")
        app_title.setProperty("heading", True)
        sidebar_layout.addWidget(app_title)

        user_label = QLabel(f"  {self.user.username} ({self.user.role})")
        user_label.setProperty("subheading", True)
        sidebar_layout.addWidget(user_label)
        sidebar_layout.addSpacing(16)

        self.stack = QStackedWidget()
        self.pages_by_name = {}

        pages = [("Dashboard", DashboardView(self.user, navigate_callback=self._navigate_to))]
        pages.append(("Billing", BillingView(self.user)))
        pages.append(("Returns", ReturnsView(self.user)))
        pages.append(("Inventory", InventoryView(self.user)))
        pages.append(("Customers", CustomersView(self.user)))
        if self.user.is_admin:
            pages.append(("Suppliers", SuppliersView()))
        pages.append(("Reports", ReportsView()))
        if self.user.is_admin:
            pages.append(("Backup / Restore", BackupView(self.user)))
            pages.append(("Settings", SettingsView(self.user)))

        nav_icons = {
            "Dashboard": "🏠",
            "Billing": "🧾",
            "Returns": "↩️",
            "Inventory": "💊",
            "Customers": "👥",
            "Suppliers": "🚚",
            "Reports": "📊",
            "Backup / Restore": "🗄️",
            "Settings": "⚙️",
        }

        for name, widget in pages:
            self.stack.addWidget(widget)
            self.pages_by_name[name] = widget
            icon = nav_icons.get(name, "")
            btn = QPushButton(f"{icon}  {name}" if icon else name)
            btn.setProperty("flat", True)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, w=widget, b=None: self._switch_page(w))
            self.nav_buttons.append(btn)
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()

        logout_btn = QPushButton("🚪  Logout")
        logout_btn.setProperty("danger", True)
        logout_btn.clicked.connect(self._logout)
        sidebar_layout.addWidget(logout_btn)

        sidebar.setLayout(sidebar_layout)

        root_layout.addWidget(sidebar)

        content_wrapper = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.addWidget(self.stack)
        content_wrapper.setLayout(content_layout)
        root_layout.addWidget(content_wrapper)

        central.setLayout(root_layout)
        self.setCentralWidget(central)

        if self.nav_buttons:
            self.nav_buttons[0].setChecked(True)
            self.nav_buttons[0].setProperty("active", True)

    def _switch_page(self, widget):
        self.stack.setCurrentWidget(widget)
        # Every page keeps its own state alive in the background (tabs are
        # never destroyed, just hidden), so without this a customer/medicine
        # added, edited or deleted on one screen would keep looking
        # unchanged on every other screen until its own manual Refresh
        # button was clicked -- easy to mistake for "delete/update doesn't
        # work" when it actually did, just not visibly yet.
        refresh = getattr(widget, "refresh", None)
        if callable(refresh):
            refresh()
        for btn in self.nav_buttons:
            is_active = self.stack.widget(self.nav_buttons.index(btn)) is widget
            btn.setChecked(is_active)
            btn.setProperty("active", is_active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _navigate_to(self, name: str):
        widget = self.pages_by_name.get(name)
        if widget:
            self._switch_page(widget)

    def _logout(self):
        from ui.login_window import LoginWindow

        self.login_window = LoginWindow()
        self.login_window.show()
        self.close()

    def closeEvent(self, event):
        backup.run_auto_backup_on_exit()
        super().closeEvent(event)
