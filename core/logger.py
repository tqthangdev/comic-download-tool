import logging

from core.utils import DATA_DIR


LOGS_DIR = DATA_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOGS_DIR / "error.log"


logger = logging.getLogger("ComicEngine")
logger.setLevel(logging.ERROR)


# File handler writes ERROR/CRITICAL logs to the writable user data directory
file_handler = logging.FileHandler(
    LOG_FILE,
    encoding="utf-8",
)
file_handler.setLevel(logging.ERROR)


formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

file_handler.setFormatter(formatter)


if not logger.handlers:
    logger.addHandler(file_handler)


__all__ = [
    "logger",
    "LOGS_DIR",
    "LOG_FILE",
]