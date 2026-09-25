from datetime import datetime

from PySide6.QtCore import QEvent, QRegularExpression, Qt, QSettings
from PySide6.QtGui import QRegularExpressionValidator, QAction, QIcon
from PySide6.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget, QSystemTrayIcon, QMenu,
)

from gui.services.worker import DatabaseWorker
from gui.tabs.presents import PresentForm
from gui.tabs.admin_panel import AdminPanel
from helpers.admin_operations import OperationsService
from gui.services.process_manager import ProcessManager


class MainWindow(QMainWindow):
    def __init__(self, service=None):
        super().__init__()
        self.service = service if service is not None else OperationsService()
        self.loaded_user_id = None
        self.worker = None
        self.settings = QSettings("server-of-dreams", "Admin")
        self.process_manager = ProcessManager(parent=self)
        self.process_manager.state_changed.connect(self._process_state)
        self.setWindowTitle("Server of Dreams · Admin")
        self.resize(1080, 850)
        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)
        top = QHBoxLayout()
        top.addWidget(QLabel("userId"))
        self.user_id = QLineEdit("6")
        self.user_id.setValidator(QRegularExpressionValidator(QRegularExpression("[0-9]{0,19}"), self))
        self.load = QPushButton("Load account")
        top.addWidget(self.user_id)
        top.addWidget(self.load)
        layout.addLayout(top)
        account = QGroupBox("Account")
        fields = QFormLayout(account)
        self.info = {}
        for key, label in (("user_id", "userId"), ("name", "Profile name"),
                           ("player_rank", "Player rank"), ("platform", "Platform"),
                           ("hash_user_id", "hashUserId")):
            value = QLabel("—")
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setWordWrap(True)
            self.info[key] = value
            fields.addRow(label, value)
        layout.addWidget(account)
        self.present = PresentForm()
        self.present.setEnabled(False)
        self.panel = AdminPanel(self, self.present, process_manager=self.process_manager)
        layout.addWidget(self.panel, 3)
        layout.addWidget(QLabel("Activity log"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        layout.addWidget(self.log, 1)
        self.load.clicked.connect(self.load_account)
        self.user_id.returnPressed.connect(self.load_account)
        self.user_id.textChanged.connect(self._invalidate_account)
        self.present.send.clicked.connect(self.send_present)
        self.append_log("Ready. Load the verified account (userId 6) to connect.")
        self._setup_tray()
        self._check_postgres()

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))
        menu = QMenu()
        open_action = menu.addAction("Open Admin")
        open_action.triggered.connect(self.showNormal)
        menu.addSeparator()
        for name, title in (("server", "Start/Stop Server"), ("proxy", "Start/Stop Proxy")):
            action = menu.addAction(title)
            action.triggered.connect(lambda _=False, n=name: self.panel.toggle_process(n))
        restart = menu.addAction("Restart All")
        restart.triggered.connect(self.panel.restart_all)
        logs = menu.addAction("View Logs")
        logs.triggered.connect(lambda: (self.showNormal(), self.panel.setCurrentIndex(self.panel.indexOf(self.panel.process_logs["server"].parentWidget()))))
        menu.addSeparator()
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self._exit_from_tray)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.showNormal() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def _check_postgres(self):
        self._start(self.service.diagnostics, lambda report: self.panel.refresh_postgres_status(report.get("db", "unknown")))

    def _process_state(self, name, state):
        self.append_log(f"[{name}] {state}")

    def _exit_from_tray(self):
        self._allow_close = True
        self.close()

    def append_log(self, message):
        self.log.appendPlainText(f"{datetime.now():%H:%M:%S}  {message}")

    def _invalidate_account(self):
        self.loaded_user_id = None
        self.panel.set_account(None)
        self.present.setEnabled(False)
        self.present.send.setText("Give Present")
        for label in self.info.values():
            label.setText("—")

    def _start(self, operation, success):
        if self.worker is not None:
            return
        self.user_id.setEnabled(False)
        self.load.setEnabled(False)
        self.present.setEnabled(False)
        self.panel.setEnabled(False)
        self.worker = DatabaseWorker(operation, self)
        self.worker.succeeded.connect(success)
        self.worker.failed.connect(lambda message: self.append_log(f"ERROR: {message}"))
        self.worker.failed.connect(lambda _: self.panel.operation_failed())
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.user_id.setEnabled(True)
        self.load.setEnabled(True)
        self.panel.setEnabled(True)
        self.present.setEnabled(self.loaded_user_id is not None)

    def load_account(self):
        if self.worker is not None:
            return
        self._invalidate_account()
        try:
            user_id = int(self.user_id.text())
            if not 0 < user_id <= 2**63 - 1:
                raise ValueError()
        except ValueError:
            self.append_log("ERROR: Enter a positive userId (BIGINT).")
            return
        self.append_log(f"Connecting and loading userId {user_id}…")
        self._start(lambda: self.service.load_account(user_id), self._account_loaded)

    def _account_loaded(self, summary):
        self.loaded_user_id = summary.user_id
        self.panel.set_account(summary.user_id)
        self.panel.connection_status.setText("DB: connected (account load succeeded)")
        for key, label in self.info.items():
            value = getattr(summary, key)
            label.setText(str(value) if value is not None else "—")
        self.present.send.setText(f"Give Present to user {summary.user_id}")
        self.append_log(f"Connected. Loaded userId {summary.user_id}.")

    def send_present(self):
        if self.worker is not None or self.loaded_user_id is None:
            return
        user_id = self.loaded_user_id
        try:
            thing_type, thing_id, amount, message = self.present.values(user_id)
        except ValueError as exc:
            self.append_log(f"ERROR: {exc}")
            return
        self.append_log(f"Sending {amount} × {thing_type.name} to userId {user_id}…")
        self._start(lambda: self.service.give_present(user_id, thing_type, thing_id, amount, message),
                    lambda inbox_id: self.append_log(
                        f"SUCCESS: {amount} × {thing_type.name} sent to userId {user_id}; inbox ID {inbox_id}. Unclaimed."))

    def closeEvent(self, event):
        if not getattr(self, "_allow_close", False) and self.panel.minimize_tray.isChecked():
            self.hide()
            self.tray.showMessage("Server of Dreams", "Admin is still running in the system tray.", QSystemTrayIcon.MessageIcon.Information, 2000)
            event.ignore()
            return
        if self.worker is not None:
            self.append_log("Please wait for the database operation to finish before closing.")
            event.ignore()
        else:
            if self.panel.stop_children.isChecked():
                self.process_manager.stop_all()
            self.tray.hide()
            event.accept()

    def changeEvent(self, event):
        super().changeEvent(event)
        if (event.type() == QEvent.Type.WindowStateChange and self.isMinimized()
                and self.panel.minimize_tray.isChecked()):
            self.hide()
