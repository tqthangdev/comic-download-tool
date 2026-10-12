from pathlib import Path

from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QGroupBox,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
)
from PyQt6.QtCore import Qt, QSettings

from core.utils import CONFIG, save_config
from core.i18n import tr
from core.logger import logger
from gui.widgets import make_checkbox
from gui.panels.preview_chapter import PreviewChapter, IMAGE_FORMAT, PDF_FORMAT

# Shared width for the small buttons on the right of each input row
# (Paste / Folder...). Keeping them equal keeps the rows aligned.
SIDE_BUTTON_WIDTH = 90


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
        # `pdf_cb` is only the DEFAULT format: it seeds the preview's combobox
        # for each story, so a PDF-only user never has to touch it. The combobox
        # then picks the format for that one job.
        self.preview.set_output_format(self.default_format())

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
    # OUTPUT FORMAT
    # =========================
    def default_format(self) -> str:
        """The format new jobs start from (`pdf_cb`, persisted in config.json)."""
        return PDF_FORMAT if self.pdf_cb.isChecked() else IMAGE_FORMAT

    def output_format(self) -> str:
        """The format picked in the preview — the format of the loaded job."""
        return self.preview.output_format()

    def wants_pdf(self) -> bool:
        """True when the loaded story should be converted to PDF."""
        return self.output_format() == PDF_FORMAT

    def apply_default_format(self) -> None:
        """Reset the preview to the default (called for each new story)."""
        self.preview.set_output_format(self.default_format())

    def on_convert_to_pdf_toggled(self, checked):
        """`pdf_cb` is the default: persist it and reflect it on the preview of
        the story currently loaded."""
        self._set_convert_to_pdf(checked)
        self.preview.set_output_format(PDF_FORMAT if checked else IMAGE_FORMAT)

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
        from gui.dialogs.setting_dialog import SettingDialog

        dialog = SettingDialog(self)
        dialog.exec()

    def open_about(self):
        from gui.dialogs.about_dialog import AboutDialog

        dialog = AboutDialog(self)
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
        self.preview.clear()
