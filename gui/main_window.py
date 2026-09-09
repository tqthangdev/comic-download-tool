import asyncio
import os
import platform
import subprocess
import sys
from pathlib import Path
import time

import requests
from qasync import asyncSlot

from PyQt6.QtGui import QPixmap, QCursor, QIcon
from PyQt6.QtWidgets import QApplication, QDialog, QWidget, QHBoxLayout, QMessageBox, QPushButton
from PyQt6.QtCore import QSettings, QTimer, Qt, QEvent

from gui.ui_left import LeftPanel
from gui.ui_right import RightPanel
from gui.restore_dialog import RestoreDialog
from gui.login_dialog import prompt_login
from gui.cursor_utils import apply_pointer_cursors
from gui.theme import MAIN_WINDOW_STYLE
from core.logger import logger
from core.i18n import tr, add_listener
from core.auth import auth_manager


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
        self.resize(850, 650)
        screen = self.screen().availableGeometry()
        window = self.frameGeometry()
        window.moveCenter(screen.center())
        self.move(window.topLeft())
        self.setStyleSheet(MAIN_WINDOW_STYLE)

        self.init_ui()
        self._closing = False
        self._loaded_data = None  # scraper result (title/thumb/referer/chapters) of the URL being previewed
        self._loaded_site_id = None  # site_id (core/auth) the previewed URL belongs to, or None if public
        self._shutdown_cancelled = False
        self._shutdown_seconds_left = 0
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
        self.right.deleteRequested.connect(self.delete_job)
        self.engine.progress.connect(self.right.update_progress)
        self.engine.finished.connect(self._update_pause_button)
        self.engine.finished.connect(self._on_engine_finished)
        self.engine.login_required.connect(self.on_login_required)

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

        Hover over a button/tool button: pointer, and switches to "forbidden"
        when disabled (tracked via eventFilter). Checkboxes and radio buttons:
        pointer, no disabled-state tracking needed in this app.
        """
        apply_pointer_cursors(self, event_filter=self)

    def eventFilter(self, obj, event):
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

        # Auto-detect whether this URL belongs to a site that requires login
        # (see core/auth). If it does and we're not authenticated yet, ask
        # for credentials *before* crawling, so the first request already
        # carries a valid session instead of failing/returning locked content.
        site_id = auth_manager.site_id_for_url(url)
        self._loaded_site_id = site_id

        if site_id and not auth_manager.is_logged_in(site_id):
            if not prompt_login(self, default_site=site_id):
                # User cancelled the login prompt — abort loading this URL.
                return

        self.left.on_loading(True)

        try:
            data = await self.engine.crawler.get_chapters(url, site_id=site_id)
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
                cookies = auth_manager.get_cookies(site_id) if site_id else None
                if site_id:
                    headers.update(auth_manager.get_headers(site_id))
                resp = await asyncio.to_thread(
                    requests.get, thumb, headers=headers, cookies=cookies, timeout=5
                )
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

            if not chapters:
                self._show_message(
                    tr("notify"),
                    tr("no_chapters")
                )
                self.left.btn_add.setEnabled(False)
            else:
                self.left._update_add_button()

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

        # Branch on the selected mode:
        #   auto -> import all links from the chosen file
        #   manual -> add the single URL currently pasted in the input box
        if self.left.rb_auto.isChecked():
            import_file = self.left.file_input.text().strip()
            await self.add_jobs_from_file(import_file)
            return

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
            # Use the site_id detected when this URL was previewed (on_load_chapters).
            # Falls back to a fresh detection in case add_queue is ever called
            # for a url that wasn't previewed through the normal flow.
            site_id = self._loaded_site_id or auth_manager.site_id_for_url(url)
            job = Job(
                url=url,
                title=title,
                save_path=save_path,
                chapters=loaded.get("chapters") or None,
                referer=loaded.get("referer"),
                thumb=loaded.get("thumb") or None,
                genres=loaded.get("genres") or None,
                site_id=site_id,
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
            self.left._update_add_button()

        except Exception as e:

            self._show_message(
                tr("error"),
                str(e),
                critical=True
            )

    # =========================
    # ADD JOBS FROM FILE
    # =========================
    @asyncSlot(str)
    async def add_jobs_from_file(self, path: str):
        """Read a list of links from a file and add each one to the queue.

        Login is resolved once per site (not per link) in a sequential pass,
        then chapters are crawled concurrently (bounded by max_workers) since
        the network request is the slow part.
        """
        base_path = self.left.path_input.text().strip()
        if not base_path:
            self._show_message(
                tr("path_warning_title"),
                tr("path_empty"),
                critical=True,
            )
            return

        from core.job_manager import Job
        from core.utils import safe_filename, CONFIG

        if not os.path.exists(path):
            self._show_message(
                tr("error"),
                tr("file_empty"),
                critical=True,
            )
            return

        from core.utils import parse_link_file

        links, error_code, error_detail = parse_link_file(path)

        if error_code is not None:
            message = tr(f"import_error_{error_code}")
            if error_detail:
                message = f"{message}\n\n{error_detail}"

            self._show_message(
                tr("import_error_title"),
                message,
                critical=True,
            )
            return

        from gui.add_jobs_dialog import AddJobsDialog

        modal = AddJobsDialog(self)
        modal.set_progress(0, len(links))
        modal.show()
        # Give the modal a chance to paint before the first crawl
        await asyncio.sleep(0)

        # ---- Pass 1: resolve site_id per link, ask login ONCE per site ----
        # (previously this was checked/prompted inside the per-link loop, which
        # is fine sequentially but would race if done inside the concurrent pass)
        site_map = {}
        sites_needed = set()
        for url in links:
            site_id = auth_manager.site_id_for_url(url)
            site_map[url] = site_id
            if site_id:
                sites_needed.add(site_id)

        for site_id in sites_needed:
            if not auth_manager.is_logged_in(site_id):
                if not prompt_login(self, default_site=site_id):
                    # User cancelled login for this site -> drop every link
                    # belonging to it instead of failing the whole batch.
                    links = [u for u in links if site_map[u] != site_id]

        if not links:
            modal.close()
            modal.deleteLater()
            self._show_message(
                tr("notify"),
                tr("adding_jobs_done").format(added=0),
            )
            return

        modal.set_progress(0, len(links))

        # ---- Pass 2: crawl concurrently, bounded by max_workers ----
        max_workers = max(1, int(CONFIG.get("max_workers", 4)))
        semaphore = asyncio.Semaphore(max_workers)
        db_lock = asyncio.Lock()  # serialize add_job + UI update, not the crawling
        state = {"completed": 0, "added": 0}

        async def process(url):
            site_id = site_map.get(url)
            data = None
            try:
                async with semaphore:
                    data = await self.engine.crawler.get_chapters(url, site_id=site_id)
            except Exception as e:
                logger.error(f"[add_from_file] Skipped {url}: {e}")

            title = data.get("title", "") if data else ""
            if title:
                save_path = Path(base_path) / safe_filename(title)
                job = Job(
                    url=url,
                    title=title,
                    save_path=save_path,
                    chapters=data.get("chapters") or None,
                    referer=data.get("referer"),
                    thumb=data.get("thumb") or None,
                    genres=data.get("genres") or None,
                    site_id=site_id,
                )

                async with db_lock:
                    result = await self.engine.add_job(job)
                    status = "Waiting" if self.engine.running else ""
                    if result in ("queued", "resume"):
                        self.right.update_queue_item(url, job, status)
                        state["added"] += 1

            state["completed"] += 1
            modal.set_progress(state["completed"], len(links))
            # Let Qt repaint periodically without adding it to every task
            if state["completed"] % 5 == 0:
                await asyncio.sleep(0)

        try:
            await asyncio.gather(*(process(url) for url in links))
        finally:
            modal.close()
            modal.deleteLater()

        self._update_pause_button()
        self._show_message(
            tr("notify"),
            tr("adding_jobs_done").format(added=state["added"]),
        )

    # =========================
    # LOGIN REQUIRED (from Engine, mid-queue)
    # =========================
    def on_login_required(self, job_title: str, url: str, site_id: str):
        """A queued/running job was paused because its site needs login
        (see Engine.login_required). Ask the user to sign in, then resume
        the job automatically if they do.
        """
        self._show_message(
            tr("notify"),
            f"'{job_title}' {tr('login_required_message').format(site_id)}."
        )

        if not site_id or not prompt_login(self, default_site=site_id):
            return  # user cancelled — job stays "paused" in the DB, can resume later

        job = self.engine.db.get_job(url)
        if job:
            asyncio.ensure_future(self.engine.add_job(job))
            self._update_pause_button()

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
            if data["status"] not in ("Done", "Failed", "Done with missing images"):
                data["status"] = "Paused"
                item.setData(Qt.ItemDataRole.UserRole, data)
        self.right.queue_list.viewport().update()

    def _mark_queue_starting(self):
        for i in range(self.right.queue_list.count()):
            item = self.right.queue_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data["status"] not in ("Done", "Failed", "Done with missing images"):
                data["status"] = "Waiting"
                item.setData(Qt.ItemDataRole.UserRole, data)
        self.right.queue_list.viewport().update()

    # =========================
    # DELETE JOB (TRASH ICON)
    # =========================
    @asyncSlot(str)
    async def delete_job(self, url: str):
        """Xóa job hoàn toàn: khỏi queue/active, khỏi DB, khỏi queue list.

        Được gọi từ nút thùng rác (RightPanel.deleteRequested).
        """
        try:
            removed = await self.engine.del_job(url)

            if removed:
                self.right.remove_queue_item(url)
                self._update_pause_button()
            else:
                # Job is no longer in the DB/queue -> just clean up any leftover UI item
                self.right.remove_queue_item(url)
        except Exception as e:
            logger.error(f"Failed to delete job {url}: {e}", exc_info=True)
            self._show_message(
                tr("error"),
                tr("delete_failed"),
                critical=True
            )

    # =========================
    # AUTO SHUTDOWN
    # =========================
    def _queue_all_finished(self) -> bool:
        """True nếu queue không rỗng và mọi job đã ở trạng thái cuối (không còn Waiting/Paused)."""
        count = self.right.queue_list.count()
        if count == 0:
            return False

        terminal = {"Done", "Failed", "Done with missing images", "Done with missing"}
        for i in range(count):
            item = self.right.queue_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole) or {}
            if data.get("status") not in terminal:
                return False
        return True

    def _on_engine_finished(self):
        if not self.left.shutdown_cb.isChecked():
            return
        if not self._queue_all_finished():
            return
        self._confirm_shutdown()

    def _confirm_shutdown(self):
        self._shutdown_cancelled = False
        self._shutdown_seconds_left = self.left.shutdown_delay_seconds

        box = QMessageBox(self)
        box.setWindowTitle(tr("shutdown_confirm_title"))
        box.setIcon(QMessageBox.Icon.Warning)
        box.setModal(False)

        def _update_text():
            box.setText(
                f"{tr('shutdown_confirm_text')}\n\n"
                f"{tr('shutdown_countdown')} {self._shutdown_seconds_left}s"
            )

        _update_text()

        btn_cancel = box.addButton(tr("cancel"), QMessageBox.ButtonRole.RejectRole)
        btn_now = box.addButton(tr("shutdown_now"), QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(btn_cancel)

        timer = QTimer(self)
        timer.setInterval(1000)

        def _tick():
            self._shutdown_seconds_left -= 1
            if self._shutdown_seconds_left <= 0:
                timer.stop()
                box.done(0)
                if not self._shutdown_cancelled:
                    self._shutdown_system()
                return
            _update_text()

        timer.timeout.connect(_tick)
        timer.start()

        def _on_clicked(btn):
            if btn is btn_cancel:
                self._shutdown_cancelled = True
                timer.stop()
            elif btn is btn_now:
                timer.stop()
                box.done(0)
                self._shutdown_system()

        box.buttonClicked.connect(_on_clicked)
        box.show()

    def _shutdown_system(self):
        system = platform.system()
        logger.info(f"Auto-shutdown triggered on {system} after all downloads finished")

        try:
            if system == "Windows":
                # /t 5: wait 5s so this process exits cleanly; cancel with `shutdown /a`
                subprocess.run(["shutdown", "/s", "/t", "5"], check=False)

            elif system == "Linux":
                try:
                    # prefer systemctl (usually no sudo needed for a user in an active session + polkit)
                    subprocess.run(["systemctl", "poweroff"], check=True)
                except Exception:
                    subprocess.run(["shutdown", "-h", "now"], check=False)

            elif system == "Darwin":
                subprocess.run(
                    ["osascript", "-e", 'tell app "System Events" to shut down'],
                    check=False
                )

            else:
                logger.warning(f"Unsupported OS for auto-shutdown: {system}")

        except Exception:
            logger.exception("Failed to shut down the system")
            self._show_message(tr("error"), tr("shutdown_failed"), critical=True)

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