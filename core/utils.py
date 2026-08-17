import sys
from pathlib import Path
import re
from urllib.parse import urlparse, parse_qs, unquote


def safe_filename(name: str, max_length=80):
    # 1. Xóa các ký tự cấm của hệ điều hành
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)

    # 2. Nếu tên quá dài, cắt ngắn lại (KHÔNG cộng thêm dấu ba chấm "..." nữa)
    if len(name) > max_length:
        name = name[:max_length]

    # 3. Tiến hành gọt sạch dấu chấm và khoảng trắng ở cuối cùng
    name = name.rstrip(" .")

    return name


def is_download_exists(path: Path) -> bool:
    if not path.exists():
        return False

    # Folder rỗng
    if not any(path.iterdir()):
        return False

    return True


def resolve_ddg_proxy(url: str) -> str:
    """Nếu là link proxy external-content.duckduckgo.com/iu/?u=... thì trả về link ảnh gốc."""
    parsed = urlparse(url)
    if parsed.netloc == "external-content.duckduckgo.com" and parsed.path == "/iu/":
        qs = parse_qs(parsed.query)
        if "u" in qs:
            return unquote(qs["u"][0])
    return url


def get_base_dir() -> Path:
    """Thư mục gốc của app — cạnh exe khi đã build, hoặc thư mục project khi chạy dev."""
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
    "max_workers": 3,
    "max_concurrent_downloads": 4,
    "download_retry": 3,
    "chapter_retry": 2,
    "request_timeout": 30,
    "download_thumb": True,
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    ),
    "default_save_dir": "downloads",
}


def load_config() -> dict:
    config_path = get_resource_path("config.json") if not getattr(sys, "frozen", False) \
        else get_base_dir() / "config.json"

    # config.json cần đọc/ghi được -> luôn ưu tiên bản cạnh exe/base dir, không lấy từ bundle chỉ-đọc
    config_path = get_base_dir() / "config.json"

    config = DEFAULT_CONFIG.copy()

    if config_path.exists() and config_path.stat().st_size > 0:
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            config.update({k: v for k, v in user_config.items() if v not in (None, "")})
        except Exception as e:
            from core.logger import logger
            logger.error(f"[config] Lỗi đọc config.json, dùng mặc định: {e}")
    else:
        # chưa có file -> tạo file mẫu với giá trị mặc định để người dùng dễ chỉnh sau
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            from core.logger import logger
            logger.error(f"[config] Không tạo được config.json mặc định: {e}")

    return config


def save_config(config: dict) -> bool:
    """Ghi config hiện tại xuống config.json (cạnh exe/base dir).
    Trả về True nếu ghi thành công."""
    config_path = get_base_dir() / "config.json"
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        from core.logger import logger
        logger.error(f"[config] Không ghi được config.json: {e}")
        return False


CONFIG = load_config()
