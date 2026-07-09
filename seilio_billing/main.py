from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from seilio_billing.db import get_session_factory, init_db
from seilio_billing.seed import seed_company
from seilio_billing.theme import follow_os_theme
from seilio_billing.ui.main_window import MainWindow


def main() -> int:
    init_db()
    seed_company()
    session_factory = get_session_factory()

    app = QApplication(sys.argv)
    app.setApplicationName("Seilio Billing")
    follow_os_theme(app)
    window = MainWindow(session_factory)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
