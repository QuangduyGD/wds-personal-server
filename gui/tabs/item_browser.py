import unicodedata

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTableView, QVBoxLayout,
)

from gui.services.icons import IconResolver, ItemPixmapCache
from gui.services.item_catalogue import load_items


def search_text(value):
    return unicodedata.normalize("NFKC", str(value)).casefold().strip()


class CatalogueWorker(QThread):
    loaded = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            self.loaded.emit(load_items())
        except Exception as exc:
            self.failed.emit(f"Cannot load local ItemMaster ({type(exc).__name__}). Check _data/masterdata.")


class ItemTableModel(QAbstractTableModel):
    HEADERS = ("Icon", "Japanese name", "ItemMaster ID", "Category")

    def __init__(self, items, pixmaps, parent=None):
        super().__init__(parent)
        self.items = items
        self.pixmaps = pixmaps
        self.search_keys = [(search_text(i.name or ""), str(i.id_)) for i in items]

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self.items[index.row()]
        if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
            return self.pixmaps.get(item)
        if role == Qt.ItemDataRole.ToolTipRole:
            return item.description or item.name or str(item.id_)
        if role == Qt.ItemDataRole.DisplayRole:
            category = item.category
            return ("", item.name or "—", str(item.id_),
                    f"{category.name} ({int(category)})" if category is not None else "—")[index.column()]


class ItemFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.query = ""

    def set_query(self, text):
        self.query = search_text(text)
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):
        return any(self.query in key for key in self.sourceModel().search_keys[row])


class ItemBrowser(QDialog):
    item_selected = Signal(object)

    def __init__(self, parent=None, *, items=None, resolver=None):
        super().__init__(parent)
        self.setWindowTitle("Item Browser · local ItemMaster")
        self.resize(900, 620)
        self.worker = None
        self.pixmaps = ItemPixmapCache(resolver or IconResolver())
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search Japanese name, part of a name, or ItemMaster ID…")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.status = QLabel("Loading local master data…")
        layout.addWidget(self.status)
        self.table = QTableView()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(56)
        layout.addWidget(self.table)
        footer = QHBoxLayout()
        footer.addWidget(QLabel("Local icons only · unavailable icons use a placeholder"))
        footer.addStretch()
        self.choose = QPushButton("Use selected item")
        self.choose.setEnabled(False)
        self.choose.setAutoDefault(False)
        footer.addWidget(self.choose)
        layout.addLayout(footer)
        self.proxy = ItemFilter(self)
        self.table.setModel(self.proxy)
        self.search.textChanged.connect(self._search)
        self.choose.clicked.connect(self.use_selected)
        self.table.doubleClicked.connect(self.use_selected)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        if items is None:
            self.worker = CatalogueWorker(self)
            self.worker.loaded.connect(self.set_items)
            self.worker.failed.connect(self.status.setText)
            self.worker.finished.connect(self._loaded)
            self.worker.start()
        else:
            self.set_items(items)

    def _loaded(self):
        self.worker.deleteLater()
        self.worker = None

    def set_items(self, items):
        self.model = ItemTableModel(items, self.pixmaps, self)
        self.proxy.setSourceModel(self.model)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 56)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 220)
        self._search(self.search.text())

    def _search(self, text):
        self.table.clearSelection()
        self.proxy.set_query(text)
        if self.proxy.sourceModel() is not None:
            self.status.setText(f"{self.proxy.rowCount()} / {len(self.model.items)} items")
        self._selection_changed()

    def _selection_changed(self):
        self.choose.setEnabled(bool(self.table.selectionModel().selectedRows()))

    def use_selected(self, *_args):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            row = self.proxy.mapToSource(rows[0]).row()
            self.item_selected.emit(self.model.items[row])
            self.accept()

    def done(self, result):
        if self.worker is not None:
            return  # Do not destroy a running loader thread.
        super().done(result)
