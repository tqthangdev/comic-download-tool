import asyncio
from pathlib import Path
import time

import requests
from qasync import asyncSlot

from PyQt6.QtGui import QPixmap, QCursor
from PyQt6.QtWidgets import QApplication, QWidget, QHBoxLayout, QMessageBox, QPushButton
from PyQt6.QtCore import QSettings, Qt

from gui.ui_left import LeftPanel
from gui.ui_right import RightPanel
from core.logger import logger


class MainWindow(QWidget):

    def __init__(self, engine):
        super().__init__()

        logger.info("GUI INIT OK")

        self.engine = engine
        self.folder = Path("downloads")

        self.settings = QSettings(
            "ComicEngine",
            "ComicDownloader"
        )

        self.setWindowTitle("Comic Download Tool")
        self.setGeometry(100, 100, 900, 650)
        self.setStyleSheet("""
        QWidget {
            background-color: #1e1e1e;
            color: #d4d4d4;
        }
        QPushButton {
            background-color: #3a3a3a;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 5px 12px;
            color: #e0e0e0;
        }
        QPushButton:hover {
            background-color: #4a4a4a;
        }
        QPushButton:pressed {
            background-color: #2f2f2f;
        }
        QPushButton:disabled {
            background-color: #262626;
            border-color: #3a3a3a;
            color: #6e6e6e;
        }
        """)

        self.init_ui()
        self._closing = False
        self._update_pause_button()

    # =========================
    # UI GIỮ NGUYÊN 2 CỘT
    # =========================
    def init_ui(self):
        layout = QHBoxLayout()

        self.left = LeftPanel(self.settings)
        self.right = RightPanel()

        layout.addWidget(self.left, 3)
        layout.addWidget(self.right, 3)

        self.setLayout(layout)

        # ================= EVENTS =================
        self.left.btn_paste.clicked.connect(self.on_paste_url)
        self.left.btn_add.clicked.connect(self.add_queue)

        self.right.btn_start.clicked.connect(self.start_engine)
        self.right.btn_pause.clicked.connect(self.toggle_pause_engine)
        self.engine.progress.connect(self.right.update_progress)

        self._apply_cursors()
        asyncio.ensure_future(self._restore_session())

    def _apply_cursors(self):
        """Qt Style Sheets không hỗ trợ thuộc tính cursor -> set qua code.

        Hover vào button: pointer. Button disabled: not-allowed (forbidden).
        """
        pointer = QCursor(Qt.CursorShape.PointingHandCursor)
        forbidden = QCursor(Qt.CursorShape.ForbiddenCursor)

        buttons = self.findChildren(QPushButton)
        for btn in buttons:
            btn.setCursor(pointer)
            # cập nhật cursor khi trạng thái enabled/disabled thay đổi
            btn.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent

        if isinstance(obj, QPushButton) and event.type() == QEvent.Type.EnabledChange:
            cursor = (
                QCursor(Qt.CursorShape.ForbiddenCursor)
                if not obj.isEnabled()
                else QCursor(Qt.CursorShape.PointingHandCursor)
            )
            obj.setCursor(cursor)
        return super().eventFilter(obj, event)

    # =========================
    # PASTE URL (BTN CLICK)
    # =========================
    @asyncSlot()
    async def on_paste_url(self):
        clipboard = QApplication.clipboard()
        new_url = clipboard.text().strip()

        if not new_url:
            return

        # Clipboard có thể chứa nội dung không phải URL (VD copy nhầm dòng
        # warning từ console) -> kiểm tra trước khi load.
        if not new_url.startswith(("http://", "https://")):
            self._show_message(
                "Lỗi",
                f"Clipboard không chứa URL hợp lệ:\n{new_url[:100]}",
                critical=True
            )
            return

        old_url = self.left.url_input.text().strip()
        old_title = self.left.manga_title.text().strip()

        # Nếu bật "Automatically add to queue" và đang có 1 truyện (A) đã load
        # xong (có title) và khác với url mới (B) -> tự add A vào queue trước
        should_auto_queue = (
                self.left.auto_queue_cb.isChecked()
                and old_url
                and old_title
                and old_url != new_url
                and self.left.btn_add.isEnabled()
        )

        if should_auto_queue:
            await self.add_queue()

        self.left.btn_add.setDisabled(True)
        self.left.url_input.setText(new_url)
        await self.on_load_chapters()

    # =========================
    # LOAD CHAPTER (PASTE URL)
    # =========================
    @asyncSlot()
    async def on_load_chapters(self):
        url = self.left.url_input.text().strip()
        if not url or url == "":
            return

        self.left.on_loading(True)

        try:
            data = await self.engine.crawler.get_chapters(url)

            title = data["title"]
            thumb = data["thumb"]
            chapters = data["chapters"]

            # =========================
            # SET TITLE
            # =========================
            self.left.manga_title.setText(title)

            # =========================
            # SET THUMB (150x200)
            # =========================
            try:
                # Chạy trong thread để không chặn event loop (gif loading xoay liên tục)
                resp = await asyncio.to_thread(requests.get, thumb, timeout=5)
                img = resp.content

                pixmap = QPixmap()
                pixmap.loadFromData(img)
                pixmap = pixmap.scaled(150, 200)

                self.left.manga_thumb.setPixmap(pixmap)

            except Exception:
                self.left.manga_thumb.clear()

            # =========================
            # TREE CHAPTER
            # =========================
            self.left.tree.clear()
            self.left.tree.setHeaderHidden(False)

            from PyQt6.QtWidgets import QTreeWidgetItem

            for chap in chapters:
                QTreeWidgetItem(
                    self.left.tree,
                    [chap["title"], chap["update_time"]]
                )

            self.left.btn_add.setDisabled(False)

            if not chapters:
                self._show_message(
                    "Thông báo",
                    "Không tìm thấy chapter nào cho truyện này."
                )
                self.left.btn_add.setDisabled(True)

            self.left.on_loading(False)

        except Exception as e:
            self.left.on_loading(False)
            logger.error(f"Error fetching preview/chapters: {e}", exc_info=True)

            # Timeout ở đây là do mạng yếu/trang không tải được
            # (trường hợp không có chapter đã được get_chapters xử lý riêng).
            from playwright.async_api import TimeoutError as PWTimeoutError

            if isinstance(e, (TimeoutError, PWTimeoutError)):
                self._show_message(
                    "Lỗi",
                    f"Không thể tải trang, vui lòng kiểm tra mạng:\n{url}",
                    critical=True
                )
            elif "extractor" in str(e).lower():
                self._show_message(
                    "Lỗi",
                    f"Không hỗ trợ website này:\n{url}\n\n"
                    f"Chi tiết: {e}",
                    critical=True
                )
            else:
                self._show_message(
                    "Lỗi",
                    f"Không thể tải danh sách chapter:\n{e}",
                    critical=True
                )

    # =========================
    # ADD QUEUE
    # =========================
    @asyncSlot()
    async def add_queue(self):

        url = self.left.url_input.text().strip()
        title = self.left.manga_title.text().strip()
        base_path = self.left.path_input.text().strip()

        if not url or not title or not base_path:
            return

        self.left.btn_add.setDisabled(True)

        try:

            from core.job_manager import Job
            from core.utils import safe_filename

            save_path = (
                    Path(base_path)
                    /
                    safe_filename(title)
            )

            job = Job(
                url=url,
                title=title,
                save_path=save_path
            )

            # FIX: không tự đoán "already_queued" dựa trên UI list nữa,
            # để engine.add_job() (đọc status thật từ DB) quyết định duy nhất.
            result = await self.engine.add_job(job)
            status = "Waiting" if self.engine.running else ""

            match result:

                case "queued":
                    self.right.update_queue_item(
                        url,
                        job,
                        status
                    )

                case "resume":
                    self.right.update_queue_item(
                        url,
                        job,
                        status
                    )

                case "already_running":
                    self._show_message(
                        "Thông báo",
                        "Truyện đang được tải."
                    )

                case "already_queued":
                    self._show_message(
                        "Thông báo",
                        "Truyện đã có trong hàng đợi."
                    )

            self._update_pause_button()

        except Exception as e:

            self._show_message(
                "Lỗi",
                str(e),
                critical=True
            )

    # =========================
    # NON-MODAL MESSAGE BOX
    # =========================
    def _show_message(self, title, text, critical=False):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(
            QMessageBox.Icon.Critical if critical
            else QMessageBox.Icon.Information
        )
        box.setModal(False)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # giữ reference để tránh bị garbage-collect trước khi hiển thị xong
        if not hasattr(self, "_active_message_boxes"):
            self._active_message_boxes = []
        self._active_message_boxes.append(box)
        box.finished.connect(
            lambda _: self._active_message_boxes.remove(box)
        )

        box.show()

    # =========================
    # CHECK SAVE PATH
    # =========================
    def _check_save_path_exists(self) -> bool:
        path_str = self.left.path_input.text().strip()
        paths_to_check = set()
        if path_str:
            paths_to_check.add(Path(path_str))

        # Thêm các đường dẫn lưu trữ của các job trong hàng đợi
        for i in range(self.right.queue_list.count()):
            item = self.right.queue_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data and "path" in data and data["path"]:
                parent_path = Path(data["path"]).parent
                paths_to_check.add(parent_path)

        if not paths_to_check:
            QMessageBox.warning(
                self,
                "Cảnh báo đường dẫn",
                "Chưa nhập đường dẫn lưu trữ! Vui lòng chọn thư mục trước khi bắt đầu."
            )
            return False

        for path in paths_to_check:
            if not path.exists():
                reply = QMessageBox.question(
                    self,
                    "Thư mục không tồn tại",
                    f"Đường dẫn lưu trữ sau không tồn tại:\n{path}\n\nBạn có muốn tự động tạo thư mục này không?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    try:
                        path.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        QMessageBox.critical(
                            self,
                            "Lỗi tạo thư mục",
                            f"Không thể tạo thư mục lưu trữ:\n{path}\nChi tiết: {e}"
                        )
                        return False
                else:
                    return False

        return True

    # =========================
    # SESSION RESTORE
    # =========================
    @asyncSlot()
    async def _restore_session(self):
        jobs = await self.engine.restore_session()
        for job in jobs:
            label = "Resume" if job.current_chap else "Paused"
            self.right.update_queue_item(job.url, job, label)

    @asyncSlot()
    async def toggle_pause_engine(self):
        if self.engine.running:
            await self.engine.stop()
            self._mark_queue_paused()
            self.right.btn_pause.setText("Resume")
        else:
            if self.right.queue_list.count() == 0:
                return
            if not self._check_save_path_exists():
                return
            self._mark_queue_starting()
            await self.engine.start()
            self.right.btn_pause.setText("Pause")
        self._update_pause_button()

    # =========================
    # ENGINE CONTROL
    # =========================
    @asyncSlot()
    async def start_engine(self):
        if self.engine.running or self.right.queue_list.count() == 0:
            return
        if not self._check_save_path_exists():
            return
        self._mark_queue_starting()
        self.right.btn_pause.setText("Pause")
        await self.engine.start()
        self._update_pause_button()

    # =========================
    # PAUSE BUTTON STATE
    # =========================
    def _update_pause_button(self):
        """Đồng bộ trạng thái nút Pause với engine + queue."""
        has_pending = any(
            self.right.queue_list.item(i).data(Qt.ItemDataRole.UserRole)["status"]
            not in ("Done", "Failed")
            for i in range(self.right.queue_list.count())
        )
        if self.engine.running:
            self.right.btn_pause.setEnabled(True)
            self.right.btn_pause.setText("Pause")
        elif has_pending:
            self.right.btn_pause.setEnabled(True)
            self.right.btn_pause.setText("Resume")
        else:
            self.right.btn_pause.setEnabled(False)
            self.right.btn_pause.setText("Pause")

    # =========================
    # MARK ALL QUEUE ITEMS AS PAUSED (UI)
    # =========================
    def _mark_queue_paused(self):
        for i in range(self.right.queue_list.count()):
            item = self.right.queue_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data["status"] != "Done":
                data["status"] = "Paused"
                item.setData(Qt.ItemDataRole.UserRole, data)
        self.right.queue_list.viewport().update()

    def _mark_queue_starting(self):
        for i in range(self.right.queue_list.count()):
            item = self.right.queue_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data["status"] not in ("Done", "Failed"):
                data["status"] = "Waiting"
                item.setData(Qt.ItemDataRole.UserRole, data)
        self.right.queue_list.viewport().update()

    # =========================
    # CLOSE EVENT CONFIRMATION
    # =========================
    def closeEvent(self, event):
        if self._closing:
            # Lần gọi close() sau khi đã bật cờ _closing -> cho phép đóng thật
            event.accept()
            return

        msg = (
            "Tiến trình tải đang chạy. Bạn có chắc chắn muốn thoát ứng dụng không?"
            if self.engine.running
            else "Bạn có chắc chắn muốn thoát ứng dụng không?"
        )

        reply = QMessageBox.question(
            self,
            "Xác nhận thoát",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            event.ignore()
            return

        # Chặn đóng cửa sổ ngay lập tức để thực hiện dừng engine/dọn dẹp
        event.ignore()

        if self.engine.running:
            logger.info("Stopping engine before exit...")
            asyncio.ensure_future(self._graceful_shutdown())
        else:
            self.engine.pause_idle_jobs()
            self._closing = True
            self.close()

    async def _graceful_shutdown(self):
        self._mark_queue_paused()
        await self.engine.stop()
        self._closing = True
        self.close()
