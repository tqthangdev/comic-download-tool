from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
)
from PyQt6.QtCore import Qt

from gui.queue_delegate import QueueDelegate


class RightPanel(QWidget):
    """
    Right side of the main window:
    - Start / Pause / Clear Done buttons (phía trên)
    - Queue list (phía dưới)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ================= BUTTON ROW (phía trên) =================
        self.btn_start = QPushButton("Start")
        self.btn_pause = QPushButton("Pause")
        self.btn_clear = QPushButton("Clear Done")

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(6)

        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_pause)
        btn_row.addWidget(self.btn_clear)

        # ================= QUEUE LIST =================
        self.queue_list = QListWidget()
        self.queue_list.setObjectName("queue_list")
        self.queue_list.setStyleSheet("""
        QWidget#queue_list {
            background: transparent;
            border: 1px solid #adadad;
            padding-right: 5px;
        }
        """)
        self.queue_list.setItemDelegate(QueueDelegate())
        self.queue_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        layout.addWidget(QLabel("Queue"))
        layout.addLayout(btn_row)
        layout.addWidget(self.queue_list)

        self.btn_clear.clicked.connect(self.clear_done)

    def exists_in_queue(self, url):
        result = {"exists": False, "data": None}
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)

            if data["url"] == url:
                result["exists"] = True
                result["data"] = data
                return result

        return result

    def add_queue_item(self, job, status="Waiting"):
        result = self.exists_in_queue(job.url)
        if result["exists"]:
            return

        item = QListWidgetItem(job.title)

        item.setData(
            Qt.ItemDataRole.UserRole,
            {
                "url": job.url,
                "title": job.title,
                "status": status,
                "path": str(job.save_path)
            }
        )

        self.queue_list.addItem(item)

    def update_queue_item(self, url, job, status):
        result = self.exists_in_queue(job.url)
        if not result["exists"]:
            self.add_queue_item(job, status)
            return
        else:
            item = result["data"]
            item["status"] = status
            self.queue_list.viewport().update()
            return

    def update_progress(self, title, status):
        for i in range(self.queue_list.count()):
            item = self.queue_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)

            if data["title"] == title:
                data["status"] = status
                item.setData(Qt.ItemDataRole.UserRole, data)
                self.queue_list.viewport().update()
                return

    def clear_done(self):
        """Xóa tất cả items có status = 'Done' khỏi queue"""
        for i in range(self.queue_list.count() - 1, -1, -1):  # Lặp ngược
            item = self.queue_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)

            if data and data.get("status") == "Done":
                self.queue_list.takeItem(i)
