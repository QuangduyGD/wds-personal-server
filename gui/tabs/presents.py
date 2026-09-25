from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLineEdit, QPushButton, QSpinBox

from helpers.admin import NO_ID_TYPES, validate_present
from models.enums import ThingTypes


class PresentForm(QGroupBox):
    def __init__(self, parent=None):
        super().__init__("Give Present — delivered to the in-game inbox", parent)
        layout = QFormLayout(self)
        self.thing_type = QComboBox()
        for thing in ThingTypes:
            self.thing_type.addItem(thing.name, int(thing))
        self.thing_id = QLineEdit()
        self.thing_id.setPlaceholderText("Required master ID")
        self.thing_id.setValidator(QRegularExpressionValidator(QRegularExpression("[0-9]{0,19}"), self))
        self.browse = QPushButton("Browse Items…")
        self.browse.clicked.connect(self.browse_items)
        self.browser = None
        item_row = QHBoxLayout()
        item_row.addWidget(self.thing_id)
        item_row.addWidget(self.browse)
        self.amount = QSpinBox()
        self.amount.setRange(1, 2**31 - 1)
        self.message = QLineEdit()
        self.message.setPlaceholderText("Optional present title and description")
        self.send = QPushButton("Give Present")
        layout.addRow("ThingType", self.thing_type)
        layout.addRow("thingId", item_row)
        layout.addRow("Amount", self.amount)
        layout.addRow("Message", self.message)
        layout.addRow(self.send)
        self.thing_type.currentIndexChanged.connect(self._type_changed)
        self.thing_type.setCurrentIndex(self.thing_type.findData(int(ThingTypes.Coin)))
        self._type_changed()

    def browse_items(self):
        from gui.tabs.item_browser import ItemBrowser
        if self.browser is None:
            self.browser = ItemBrowser(self)
            self.browser.item_selected.connect(self.select_item)
        self.browser.exec()

    def select_item(self, item):
        self.thing_type.setCurrentIndex(self.thing_type.findData(int(ThingTypes.Item)))
        self.thing_id.setText(str(item.id_))

    def _type_changed(self):
        needs_id = ThingTypes(self.thing_type.currentData()) not in NO_ID_TYPES
        self.thing_id.setEnabled(needs_id)
        self.thing_id.setPlaceholderText("Required master ID" if needs_id else "Not applicable (0)")

    def values(self, user_id):
        thing_type = ThingTypes(self.thing_type.currentData())
        thing_id = int(self.thing_id.text() or "0") if thing_type not in NO_ID_TYPES else 0
        amount = self.amount.value()
        validate_present(user_id, thing_type, thing_id, amount)
        return thing_type, thing_id, amount, self.message.text()
