import sys
from pathlib import Path
import re
from urllib.parse import urlparse, parse_qs, unquote


def safe_filename(name: str, max_length=80):
    # 1. Strip characters forbidden by the OS
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)

    # 2. Truncate long names (no longer appends "..." )
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
    """If this is an external-content.duckduckgo.com/iu/?u=... proxy link, return the real image URL."""
    parsed = urlparse(url)
    if parsed.netloc == "external-content.duckduckgo.com" and parsed.path == "/iu/":
        qs = parse_qs(parsed.query)
        if "u" in qs:
            return unquote(qs["u"][0])
    return url


def get_base_dir() -> Path:
    """Root folder of the app — next to the executable when built, or the project folder when running in dev."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent


def get_resource_path(relative_path: str) -> Path:
    if getattr(sys, "frozen", False):
        base_path = Path(getattr(sys, "_MEIPASS", None) or Path(sys.executable).parent)
    else:
        base_path = Path(__file__).parent.parent
    return base_path / relative_path


BASE_DIR = get_base_dir()
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

import json

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


def load_config() -> dict:
    config_path = get_resource_path("config.json") if not getattr(sys, "frozen", False) \
        else get_base_dir() / "config.json"

    # config.json must be readable/writable -> always prefer the copy next to the
    # executable/base dir, never the read-only copy from the bundle
    config_path = get_base_dir() / "config.json"

    config = DEFAULT_CONFIG.copy()

    if config_path.exists() and config_path.stat().st_size > 0:
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            config.update({k: v for k, v in user_config.items() if v not in (None, "")})
            # Fill in any missing keys (e.g. new fields added later)
            if set(DEFAULT_CONFIG) - set(user_config):
                try:
                    with open(config_path, "w", encoding="utf-8") as f:
                        json.dump(config, f, indent=4, ensure_ascii=False)
                except Exception as e:
                    from core.logger import logger
                    logger.error(f"[config] Failed to write missing default fields: {e}")
        except Exception as e:
            from core.logger import logger
            logger.error(f"[config] Error reading config.json, using defaults: {e}")
            # Corrupt file -> rewrite it with all default fields
            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=4, ensure_ascii=False)
            except Exception:
                pass
    else:
        # No file yet -> create a sample file with defaults for easy editing
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            from core.logger import logger
            logger.error(f"[config] Failed to create default config.json: {e}")

    return config


def save_config(config: dict) -> bool:
    """Write the current config down to config.json (next to the exe/base dir).
    Returns True on success."""
    config_path = get_base_dir() / "config.json"
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        from core.logger import logger
        logger.error(f"[config] Failed to write config.json: {e}")
        return False


CONFIG = load_config()
