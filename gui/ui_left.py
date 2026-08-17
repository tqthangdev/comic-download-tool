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
)
from PyQt6.QtCore import Qt, QSize, QSettings

from core.utils import get_resource_path


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

        # ================= CHECKBOX =================
        self.auto_queue_cb = QCheckBox("Automatically add to queue")
        auto_queue_saved = self.settings.value("auto_queue", False, type=bool)
        self.auto_queue_cb.setChecked(auto_queue_saved)
        self.auto_queue_cb.toggled.connect(self.on_auto_queue_toggled)

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
        layout.addWidget(self.auto_queue_cb)
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
