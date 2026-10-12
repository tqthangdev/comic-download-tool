"""Session registry: each session is a self-contained job database.

A session groups a set of downloads and is stored as a single SQLite file
(``data/jobs_<id>.db``). The registry (``data/sessions.json``) maps each
session's stable random id to a display name and remembers which one is
current. See :mod:`core.sessions.sessions` for the implementation.
"""

from core.sessions.sessions import (
    SESSION_NAME_MAX_LENGTH,
    SessionInfo,
    SessionStore,
    clean_session_name,
    cleanup_scratch,
    delete_session_files,
    delete_session_scratch,
    job_scratch_dir,
    new_session_id,
    scratch_dir,
    session_db_path,
)

__all__ = [
    "SESSION_NAME_MAX_LENGTH",
    "SessionInfo",
    "SessionStore",
    "clean_session_name",
    "cleanup_scratch",
    "delete_session_files",
    "delete_session_scratch",
    "job_scratch_dir",
    "new_session_id",
    "scratch_dir",
    "session_db_path",
]
