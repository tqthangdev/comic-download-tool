import asyncio
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


class JobManager:

    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: executor sẽ gọi từ thread khác thread tạo connection
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # sqlite3 connection không an toàn khi nhiều thread cùng ghi -> cần lock
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
                    current_chap  INTEGER
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

    # ------------------------------------------------------------------
    # CRUD (đồng bộ - giữ nguyên để dùng nội bộ / lúc khởi tạo, không hot path)
    # ------------------------------------------------------------------

    def add(self, job: Job):
        with self._lock:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO jobs (url, title, save_path, status, current_chap)
                VALUES (?, ?, ?, 'waiting', NULL)
                """,
                (job.url, job.title, str(job.save_path)),
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
        )

    def update_status(self, url: str, status: str):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET status = ? WHERE url = ?",
                (status, url),
            )
            self.conn.commit()

    def update_current_chap(self, url: str, chap_index: int):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET current_chap = ? WHERE url = ?",
                (chap_index, url),
            )
            self.conn.commit()

    def reset_current_chap(self, url: str):
        with self._lock:
            self.conn.execute(
                "UPDATE jobs SET current_chap = NULL WHERE url = ?",
                (url,),
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
            )
            for r in rows
        ]

    def get_restorable_jobs(self) -> list[Job]:
        with self._lock:
            # ORDER BY rowid để giữ đúng thứ tự thêm vào — restore về queue
            # theo đúng thứ tự queue list.
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
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # ASYNC WRAPPERS - dùng ở hot path (bên trong worker/download loop)
    # để không block event loop chính (qasync dùng chung loop với GUI)
    # ------------------------------------------------------------------

    async def aupdate_status(self, url: str, status: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_status, url, status)

    async def aupdate_current_chap(self, url: str, chap_index: int):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.update_current_chap, url, chap_index)

    async def areset_current_chap(self, url: str):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.reset_current_chap, url)
