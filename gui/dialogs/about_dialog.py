"""About dialog: basic information about the app."""

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QToolButton,
    QDialogButtonBox,
)
from PyQt6.QtCore import Qt

from core.i18n import tr
from core.updater.version import display_version, read_current_version
from gui.widgets import apply_pointer_cursors


class AboutDialog(QDialog):
    """Modal showing basic information about the app."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("about_title"))
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Title
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(4)

        title_label = QLabel(tr('app_title'))
        title_label.setObjectName("dialog_title")
        title_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        title_row.addWidget(title_label)
        title_row.addStretch()

        version = display_version(read_current_version())
        # The "{check}" slot becomes a link that opens the version/update modal.
        check_link = f'<a href="check">{tr("check_version")}</a>'
        desc_label = QLabel(
            tr("about_desc")
            .format(version=version, check=check_link)
            .replace("\n", "<br>")
        )
        desc_label.setWordWrap(True)
        desc_label.setTextFormat(Qt.TextFormat.RichText)
        desc_label.setOpenExternalLinks(False)
        desc_label.linkActivated.connect(self._on_desc_link)
        desc_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )

        buttons = QDialogButtonBox()
        btn_ok = buttons.addButton(tr("ok"), QDialogButtonBox.ButtonRole.AcceptRole)
        btn_ok.clicked.connect(self.accept)

        layout.addLayout(title_row)
        layout.addWidget(desc_label)
        layout.addWidget(buttons)

        apply_pointer_cursors(self)

    def _on_desc_link(self, href: str):
        # Only the "{check}" link opens the update dialog; the source URL link
        # (if any) is left alone.
        if href == "check":
            self._open_version()

    def _open_version(self):
        from gui.dialogs.version_dialog import VersionDialog

        VersionDialog(self).exec()
