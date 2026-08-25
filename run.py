import sys
import os
from pathlib import Path


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _default_playwright_browsers_path() -> Path:
    """Default path Playwright uses when no env var is set."""
    if sys.platform == "win32":
        return Path(os.environ["USERPROFILE"]) / "AppData" / "Local" / "ms-playwright"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    else:
        return Path.home() / ".cache" / "ms-playwright"


def _has_chromium_installed(browsers_dir: Path) -> bool:
    """Check whether any chromium build already exists in the ms-playwright folder."""
    if not browsers_dir.exists():
        return False
    return any(
        p.is_dir() and p.name.startswith("chromium")
        for p in browsers_dir.iterdir()
    )


def _setup_playwright_browsers_path():
    from core.logger import logger
    default_path = _default_playwright_browsers_path()

    if _has_chromium_installed(default_path):
        # A system Chromium already exists (installed via "playwright install")
        # -> do not set the env var; let Playwright use its default path.
        logger.info(f"[Playwright] Using existing Chromium at: {default_path}")
        return

    # Not at the default path -> use the portable build next to the executable
    portable_path = _get_base_dir() / "ms-playwright"
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(portable_path)
    logger.info(f"[Playwright] Using portable build at: {portable_path}")


_setup_playwright_browsers_path()

# --- Normal app run mode ---
import asyncio
import traceback

from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop

from gui.main_window import MainWindow
from core.engine import Engine

from core.utils import CONFIG

def main():
    from PyQt6.QtGui import QIcon

    app = QApplication(sys.argv)

    icon_path = _get_base_dir() / "assets" / "icon.png"

    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    engine = Engine(max_workers=CONFIG["max_workers"])
    window = MainWindow(engine)

    window.show()

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        from core.logger import logger
        logger.critical("Critical error / crash occurred", exc_info=True)
        raise