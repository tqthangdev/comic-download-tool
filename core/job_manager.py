import asyncio
import json
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from core.utils import DATA_DIR

DB_PATH = DATA_DIR / "jobs.db"


@dataclass
class Job:
    url: str
    title: str
    save_path: Path
    current_chap: int = field(default=None)
    status: str = field(default="waiting")
    chapters: list = field(default=None)  # [{title, url, update_time}] from scraper.py
    referer: str = field(default=None)    # referer derived from scraper (origin URL)
    thumb: str = field(default=None)      # cover image URL from scraper.py
    site_id: str = field(default=None)    # registered site id in core/auth (None = public, no login needed)
    genres: list = field(default=None)    # genres derived from scraper (list of strings)


class JobManager:

    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: the executor calls from a different thread
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # sqlite3 connections are not thread-safe -> guard writes with a lock
        self._lock = threading.Lock()
        self._create_table()
        self._migrate()

    # ------------------------------------------------------------------
    # SCHEMA
    # ------------------------------------------------------------------

    def _create_table(self):
        with self._lock:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    url           TEXT PRIMARY KEY,
                    title         TEXT,
                    save_path     TEXT,
                    status        TEXT DEFAULT 'waiting',
                    current_chap  INTEGER,
                    chapters      TEXT,
                    thumb         TEXT,
                    referer       TEXT,
                    site_id       TEXT,
                    genres        TEXT
                )
            """)
            self.conn.commit()

    def _migrate(self):
        with self._lock:
            cols = {
                row[1]
                for row in self.conn.execute("PRAGMA table_info(jobs)")
            }
            if "current_chap" not in cols:
                self.conn.execute(
                    "ALTER TABLE jobs ADD COLUMN current_chap INTEGER"
                )
                self.conn.commit()
            if "chapters" not in cols:
                self.conn.execute(
                    "ALTER TABLE jobs ADD COLUMN chapters TEXT"
                )
                self.conn.commit()
            if "thumb" not in cols:
                self.conn.execute(
                    "ALTER TABLE jobs ADD COLUMN thumb TEXT"
                )
                self.conn.commit()
            if "referer" not in cols:
                self.conn.execute(
                    "ALTER TABLE jobs ADD COLUMN referer TEXT"
                )
                self.conn.commit()
            if "site_id" not in cols:
                self.conn.execute(
                    "ALTER TABLE jobs ADD COLUMN site_id TEXT"
                )
                self.conn.commit()
            if "genres" not in cols:
                self.conn.execute(
                    "ALTER TABLE jobs ADD COLUMN genres TEXT"
                )
                self.conn.commit()

    # ------------------------------------------------------------------
    # CRUD (synchronous - kept for internal use / startup, not the hot path)
    # ------------------------------------------------------------------

    @staticmethod
    def _chapters_to_json(chapters) -> str | None:
        if not chapters:
            return None
        try:
            return json.dumps(chapters, ensure_ascii=False)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _chapters_from_json(raw) -> list:
        if not raw:
            return None
        try:
            chapters = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return chapters if isinstance(chapters, list) else None

    @staticmethod
    def _genres_to_json(genres) -> str | None:
        if not genres:
            return None
        try:
            return json.dumps(genres, ensure_ascii=False)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _genres_from_json(raw) -> list:
        if not raw:
            return None
        try:
            genres = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return genres if isinstance(genres, list) else None

    def add(self, job: Job):
        with self._lock:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO jobs (url, title, save_path, status, current_chap, chapters, thumb, referer, site_id, genres)
                VALUES (?, ?, ?, 'waiting', NULL, ?, ?, ?, ?, ?)
                """,
                (job.url, job.title, str(job.save_path),
                 self._chapters_to_json(job.chapters), job.thumb, job.referer, job.site_id,
                 self._genres_to_json(job.genres)),
            )
            self.conn.commit()

    def get_job(self, url: str) -> Job | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM jobs WHERE url = ?", (url,)
            ).fetchone()
        if row is None:
            return None
        return Job(
            url=row["url"],
            title=row["title"],
            save_path=Path(row["save_path"]),
            current_chap=row["current_chap"],
            status=row["status"],
            chapters=self._chapters_from_json(row["chapters"]),
            thumb=row["thumb"],
            referer=row["referer"],
            site_id=row["site_id"],
            genres=self._genres_from_json(row["genres"]),
        )

    def update_status(self, url: str, status: str):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET status = ? WHERE url = ?",
                (status, url),
            )
            self.conn.commit()

    def update_status_bulk(self, urls: list[str], status: str):
        if not urls:
            return

        with self._lock:
            self.conn.executemany(
                "UPDATE jobs SET status = ? WHERE url = ?",
                [(status, url) for url in urls],
            )
            self.conn.commit()

    def update_save_path(self, url: str, save_path: Path):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET save_path = ? WHERE url = ?",
                (str(save_path), url),
            )
            self.conn.commit()

    def update_site_id(self, url: str, site_id: str):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET site_id = ? WHERE url = ?",
                (site_id, url),
            )
            self.conn.commit()

    def update_genres(self, url: str, genres: list):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET genres = ? WHERE url = ?",
                (self._genres_to_json(genres), url),
            )
            self.conn.commit()

    def update_current_chap(self, url: str, chap_index: int):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET current_chap = ? WHERE url = ?",
                (chap_index, url),
            )
            self.conn.commit()

    def update_chapters(self, url: str, chapters: list):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET chapters = ? WHERE url = ?",
                (self._chapters_to_json(chapters), url),
            )
            self.conn.commit()

    def update_thumb(self, url: str, thumb: str):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET thumb = ? WHERE url = ?",
                (thumb, url),
            )
            self.conn.commit()

    def reset_current_chap(self, url: str):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET current_chap = NULL WHERE url = ?",
                (url,),
            )
            self.conn.commit()

    def delete(self, url: str):
        with self._lock:
            self.conn.execute(
                "DELETE FROM jobs WHERE url = ?",
                (url,),
            )
            self.conn.commit()

    def delete_bulk(self, urls: list[str]):
        if not urls:
            return
        with self._lock:
            self.conn.executemany(
                "DELETE FROM jobs WHERE url = ?",
                [(url,) for url in urls],
            )
            self.conn.commit()

    def all_jobs(self) -> list[Job]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM jobs").fetchall()
        return [
            Job(
                url=r["url"],
                title=r["title"],
                save_path=Path(r["save_path"]),
                current_chap=r["current_chap"],
                status=r["status"],
                chapters=self._chapters_from_json(r["chapters"]),
                thumb=r["thumb"],
                referer=r["referer"],
                site_id=r["site_id"],
                genres=self._genres_from_json(r["genres"]),
            )
            for r in rows
        ]

    def get_restorable_jobs(self) -> list[Job]:
        with self._lock:
            # ORDER BY rowid to preserve insertion order — restore into the queue
            # in the same order as the queue list.
            rows = self.conn.execute(
                "SELECT * FROM jobs WHERE status IN ('waiting', 'paused', 'failed', 'running') ORDER BY rowid"
            ).fetchall()
        return [
            Job(
                url=r["url"],
                title=r["title"],
                save_path=Path(r["save_path"]),
                current_chap=r["current_chap"],
                status=r["status"],
                chapters=self._chapters_from_json(r["chapters"]),
                thumb=r["thumb"],
                referer=r["referer"],
                site_id=r["site_id"],
                genres=self._genres_from_json(r["genres"]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # ASYNC WRAPPERS - used in the hot path (inside the worker/download loop)
    # so writes do not block the main event loop (qasync shares the loop with the GUI)
    # ------------------------------------------------------------------

    async def aupdate_status(self, url: str, status: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_status, url, status)

    async def aupdate_current_chap(self, url: str, chap_index: int):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_current_chap, url, chap_index)

    async def aupdate_chapters(self, url: str, chapters: list):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_chapters, url, chapters)

    async def aupdate_thumb(self, url: str, thumb: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_thumb, url, thumb)

    async def aupdate_site_id(self, url: str, site_id: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_site_id, url, site_id)

    async def aupdate_genres(self, url: str, genres: list):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_genres, url, genres)

    async def areset_current_chap(self, url: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.reset_current_chap, url)

    async def adelete(self, url: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.delete, url)
