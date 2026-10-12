"""Settings dialog: edit the values in config.json."""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
    QSpinBox,
    QLineEdit,
    QToolButton,
    QButtonGroup,
)
from PyQt6.QtCore import Qt

from core.utils import CONFIG, save_config
from core.i18n import tr
from gui.widgets import apply_pointer_cursors, make_radio_button


class _HelpDialog(QDialog):
    """Modal showing the detail + recommendation of an option."""

    def __init__(self, title: str, description: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("settings_help_title"))
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        title_label = QLabel(title)
        title_label.setObjectName("dialog_title")
        title_label.setWordWrap(True)

        desc_label = QLabel(description)
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


class SettingDialog(QDialog):
    """Modal to edit the values in config.json."""

    # (i18n label key, config key, type, i18n description key)
    FIELDS = [
        ("field_max_workers", "max_workers", int, "field_max_workers_desc"),
        ("field_max_concurrent", "max_concurrent_downloads", int, "field_max_concurrent_desc"),
        ("field_download_retry", "download_retry", int, "field_download_retry_desc"),
        ("field_chapter_retry", "chapter_retry", int, "field_chapter_retry_desc"),
        ("field_timeout", "request_timeout", int, "field_timeout_desc"),
    ]

    @staticmethod
    def _make_help_button(callback) -> QToolButton:
        """Create a "?" icon button with the shared hover style,
        used to open a _HelpDialog with more detail about an option."""
        btn = QToolButton()
        btn.setText("?")
        btn.setFixedSize(24, 24)
        btn.setAutoRaise(True)
        btn.clicked.connect(callback)
        return btn

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("settings_title"))
        self.setModal(True)
        self.setMinimumWidth(480)

        self._inputs = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        for label_key, key, cast, desc_key in self.FIELDS:
            label = tr(label_key)
            desc = tr(desc_key)
            value = CONFIG.get(key, "")

            if cast is int:
                widget = QSpinBox()
                widget.setMinimum(1)
                widget.setMaximum(9999)
                try:
                    widget.setValue(int(value))
                except (TypeError, ValueError):
                    widget.setValue(1)
            else:
                widget = QLineEdit(str(value))

            self._inputs[key] = widget

            # "?" icon — click to open the option detail modal
            btn_help = self._make_help_button(
                lambda _=False, t=label, d=desc: _HelpDialog(t, d, self).exec()
            )

            row = QWidget()
            row.setFixedHeight(26)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)

            row_layout.addWidget(widget, 1)
            row_layout.addWidget(btn_help)

            form.addRow(label, row)

        layout.addLayout(form)

        # ===== RADIO: SAVE THUMBNAIL WHEN DOWNLOADING =====
        thumb_row = QWidget()
        thumb_row.setFixedHeight(26)

        thumb_layout = QHBoxLayout(thumb_row)
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setSpacing(4)

        self.rb_thumb_yes = make_radio_button(tr("thumb_yes"))
        self.rb_thumb_no = make_radio_button(tr("thumb_no"))
        self._thumb_group = QButtonGroup(self)
        self._thumb_group.addButton(self.rb_thumb_yes)
        self._thumb_group.addButton(self.rb_thumb_no)

        download_thumb = CONFIG.get("download_thumb", True)
        (self.rb_thumb_yes if download_thumb else self.rb_thumb_no).setChecked(True)

        thumb_layout.addWidget(self.rb_thumb_yes)
        thumb_layout.addSpacing(24)
        thumb_layout.addWidget(self.rb_thumb_no)
        thumb_layout.addStretch()

        btn_thumb_help = self._make_help_button(
            lambda _=False: _HelpDialog(
                tr("thumb_help_title"),
                tr("thumb_help_desc"),
                self,
            ).exec()
        )

        thumb_layout.addWidget(btn_thumb_help)
        form.addRow(tr("save_thumb"), thumb_row)

        # ===== RADIO: SAVE GENRES WHEN DOWNLOADING =====
        genres_row = QWidget()
        genres_row.setFixedHeight(26)

        genres_layout = QHBoxLayout(genres_row)
        genres_layout.setContentsMargins(0, 0, 0, 0)
        genres_layout.setSpacing(4)

        self.rb_genres_yes = make_radio_button(tr("thumb_yes"))
        self.rb_genres_no = make_radio_button(tr("thumb_no"))
        self._genres_group = QButtonGroup(self)
        self._genres_group.addButton(self.rb_genres_yes)
        self._genres_group.addButton(self.rb_genres_no)

        download_genres = CONFIG.get("download_genres", True)
        (self.rb_genres_yes if download_genres else self.rb_genres_no).setChecked(True)

        genres_layout.addWidget(self.rb_genres_yes)
        genres_layout.addSpacing(24)
        genres_layout.addWidget(self.rb_genres_no)
        genres_layout.addStretch()

        btn_genres_help = self._make_help_button(
            lambda _=False: _HelpDialog(
                tr("genres_help_title"),
                tr("genres_help_desc"),
                self,
            ).exec()
        )

        genres_layout.addWidget(btn_genres_help)
        form.addRow(tr("save_genres"), genres_row)

        buttons = QDialogButtonBox()
        btn_apply = buttons.addButton(tr("apply"), QDialogButtonBox.ButtonRole.AcceptRole)
        btn_cancel = buttons.addButton(tr("cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        btn_apply.clicked.connect(self._on_apply)
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(buttons)

        apply_pointer_cursors(self)

        # Don't auto-focus the first widget when the dialog opens.
        self.setFocus()

    def _on_apply(self):
        new_config = dict(CONFIG)
        for label_key, key, cast, desc_key in self.FIELDS:
            widget = self._inputs[key]
            if cast is int:
                new_config[key] = widget.value()
            else:
                text = widget.text().strip()
                if text:
                    new_config[key] = text

        new_config["download_thumb"] = self.rb_thumb_yes.isChecked()
        new_config["download_genres"] = self.rb_genres_yes.isChecked()

        if save_config(new_config):
            # Update the in-memory CONFIG so the change applies immediately
            CONFIG.clear()
            CONFIG.update(new_config)
            self.accept()
        else:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(
                self,
                tr("error"),
                tr("save_error")
            )
