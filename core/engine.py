import asyncio
import traceback
import aiohttp

from PyQt6.QtCore import QObject, pyqtSignal

from pathlib import Path

from core.crawler import Crawler
from core.downloader import Downloader
from core.job_manager import Job, JobManager
from core.utils import safe_filename, CONFIG
from core.logger import logger

class Engine(QObject):
    progress = pyqtSignal(str, str)

    def __init__(self, max_workers=3):
        super().__init__()
        self.queue = asyncio.Queue()
        self.max_workers = max_workers
        self.workers = []
        self.crawler = Crawler()
        self.downloader = Downloader()
        self.db = JobManager()
        self.running = False
        self.active_jobs = {}  # url -> currently running Job, for stop() to retrieve

    async def add_job(self, job: Job):
        existing = self.db.get_job(job.url)

        if existing:
            # Always prefer the save_path from the GUI (current input path),
            # not the old path stored in the DB. If the user changed the path,
            # persist it back to the DB so the next run stays in sync.
            if existing.save_path != job.save_path:
                self.db.update_save_path(job.url, job.save_path)
            job.current_chap = existing.current_chap  # keep the resume point
            status = existing.status
            # An old (restored) job may lack chapters/thumb -> take them from the
            # GUI if available and store them so the next run does not re-crawl.
            if not existing.chapters and job.chapters:
                await self.db.aupdate_chapters(job.url, job.chapters)
            elif existing.chapters and not job.chapters:
                job.chapters = existing.chapters
            if not existing.thumb and job.thumb:
                await self.db.aupdate_thumb(job.url, job.thumb)
            elif existing.thumb and not job.thumb:
                job.thumb = existing.thumb
        else:
            status = None

        if status == "running":
            return "already_running"
        if status == "waiting":
            return "already_queued"

        if status == "paused":
            self.db.update_status(job.url, "waiting")
            await self.queue.put(job)
            return "resume"

        if status == "done" or status == "done_with_missing":
            self.db.update_status(job.url, "waiting")
            await self.queue.put(job)
            if self.has_local_data(job):
                return "resume"
            else:
                return "queued"

        if status is None:
            self.db.add(job)

        await self.queue.put(job)
        return "queued"

    async def start(self):
        if self.running:
            return
        self.running = True

        headers = {"User-Agent": CONFIG.get("user_agent", "")}

        async with aiohttp.ClientSession(headers=headers) as session:
            self.downloader.set_session(session)
            self.crawler.set_http_session(session)

            self.workers = [
                asyncio.create_task(self.worker(i))
                for i in range(self.max_workers)
            ]

            # return_exceptions=True: cancelled workers (CancelledError) are gathered
            # into the result instead of bubbling up to start_engine() and
            # raising an "unhandled exception" inside an asyncSlot.
            await asyncio.gather(*self.workers, return_exceptions=True)

        self.running = False
        self.workers.clear()

    async def stop(self):
        self.running = False

        # incomplete job -> mark "paused" and put it back on the queue to resume
        for job in list(self.active_jobs.values()):
            self.db.update_status(job.url, "paused")
            await self.queue.put(job)

        for task in self.workers:
            task.cancel()

        self.workers.clear()
        self.active_jobs.clear()

    async def restore_session(self, base_path: str = None):
        """Restore incomplete jobs (waiting/paused/failed) from the previous
        session back into the queue."""
        restored = []
        for job in self.db.get_restorable_jobs():
            # Always use the current path (from the path input) instead of the
            # old one in the DB, matching the "prefer current path" rule of add_job.
            if base_path:
                new_path = Path(base_path) / safe_filename(job.title)
                if job.save_path != new_path:
                    job.save_path = new_path
                    self.db.update_save_path(job.url, job.save_path)
            self.db.update_status(job.url, "waiting")
            await self.queue.put(job)
            restored.append(job)
        return restored

    async def sync_paths(self, base_path: str = None):
        """Apply the current save path (from the path input) to every job still
        waiting in the queue, so changing the target folder before Start takes
        effect instead of using the old path captured at Add Queue time."""
        if not base_path:
            return

        # Drain the queue, update each pending job's path, then put them back.
        pending = []
        while not self.queue.empty():
            job = self.queue.get_nowait()
            new_path = Path(base_path) / safe_filename(job.title)
            if job.save_path != new_path:
                job.save_path = new_path
                self.db.update_save_path(job.url, job.save_path)
            pending.append(job)

        for job in pending:
            self.queue.put_nowait(job)

    async def worker(self, wid):
        while self.running:
            try:
                job = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            self.active_jobs[job.url] = job
            try:
                await self.db.aupdate_status(job.url, "running")
                logger.info(f"[W{wid}] {job.title}")

                # If the job was added while the app was running, chapters/thumb already
                # exist (from preview) — only re-crawl when the job was restored
                # (no chapters yet).
                if not job.chapters:
                    data = await self.crawl_job(job)
                    job.chapters = data.get("chapters") or []
                    job.thumb = data.get("thumb") or ""
                    if job.chapters:
                        await self.db.aupdate_chapters(job.url, job.chapters)
                    if job.thumb:
                        await self.db.aupdate_thumb(job.url, job.thumb)
                else:
                    data = {
                        "title": job.title,
                        "thumb": job.thumb or "",
                        "referer": job.referer or "",
                        "chapters": job.chapters,
                    }

                has_failed, has_missing = await self.download_job(job, data)

                if has_failed:
                    await self.db.aupdate_status(job.url, "failed")
                    self.progress.emit(job.title, "Failed")
                    logger.warning(f"[{job.title}] Has failed images, marking Failed.")
                elif has_missing:
                    await self.finish_job(job, missing=True)
                else:
                    await self.finish_job(job)

            except asyncio.CancelledError:
                raise

            except Exception as e:
                logger.error(f"ERROR processing job [{job.title}]: {e}", exc_info=True)
                await self.db.aupdate_status(job.url, "failed")
                self.progress.emit(job.title, "Failed")

            finally:
                self.active_jobs.pop(job.url, None)
                self.queue.task_done()

    def has_local_data(self, job):
        return job.save_path.exists() and any(job.save_path.iterdir())

    async def crawl_job(self, job):
        return await self.crawler.get_chapters(job.url)

    async def download_job(self, job, data):
        """Tải cả job. Trả về (has_failed, has_missing).

        - has_failed:  có ảnh lỗi mạng/server sau khi retry hết → job Failed.
        - has_missing: có ảnh HTTP 404 (thiếu trên nguồn) nhưng quá trình vẫn
                       diễn ra bình thường → job Done with missing images.
        """
        await self._download_thumb(job, data)
        referer = data.get("referer") or ""

        chapters = list(reversed(data["chapters"]))
        total_chap = len(chapters)
        start_index = job.current_chap or 1
        has_failed = False
        has_missing = False

        for chap_index, chap in enumerate(chapters, 1):
            if chap_index < start_index:
                continue

            job.current_chap = chap_index
            await self.db.aupdate_current_chap(job.url, chap_index)

            imgs = await self._extract_images_with_retry(chap["url"])
            chap_path = job.save_path / safe_filename(chap["title"])

            if self.verify_chapter(chap_path, len(imgs)):
                if self.running:
                    self.progress.emit(
                        job.title, f"Downloading...({chap_index}/{total_chap}): 100%"
                    )
                continue

            def progress_callback(current, total, chap_index=chap_index):
                if not self.running:
                    return
                chap_percent = (current / total * 100) if total else 0
                self.progress.emit(
                    job.title, f"Downloading...({chap_index}/{total_chap}): {chap_percent:.0f}%"
                )

            failed_urls, missing_urls = await self.downloader.download_batch(imgs, chap_path, referer=referer, progress=progress_callback)

            if failed_urls:
                has_failed = True
                logger.error(f"[{job.title}] Chapter {chap['title']}: {len(failed_urls)} failed images: {failed_urls}")

            if missing_urls:
                has_missing = True
                logger.warning(f"[{job.title}] Chapter {chap['title']}: {len(missing_urls)} missing images: {missing_urls}")

        return has_failed, has_missing

    async def _download_thumb(self, job, data):
        """Download the job's cover image (thumbnail) into job.save_path/thumb.jpg."""
        if not CONFIG.get("download_thumb", True):
            return

        thumb_url = data.get("thumb")
        if not thumb_url:
            return

        thumb_path = job.save_path

        # Skip if thumb.jpg already exists (resume/rerun) — only check that specific
        # file, NOT the folder contents (a folder with chapters but no thumb
        # must still be downloaded).
        if (thumb_path / "thumb.jpg").exists():
            return

        referer = data.get("referer") or ""
        failed_urls, _missing = await self.downloader.download_batch([thumb_url], thumb_path, referer=referer)

        if failed_urls:
            logger.error(f"[{job.title}] Thumbnail download error: {thumb_url}")
            return

        # download_batch names files "0000.jpg" by index -> rename for clarity
        raw_file = thumb_path / "0000.jpg"
        if raw_file.exists():
            raw_file.rename(thumb_path / "thumb.jpg")

    async def _extract_images_with_retry(self, url, retries=2):
        last_err = None
        for attempt in range(retries + 1):
            try:
                return await self.crawler.extract_images(url)
            except asyncio.CancelledError:
                raise  # do not retry on an intentional pause/cancel
            except Exception as e:
                last_err = e
                logger.warning(f"Retry extract_images ({attempt + 1}/{retries}) due to error: {e}")
        raise last_err

    def verify_chapter(self, path, total_images):
        if not path.exists():
            return False
        downloaded = len(list(path.glob("*.jpg")))
        failed_marker = path / ".failed_count"
        failed_count = 0
        if failed_marker.exists():
            try:
                failed_count = int(failed_marker.read_text().strip())
            except Exception:
                failed_count = 0
        return (downloaded + failed_count) == total_images

    async def finish_job(self, job, missing=False):
        if missing:
            await self.db.aupdate_status(job.url, "done_with_missing")
            await self.db.areset_current_chap(job.url)
            logger.warning(f"DONE WITH MISSING IMAGES: {job.title}")
            self.progress.emit(job.title, "Done with missing images")
            return
        await self.db.aupdate_status(job.url, "done")
        await self.db.areset_current_chap(job.url)
        logger.info(f"DONE: {job.title}")
        self.progress.emit(job.title, "Done")

    def pause_idle_jobs(self):
        paused_urls = []
        temp = []

        while not self.queue.empty():
            job = self.queue.get_nowait()
            self.db.update_status(job.url, "paused")
            paused_urls.append(job.url)
            temp.append(job)

        for job in temp:
            self.queue.put_nowait(job)

        return paused_urls
