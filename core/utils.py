import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


def safe_filename(name: str, max_length=200):
    # 1. Strip characters forbidden by the OS
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)

    # 2. Truncate long names
    if len(name) > max_length:
        name = name[:max_length]

    # 3. Strip trailing dots and spaces
    name = name.rstrip(" .")

    return name


def is_download_exists(path: Path) -> bool:
    if not path.exists():
        return False

    # Empty folder
    if not any(path.iterdir()):
        return False

    return True


def resolve_ddg_proxy(url: str) -> str:
    """Resolve DuckDuckGo image proxy URLs to the original image URL."""
    parsed = urlparse(url)

    if (
        parsed.netloc == "external-content.duckduckgo.com"
        and parsed.path == "/iu/"
    ):
        qs = parse_qs(parsed.query)

        if "u" in qs:
            return unquote(qs["u"][0])

    return url


def get_base_dir() -> Path:
    """Return the directory containing the executable or project root."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    return Path(__file__).parent.parent


def get_resource_path(relative_path: str) -> Path:
    """Return the path to a bundled/read-only application resource."""
    if getattr(sys, "frozen", False):
        base_path = Path(
            getattr(sys, "_MEIPASS", None)
            or Path(sys.executable).parent
        )
    else:
        base_path = Path(__file__).parent.parent

    return base_path / relative_path


BASE_DIR = get_base_dir()


def get_user_data_dir() -> Path:
    """
    Return a writable directory for application data.

    The data directory is created right next to the executable (release)
    or in the project root (dev), so config.json / jobs.db live wherever
    the app is run from.
    """
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    return data_dir


# Writable application data directory.
DATA_DIR = get_user_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)


DEFAULT_CONFIG = {
    "max_workers": 10,
    "max_concurrent_downloads": 10,
    "download_retry": 3,
    "chapter_retry": 2,
    "request_timeout": 30,
    "download_thumb": True,
    "language": "en",
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    ),
}


def get_config_path() -> Path:
    """Return the writable user configuration path."""
    return DATA_DIR / "config.json"


def load_config() -> dict:
    """
    Load configuration from the writable user data directory.

    A bundled config.json is used as the initial template when no
    user configuration exists yet.
    """
    config_path = get_config_path()
    bundled_config_path = get_resource_path("config.json")

    config = DEFAULT_CONFIG.copy()

    # Existing user configuration
    if config_path.exists() and config_path.stat().st_size > 0:
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)

            config.update(
                {
                    k: v
                    for k, v in user_config.items()
                    if v not in (None, "")
                }
            )

            # Add newly introduced default fields
            if set(DEFAULT_CONFIG) - set(user_config):
                try:
                    with open(config_path, "w", encoding="utf-8") as f:
                        json.dump(
                            config,
                            f,
                            indent=4,
                            ensure_ascii=False,
                        )
                except Exception as e:
                    from core.logger import logger

                    logger.error(
                        f"[config] Failed to update config.json: {e}"
                    )

        except Exception as e:
            from core.logger import logger

            logger.error(
                f"[config] Error reading config.json, using defaults: {e}"
            )

            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(
                        config,
                        f,
                        indent=4,
                        ensure_ascii=False,
                    )
            except Exception:
                pass

    # No user config yet
    else:
        # If the bundled config exists, use it as the initial config.
        if bundled_config_path.exists():
            try:
                with open(
                    bundled_config_path,
                    "r",
                    encoding="utf-8",
                ) as f:
                    bundled_config = json.load(f)

                config.update(
                    {
                        k: v
                        for k, v in bundled_config.items()
                        if v not in (None, "")
                    }
                )

            except Exception as e:
                from core.logger import logger

                logger.error(
                    f"[config] Error reading bundled config.json: {e}"
                )

        # Create writable user config
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(
                    config,
                    f,
                    indent=4,
                    ensure_ascii=False,
                )

        except Exception as e:
            from core.logger import logger

            logger.error(
                f"[config] Failed to create config.json: {e}"
            )

    return config


def save_config(config: dict) -> bool:
    """Save configuration to the writable user data directory."""
    config_path = get_config_path()

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(
                config,
                f,
                indent=4,
                ensure_ascii=False,
            )

        return True

    except Exception as e:
        from core.logger import logger

        logger.error(
            f"[config] Failed to write config.json: {e}"
        )

        return False


CONFIG = load_config()