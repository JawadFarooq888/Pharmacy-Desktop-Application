"""Application entry point: initializes the database, applies the app-wide
stylesheet, and shows the login screen."""
import sys

from PySide6.QtWidgets import QApplication

from database.db_manager import init_db
from ui.login_window import LoginWindow
from ui.styles import APP_STYLESHEET


def main():
    init_db()

    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)

    login_window = LoginWindow()
    login_window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
