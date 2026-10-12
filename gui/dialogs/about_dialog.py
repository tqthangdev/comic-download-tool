"""About dialog: basic information about the app."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QDialogButtonBox,
)
from PyQt6.QtCore import Qt

from core.i18n import tr
from gui.widgets import apply_pointer_cursors


class AboutDialog(QDialog):
    """Modal showing basic information about the app."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("about_title"))
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        title_label = QLabel(tr("app_title"))
        title_label.setObjectName("dialog_title")
        title_label.setWordWrap(True)

        desc_label = QLabel(tr("about_desc"))
        desc_label.setWordWrap(True)
        desc_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        buttons = QDialogButtonBox()
        btn_ok = buttons.addButton(tr("ok"), QDialogButtonBox.ButtonRole.AcceptRole)
        btn_ok.clicked.connect(self.accept)

        layout.addWidget(title_label)
        layout.addWidget(desc_label)
        layout.addWidget(buttons)

        apply_pointer_cursors(self)
