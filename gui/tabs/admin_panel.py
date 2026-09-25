"""UI orchestration only; database/snapshot work stays in shared services."""

from pathlib import Path
import hashlib

from PySide6.QtCore import QFileSystemWatcher, Qt, Signal, QUrl, QSettings
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QTextBrowser, QVBoxLayout, QWidget, QCheckBox,
)

from helpers.admin_operations import BACKUPS, ROOT, OperationsService, list_backups, load_snapshot


def table():
    widget = QTableWidget()
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    return widget


def populate(widget, rows):
    columns = list(rows[0]) if rows else []
    widget.setRowCount(len(rows))
    widget.setColumnCount(len(columns))
    widget.setHorizontalHeaderLabels(columns)
    for r, row in enumerate(rows):
        for c, key in enumerate(columns):
            widget.setItem(r, c, QTableWidgetItem(str(row[key]) if row[key] is not None else "—"))
    widget.resizeColumnsToContents()


class AdminPanel(QTabWidget):
    progress = Signal(str)

    def __init__(self, window, present, service=None, process_manager=None):
        super().__init__(window)
        self.window = window
        self.service = service or OperationsService()
        self.process_manager = process_manager
        self.settings = QSettings("server-of-dreams", "Admin")
        self.user_id = None
        self.validation = None
        self.progress.connect(window.append_log)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self.invalidate)
        self.watcher.directoryChanged.connect(self.invalidate)
        self.dashboard, dash = self.page("Dashboard")
        self.connection_status = QLabel("DB status: not checked. Use Load account or Diagnostics.")
        dash.addWidget(self.connection_status)
        dash.addWidget(QLabel("Active target is shown above. Account changes clear inventory and import validation."))
        status_row = QHBoxLayout()
        self.process_labels = {}
        for name, label in (("server", "Server"), ("postgres", "PostgreSQL"), ("proxy", "Proxy"), ("adb", "ADB / emulator")):
            value = QLabel(f"{label}: unknown")
            self.process_labels[name] = value
            status_row.addWidget(value)
        dash.addLayout(status_row)
        process_row = QHBoxLayout()
        for name, label in (("server", "Start Server"), ("proxy", "Start Proxy")):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, n=name: self.toggle_process(n))
            process_row.addWidget(button)
        restart = QPushButton("Restart All")
        restart.clicked.connect(self.restart_all)
        process_row.addWidget(restart)
        dash.addLayout(process_row)
        settings_row = QHBoxLayout()
        self.start_server = QCheckBox("Start server when GUI opens")
        self.start_proxy = QCheckBox("Start proxy when GUI opens")
        self.minimize_tray = QCheckBox("Minimize to tray")
        self.stop_children = QCheckBox("Stop child processes on exit")
        for box, key, default in ((self.start_server, "start_server", False), (self.start_proxy, "start_proxy", False), (self.minimize_tray, "minimize_tray", True), (self.stop_children, "stop_children", True)):
            box.setChecked(self.settings.value(key, default, type=bool))
            box.toggled.connect(lambda checked, k=key: self.settings.setValue(k, checked))
            settings_row.addWidget(box)
        dash.addLayout(settings_row)
        dash.addStretch()

        _, logs = self.page("Process Logs")
        self.process_logs = {}
        for name, title in (("server", "Server output"), ("proxy", "Proxy output")):
            logs.addWidget(QLabel(title))
            output = QTextBrowser()
            output.setOpenExternalLinks(False)
            logs.addWidget(output, 1)
            self.process_logs[name] = output
        if self.process_manager:
            self.process_manager.log.connect(self.process_log)
            self.process_manager.state_changed.connect(self.process_state)
            if self.start_server.isChecked():
                self.process_manager.start("server")
            if self.start_proxy.isChecked():
                self.process_manager.start("proxy")

        _, accounts = self.page("Accounts")
        self.account_search = QLineEdit()
        self.account_search.setPlaceholderText("Profile name or userId (up to 200 results)")
        accounts.addWidget(self.account_search)
        find = QPushButton("Search / list accounts")
        find.clicked.connect(self.find_accounts)
        accounts.addWidget(find)
        self.account_table = table()
        accounts.addWidget(self.account_table)
        select = QPushButton("Load selected account as active target")
        select.clicked.connect(self.select_account)
        accounts.addWidget(select)

        _, presents = self.page("Give Present")
        presents.addWidget(present)
        presents.addStretch()
        _, inventory = self.page("Inventory")
        self.inventory_kind = QComboBox()
        self.inventory_kind.addItems(["Items", "Characters", "Posters", "Accessories"])
        inventory.addWidget(self.inventory_kind)
        refresh = QPushButton("Read inventory for active target")
        refresh.clicked.connect(self.read_inventory)
        inventory.addWidget(refresh)
        self.inventory_table = table()
        inventory.addWidget(self.inventory_table)

        self.snapshot_page, snapshot = self.page("Import / Export")
        self.snapshot_path = QLineEdit()
        self.snapshot_path.setPlaceholderText("Choose a trusted .pkl snapshot")
        self.snapshot_path.textChanged.connect(self.snapshot_changed)
        snapshot.addWidget(self.snapshot_path)
        choose = QPushButton("Choose snapshot…")
        choose.clicked.connect(self.choose_snapshot)
        snapshot.addWidget(choose)
        self.snapshot_status = QLabel("Not inspected or validated")
        self.snapshot_status.setWordWrap(True)
        self.snapshot_status.setTextFormat(Qt.TextFormat.PlainText)
        snapshot.addWidget(self.snapshot_status)
        inspect = QPushButton("Inspect + in-memory validation")
        inspect.clicked.connect(self.inspect_snapshot)
        snapshot.addWidget(inspect)
        validate = QPushButton("Dry-run + DB round-trip (always rollback)")
        validate.clicked.connect(self.validate_snapshot)
        snapshot.addWidget(validate)
        self.commit = QPushButton("Import — requires PASS and typed confirmation")
        self.commit.setEnabled(False)
        self.commit.clicked.connect(self.commit_snapshot)
        snapshot.addWidget(self.commit)
        self.json_export = QCheckBox("Also create readable JSON (not a restore format)")
        snapshot.addWidget(self.json_export)
        export = QPushButton("Export / backup active account…")
        export.clicked.connect(self.export_account)
        snapshot.addWidget(export)
        snapshot.addWidget(QLabel("Stop game activity before replacement. Backup is created before any deletion.\n"
                                  "Account credentials/tokens are excluded. Restore requires the .meta.json sidecar."))
        snapshot.addStretch()

        _, backups = self.page("Backups")
        backups.addWidget(QLabel(str(BACKUPS)))
        refresh_backups = QPushButton("Refresh local backups")
        refresh_backups.clicked.connect(self.refresh_backups)
        backups.addWidget(refresh_backups)
        self.backup_table = table()
        backups.addWidget(self.backup_table)
        restore = QPushButton("Select backup for inspection / safe restore")
        restore.clicked.connect(self.choose_backup)
        backups.addWidget(restore)

        _, diagnostics = self.page("Tools / Diagnostics")
        check = QPushButton("Check DB, server, masterdata and local icons")
        check.clicked.connect(self.diagnostics)
        diagnostics.addWidget(check)
        self.diagnostic_text = QTextBrowser()
        diagnostics.addWidget(self.diagnostic_text)
        _, guide = self.page("Guide")
        self.guide = QTextBrowser()
        self.guide.setOpenExternalLinks(False)
        path = ROOT / "docs/SETUP_AND_ADMIN_GUIDE.md"
        self.guide.document().setBaseUrl(QUrl.fromLocalFile(str(path)))
        self.guide.setMarkdown(path.read_text(encoding="utf-8") if path.exists() else "Guide file not found.")
        guide.addWidget(self.guide)

    def page(self, title):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.addTab(widget, title)
        return widget, layout

    def process_log(self, name, line):
        if name in self.process_logs:
            self.process_logs[name].append(line)
        self.window.append_log(f"[{name}] {line}")

    def process_state(self, name, state):
        if name in self.process_labels:
            self.process_labels[name].setText(f"{name.title()}: {state}")
        if name in ("server", "proxy"):
            self.process_log(name, f"STATE: {state}")

    def toggle_process(self, name):
        if not self.process_manager:
            return
        if self.process_manager.is_running(name):
            self.process_manager.stop(name)
        else:
            self.process_manager.start(name)

    def restart_all(self):
        if self.process_manager:
            for name in ("server", "proxy"):
                self.process_manager.restart(name)

    def refresh_postgres_status(self, status):
        self.process_labels["postgres"].setText(f"PostgreSQL: {status}")

    def set_account(self, user_id):
        self.user_id = user_id
        self.invalidate()
        populate(self.inventory_table, [])

    def invalidate(self, *_args):
        self.validation = None
        self.commit.setEnabled(False)
        self.snapshot_status.setText("Validation cleared. Inspect and dry-run the selected file for the active user.")

    def snapshot_changed(self):
        self.invalidate()
        paths = self.watcher.files() + self.watcher.directories()
        if paths:
            self.watcher.removePaths(paths)
        path = Path(self.snapshot_path.text())
        if path.is_file():
            self.watcher.addPath(str(path.resolve()))
            self.watcher.addPath(str(path.resolve().parent))
            if path.with_suffix(".meta.json").exists():
                self.watcher.addPath(str(path.with_suffix(".meta.json").resolve()))

    def require_target(self):
        if self.user_id is None:
            self.window.append_log("ERROR: Load an account first.")
            return False
        return True

    def find_accounts(self):
        query = self.account_search.text()
        self.window._start(lambda: self.service.accounts(query), lambda rows: populate(self.account_table, rows))

    def select_account(self):
        row = self.account_table.currentRow()
        if row >= 0:
            uid = self.account_table.item(row, 0).text()
            self.window.user_id.setText(uid)
            self.window.load_account()

    def read_inventory(self):
        if self.require_target():
            uid, kind = self.user_id, self.inventory_kind.currentText()
            self.window._start(lambda: self.service.inventory(uid, kind), lambda rows: populate(self.inventory_table, rows))

    def choose_snapshot(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose trusted snapshot", str(ROOT), "Snapshot (*.pkl)")
        if path:
            self.snapshot_path.setText(path)

    def inspect_snapshot(self):
        self.invalidate()
        path = self.snapshot_path.text()
        async def operation():
            return load_snapshot(path)
        self.window._start(operation, lambda s: self.snapshot_status.setText(
            f"Inspection PASS: {s.objects} objects, {s.types} types, {s.nulls} null slots.\nSHA-256: {s.sha256}"))

    def validate_snapshot(self):
        if not self.require_target():
            return
        self.invalidate()
        uid, path = self.user_id, self.snapshot_path.text()
        self.snapshot_status.setText("Running temporary-account round-trip and target dry-run…")
        self.window._start(lambda: self.service.validate_import(uid, path, self.progress.emit), self.validated)

    def validated(self, result):
        if result.user_id == self.user_id and result.path == Path(self.snapshot_path.text()).resolve():
            try:
                metadata = result.path.with_suffix(".meta.json")
                if (hashlib.sha256(result.path.read_bytes()).hexdigest() != result.sha256 or
                    hashlib.sha256(metadata.read_bytes() if metadata.exists() else b"").hexdigest() != result.metadata_sha256):
                    self.invalidate()
                    return
            except OSError:
                self.invalidate()
                return
            self.validation = result
            self.commit.setEnabled(True)
            self.snapshot_status.setText(f"PASS — user {result.user_id}; {result.objects} objects; Missing 0 / Extra 0\nSHA-256: {result.sha256}")

    def operation_failed(self):
        if self.snapshot_status.text().startswith("Running"):
            self.invalidate()
            self.snapshot_status.setText("FAIL — inspect/dry-run did not complete. No import committed.")

    def commit_snapshot(self):
        if self.validation is None or not self.require_target():
            return
        uid, path, receipt = self.user_id, self.snapshot_path.text(), self.validation
        name = self.window.info["name"].text()
        text, accepted = QInputDialog.getText(self, "Confirm account replacement",
            f"Target userId: {uid}\nProfile: {name}\nA backup will be saved first.\nType IMPORT {uid} to commit:")
        if not accepted:
            return
        if text != f"IMPORT {uid}":
            self.window.append_log("ERROR: Import confirmation did not match; nothing written.")
            return
        self.invalidate()
        self.window._start(lambda: self.service.commit_import(uid, path, receipt, text, self.progress.emit),
                           lambda backup: self.window.append_log(f"Import committed for user {uid}. Backup: {backup.name}"))

    def export_account(self):
        if not self.require_target():
            return
        directory = QFileDialog.getExistingDirectory(self, "Backup folder", str(BACKUPS if BACKUPS.exists() else ROOT))
        if directory:
            uid, readable = self.user_id, self.json_export.isChecked()
            self.window._start(lambda: self.service.export_account(uid, directory, readable),
                               lambda path: self.window.append_log(f"Export complete: {path}"))

    def refresh_backups(self):
        populate(self.backup_table, list_backups())

    def choose_backup(self):
        row = self.backup_table.currentRow()
        if row >= 0:
            path = self.backup_table.item(row, 4).text()
            self.snapshot_path.setText(path)
            self.setCurrentWidget(self.snapshot_page)
            self.window.append_log("Backup selected. Active target unchanged; inspect and dry-run before restore.")

    def diagnostics(self):
        def show(report):
            self.connection_status.setText(f"DB: {report['db']}\nServer: {report['server']}")
            self.diagnostic_text.setPlainText("\n".join(f"{key}: {value}" for key, value in report.items()))
        self.window._start(self.service.diagnostics, show)
