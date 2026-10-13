import asyncio
from pathlib import Path
import shutil
import traceback
import aiohttp
from PyQt6.QtCore import QObject, pyqtSignal

from core.net.crawler import Crawler
from core.net.downloader import Downloader, CONTENT_TYPE_EXT
from core.scraping.sites import cuutruyen
from core.jobs.job_manager import Job, JobManager
from core.logger import logger
from core.sessions import (
    SessionStore,
    cleanup_scratch,
    delete_session_files,
    delete_session_scratch,
    job_scratch_dir,
    session_db_path,
)
from core.utils import CONFIG, safe_filename
from core.auth import auth_manager, AuthError
from core.engines import gallerydl as gallerydl_engine
from core.engines import selector
from core.engines.base import (
    DELETED,
    DONE,
    DONE_WITH_MISSING,
    FAILED,
    BackendError,
)
from core.engines.native import NativeBackend
from core.engines.gallerydl import GalleryDLBackend


class Engine(QObject):
    progress = pyqtSignal(str, str)
    # Emitted whenever the running state changes on its own (e.g. the queue
    # finishes naturally, or a job crashes) so the UI can resync the
    # pause/resume buttons without waiting for a manual pause/resume click.
    finished = pyqtSignal()
    # Emitted when a job is paused because its site requires login and the
    # user isn't (or is no longer) authenticated. Args: (job_title, job_url, site_id).
    # The GUI should catch this and open gui/login_dialog.py's LoginDialog
    # for site_id, then re-add the job by url (its status is already "paused",
    # so add_job() will simply resume it).
    login_required = pyqtSignal(str, str, str)

    def __init__(self, max_workers=3):
        super().__init__()
        self.queue = asyncio.Queue()
        self.max_workers = max_workers
        self.workers = []
        self.crawler = Crawler()
        self.downloader = Downloader()
        # One SQLite database per session; the registry tracks which is current.
        self.session_store = SessionStore()
        self.session_id = self.session_store.ensure_current().id
        self.db = JobManager(session_db_path(self.session_id))
        # Scratch (.temp/<session>/<job>) for sessions/jobs that are gone.
        cleanup_scratch(self.session_store)
        # The two download backends. `native` wraps the existing pipeline;
        # `gallerydl` shells out to gallery-dl. The selector picks between them.
        self.backends = {
            "native": NativeBackend(self),
            "gallerydl": GalleryDLBackend(self),
        }
        self.running = False
        self.active_jobs = (
            {}
        )  # (url, format_key) -> currently running Job, for stop() to retrieve
        self._run_task = None  # background task created by start()
        # True once the current run has set up its HTTP session and spawned the
        # initial pool. Guards add_job()'s top-up from spawning a worker before
        # the session the worker needs exists.
        self._pool_ready = False
        # (url, format_key) the user asked to delete while a job was actively
        # downloading; checked by download_job() so it can bail out early
        # instead of finishing the whole job after the record was removed.
        self.deleted_urls = set()

    @staticmethod
    def _normalize_genres(raw_genres, key: str = "slug") -> list[str]:
        """Normalize genres to a flat list[str]."""
        if not raw_genres:
            return []

        genres = []
        for genre in raw_genres:
            if isinstance(genre, str):
                value = genre.strip()
            elif isinstance(genre, dict):
                value = str(genre.get(key) or "").strip()
            else:
                value = ""
            if value:
                genres.append(value)
        return genres

    async def add_job(self, job: Job):
        # Identity within the session DB is (url, format_key).
        format_key = job.format_key or JobManager.format_key_for(job)
        job.format_key = format_key
        existing = self.db.get_job(job.url, format_key)

        if existing:
            # Always prefer the save_path from the GUI (current input path),
            # not the old path stored in the DB. If the user changed the path,
            # persist it back to the DB so the next run stays in sync.
            if existing.save_path != job.save_path:
                self.db.update_save_path(job.url, format_key, job.save_path)
            job.current_chap = existing.current_chap  # keep the resume point
            job.id = existing.id
            status = existing.status
            # An old (restored) job may lack chapters/thumb -> take them from the
            # GUI if available and store them so the next run does not re-crawl.
            if not existing.chapters and job.chapters:
                await self.db.aupdate_chapters(job.url, format_key, job.chapters)
            elif existing.chapters and not job.chapters:
                job.chapters = existing.chapters
            if not existing.thumb and job.thumb:
                await self.db.aupdate_thumb(job.url, format_key, job.thumb)
            elif existing.thumb and not job.thumb:
                job.thumb = existing.thumb
            # Genres may be a list of {name, slug, url} dicts (fresh from the
            # scraper) or a flat list of strings (already normalized): normalize
            # to the flat list shape before storing / comparing.
            if not existing.genres and job.genres:
                job.genres = self._normalize_genres(job.genres)
                await self.db.aupdate_genres(job.url, format_key, job.genres)
            elif existing.genres and not job.genres:
                job.genres = self._normalize_genres(existing.genres)
            # Keep the site_id already on record unless the GUI explicitly
            # supplied a new one (e.g. user re-added the job picking a site).
            if not existing.site_id and job.site_id:
                self.db.update_site_id(job.url, format_key, job.site_id)
            elif existing.site_id and not job.site_id:
                job.site_id = existing.site_id
        else:
            status = None

        if status == "running":
            return "already_running"
        if status == "waiting":
            return "already_queued"

        if status == "paused":
            self.db.update_status(job.url, format_key, "waiting")
            await self.queue.put(job)
            self._ensure_workers()
            return "resume"

        if status == "done" or status == "done_with_missing":
            self.db.update_status(job.url, format_key, "waiting")
            await self.queue.put(job)
            self._ensure_workers()
            if self.has_local_data(job):
                return "resume"
            else:
                return "queued"

        if status is None:
            self.db.add(job)

        await self.queue.put(job)
        self._ensure_workers()
        return "queued"

    @staticmethod
    def _job_key(job) -> tuple:
        """Identity of a job inside its session DB: (url, format_key)."""
        return (job.url, job.format_key)

    async def del_job(self, url: str, format_key: str) -> bool:
        """Delete a job entirely: drop it from the queue if it's still
        'waiting', flag it so an in-progress worker stops early, and remove
        its record from the DB.

        Returns True if the job existed anywhere (queue, active, or DB).
        """
        existing = self.db.get_job(url, format_key)
        key = (url, format_key)

        # Remove it from the queue if it's just sitting there "waiting"
        was_queued = False
        pending = []
        while not self.queue.empty():
            job = self.queue.get_nowait()
            if self._job_key(job) == key:
                was_queued = True
                continue
            pending.append(job)
        for job in pending:
            self.queue.put_nowait(job)

        # If it's currently being downloaded, flag it so the worker bails
        # out at the next chapter boundary instead of finishing the job.
        was_running = key in self.active_jobs
        if was_running:
            self.deleted_urls.add(key)
            self.active_jobs.pop(key, None)

        # Remove the DB record, if any
        if existing:
            await self.db.adelete(url, format_key)

        return bool(existing or was_queued or was_running)

    # ------------------------------------------------------------------
    # SESSIONS
    # ------------------------------------------------------------------

    def list_sessions(self):
        """Every registered session (registry order)."""
        return self.session_store.list()

    def rename_session(self, session_id: str, name: str):
        """Rename a session (registry only — the DB file name never changes)."""
        self.session_store.rename(session_id, name)

    def _load_db(self, session_id: str):
        """Point the engine at another session's database."""
        if getattr(self, "db", None) is not None:
            self.db.close()
        self.session_id = session_id
        self.db = JobManager(session_db_path(session_id))

    async def activate_session(self, session_id):
        """Switch to ``session_id`` and return all of its jobs.

        Callers must stop the engine first. Unfinished jobs are re-queued and
        marked 'waiting'; finished ("done") jobs are returned so the UI can
        still show them, but they are not enqueued again.
        """
        if self.running:
            raise RuntimeError("cannot switch session while the engine is running")

        self.session_store.set_current(session_id)
        self._load_db(session_id)

        # Reset the in-memory queue/state for the new session.
        self.queue = asyncio.Queue()
        self.active_jobs.clear()
        self.deleted_urls.clear()

        jobs = self.db.all_jobs()
        for job in jobs:
            if (job.status or "waiting") == "done":
                continue
            self.db.update_status(job.url, job.format_key, "waiting")
            job.status = "waiting"
            await self.queue.put(job)
        return jobs

    async def create_session(self, name: str = None):
        """Create a fresh empty session and switch to it."""
        info = self.session_store.create(name)
        return await self.activate_session(info.id)

    async def delete_session(self, session_id):
        """Delete a session: registry entry + database + scratch folder.

        When the current session is deleted, another one is opened (or an empty
        one created) and its jobs are returned; otherwise returns None.
        """
        if self.running:
            raise RuntimeError("cannot delete a session while the engine is running")

        was_current = self.session_store.remove(session_id)
        delete_session_files(session_id)
        delete_session_scratch(session_id)

        if was_current:
            info = self.session_store.ensure_current()
            return await self.activate_session(info.id)
        return None

    async def delete_all_sessions(self):
        """Remove every session, then open a fresh empty one."""
        if self.running:
            raise RuntimeError("cannot delete sessions while the engine is running")

        for info in list(self.session_store.list()):
            self.session_store.remove(info.id)
            delete_session_files(info.id)
            delete_session_scratch(info.id)

        info = self.session_store.create()
        return await self.activate_session(info.id)

    async def start(self):
        """Mark the engine as running and kick off the worker pool in the

        background, then return immediately.
        """
        if self.running:
            return
        self.running = True
        self._run_task = asyncio.ensure_future(self._run_workers())

    def _spawn_workers(self, count: int):
        """Create ``count`` worker tasks and track them for the current run."""
        for _ in range(count):
            self.workers.append(asyncio.create_task(self.worker(len(self.workers))))

    def _ensure_workers(self):
        """Top the pool back up after a job is queued mid-run.

        Workers exit as soon as the queue drains, so a run that began with a
        single job collapses to a single worker. To let a job added later start
        right away (instead of waiting for the current job to finish), spawn as
        many workers as the queue needs, capped at ``max_workers``.
        """
        if not self.running or not self._pool_ready:
            return
        live = sum(1 for w in self.workers if not w.done())
        missing = self.max_workers - live
        if missing <= 0:
            return
        queued = self.queue.qsize()
        wanted = min(missing, max(1, queued))
        self._spawn_workers(wanted)
        logger.info(f"Worker top-up: +{wanted} (live={live}, queued={queued}).")

    async def _run_workers(self):
        try:
            headers = {"User-Agent": CONFIG.get("user_agent", "")}

            # MAXIMIZE AIOHTTP NETWORK CONFIGURATION
            connector = aiohttp.TCPConnector(
                limit=0,  # No limit on total open connections (managed by the Downloader's Semaphore)
                limit_per_host=0,  # Remove aiohttp's default limit of 20 connections/domain
                ttl_dns_cache=300,  # Cache DNS results for 5 minutes to speed up connections
                enable_cleanup_closed=True,  # Automatically clean up closed sockets
                keepalive_timeout=30,  # Keep connections alive longer for reuse
            )

            async with aiohttp.ClientSession(
                headers=headers, connector=connector
            ) as session:
                self.downloader.set_session(session)
                self.crawler.set_http_session(session)

                # Fresh pool for this run: workers drain the queue from the
                # front (so a fresh Start/resume always begins at the head) and
                # exit once it is empty. An empty pool is our "run finished"
                # signal; add_job() tops the pool back up while it is alive.
                self.workers.clear()
                self._spawn_workers(self.max_workers)
                self._pool_ready = True

                # Supervise until the whole pool has drained. Re-scan after each
                # gather so workers spawned mid-run are awaited too.
                while True:
                    live = [w for w in self.workers if not w.done()]
                    if not live:
                        break
                    # return_exceptions=True: cancelled workers (CancelledError)
                    # are collected as results instead of bubbling up and raising
                    # an "unhandled exception" from a background task.
                    await asyncio.gather(*live, return_exceptions=True)

        finally:
            self.running = False
            self._pool_ready = False
            self.workers.clear()
            self._run_task = None
            # Let the UI know the run ended (naturally or by error) so it can
            # resync the pause/resume buttons even if the user never clicked Pause.
            self.finished.emit()

    async def stop(self):
        self.running = False

        active_jobs = list(self.active_jobs.values())

        if active_jobs:
            # Update the DB once instead of updating each job individually
            self.db.update_status_bulk(
                [self._job_key(job) for job in active_jobs], "paused"
            )

            # Re-queue the paused jobs at the FRONT so the next resume picks
            # them back up before any job that was merely waiting its turn.
            self._requeue_front(active_jobs)

        # Cancel workers
        for task in self.workers:
            task.cancel()

        self.workers.clear()
        self.active_jobs.clear()

        # Wait for the background run task to yield completely
        if self._run_task:
            try:
                await self._run_task
            except (asyncio.CancelledError, Exception):
                pass
            self._run_task = None

    def _requeue_front(self, jobs):
        """Put ``jobs`` at the head of the queue, ahead of waiting ones.

        Used when pausing: the jobs that were mid-download should be the first
        picked up on resume, before jobs that had not started yet.
        """
        waiting = []
        while not self.queue.empty():
            waiting.append(self.queue.get_nowait())

        for job in jobs:
            self.queue.put_nowait(job)
        for job in waiting:
            self.queue.put_nowait(job)

    def has_restorable_jobs(self) -> bool:
        """True when the current session has unfinished jobs to bring back.

        Used at startup to skip the "restore session?" prompt when there is
        nothing to restore (empty queue, or every job already done).
        """
        return bool(self.db.get_restorable_jobs())

    async def restore_session(self, base_path: str = None):
        """Restore incomplete jobs from the previous session."""
        jobs = self.db.get_restorable_jobs()
        total = len(jobs)

        for current, job in enumerate(jobs, start=1):
            if base_path:
                new_path = Path(base_path) / safe_filename(job.title)

                if job.save_path != new_path:
                    job.save_path = new_path
                    self.db.update_save_path(job.url, job.format_key, job.save_path)

            self.db.update_status(job.url, job.format_key, "waiting")

            await self.queue.put(job)

            # Return job to UI immediately
            yield current, total, job

            # Yield event loop periodically
            if current % 10 == 0:
                await asyncio.sleep(0)

    async def sync_paths(self, base_path: str = None):
        """Apply current save path to queued jobs."""
        if not base_path:
            return

        pending = []
        while not self.queue.empty():
            job = self.queue.get_nowait()
            new_path = Path(base_path) / safe_filename(job.title)
            if job.save_path != new_path:
                job.save_path = new_path
                self.db.update_save_path(job.url, job.format_key, job.save_path)
            pending.append(job)

        for job in pending:
            self.queue.put_nowait(job)

    async def worker(self, wid):
        while self.running:
            try:
                job = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            # Skip jobs that were deleted while still sitting in the queue
            # (del_job already dropped them from self.queue, but this guards
            # against any edge case where one slips through).
            if self._job_key(job) in self.deleted_urls:
                self.deleted_urls.discard(self._job_key(job))
                self.queue.task_done()
                continue

            # Site requires login and we're not (or no longer) authenticated:
            # pause the job instead of letting it fail deep inside crawl/download,
            # and let the GUI prompt the user to log in.
            if job.site_id:
                try:
                    auth_manager.ensure_logged_in(job.site_id, job.url)
                except AuthError:
                    await self.db.aupdate_status(job.url, job.format_key, "paused")
                    self.progress.emit(job.title, "Login required")
                    self.login_required.emit(job.title, job.url, job.site_id)
                    logger.warning(
                        f"[{job.title}] Paused — not logged in to site '{job.site_id}'."
                    )
                    self.queue.task_done()
                    continue

            key = self._job_key(job)
            self.active_jobs[key] = job
            try:
                await self.db.aupdate_status(job.url, job.format_key, "running")
                logger.info(f"[W{wid}] {job.title}")

                outcome, used = await self._download_with_fallback(job)
                await self.db.aupdate_engine(job.url, job.format_key, used)

                if outcome.status == DELETED:
                    # Job was removed by the user mid-download; its DB record
                    # is already gone, so there's nothing left to update.
                    logger.info(f"[{job.title}] Skipped finishing — job was deleted.")
                elif outcome.status == FAILED:
                    await self.db.aupdate_status(job.url, job.format_key, "failed")
                    self.progress.emit(job.title, "Failed")
                    logger.warning(
                        f"[{job.title}] Download failed, marking Failed."
                    )
                elif outcome.status == DONE_WITH_MISSING:
                    await self.finish_job(
                        job, missing=True, missing_details=outcome.missing_details
                    )
                else:
                    await self.finish_job(job)

            except asyncio.CancelledError:
                raise

            except AuthError as e:
                # Session expired mid-run (e.g. cookie invalidated by the site).
                # Pause and ask the GUI to re-authenticate, same as the pre-check above.
                await self.db.aupdate_status(job.url, job.format_key, "paused")
                self.progress.emit(job.title, "Login required")
                self.login_required.emit(job.title, job.url, job.site_id or "")
                logger.warning(f"[{job.title}] Session expired mid-run: {e}")

            except Exception as e:
                logger.error(
                    f"ERROR processing job [{job.title}]: {e}", exc_info=True
                )
                await self.db.aupdate_status(job.url, job.format_key, "failed")
                self.progress.emit(job.title, "Failed")

            finally:
                self.active_jobs.pop(key, None)
                self.queue.task_done()

    def has_local_data(self, job):
        return job.save_path.exists() and any(job.save_path.iterdir())

    # ------------------------------------------------------------------
    # Backend selection (native vs gallery-dl)
    # ------------------------------------------------------------------

    def available_backends(self) -> dict:
        """Backends usable right now (gallery-dl only when it is installed)."""
        available = {"native": self.backends["native"]}
        if gallerydl_engine.available():
            available["gallerydl"] = self.backends["gallerydl"]
        return available

    def backend_plan(self, url: str, preferred: str = None):
        """Ordered [(name, backend)] to try for `url`, primary first."""
        available = self.available_backends()
        return [
            (name, available[name])
            for name in selector.candidates(url, available.keys(), preferred)
        ]

    async def probe(self, url: str, site_id=None, engine: str = None):
        """Story metadata for the preview, using the configured backend.

        Falls back once to the other backend when the primary finds nothing
        (e.g. the heuristic engine cannot read a site gallery-dl supports).
        Returns (StoryMeta, backend_name). A bot wall propagates untouched so
        the GUI keeps showing its dedicated message.
        """
        plan = self.backend_plan(url, engine)
        if not plan:
            raise BackendError("no download backend available")

        last_error = None
        for attempt, (name, backend) in enumerate(plan):
            try:
                meta = await backend.probe(url, site_id=site_id)
            except BackendError as e:
                last_error = e
                if attempt + 1 < len(plan) and selector.fallback_allowed(e.code, name):
                    logger.info(f"[probe] '{name}' cannot handle it, trying next backend")
                    continue
                raise

            if meta.chapters or attempt + 1 >= len(plan):
                return meta, name

            logger.info(f"[probe] '{name}' found no chapters, trying next backend")

        raise last_error or BackendError("no download backend available")

    async def _ensure_metadata(self, job, backend) -> None:
        """Fill/save the chapter list via the chosen backend.

        A no-op when the preview already populated `job.chapters` (the usual
        case) — the fallback path re-probes with the other backend.
        """
        if job.chapters:
            return

        meta = await backend.probe(job.url, site_id=job.site_id)
        job.chapters = meta.chapters
        job.thumb = meta.thumb
        # scraper.py's find_genres() returns list[dict({name, slug, url})];
        # normalize to list[str] so job.genres and the DB column share one shape.
        job.genres = self._normalize_genres(meta.genres)
        if meta.referer:
            job.referer = meta.referer

        if job.chapters:
            await self.db.aupdate_chapters(job.url, job.format_key, job.chapters)
        if job.thumb:
            await self.db.aupdate_thumb(job.url, job.format_key, job.thumb)
        if job.genres:
            await self.db.aupdate_genres(job.url, job.format_key, job.genres)

    async def _download_with_fallback(self, job):
        """Run the job on its backend, falling back once to the other.

        Returns (JobOutcome, engine_name_used).
        """
        plan = self.backend_plan(job.url, job.engine)
        if not plan:
            raise BackendError("no download backend available")

        last_error = None
        for attempt, (name, backend) in enumerate(plan):
            if attempt > 0:
                await self.db.aupdate_engine_fallback_used(job.url, job.format_key, True)
                logger.warning(f"[{job.title}] Falling back to engine '{name}'")

            try:
                await self._ensure_metadata(job, backend)
                outcome = await backend.download(job)
            except AuthError:
                raise
            except BackendError as e:
                last_error = e
                await self.db.aupdate_engine_error(job.url, job.format_key, str(e))
                if attempt + 1 < len(plan) and selector.fallback_allowed(e.code, name):
                    continue
                raise

            if outcome.status != FAILED or attempt + 1 >= len(plan):
                # Build the PDFs once the backend has finished. Done here (not
                # in a backend) so it applies to native and gallery-dl alike.
                if outcome.status in (DONE, DONE_WITH_MISSING) and self._wants_pdf(job):
                    await self._build_chapter_pdfs(job)
                return outcome, name

            await self.db.aupdate_engine_error(job.url, job.format_key, "download failed")

        raise last_error or BackendError("download failed")

    @staticmethod
    def _wants_pdf(job) -> bool:
        """Whether this job's output should be PDF.

        The format is per job (the preview's format picker); jobs stored before
        it existed fall back to the global default (`pdf_cb`).
        """
        if job.convert_to_pdf is not None:
            return bool(job.convert_to_pdf)
        return bool(CONFIG.get("convert_to_pdf", False))

    async def download_job(self, job, data):
        await self._download_thumb(job, data)
        await self._save_genres(job, data)
        referer = data.get("referer") or ""
        use_pdf = self._wants_pdf(job)

        chapters = list(reversed(data["chapters"]))
        total_chap = len(chapters)
        start_index = job.current_chap or 1
        has_failed = False
        has_missing = False
        missing_details = {}  # chapter title -> list of missing image urls
        loop = asyncio.get_running_loop()

        # Every engine stages its chapter downloads in the session's per-job
        # scratch folder (".temp/<session>/<job_id>/") and moves each finished
        # chapter into the save path — so removing a session also drops its
        # scratch. Falls back to the save path directly when the job has no id
        # yet (defensive).
        staging = None
        if job.id is not None:
            staging = job_scratch_dir(self.session_id, job.id)
            await loop.run_in_executor(
                None, lambda: staging.mkdir(parents=True, exist_ok=True)
            )

        for chap_index, chap in enumerate(chapters, 1):
            # The user deleted this job while it was mid-download: stop
            # immediately, don't touch the DB again (record is already gone).
            if self._job_key(job) in self.deleted_urls:
                self.deleted_urls.discard(self._job_key(job))
                logger.info(f"[{job.title}] Job deleted by user, stopping download.")
                return "deleted", False, {}

            if chap_index < start_index:
                continue

            job.current_chap = chap_index
            await self.db.aupdate_current_chap(job.url, job.format_key, chap_index)

            chap_folder_name = f"{chap_index:04d} - {safe_filename(chap['title'])}"
            chap_path = job.save_path / chap_folder_name
            work_path = staging / chap_folder_name if staging else chap_path

            # In "Convert to PDF" mode the PDF is the finished artifact, so a
            # chapter that already has one is done — skip fetching its images.
            if use_pdf and (
                job.save_path / f"{chap_folder_name}.pdf"
            ).exists():
                if self.running:
                    self.progress.emit(
                        job.title,
                        f"Downloading...({chap_index}/{total_chap}): 100%",
                    )
                continue

            # cuutruyen pages are DRM-scrambled: fetch the page metadata (the
            # images themselves are rendered through the site's wasm module).
            use_cuutruyen = cuutruyen.is_cuutruyen_url(chap["url"])
            if use_cuutruyen:
                imgs = await loop.run_in_executor(
                    None, cuutruyen.fetch_pages, chap["url"]
                )
            else:
                imgs = await self._extract_images_with_retry(
                    chap["url"], site_id=job.site_id
                )

            # Migration cho job tải bằng bản cũ (chưa có prefix số)
            legacy_path = job.save_path / safe_filename(chap["title"])
            if not chap_path.exists() and legacy_path.exists() and legacy_path != chap_path:
                try:
                    legacy_path.rename(chap_path)
                    logger.info(
                        f"[{job.title}] Migrated legacy chapter folder: "
                        f"'{legacy_path.name}' -> '{chap_path.name}'"
                    )
                except OSError as e:
                    logger.warning(
                        f"[{job.title}] Failed to migrate legacy folder "
                        f"'{legacy_path.name}': {e}"
                    )

            # Already complete in the save path from a previous run.
            if self.verify_chapter(chap_path, len(imgs)):
                if self.running:
                    self.progress.emit(
                        job.title,
                        f"Downloading...({chap_index}/{total_chap}): 100%",
                    )
                continue

            # A finished chapter left in scratch by an earlier run: just move it.
            if (
                staging
                and work_path != chap_path
                and self.verify_chapter(work_path, len(imgs))
            ):
                await loop.run_in_executor(
                    None, self._move_chapter, work_path, chap_path
                )
                if self.running:
                    self.progress.emit(
                        job.title,
                        f"Downloading...({chap_index}/{total_chap}): 100%",
                    )
                continue

            def progress_callback(current, total, chap_index=chap_index):
                if not self.running:
                    return
                chap_percent = (current / total * 100) if total else 0
                self.progress.emit(
                    job.title,
                    f"Downloading...({chap_index}/{total_chap}): {chap_percent:.0f}%",
                )

            if use_cuutruyen:
                failed_urls, missing_urls = await cuutruyen.render_pages(
                    imgs, work_path, progress_callback
                )
            else:
                failed_urls, missing_urls = await self.downloader.download_batch(
                    imgs, work_path, referer=referer, progress=progress_callback,
                    site_id=job.site_id,
                )

            # Move the freshly downloaded chapter out of scratch into the save
            # path (per chapter, so the finished folder shows up right away).
            if staging and work_path != chap_path:
                await loop.run_in_executor(
                    None, self._move_chapter, work_path, chap_path
                )

            if failed_urls:
                has_failed = True
                logger.error(
                    f"[{job.title}] Chapter {chap['title']}: {len(failed_urls)} failed images: {failed_urls}"
                )

            if missing_urls:
                has_missing = True
                missing_details[chap["title"]] = missing_urls
                logger.warning(
                    f"[{job.title}] Chapter {chap['title']}: {len(missing_urls)} missing images: {missing_urls}"
                )

        # Best-effort: drop the per-job scratch folder once nothing is left in
        # it (rmdir only removes it when empty, so a partial is kept for resume).
        if staging is not None:
            try:
                staging.rmdir()
            except OSError:
                pass

        return has_failed, has_missing, missing_details

    async def _build_chapter_pdfs(self, job):
        """Turn each downloaded chapter into a single PDF, one at a time so the
        queue can show how far the conversion has got."""
        from core.export import pdf

        folders = pdf.chapter_folders(job.save_path)
        total = len(folders)
        if not total:
            return

        loop = asyncio.get_running_loop()
        built = 0

        for index, folder in enumerate(folders, 1):
            self.progress.emit(job.title, f"Converting to pdf {index}/{total}")
            try:
                result = await loop.run_in_executor(
                    None, pdf.convert_chapter, folder, job.save_path
                )
            except Exception as e:
                logger.error(
                    f"[{job.title}] PDF conversion failed for '{folder.name}': {e}"
                )
                continue

            if result == pdf.PDF_BUILT:
                built += 1

        if built:
            logger.info(f"[{job.title}] Converted {built} chapter(s) to PDF")

    async def _download_thumb(self, job, data):
        if not CONFIG.get("download_thumb", True):
            return

        thumb_url = data.get("thumb")
        if not thumb_url:
            return

        thumb_path = job.save_path

        # Đã có thumb với bất kỳ extension nào trong CONTENT_TYPE_EXT thì bỏ qua
        if any(
            (thumb_path / f"thumb{ext}").exists()
            for ext in CONTENT_TYPE_EXT.values()
        ):
            return

        referer = data.get("referer") or ""
        failed_urls, _missing = await self.downloader.download_batch(
            [thumb_url], thumb_path, referer=referer, site_id=job.site_id,
        )

        if failed_urls:
            logger.error(
                f"[{job.title}] Thumbnail download error: {thumb_url}"
            )
            return

        # Tìm file vừa tải (0000.<ext thực tế>) và đổi tên thành thumb.<ext>
        raw_files = list(thumb_path.glob("0000.*"))
        if raw_files:
            raw_file = raw_files[0]
            ext = raw_file.suffix.lower()
            if ext not in CONTENT_TYPE_EXT.values():
                ext = ".jpg"  # fallback an toàn nếu extension lạ
            raw_file.rename(thumb_path / f"thumb{ext}")

    async def _save_genres(self, job, data):
        """Save the story's genres as a plain-text file (comma-separated),
        in the same directory as the thumbnail (job.save_path).

        data["genres"] is already normalized to list[str] by worker()."""
        if not CONFIG.get("download_genres", True):
            return

        names = self._normalize_genres(data.get("genres"))
        if not names:
            return

        genres_path = job.save_path / "genres.txt"
        if genres_path.exists():
            return  # already saved from a previous run

        loop = asyncio.get_running_loop()

        def _write():
            job.save_path.mkdir(parents=True, exist_ok=True)
            genres_path.write_text(", ".join(names), encoding="utf-8")

        try:
            await loop.run_in_executor(None, _write)
        except Exception as e:
            logger.error(f"[{job.title}] Failed to save genres.txt: {e}")

    async def _extract_images_with_retry(self, url, retries=2, site_id=None):
        last_err = None
        for attempt in range(retries + 1):
            try:
                return await self.crawler.extract_images(url, site_id=site_id)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                last_err = e
                logger.warning(
                    f"Retry extract_images ({attempt + 1}/{retries}) due to error: {e}"
                )
        raise last_err

    @staticmethod
    def _move_chapter(src: Path, dst: Path):
        """Move a finished chapter folder from scratch into the save path.

        Handles the cross-device case (shutil.move copies then deletes) and
        merges into a pre-existing partial destination folder.
        """
        dst.mkdir(parents=True, exist_ok=True)
        for item in list(src.iterdir()):
            target = dst / item.name
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists():
                target.unlink(missing_ok=True)
            shutil.move(str(item), str(target))
        shutil.rmtree(src, ignore_errors=True)

    def verify_chapter(self, path, total_images):
        """True when the chapter folder already holds every image it should.

        Counts every image extension the downloader can produce (jpg, png, webp,
        gif, bmp, avif) — sites serve .webp as often as .jpg.
        """
        if not path.exists():
            return False
        downloaded = sum(
            1
            for p in path.iterdir()
            if p.is_file() and p.suffix.lower() in CONTENT_TYPE_EXT.values()
        )
        failed_marker = path / ".failed_count"
        failed_count = 0
        if failed_marker.exists():
            try:
                failed_count = int(failed_marker.read_text().strip())
            except Exception:
                failed_count = 0
        return (downloaded + failed_count) == total_images

    async def finish_job(self, job, missing=False, missing_details=None):
        if missing:
            await self.db.aupdate_status(job.url, job.format_key, "done_with_missing")
            await self.db.areset_current_chap(job.url, job.format_key)

            missing_details = missing_details or {}
            total_missing = sum(len(urls) for urls in missing_details.values())
            logger.warning(
                f"DONE WITH MISSING IMAGES: {job.title} "
                f"({total_missing} images across {len(missing_details)} chapters)"
            )
            for chap_title, urls in missing_details.items():
                logger.warning(
                    f"[{job.title}] Missing in chapter '{chap_title}': {urls}"
                )

            self.progress.emit(job.title, "Done with missing images")
            return
        await self.db.aupdate_status(job.url, job.format_key, "done")
        # Nothing left to resume on a finished job: clear the resume point so
        # re-adding the story later runs a full pass from chapter 1 again
        # (verify_chapter then re-downloads any chapter the user deleted).
        await self.db.areset_current_chap(job.url, job.format_key)
        logger.info(f"DONE: {job.title}")
        self.progress.emit(job.title, "Done")

    def pause_idle_jobs(self):
        paused_urls = []
        temp = []

        while not self.queue.empty():
            job = self.queue.get_nowait()
            self.db.update_status(job.url, job.format_key, "paused")
            paused_urls.append(job.url)
            temp.append(job)

        for job in temp:
            self.queue.put_nowait(job)

        return paused_urls