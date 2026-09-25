"""Launch with: python -m gui.main"""

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from gui.windows.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
