from pathlib import Path

from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QGroupBox,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QLabel,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
    QSpinBox,
    QToolButton,
    QRadioButton,
    QButtonGroup,
    QComboBox,
)
from PyQt6.QtCore import Qt, QSettings

from core.utils import CONFIG, save_config
from core.i18n import tr, set_lang, get_lang
from core.logger import logger
from gui.cursor_utils import apply_pointer_cursors
from gui.panels.preview_chapter import PreviewChapter, IMAGE_FORMAT, PDF_FORMAT

# Shared width for the small buttons on the right of each input row
# (Paste / Folder...). Keeping them equal keeps the rows aligned.
SIDE_BUTTON_WIDTH = 90


def make_radio_button(text: str) -> QRadioButton:
    """Create a QRadioButton with the app's custom indicator icons
    (checked/unchecked SVGs) applied, so every radio button in the app
    looks consistent without repeating the same stylesheet everywhere.
    """
    btn = QRadioButton(text)
    return btn


def make_checkbox(text: str) -> QCheckBox:
    """Create a QCheckBox with the app's custom indicator icons
    (checked/unchecked SVGs) applied, so every checkbox in the app
    looks consistent without repeating the same stylesheet everywhere.
    """
    cb = QCheckBox(text)
    return cb


class LeftPanel(QWidget):
    """Left column: the input form (comic URL, save path, options, Add Queue)
    and the preview area (cover, title, output format, chapter list).

    Everything else — settings, select-files, language, version, about, quit —
    lives in the main window's menu bar.
    """

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)

        self.settings = settings
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)

        # ================= DOWNLOAD SETTINGS =================
        source_group = QGroupBox(tr("source"))
        source_layout = QVBoxLayout(source_group)
        source_layout.setContentsMargins(6, 6, 6, 6)
        source_layout.setSpacing(6)

        # ================= URL ROW =================
        url_area = QWidget()
        url_layout = QHBoxLayout(url_area)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(6)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(tr("url_placeholder"))
        self.url_input.setReadOnly(True)
        self.url_input.setFixedHeight(29)

        self.btn_paste = QPushButton(tr("paste"))
        self.btn_paste.setFixedWidth(SIDE_BUTTON_WIDTH)

        url_layout.addWidget(self.url_input, 1)
        url_layout.addWidget(self.btn_paste)

        source_layout.addWidget(url_area)

        # ================= PATH ROW =================
        path_area = QWidget()
        path_layout = QHBoxLayout(path_area)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(6)

        self.path_input = QLineEdit()
        default_path = str(Path.home() / "Documents")
        saved_path = self.settings.value("save_path", "", type=str)

        # The saved path may come from another machine (e.g. Windows E:\...) or a
        # disconnected drive -> fall back to the default folder.
        if not saved_path or not Path(saved_path).is_absolute() or not Path(saved_path).exists():
            saved_path = default_path

        self.path_input.setPlaceholderText(tr("path_placeholder"))
        self.path_input.setText(saved_path)
        # The path is always editable; each change (pick folder / typing) is saved
        self.path_input.editingFinished.connect(self._save_path)

        self.btn_folder = QPushButton(tr("folder"))
        self.btn_folder.setFixedWidth(SIDE_BUTTON_WIDTH)

        path_layout.addWidget(self.path_input, 1)
        path_layout.addWidget(self.btn_folder)

        source_layout.addWidget(path_area)

        # ================= ADD QUEUE BUTTON =================
        self.btn_add = QPushButton(tr("add_queue"))
        self.btn_add.setObjectName("add_queue")
        self.btn_add.setDisabled(True)
        source_layout.addWidget(self.btn_add, 1)

        # ================= OPTIONS (checkboxes) =================
        options_group = QGroupBox(tr("options"))
        options_layout = QVBoxLayout(options_group)
        options_layout.setContentsMargins(6, 6, 6, 6)
        options_layout.setSpacing(6)

        self.auto_queue_cb = make_checkbox(tr("auto_queue"))
        self.auto_queue_cb.setChecked(
            self.settings.value("auto_queue", False, type=bool)
        )
        self.auto_queue_cb.toggled.connect(self.on_auto_queue_toggled)
        options_layout.addWidget(self.auto_queue_cb, 0, Qt.AlignmentFlag.AlignLeft)

        # Output format: exposed as a checkbox here and as the preview's
        # combobox; both write the same config key (`convert_to_pdf`).
        self.pdf_cb = make_checkbox(tr("convert_to_pdf"))
        self.pdf_cb.setChecked(bool(CONFIG.get("convert_to_pdf", False)))
        self.pdf_cb.toggled.connect(self.on_convert_to_pdf_toggled)
        options_layout.addWidget(self.pdf_cb, 0, Qt.AlignmentFlag.AlignLeft)

        shutdown_row = QWidget()
        shutdown_layout = QHBoxLayout(shutdown_row)
        shutdown_layout.setContentsMargins(0, 0, 0, 0)
        shutdown_layout.setSpacing(6)

        self.shutdown_cb = make_checkbox(tr("shutdown_after_done"))
        self.shutdown_cb.setChecked(
            self.settings.value("shutdown_after_done", False, type=bool)
        )
        self.shutdown_cb.toggled.connect(self.on_shutdown_toggled)

        # Text box next to the checkbox: countdown (seconds) before shutdown.
        saved_delay = self.settings.value("shutdown_delay", 60, type=int)
        self.shutdown_delay = QLineEdit()
        self.shutdown_delay.setValidator(QIntValidator(1, 3600, self))
        self.shutdown_delay.setText(str(saved_delay if isinstance(saved_delay, int) else 60))
        self.shutdown_delay.setFixedSize(38, 22)
        self.shutdown_delay.setObjectName("shutdown_delay")
        self.shutdown_delay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.shutdown_delay.setToolTip(tr("shutdown_delay_hint"))
        self.shutdown_delay.editingFinished.connect(self._save_shutdown_delay)
        self.shutdown_delay.setEnabled(self.shutdown_cb.isChecked())

        self.shutdown_delay_unit = QLabel(tr("shutdown_seconds"))
        self.shutdown_delay_unit.setToolTip(tr("shutdown_delay_hint"))

        shutdown_layout.addWidget(self.shutdown_cb)
        shutdown_layout.addWidget(self.shutdown_delay)
        shutdown_layout.addWidget(self.shutdown_delay_unit)
        shutdown_layout.addStretch()
        options_layout.addWidget(shutdown_row, 0)

        # ================= PREVIEW (cover/title/format/chapters) =================
        preview_group = QGroupBox(tr("preview"))
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        preview_layout.setSpacing(6)
        
        self.preview = PreviewChapter()
        preview_layout.addWidget(self.preview, 1)

        layout.addWidget(source_group, 0)
        layout.addWidget(options_group, 0)
        layout.addWidget(preview_group, 0)

        # events that only affect this panel's own widgets
        self.btn_folder.clicked.connect(self.pick_folder)
        self.url_input.textChanged.connect(lambda _=None: self._update_add_button())
        # pdf_cb (persisted) drives the preview's format combobox; changing the
        # combobox writes the setting back, so the two stay in sync.
        self.preview.format_combo.currentIndexChanged.connect(self._on_format_changed)
        self.preview.set_output_format(
            PDF_FORMAT if self.pdf_cb.isChecked() else IMAGE_FORMAT
        )

    # =========================
    # SAVE THE SELECTED PATH (for the next run)
    # =========================
    def _save_path(self):
        path = self.path_input.text().strip()
        if path:
            self.settings.setValue("save_path", path)

    # =========================
    # checkbox "Automatically add to queue"
    # =========================
    def on_auto_queue_toggled(self, checked):
        self.settings.setValue("auto_queue", checked)

    # =========================
    # checkbox "Shutdown when done"
    # =========================
    def on_shutdown_toggled(self, checked):
        self.settings.setValue("shutdown_after_done", checked)
        self.shutdown_delay.setEnabled(checked)

    def _save_shutdown_delay(self):
        """Clamp + persist the countdown value typed in the delay text box."""
        try:
            value = max(1, min(int(self.shutdown_delay.text().strip() or "60"), 3600))
        except ValueError:
            value = 60
        self.shutdown_delay.setText(str(value))
        self.settings.setValue("shutdown_delay", value)

    @property
    def shutdown_delay_seconds(self) -> int:
        """Countdown (seconds) currently shown next to the shutdown checkbox."""
        try:
            return max(1, min(int(self.shutdown_delay.text().strip() or "60"), 3600))
        except ValueError:
            return 60

    # =========================
    # OUTPUT FORMAT (checkbox <-> preview combobox, one config key)
    # =========================
    def on_convert_to_pdf_toggled(self, checked):
        """Persist to config.json — the engine reads it to build the PDFs."""
        self._set_convert_to_pdf(checked)
        self.preview.format_combo.blockSignals(True)
        self.preview.set_output_format(PDF_FORMAT if checked else IMAGE_FORMAT)
        self.preview.format_combo.blockSignals(False)

    def _on_format_changed(self):
        want_pdf = self.preview.output_format() == PDF_FORMAT
        if want_pdf != self.pdf_cb.isChecked():
            self.pdf_cb.blockSignals(True)
            self.pdf_cb.setChecked(want_pdf)
            self.pdf_cb.blockSignals(False)
        self._set_convert_to_pdf(want_pdf)

    def _set_convert_to_pdf(self, checked: bool):
        new_config = dict(CONFIG)
        new_config["convert_to_pdf"] = checked
        if save_config(new_config):
            CONFIG.clear()
            CONFIG.update(new_config)
        else:
            logger.error("[config] Failed to persist convert_to_pdf")

    # =========================
    # UPDATE TEXT WHEN THE LANGUAGE CHANGES
    # =========================
    def retranslate(self):
        self.url_input.setPlaceholderText(tr("url_placeholder"))
        self.path_input.setPlaceholderText(tr("path_placeholder"))
        self.btn_paste.setText(tr("paste"))
        self.btn_folder.setText(tr("folder"))
        self.btn_add.setText(tr("add_queue"))
        self.auto_queue_cb.setText(tr("auto_queue"))
        self.pdf_cb.setText(tr("convert_to_pdf"))
        self.shutdown_cb.setText(tr("shutdown_after_done"))
        self.shutdown_delay.setToolTip(tr("shutdown_delay_hint"))
        self.shutdown_delay_unit.setText(tr("shutdown_seconds"))
        self.shutdown_delay_unit.setToolTip(tr("shutdown_delay_hint"))
        self.preview.retranslate()

    # =========================
    # SETTINGS / ABOUT / VERSION MODALS (opened from the menu bar)
    # =========================
    def open_settings(self):
        dialog = _ConfigDialog(self)
        dialog.exec()

    def open_about(self):
        dialog = _AboutDialog(self)
        dialog.exec()

    def open_version(self):
        from gui.dialogs.version_dialog import VersionDialog

        dialog = VersionDialog(self)
        dialog.exec()

    # =========================
    # FOLDER PICKER
    # =========================
    def pick_folder(self):
        from PyQt6.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(self, tr("pick_folder_title"))
        if folder:
            self.path_input.setText(folder)
            self._save_path()

    # =========================
    # UPDATE ADD-QUEUE BUTTON STATE
    # =========================
    def _update_add_button(self):
        """Enable Add Queue once a URL is loaded and its title is known."""
        self.btn_add.setEnabled(
            bool(self.url_input.text().strip())
            and bool(self.preview.title_text().strip())
        )

    # =========================
    # SHOW / HIDE LOADING
    # =========================
    def on_loading(self, show: bool):
        self.preview.set_loading(show)

    # =========================
    # RESET VIEW
    # =========================
    def reset_view(self):
        self.preview.reset()


class _ConfigDialog(QDialog):
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


class _AboutDialog(QDialog):
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
