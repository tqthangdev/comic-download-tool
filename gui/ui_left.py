from pathlib import Path

from PyQt6.QtGui import QMovie
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QLabel,
    QTreeWidget,
    QHeaderView,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
    QSpinBox,
    QToolButton,
    QRadioButton,
    QButtonGroup,
)
from PyQt6.QtCore import Qt, QSize, QSettings

from core.utils import get_resource_path, CONFIG, save_config


class LeftPanel(QWidget):
    """
    Left side of the main window:
    - URL input + paste button
    - Save path input + folder picker
    - "Use this path by default" checkbox
    - Add Queue button
    - Chapter header (loading spinner, thumbnail, title)
    - Chapter tree
    """

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)

        self.settings = settings
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ================= URL AREA =================
        url_area = QWidget()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste comic URL...")
        self.url_input.setReadOnly(True)

        self.btn_paste = QPushButton("Paste")
        self.btn_paste.setFixedWidth(80)

        url_layout = QHBoxLayout(url_area)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(6)

        url_label = QLabel("URL")
        url_layout.addWidget(url_label)

        url_layout.addWidget(self.url_input, 1)
        url_layout.addWidget(self.btn_paste)

        # ================= CHECKBOX + SETTINGS =================
        settings_row = QWidget()
        settings_layout = QHBoxLayout(settings_row)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(6)

        self.auto_queue_cb = QCheckBox("Automatically add to queue")
        auto_queue_saved = self.settings.value("auto_queue", False, type=bool)
        self.auto_queue_cb.setChecked(auto_queue_saved)
        self.auto_queue_cb.toggled.connect(self.on_auto_queue_toggled)

        self.btn_settings = QPushButton("Settings")
        self.btn_settings.setFixedWidth(80)
        self.btn_settings.clicked.connect(self.open_settings)

        settings_layout.addWidget(self.auto_queue_cb, 1)
        settings_layout.addWidget(self.btn_settings)

        # ================= PATH AREA =================
        path_area = QWidget()
        path_layout = QHBoxLayout(path_area)

        self.btn_folder = QPushButton("Folder")
        self.btn_folder.setFixedWidth(80)

        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(6)

        path_label = QLabel("Path")
        path_layout.addWidget(path_label)

        self.path_input = QLineEdit()
        default_path = str(Path.home() / "Documents")
        saved_path = self.settings.value("save_path", "", type=str)

        # Path lưu từ lần chạy trước có thể là của máy khác (VD Windows E:\...)
        # hoặc ổ đĩa đã ngắt kết nối -> fallback về thư mục mặc định.
        if not saved_path or not Path(saved_path).is_absolute() or not Path(saved_path).exists():
            saved_path = default_path

        self.path_input.setPlaceholderText("Đường dẫn lưu...")
        self.path_input.setText(saved_path)
        # Luôn cho sửa path, và mỗi lần đổi (pick folder / gõ tay) là lưu lại
        self.path_input.editingFinished.connect(self._save_path)

        path_layout.addWidget(self.path_input, 1)
        path_layout.addWidget(self.btn_folder)

        # ================= TREE =================
        self.tree = QTreeWidget()
        self.tree.setObjectName("detail_tree")
        self.tree.setStyleSheet("""
        QWidget#detail_tree {
            background: transparent;
            border: 1px solid transparent;
        }
        QTreeWidget#detail_tree::item {
            background: transparent;
            color: #00e5ff;
        }
        """)
        self.tree.setHeaderLabels(["Chapter", "Time"])
        self.tree.setHeaderHidden(True)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch,
        )
        self.tree.header().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.ResizeToContents,
        )

        # ================= ADD QUEUE BUTTON =================
        self.btn_add = QPushButton("Add Queue")
        self.btn_add.setDisabled(True)

        # ================= HEADER PANEL =================
        self.chapter_header = QWidget()

        header_main = QVBoxLayout(self.chapter_header)
        header_main.setContentsMargins(4, 4, 4, 4)
        header_main.setSpacing(4)

        # ===== LOADING ROW =====
        loading_layout = QHBoxLayout()

        self.loading = QLabel()
        self.loading.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.movie = QMovie(str(get_resource_path("assets/loading.gif")))
        self.movie.setScaledSize(QSize(48, 48))

        self.loading.setMovie(self.movie)

        loading_layout.addStretch()
        loading_layout.addWidget(self.loading)
        loading_layout.addStretch()

        # ===== INFO ROW =====
        info_layout = QHBoxLayout()

        # THUMB
        self.manga_thumb = QLabel()
        self.manga_thumb.setFixedSize(150, 200)
        self.manga_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # TITLE
        self.manga_title = QLabel("")
        self.manga_title.setStyleSheet("font-size:16px; font-weight:bold; color:#ff9800;")
        self.manga_title.setWordWrap(True)

        info_layout.addWidget(self.manga_thumb)
        info_layout.addWidget(self.manga_title)
        info_layout.addStretch()

        header_main.addLayout(loading_layout)
        header_main.addLayout(info_layout)

        # ================= DETAIL CHAPTER PANEL =================
        self.detail_chapter = QWidget()
        self.detail_chapter.setObjectName("detail_chapter")
        self.detail_chapter.setStyleSheet("""
        QWidget#detail_chapter {
            background: transparent;
            border: 1px solid #adadad;
        }
        QHeaderView::section {
            background: transparent;
            color: #00e5ff;
            border: none;
        }
        """)
        detail_layout = QVBoxLayout(self.detail_chapter)

        detail_layout.addWidget(self.chapter_header)
        detail_layout.addWidget(self.tree)

        # ================= ASSEMBLE LEFT PANEL =================
        layout.addWidget(QLabel(""))
        layout.addWidget(url_area)
        layout.addWidget(path_area)
        layout.addWidget(settings_row)
        layout.addWidget(self.btn_add)
        layout.addWidget(self.detail_chapter)

        # events that only affect this panel's own widgets
        self.btn_folder.clicked.connect(self.pick_folder)

    # =========================
    # LƯU PATH ĐÃ CHỌN (cho lần chạy sau)
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
    # SETTINGS MODAL (đọc/ghi config.json)
    # =========================
    def open_settings(self):
        dialog = _ConfigDialog(self)
        dialog.exec()

    # =========================
    # FOLDER PICKER
    # =========================
    def pick_folder(self):
        from PyQt6.QtWidgets import QFileDialog

        folder = QFileDialog.getExistingDirectory(self, "Chọn folder")
        if folder:
            self.path_input.setText(folder)
            self._save_path()

    # =========================
    # SHOW / HIDE LOADING
    # =========================
    def on_loading(self, show: bool):
        if show:
            self.reset_view()
            self.loading.show()
            self.movie.start()
        else:
            self.movie.stop()
            self.loading.hide()

    # =========================
    # RESET VIEW
    # =========================
    def reset_view(self):
        self.manga_title.clear()
        self.manga_thumb.clear()
        self.tree.setHeaderHidden(True)
        self.tree.clear()


class _ConfigDialog(QDialog):
    """Modal chỉnh các giá trị trong config.json."""

    # (nhãn, key, kiểu, mô tả chi tiết + khuyến nghị)
    FIELDS = [
        (
            "Số truyện tải song song (worker)",
            "max_workers",
            int,
            "Số truyện được xử lý cùng lúc.\n\n"
            "Khuyến nghị: 3-5. Đặt quá cao (10+) khiến máy lag, "
            "chiếm nhiều RAM/CPU và dễ bị website chặn.",
        ),
        (
            "Tổng số ảnh tải đồng thời",
            "max_concurrent_downloads",
            int,
            "Số request tải ảnh tối đa cùng lúc trên toàn app "
            "(chia sẻ giữa mọi truyện đang tải).\n\n"
            "Khuyến nghị: 4-8. Quá cao làm nghẽn băng thông, "
            "ảnh lỗi nhiều và có thể bị chặn IP.",
        ),
        (
            "Số lần thử lại khi tải ảnh lỗi",
            "download_retry",
            int,
            "Khi tải 1 ảnh thất bại, tự động thử lại bao nhiêu lần.\n\n"
            "Khuyến nghị: 2-3. Quá cao làm chậm cả queue khi ảnh "
            "thực sự hỏng (thử lại vô ích).",
        ),
        (
            "Số lần thử lại khi lấy danh sách chapter lỗi",
            "chapter_retry",
            int,
            "Khi không tải được danh sách chapter (mạng chập chờn), "
            "thử lại bao nhiêu lần.\n\n"
            "Khuyến nghị: 2. Quá cao khiến chờ lâu trước khi báo lỗi.",
        ),
        (
            "Thời gian chờ tải trang (giây)",
            "request_timeout",
            int,
            "Thời gian tối đa chờ trang web phản hồi trước khi báo lỗi.\n\n"
            "Khuyến nghị: 30. Quá thấp dễ báo lỗi khi mạng chậm, "
            "quá cao làm treo lâu khi trang không vào được.",
        ),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(480)

        self._inputs = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        for label, key, cast, desc in self.FIELDS:
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

            # Icon "?" — nhấn để mở modal chi tiết option
            btn_help = QToolButton()
            btn_help.setText("?")
            btn_help.setFixedSize(24, 24)
            btn_help.setAutoRaise(True)
            btn_help.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_help.clicked.connect(
                lambda _=False, t=label, d=desc: _HelpDialog(t, d, self).exec()
            )

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)
            row_layout.addWidget(widget, 1)
            row_layout.addWidget(btn_help)

            form.addRow(label, row)

        layout.addLayout(form)

        # ===== RADIO: LƯU THUMBNAIL KHI TẢI =====
        thumb_row = QWidget()
        thumb_layout = QHBoxLayout(thumb_row)
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setSpacing(4)

        self.rb_thumb_yes = QRadioButton("Có")
        self.rb_thumb_no = QRadioButton("Không")
        self._thumb_group = QButtonGroup(self)
        self._thumb_group.addButton(self.rb_thumb_yes)
        self._thumb_group.addButton(self.rb_thumb_no)

        download_thumb = CONFIG.get("download_thumb", True)
        (self.rb_thumb_yes if download_thumb else self.rb_thumb_no).setChecked(True)

        thumb_layout.addWidget(self.rb_thumb_yes)
        thumb_layout.addSpacing(24)
        thumb_layout.addWidget(self.rb_thumb_no)
        thumb_layout.addStretch()

        btn_thumb_help = QToolButton()
        btn_thumb_help.setText("?")
        btn_thumb_help.setFixedSize(24, 24)
        btn_thumb_help.setAutoRaise(True)
        btn_thumb_help.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_thumb_help.clicked.connect(
            lambda _=False: _HelpDialog(
                "Lưu thumbnail khi tải",
                "Có: lưu ảnh bìa (thumb.jpg) vào thư mục mỗi truyện khi tải.\n\n"
                "Không: bỏ qua ảnh bìa, chỉ tải các chapter — tiết kiệm băng thông "
                "và 1 request ảnh mỗi truyện.\n\nKhuyến nghị: Có.",
                self,
            ).exec()
        )

        thumb_layout.addWidget(btn_thumb_help)

        form.addRow("Lưu thumbnail khi tải", thumb_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_save(self):
        new_config = dict(CONFIG)
        for label, key, cast, desc in self.FIELDS:
            widget = self._inputs[key]
            if cast is int:
                new_config[key] = widget.value()
            else:
                text = widget.text().strip()
                if text:
                    new_config[key] = text

        new_config["download_thumb"] = self.rb_thumb_yes.isChecked()

        if save_config(new_config):
            # Cập nhật CONFIG trong bộ nhớ để app dùng ngay
            CONFIG.clear()
            CONFIG.update(new_config)
            self.accept()
        else:
            from PyQt6.QtWidgets import QMessageBox

            QMessageBox.critical(
                self,
                "Lỗi",
                "Không thể ghi config.json. Kiểm tra quyền thư mục."
            )


class _HelpDialog(QDialog):
    """Modal hiển thị chi tiết + khuyến nghị của một option."""

    def __init__(self, title: str, description: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chi tiết option")
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size:14px; font-weight:bold; color:#ff9800;")
        title_label.setWordWrap(True)

        desc_label = QLabel(description)
        desc_label.setWordWrap(True)
        desc_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)

        layout.addWidget(title_label)
        layout.addWidget(desc_label)
        layout.addWidget(buttons)
