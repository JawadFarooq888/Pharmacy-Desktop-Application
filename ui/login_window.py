"""Login screen. On success, opens the MainWindow with the authenticated user."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logic import audit, auth


class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Shani Pharmacy Management System (SPMS) - Login")
        # A minimum (not fixed) size: the layout below needs a certain
        # amount of room for all its rows, but isn't locked to it -- a
        # fixed size here previously clipped/hid the bottom of the form
        # every time a new row was added to it.
        self.setMinimumSize(400, 440)
        self.resize(400, 440)
        self.main_window = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(14)

        title = QLabel("Shani Pharmacy Management System (SPMS)")
        title.setProperty("heading", True)
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        layout.addWidget(title)

        subtitle = QLabel("Sign in to continue")
        subtitle.setProperty("subheading", True)
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        layout.addWidget(self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self._attempt_login)
        layout.addWidget(self.password_input)

        self.error_label = QLabel("")
        self.error_label.setProperty("warning", True)
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        login_btn = QPushButton("🔐  Login")
        login_btn.setProperty("success", True)
        login_btn.clicked.connect(self._attempt_login)
        layout.addWidget(login_btn)

        hint = QLabel("Default admin login: admin / admin123")
        hint.setProperty("subheading", True)
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

        forgot_btn = QPushButton("Forgot admin password?")
        forgot_btn.setProperty("flat", True)
        forgot_btn.setStyleSheet("text-align: center;")
        forgot_btn.clicked.connect(self._recover_admin)
        layout.addWidget(forgot_btn)

        self.setLayout(layout)
        self.username_input.setFocus()

    def _recover_admin(self):
        pin, ok = QInputDialog.getText(
            self,
            "Reset Admin Password",
            "Enter your Recovery PIN to continue.\n\n"
            "(Set in Settings by the shop owner. If it's been forgotten too, "
            "contact the developer for the master recovery PIN.)",
            QLineEdit.Password,
        )
        if not ok:
            return
        if not auth.verify_recovery_pin(pin):
            QMessageBox.warning(self, "Incorrect PIN", "That Recovery PIN is not correct.")
            return

        reply = QMessageBox.warning(
            self,
            "Reset Admin Password",
            "This resets the admin account's password back to the default "
            f"(admin / {auth.RECOVERY_PASSWORD}) so you can sign back in.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        username = auth.recover_admin_access()
        audit.log(None, "(recovery)", "admin_password_reset", f"admin account '{username}' reset via Recovery PIN")
        QMessageBox.information(
            self,
            "Password Reset",
            f"Done. Sign in with:\n\nUsername: {username}\nPassword: {auth.RECOVERY_PASSWORD}\n\n"
            "Please change this password right away from Settings after signing in.",
        )
        self.username_input.setText(username)
        self.password_input.setText(auth.RECOVERY_PASSWORD)

    def _attempt_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username or not password:
            self.error_label.setText("Please enter both username and password.")
            return

        user = auth.login(username, password)
        if user is None:
            self.error_label.setText("Invalid username or password.")
            self.password_input.clear()
            return

        self.error_label.setText("")
        self._open_main_window(user)

    def _open_main_window(self, user):
        # Imported here to avoid a circular import (main_window imports feature
        # views which may, in turn, import back into ui in future modules).
        from ui.main_window import MainWindow

        self.main_window = MainWindow(user)
        self.main_window.show()
        self.close()
