import asyncio
import sys
from pathlib import Path
import time

import requests
from qasync import asyncSlot

from PyQt6.QtGui import QPixmap, QCursor, QIcon
from PyQt6.QtWidgets import QApplication, QDialog, QProgressDialog, QWidget, QHBoxLayout, QMessageBox, QPushButton
from PyQt6.QtCore import QSettings, QTimer, Qt

from gui.ui_left import LeftPanel
from gui.ui_right import RightPanel
from gui.custom_dialog import RestoreDialog
from core.logger import logger
from core.i18n import tr, add_listener


class MainWindow(QWidget):

    def __init__(self, engine):
        super().__init__()

        # Set the main window icon (works both in development and after building)
        base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
        icon_path = base / "assets" / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        logger.info("GUI INIT OK")

        self.engine = engine
        self.folder = Path("downloads")

        self.settings = QSettings(
            "ComicEngine",
            "ComicDownloader"
        )

        # Read language from config.json (default vi)
        from core.i18n import set_lang
        from core.utils import CONFIG
        set_lang(CONFIG.get("language", "vi"))

        self.setWindowTitle(tr("app_title"))
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
        QLineEdit {
            background-color: #2d2d2d;
            border: 1px solid #ffffff;
            border-radius: 4px;
            padding: 5px 8px;
            color: #e0e0e0;
        }
        QLineEdit:focus {
            border: 2px solid #4fc3f7;
            background-color: #333333;
        }
        """)

        self.init_ui()
        self._closing = False
        self._loaded_data = None  # scraper result (title/thumb/referer/chapters) of the URL being previewed
        self._update_pause_button()

    # =========================
    # UI KEEPS 2 COLUMNS
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
        self.right.btn_resume.clicked.connect(self.toggle_resume_engine)
        self.right.btn_pause.clicked.connect(self.toggle_pause_engine)
        self.engine.progress.connect(self.right.update_progress)
        self.engine.finished.connect(self._update_pause_button)

        self._apply_cursors()
        add_listener(self._retranslate)

        # Wait for the window to finish rendering
        QTimer.singleShot(100, self._start_restore)

    def _start_restore(self):
        self.restore_modal = RestoreDialog(self)

        self.restore_modal.show()

        # Let the modal render first
        QTimer.singleShot(
            0,
            self._run_restore
        )


    def _run_restore(self):
        task = asyncio.ensure_future(
            self._restore_session()
        )

        task.add_done_callback(
            self._restore_finished
        )

    def _restore_finished(self, future):
        try:
            future.result()

        except Exception:
            logger.exception(
                "Failed to restore session"
            )

        finally:
            if self.restore_modal:
                self.restore_modal.done(
                    QDialog.DialogCode.Accepted
                )

                self.restore_modal.deleteLater()
                self.restore_modal = None

    def _retranslate(self):
        self.setWindowTitle(tr("app_title"))
        self.left.retranslate()
        self.right.retranslate()
        self._update_pause_button()

    def _apply_cursors(self):
        """Qt Style Sheets do not support the cursor property -> set it in code.

        Hover over a button: pointer. Disabled button: not-allowed (forbidden).
        """
        pointer = QCursor(Qt.CursorShape.PointingHandCursor)
        forbidden = QCursor(Qt.CursorShape.ForbiddenCursor)

        buttons = self.findChildren(QPushButton)
        for btn in buttons:
            btn.setCursor(pointer)
            # update the cursor when the enabled/disabled state changes
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

        # The clipboard may hold non-URL content (e.g. accidentally copied a
        # console warning line) -> validate before loading.
        if not new_url.startswith(("http://", "https://")):
            self._show_message(
                tr("error"),
                f"{tr('clipboard_invalid')}:\n{new_url[:100]}",
                critical=True
            )
            return

        old_url = self.left.url_input.text().strip()
        old_title = self.left.manga_title.text().strip()

        # If "Automatically add to queue" is on and there is a story (A) already
        # loaded (has a title) different from the new url (B), auto-add A first
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
        from core.utils import CONFIG
        url = self.left.url_input.text().strip()
        if not url or url == "":
            return

        self.left.on_loading(True)

        try:
            data = await self.engine.crawler.get_chapters(url)
            self._loaded_data = data

            title = data.get("title", "")
            thumb = data.get("thumb", "")
            chapters = data.get("chapters") or []

            # =========================
            # SET TITLE
            # =========================
            self.left.manga_title.setText(title)

            # =========================
            # SET THUMB (150x200)
            # =========================
            try:
                # Run in a thread so the loading gif keeps spinning (does not block the event loop)
                headers = {
                    "User-Agent": CONFIG["user_agent"],
                    "Referer": data.get("referer") or "",
                }
                resp = await asyncio.to_thread(requests.get, thumb, headers=headers, timeout=5)
                img = resp.content

                pixmap = QPixmap()
                pixmap.loadFromData(img)
                pixmap = pixmap.scaled(150, 200)

                self.left.manga_thumb.setPixmap(pixmap)

            except Exception as e:
                logger.error(f"Thumbnail preview load error: {e}")
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
                    tr("notify"),
                    tr("no_chapters")
                )
                self.left.btn_add.setDisabled(True)

            self.left.on_loading(False)

        except Exception as e:
            self.left.on_loading(False)
            logger.error(f"Error fetching preview/chapters: {e}", exc_info=True)

            # Timeout/network error from scraper.py (requests) — page could not load
            # (the no-chapters case is handled separately by get_chapters).
            if isinstance(e, (TimeoutError, requests.RequestException)):
                self._show_message(
                    tr("error"),
                    f"{tr('network_error')}:\n{url}",
                    critical=True
                )
            else:
                self._show_message(
                    tr("error"),
                    f"{tr('load_chapters_error')}:\n{e}",
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

            loaded = self._loaded_data or {}
            job = Job(
                url=url,
                title=title,
                save_path=save_path,
                chapters=loaded.get("chapters") or None,
                referer=loaded.get("referer"),
                thumb=loaded.get("thumb") or None,
            )

            # FIX: no longer guess "already_queued" from the UI list; let
            # engine.add_job() (which reads the real status from the DB) decide.
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
                        tr("notify"),
                        tr("already_running")
                    )

                case "already_queued":
                    self._show_message(
                        tr("notify"),
                        tr("already_queued")
                    )

            self._update_pause_button()

        except Exception as e:

            self._show_message(
                tr("error"),
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

        # keep a reference to avoid being garbage-collected before it finishes showing
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

        # Also add the storage paths of the queued jobs
        for i in range(self.right.queue_list.count()):
            item = self.right.queue_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data and "path" in data and data["path"]:
                parent_path = Path(data["path"]).parent
                paths_to_check.add(parent_path)

        if not paths_to_check:
            QMessageBox.warning(
                self,
                tr("path_warning_title"),
                tr("path_empty")
            )
            return False

        for path in paths_to_check:
            if not path.is_absolute():
                QMessageBox.warning(
                    self,
                    tr("path_invalid_title"),
                    f"{tr('path_invalid')}:\n{path}\n\n"
                    f"{tr('pick_folder_title')}."
                )
                return False
            if not path.exists():
                QMessageBox.warning(
                    self,
                    tr("path_not_found_title"),
                    f"{tr('path_not_found')}:\n{path}\n\n"
                    f"{tr('pick_folder_title')}."
                )
                return False

        return True

    # =========================
    # SESSION RESTORE
    # =========================
    @asyncSlot()
    async def _restore_session(self):
        base_path = self.left.path_input.text().strip()

        queue = self.right.queue_list
        queue.setUpdatesEnabled(False)

        try:
            async for current, total, job in self.engine.restore_session(
                base_path
            ):
                status = getattr(job, "status", None)

                if status == "done_with_missing":
                    status = "Done with missing"

                elif status not in (
                    "Paused",
                    "Waiting",
                    "Done",
                    "Failed",
                ):
                    status = "Paused" if job.current_chap else ""

                self.right.update_queue_item(
                    job.url,
                    job,
                    status
                )

                if self.restore_modal:
                    self.restore_modal.set_progress(
                        current,
                        total
                    )

                # Let Qt repaint and process events
                if current % 10 == 0:
                    await asyncio.sleep(0)

        finally:
            queue.setUpdatesEnabled(True)
            queue.viewport().update()

        self._update_pause_button()

    # =========================
    # BTN PAUSE
    # =========================
    @asyncSlot()
    async def toggle_pause_engine(self):
        if self.engine.running:
            await self.engine.stop()
            self._mark_queue_paused()

        self._update_pause_button()

    # =========================
    # BTN RESUME
    # =========================
    @asyncSlot()
    async def toggle_resume_engine(self):
        if not self.engine.running:
            if self.right.queue_list.count() == 0:
                return
            if not self._check_save_path_exists():
                return
            self._mark_queue_starting()
            # Re-apply the current save path (from the path input) so a changed
            # folder is used instead of the old one captured at Add Queue time.
            base_path = self.left.path_input.text().strip()
            await self.engine.sync_paths(base_path)
            await self.engine.start()

        self._update_pause_button()

    # =========================
    # ENGINE CONTROL
    # =========================
    @asyncSlot()
    async def start_engine(self):
        if self.engine.running:
            return
        if self.right.queue_list.count() == 0:
            self._show_message(
                tr("notify"),
                tr("queue_empty")
            )
            return
        if not self._check_save_path_exists():
            return
        self._mark_queue_starting()
        # Re-apply the current save path (from the path input) so a changed
        # folder is used instead of the old one captured at Add Queue time.
        base_path = self.left.path_input.text().strip()
        await self.engine.sync_paths(base_path)
        await self.engine.start()
        self._update_pause_button()

    # =========================
    # PAUSE BUTTON STATE
    # =========================
    def _update_pause_button(self):
        can_resume = any(
            self.right.queue_list.item(i)
            .data(Qt.ItemDataRole.UserRole)["status"] == "Paused"
            for i in range(self.right.queue_list.count())
        )

        if self.engine.running:
            self.right.btn_resume.setEnabled(False)
            self.right.btn_pause.setEnabled(True)

        elif can_resume:
            self.right.btn_resume.setEnabled(True)
            self.right.btn_pause.setEnabled(False)

        else:
            self.right.btn_resume.setEnabled(False)
            self.right.btn_pause.setEnabled(False)

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
            event.accept()
            return

        msg = (
            tr("close_confirm_running")
            if self.engine.running
            else tr("close_confirm_idle")
        )

        box = QMessageBox(self)
        box.setWindowTitle(tr("close_confirm_title"))
        box.setText(msg)
        box.setIcon(QMessageBox.Icon.Question)

        btn_yes = box.addButton(
            tr("yes"),
            QMessageBox.ButtonRole.YesRole
        )
        btn_no = box.addButton(
            tr("no"),
            QMessageBox.ButtonRole.NoRole
        )

        box.setDefaultButton(btn_no)
        box.exec()

        if box.clickedButton() != btn_yes:
            event.ignore()
            return

        # Prevent immediate closing
        event.ignore()

        if self.engine.running:
            logger.info("Stopping engine before exit...")
            asyncio.ensure_future(
                self._graceful_shutdown()
            )
        else:
            asyncio.ensure_future(
                self._shutdown_idle()
            )

    async def _shutdown_idle(self):
        try:
            if hasattr(self.engine, "prepare_shutdown"):
                await self.engine.prepare_shutdown()
            else:
                logger.info("No prepare_shutdown method found in engine, skipping...")

        except Exception:
            logger.exception("Failed to prepare shutdown")

        finally:
            self._closing = True
            self.close()

    async def _graceful_shutdown(self):
        try:
            await self.engine.stop()

        except Exception:
            logger.exception("Failed to stop engine")

        finally:
            self._closing = True
            self.close()