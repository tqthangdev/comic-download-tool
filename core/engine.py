import asyncio
import traceback
import aiohttp

from PyQt6.QtCore import QObject, pyqtSignal

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
        self.active_jobs = {}  # url -> Job đang chạy, để stop() lấy lại được

    async def add_job(self, job: Job):
        existing = self.db.get_job(job.url)

        if existing:
            job.save_path = existing.save_path
            job.current_chap = existing.current_chap  # mang theo điểm dừng
            status = existing.status
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

        if status == "done":
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

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            self.downloader.set_session(session)
            self.crawler.set_http_session(session)

            self.workers = [
                asyncio.create_task(self.worker(i))
                for i in range(self.max_workers)
            ]

            # return_exceptions=True: các worker bị cancel (CancelledError)
            # sẽ được gom vào kết quả thay vì bay ngược lên gọi tiếp lên
            # start_engine() gây "unhandled exception" trong asyncSlot.
            await asyncio.gather(*self.workers, return_exceptions=True)

        self.running = False
        self.workers.clear()

    async def stop(self):
        self.running = False

        # job đang dở dang -> "paused" + trả lại queue để start() sau tải tiếp
        for job in list(self.active_jobs.values()):
            self.db.update_status(job.url, "paused")
            await self.queue.put(job)

        for task in self.workers:
            task.cancel()

        self.workers.clear()
        self.active_jobs.clear()

    async def restore_session(self):
        """Khôi phục job dở dang (waiting/paused/failed) từ session trước vào lại queue."""
        restored = []
        for job in self.db.get_restorable_jobs():
            self.db.update_status(job.url, "waiting")
            await self.queue.put(job)
            restored.append(job)
        return restored

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
                data = await self.crawl_job(job)
                has_failed = await self.download_job(job, data)

                if has_failed:
                    await self.db.aupdate_status(job.url, "failed")
                    self.progress.emit(job.title, "Failed")
                    logger.warning(f"[{job.title}] Có ảnh lỗi, đánh dấu Failed.")
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

    async def download_job_old(self, job, data) -> bool:
        """Trả về True nếu có ít nhất 1 ảnh lỗi vĩnh viễn trong toàn bộ job."""
        await self._download_thumb(job, data)

        chapters = list(reversed(data["chapters"]))
        total_chap = len(chapters)
        start_index = job.current_chap or 1
        has_failed = False

        for chap_index, chap in enumerate(chapters, 1):
            if chap_index < start_index:
                continue

            job.current_chap = chap_index
            await self.db.aupdate_current_chap(job.url, chap_index)

            imgs = await self._extract_images_with_retry(chap["url"])
            chap_path = job.save_path / safe_filename(chap["title"])

            if self.verify_chapter(chap_path, len(imgs)):
                if self.running:
                    overall_percent = chap_index / total_chap * 100
                    self.progress.emit(job.title, f"Downloading {overall_percent:.0f}%")
                continue

            def progress_callback(current, total, chap_index=chap_index):
                if not self.running:
                    return
                chap_progress = (current / total) if total else 0
                overall_percent = (chap_index - 1 + chap_progress) / total_chap * 100
                self.progress.emit(job.title, f"Downloading {overall_percent:.0f}%")

            failed_urls = await self.downloader.download_batch(imgs, chap_path, progress=progress_callback)

            if failed_urls:
                has_failed = True
                logger.error(f"[{job.title}] Chapter {chap['title']}: {len(failed_urls)} ảnh lỗi: {failed_urls}")

        return has_failed

    async def download_job(self, job, data) -> bool:
        """Trả về True nếu có ít nhất 1 ảnh lỗi vĩnh viễn trong toàn bộ job."""
        await self._download_thumb(job, data)

        chapters = list(reversed(data["chapters"]))
        total_chap = len(chapters)
        start_index = job.current_chap or 1
        has_failed = False

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

            failed_urls = await self.downloader.download_batch(imgs, chap_path, progress=progress_callback)

            if failed_urls:
                has_failed = True
                logger.error(f"[{job.title}] Chapter {chap['title']}: {len(failed_urls)} ảnh lỗi: {failed_urls}")

        return has_failed

    async def _download_thumb(self, job, data):
        """Tải ảnh bìa (thumbnail) của job vào job.save_path/thumb.jpg."""
        if not CONFIG.get("download_thumb", True):
            return

        thumb_url = data.get("thumb")
        if not thumb_url:
            return

        thumb_path = job.save_path

        # đã có sẵn (job resume/rerun) -> khỏi tải lại
        if thumb_path.exists() and any(thumb_path.iterdir()):
            return

        failed_urls = await self.downloader.download_batch([thumb_url], thumb_path)

        if failed_urls:
            logger.error(f"[{job.title}] Lỗi tải thumbnail: {thumb_url}")
            return

        # download_batch đặt tên "0000.jpg" theo index -> đổi lại tên cho rõ nghĩa
        raw_file = thumb_path / "0000.jpg"
        if raw_file.exists():
            raw_file.rename(thumb_path / "thumb.jpg")

    async def _extract_images_with_retry(self, url, retries=2):
        last_err = None
        for attempt in range(retries + 1):
            try:
                return await self.crawler.extract_images(url)
            except asyncio.CancelledError:
                raise  # không retry khi bị pause/cancel chủ động
            except Exception as e:
                last_err = e
                logger.warning(f"Retry extract_images ({attempt + 1}/{retries}) do lỗi: {e}")
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

    async def finish_job(self, job):
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
