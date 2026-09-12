import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


# Linux limits each path component to 255 bytes (NAME_MAX) — Windows to 255
# UTF-16 code units. Multibyte UTF-8 characters (Vietnamese, CJK, emoji) can
# blow past that even at well under 255 *characters*, so keep a safe margin
# and truncate by bytes, never splitting a character in the middle.
MAX_FILENAME_BYTES = 255


def safe_filename(name: str, max_length: int = MAX_FILENAME_BYTES):
    # 1. Strip characters forbidden by the OS
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)

    # 2. Truncate long names — by *bytes* so multibyte UTF-8 (Vietnamese, CJK,
    #    emoji) can't exceed the filesystem's per-component byte limit.
    encoded = name.encode("utf-8", errors="ignore")
    if len(encoded) > max_length:
        # Cut at the byte boundary, then trim any trailing partial character.
        encoded = encoded[:max_length]
        name = encoded.decode("utf-8", errors="ignore")

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
    "max_workers": 8,
    "max_concurrent_downloads": 8,
    "download_retry": 3,
    "chapter_retry": 2,
    "request_timeout": 30,
    "download_thumb": True,
    "download_genres": True,
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

# ================= LINK FILE VALIDATION (Add Queue by file) =================

# A line is considered a valid job entry if it looks like an http(s) URL.
URL_PATTERN = re.compile(r"^https?://\S+$", re.IGNORECASE)

# Reject files above this size before even trying to read them (a link list
# file should never be this large; avoids loading a huge binary into RAM).
MAX_LINK_FILE_BYTES = 5 * 1024 * 1024  # 5 MB

# How many leading bytes to sniff for a NUL byte (binary-content signature).
BINARY_SNIFF_BYTES = 8192


def _looks_binary(path: Path) -> bool:
    """Cheap binary-content check: text files essentially never contain a
    NUL byte, while executables/archives/media almost always do within the
    first few KB. This catches .exe/.dll/.zip/etc. regardless of extension,
    without needing to read the whole file."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(BINARY_SNIFF_BYTES)
    except OSError:
        return False  # let the caller's own read attempt report the error
    return b"\x00" in chunk


def parse_link_file(path) -> tuple[list, str | None, str | None]:
    """Read and validate a link-list file.

    Blank lines and lines starting with "#" are treated as comments and
    ignored (not counted as invalid). Every remaining line must match
    URL_PATTERN.

    Returns (urls, error_code, error_detail):
    - Success: (urls, None, None)
    - Failure: ([], error_code, error_detail)
      error_code is one of "too_large", "binary", "not_text", "read",
      "empty", "invalid". error_detail holds extra context (offending
      lines / OS error text) when relevant, otherwise None.
    """
    file_path = Path(path)

    try:
        size = file_path.stat().st_size
    except OSError as e:
        return [], "read", str(e)

    if size > MAX_LINK_FILE_BYTES:
        return [], "too_large", None

    # Catches binaries (exe/dll/zip/media/...) regardless of extension,
    # before we ever try to decode the whole file as text.
    if _looks_binary(file_path):
        return [], "binary", None

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], "not_text", None
    except OSError as e:
        return [], "read", str(e)

    lines = [line.strip() for line in content.splitlines()]
    lines = [line for line in lines if line and not line.startswith("#")]

    if not lines:
        return [], "empty", None

    invalid_lines = [line for line in lines if not URL_PATTERN.match(line)]
    if invalid_lines:
        preview = "\n".join(invalid_lines[:5])
        if len(invalid_lines) > 5:
            preview += f"\n... (+{len(invalid_lines) - 5})"
        return [], "invalid", preview

    return lines, None, None