import asyncio

from PySide6.QtCore import QThread, Signal


class DatabaseWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            result = asyncio.run(self.operation())
        except ValueError as exc:
            self.failed.emit(str(exc) if type(exc) is ValueError else "Validation failed; no sensitive details logged.")
        except Exception as exc:
            # Driver errors can contain connection details; keep secrets out of the UI.
            self.failed.emit(f"Database operation failed ({type(exc).__name__}). Check database availability and config.yml.")
        else:
            self.succeeded.emit(result)
