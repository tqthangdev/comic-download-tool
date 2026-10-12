import asyncio
import json
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from core.utils import CONFIG, DATA_DIR

# Legacy single-file database (pre-session). New installs open one file per
# session instead (see core.sessions); this default is still used by tooling and
# by the legacy migration in core.sessions.sessions.
DB_PATH = DATA_DIR / "jobs.db"

# A job's identity inside a session database is (url, format_key): the same URL
# in two output formats is two jobs.
IMAGE_FORMAT_KEY = "image"
PDF_FORMAT_KEY = "pdf"

_CREATE_JOBS_TABLE = """
    CREATE TABLE IF NOT EXISTS jobs (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        url                   TEXT NOT NULL,
        format_key            TEXT NOT NULL DEFAULT 'image',
        title                 TEXT,
        save_path             TEXT,
        status                TEXT DEFAULT 'waiting',
        current_chap          INTEGER,
        chapters              TEXT,
        thumb                 TEXT,
        referer               TEXT,
        site_id               TEXT,
        genres                TEXT,
        engine                TEXT,
        engine_fallback_used  INTEGER,
        engine_error          TEXT,
        convert_to_pdf        INTEGER,
        UNIQUE(url, format_key)
    )
"""


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
    engine: str = field(default=None)     # backend actually used: "native" / "gallerydl"
    engine_fallback_used: int = field(default=None)  # 1 when the job was retried on the other engine
    engine_error: str = field(default=None)          # last engine error (debug / tooltip)
    convert_to_pdf: bool = field(default=None)       # per-job output format (None = config default)
    # (url, format_key) identifies a job within its session; `id` is the DB row
    # id, used to scope the job's scratch folder (".temp/<session>/<id>/").
    format_key: str = field(default=None)
    id: int = field(default=None)


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

    def close(self):
        """Close the underlying connection (used when switching sessions)."""
        with self._lock:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass

    # ------------------------------------------------------------------
    # SCHEMA
    # ------------------------------------------------------------------

    def _create_table(self):
        with self._lock:
            self.conn.execute(_CREATE_JOBS_TABLE)
            self.conn.commit()

    def _migrate(self):
        with self._lock:
            cols = {row[1] for row in self.conn.execute("PRAGMA table_info(jobs)")}
            if not cols or "id" in cols:
                # Brand-new v2 table, or already migrated.
                return

            # Bring an older table up to date column-wise before copying it, so
            # the rebuild can reference every field.
            for column, ddl in (
                ("current_chap", "INTEGER"),
                ("chapters", "TEXT"),
                ("thumb", "TEXT"),
                ("referer", "TEXT"),
                ("site_id", "TEXT"),
                ("genres", "TEXT"),
                ("engine", "TEXT"),
                ("engine_fallback_used", "INTEGER"),
                ("engine_error", "TEXT"),
                ("convert_to_pdf", "INTEGER"),
            ):
                if column not in cols:
                    self.conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {ddl}")

            # Rebuild the legacy (url PRIMARY KEY) table into the v2 schema so a
            # job's identity becomes (url, format_key).
            self.conn.execute("ALTER TABLE jobs RENAME TO jobs_legacy")
            self.conn.execute(_CREATE_JOBS_TABLE)
            self.conn.execute(
                """
                INSERT INTO jobs (
                    url, format_key, title, save_path, status, current_chap,
                    chapters, thumb, referer, site_id, genres, engine,
                    engine_fallback_used, engine_error, convert_to_pdf
                )
                SELECT
                    url,
                    CASE WHEN convert_to_pdf = 1 THEN 'pdf' ELSE 'image' END,
                    title, save_path, status, current_chap, chapters, thumb,
                    referer, site_id, genres, engine, engine_fallback_used,
                    engine_error, convert_to_pdf
                FROM jobs_legacy
                """
            )
            self.conn.execute("DROP TABLE jobs_legacy")
            self.conn.commit()

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def format_key_for(job) -> str:
        """The (url, format_key) identity component for a job.

        Mirrors Engine._wants_pdf: an explicit per-job value wins, otherwise the
        global config default applies.
        """
        value = getattr(job, "convert_to_pdf", None)
        pdf = bool(value) if value is not None else bool(CONFIG.get("convert_to_pdf", False))
        return PDF_FORMAT_KEY if pdf else IMAGE_FORMAT_KEY

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

    @staticmethod
    def _col(row, name, default=None):
        """Read a column defensively (legacy rows may lack newer columns)."""
        return row[name] if name in row.keys() else default

    @staticmethod
    def _row_to_job(row) -> Job:
        convert_to_pdf = (
            None if JobManager._col(row, "convert_to_pdf") is None
            else bool(JobManager._col(row, "convert_to_pdf"))
        )
        format_key = JobManager._col(row, "format_key")
        if not format_key:
            format_key = PDF_FORMAT_KEY if convert_to_pdf else IMAGE_FORMAT_KEY
        return Job(
            url=row["url"],
            title=JobManager._col(row, "title"),
            save_path=Path(row["save_path"]),
            current_chap=JobManager._col(row, "current_chap"),
            status=JobManager._col(row, "status"),
            chapters=JobManager._chapters_from_json(JobManager._col(row, "chapters")),
            thumb=JobManager._col(row, "thumb"),
            referer=JobManager._col(row, "referer"),
            site_id=JobManager._col(row, "site_id"),
            genres=JobManager._genres_from_json(JobManager._col(row, "genres")),
            engine=JobManager._col(row, "engine"),
            engine_fallback_used=JobManager._col(row, "engine_fallback_used"),
            engine_error=JobManager._col(row, "engine_error"),
            convert_to_pdf=convert_to_pdf,
            format_key=format_key,
            id=JobManager._col(row, "id"),
        )

    # ------------------------------------------------------------------
    # CRUD (synchronous - kept for internal use / startup, not the hot path)
    # ------------------------------------------------------------------

    def add(self, job: Job):
        format_key = job.format_key or self.format_key_for(job)
        job.format_key = format_key
        with self._lock:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO jobs (url, format_key, title, save_path, status, chapters, thumb, referer, site_id, genres, engine, convert_to_pdf)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (job.url, format_key, job.title, str(job.save_path),
                 job.status or "waiting",
                 self._chapters_to_json(job.chapters), job.thumb, job.referer, job.site_id,
                 self._genres_to_json(job.genres), job.engine,
                 None if job.convert_to_pdf is None else int(bool(job.convert_to_pdf))),
            )
            self.conn.commit()
        job.id = self.get_job_id(job.url, format_key)

    def get_job(self, url: str, format_key: str) -> Job | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM jobs WHERE url = ? AND format_key = ?",
                (url, format_key),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    def get_jobs_by_url(self, url: str) -> list[Job]:
        """Every format variant of a URL in the current session."""
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM jobs WHERE url = ? ORDER BY id", (url,)
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def get_job_id(self, url: str, format_key: str) -> int | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT id FROM jobs WHERE url = ? AND format_key = ?",
                (url, format_key),
            ).fetchone()
        return row["id"] if row else None

    def update_status(self, url: str, format_key: str, status: str):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET status = ? WHERE url = ? AND format_key = ?",
                (status, url, format_key),
            )
            self.conn.commit()

    def update_status_bulk(self, keys: list[tuple[str, str]], status: str):
        """keys: iterable of (url, format_key)."""
        pairs = list(keys)
        if not pairs:
            return
        with self._lock:
            self.conn.executemany(
                "UPDATE jobs SET status = ? WHERE url = ? AND format_key = ?",
                [(status, url, format_key) for (url, format_key) in pairs],
            )
            self.conn.commit()

    def update_save_path(self, url: str, format_key: str, save_path: Path):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET save_path = ? WHERE url = ? AND format_key = ?",
                (str(save_path), url, format_key),
            )
            self.conn.commit()

    def update_site_id(self, url: str, format_key: str, site_id: str):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET site_id = ? WHERE url = ? AND format_key = ?",
                (site_id, url, format_key),
            )
            self.conn.commit()

    def update_genres(self, url: str, format_key: str, genres: list):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET genres = ? WHERE url = ? AND format_key = ?",
                (self._genres_to_json(genres), url, format_key),
            )
            self.conn.commit()

    def update_engine(self, url: str, format_key: str, engine: str):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET engine = ? WHERE url = ? AND format_key = ?",
                (engine, url, format_key),
            )
            self.conn.commit()

    def update_engine_fallback_used(self, url: str, format_key: str, used: bool):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET engine_fallback_used = ? WHERE url = ? AND format_key = ?",
                (1 if used else 0, url, format_key),
            )
            self.conn.commit()

    def update_engine_error(self, url: str, format_key: str, error: str):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET engine_error = ? WHERE url = ? AND format_key = ?",
                (error, url, format_key),
            )
            self.conn.commit()

    def update_current_chap(self, url: str, format_key: str, chap_index: int):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET current_chap = ? WHERE url = ? AND format_key = ?",
                (chap_index, url, format_key),
            )
            self.conn.commit()

    def update_chapters(self, url: str, format_key: str, chapters: list):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET chapters = ? WHERE url = ? AND format_key = ?",
                (self._chapters_to_json(chapters), url, format_key),
            )
            self.conn.commit()

    def update_thumb(self, url: str, format_key: str, thumb: str):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET thumb = ? WHERE url = ? AND format_key = ?",
                (thumb, url, format_key),
            )
            self.conn.commit()

    def reset_current_chap(self, url: str, format_key: str):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET current_chap = NULL WHERE url = ? AND format_key = ?",
                (url, format_key),
            )
            self.conn.commit()

    def delete(self, url: str, format_key: str):
        with self._lock:
            self.conn.execute(
                "DELETE FROM jobs WHERE url = ? AND format_key = ?",
                (url, format_key),
            )
            self.conn.commit()

    def delete_bulk(self, keys: list[tuple[str, str]]):
        pairs = list(keys)
        if not pairs:
            return
        with self._lock:
            self.conn.executemany(
                "DELETE FROM jobs WHERE url = ? AND format_key = ?",
                [(url, format_key) for (url, format_key) in pairs],
            )
            self.conn.commit()

    def all_jobs(self) -> list[Job]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM jobs ORDER BY id").fetchall()
        return [self._row_to_job(r) for r in rows]

    def get_restorable_jobs(self) -> list[Job]:
        with self._lock:
            # Every job that is not fully finished ("done") must come back on
            # the next launch — including "done_with_missing", "failed",
            # "paused", "waiting" and "running".
            # ORDER BY id to preserve insertion order — restore into the queue
            # in the same order as the queue list.
            rows = self.conn.execute(
                "SELECT * FROM jobs WHERE status IS NULL OR status != 'done' ORDER BY id"
            ).fetchall()
        return [self._row_to_job(r) for r in rows]

    # ------------------------------------------------------------------
    # ASYNC WRAPPERS - used in the hot path (inside the worker/download loop)
    # so writes do not block the main event loop (qasync shares the loop with the GUI)
    # ------------------------------------------------------------------

    async def aupdate_status(self, url: str, format_key: str, status: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_status, url, format_key, status)

    async def aupdate_current_chap(self, url: str, format_key: str, chap_index: int):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_current_chap, url, format_key, chap_index)

    async def aupdate_chapters(self, url: str, format_key: str, chapters: list):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_chapters, url, format_key, chapters)

    async def aupdate_thumb(self, url: str, format_key: str, thumb: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_thumb, url, format_key, thumb)

    async def aupdate_site_id(self, url: str, format_key: str, site_id: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_site_id, url, format_key, site_id)

    async def aupdate_genres(self, url: str, format_key: str, genres: list):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_genres, url, format_key, genres)

    async def aupdate_engine(self, url: str, format_key: str, engine: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_engine, url, format_key, engine)

    async def aupdate_engine_fallback_used(self, url: str, format_key: str, used: bool):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_engine_fallback_used, url, format_key, used)

    async def aupdate_engine_error(self, url: str, format_key: str, error: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_engine_error, url, format_key, error)

    async def areset_current_chap(self, url: str, format_key: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.reset_current_chap, url, format_key)

    async def adelete(self, url: str, format_key: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.delete, url, format_key)
