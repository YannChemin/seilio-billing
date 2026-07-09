from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLineEdit,
    QComboBox,
    QFormLayout,
    QMessageBox,
    QHeaderView,
    QGroupBox,
    QScrollArea,
)

from seilio_billing.models import Client

COLUMNS = [
    "Name", "Contact", "Position", "Phone (fixed)", "Phone (mobile)",
    "Email", "City", "Country", "VAT number", "Website",
]

TITLES = ["", "Mr", "Mrs", "Ms", "Dr", "Prof"]


class ClientsTab(QWidget):
    def __init__(self, session_factory):
        super().__init__()
        self.session_factory = session_factory
        self.session = session_factory()
        self._editing_id: int | None = None

        layout = QHBoxLayout(self)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.itemSelectionChanged.connect(self._on_select)
        layout.addWidget(self.table, stretch=2)

        form_scroll = QScrollArea()
        form_scroll.setWidgetResizable(True)
        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)

        company_box = QGroupBox("Client / company")
        company_form = QFormLayout(company_box)
        self.name_edit = QLineEdit()
        self.address_edit = QLineEdit()
        self.postal_edit = QLineEdit()
        self.city_edit = QLineEdit()
        self.country_edit = QLineEdit()
        self.vat_edit = QLineEdit()
        self.website_edit = QLineEdit()
        self.website_edit.setPlaceholderText("https://…")
        company_form.addRow("Name", self.name_edit)
        company_form.addRow("Address", self.address_edit)
        company_form.addRow("Postal code", self.postal_edit)
        company_form.addRow("City", self.city_edit)
        company_form.addRow("Country", self.country_edit)
        company_form.addRow("VAT number", self.vat_edit)
        company_form.addRow("Website", self.website_edit)
        form_layout.addWidget(company_box)

        contact_box = QGroupBox("Contact person")
        contact_form = QFormLayout(contact_box)
        self.title_combo = QComboBox()
        self.title_combo.addItems(TITLES)
        self.title_combo.setEditable(True)
        self.contact_name_edit = QLineEdit()
        self.position_edit = QLineEdit()
        self.phone_fixed_edit = QLineEdit()
        self.phone_mobile_edit = QLineEdit()
        self.email_edit = QLineEdit()
        contact_form.addRow("Title", self.title_combo)
        contact_form.addRow("Contact name", self.contact_name_edit)
        contact_form.addRow("Position", self.position_edit)
        contact_form.addRow("Phone (fixed)", self.phone_fixed_edit)
        contact_form.addRow("Phone (mobile)", self.phone_mobile_edit)
        contact_form.addRow("Email", self.email_edit)
        form_layout.addWidget(contact_box)

        notes_box = QGroupBox("Notes")
        notes_form = QFormLayout(notes_box)
        self.notes_edit = QLineEdit()
        notes_form.addRow(self.notes_edit)
        form_layout.addWidget(notes_box)

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._save)
        self.new_btn = QPushButton("New")
        self.new_btn.clicked.connect(self._clear_form)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(self._delete)
        btn_row.addWidget(self.new_btn)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.delete_btn)
        form_layout.addLayout(btn_row)
        form_layout.addStretch()

        form_scroll.setWidget(form_container)
        layout.addWidget(form_scroll, stretch=1)

        self.refresh()

    def refresh(self):
        clients = self.session.query(Client).order_by(Client.name).all()
        self.table.setRowCount(len(clients))
        for row, c in enumerate(clients):
            contact = " ".join(p for p in (c.title, c.contact_name) if p)
            values = [
                c.name, contact, c.position, c.phone_fixed, c.phone_mobile,
                c.contact_email, c.city, c.country, c.vat_number, c.website,
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(val or "")
                item.setData(256, c.id)  # Qt.ItemDataRole.UserRole == 256
                self.table.setItem(row, col, item)

    def _on_select(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table.item(rows[0].row(), 0)
        client_id = item.data(256)
        client = self.session.get(Client, client_id)
        if client is None:
            return
        self._editing_id = client.id
        self.name_edit.setText(client.name)
        self.address_edit.setText(client.address_line)
        self.postal_edit.setText(client.postal_code)
        self.city_edit.setText(client.city)
        self.country_edit.setText(client.country)
        self.vat_edit.setText(client.vat_number)
        self.website_edit.setText(client.website)
        self.title_combo.setCurrentText(client.title)
        self.contact_name_edit.setText(client.contact_name)
        self.position_edit.setText(client.position)
        self.phone_fixed_edit.setText(client.phone_fixed)
        self.phone_mobile_edit.setText(client.phone_mobile)
        self.email_edit.setText(client.contact_email)
        self.notes_edit.setText(client.notes)

    def _clear_form(self):
        self._editing_id = None
        for edit in (
            self.name_edit,
            self.address_edit,
            self.postal_edit,
            self.city_edit,
            self.country_edit,
            self.vat_edit,
            self.website_edit,
            self.contact_name_edit,
            self.position_edit,
            self.phone_fixed_edit,
            self.phone_mobile_edit,
            self.email_edit,
            self.notes_edit,
        ):
            edit.clear()
        self.title_combo.setCurrentIndex(0)
        self.table.clearSelection()

    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing name", "Client name is required.")
            return
        if self._editing_id is not None:
            client = self.session.get(Client, self._editing_id)
        else:
            client = Client(name=name)
            self.session.add(client)
        client.name = name
        client.address_line = self.address_edit.text().strip()
        client.postal_code = self.postal_edit.text().strip()
        client.city = self.city_edit.text().strip()
        client.country = self.country_edit.text().strip()
        client.vat_number = self.vat_edit.text().strip()
        client.website = self.website_edit.text().strip()
        client.title = self.title_combo.currentText().strip()
        client.contact_name = self.contact_name_edit.text().strip()
        client.position = self.position_edit.text().strip()
        client.phone_fixed = self.phone_fixed_edit.text().strip()
        client.phone_mobile = self.phone_mobile_edit.text().strip()
        client.contact_email = self.email_edit.text().strip()
        client.notes = self.notes_edit.text().strip()
        self.session.commit()
        self._clear_form()
        self.refresh()

    def _delete(self):
        if self._editing_id is None:
            return
        client = self.session.get(Client, self._editing_id)
        if client is None:
            return
        if client.documents:
            QMessageBox.warning(
                self, "Cannot delete", "This client has documents attached; remove those first."
            )
            return
        self.session.delete(client)
        self.session.commit()
        self._clear_form()
        self.refresh()
