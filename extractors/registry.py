import json
from pathlib import Path
from core.base_extractor import BaseExtractor
from extractors.base import ConfigExtractor

EXTRACTORS = []


def _config_path() -> Path:
    return Path(__file__).resolve().parent.parent / "extractor.json"


def load_extractors():
    global EXTRACTORS
    EXTRACTORS.clear()

    path = _config_path()
    if not path.exists():
        return

    try:
        configs = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        from core.logger import logger
        logger.error(f"[Registry] Lỗi đọc extractor.json: {e}")
        return

    for cfg in configs:
        if not isinstance(cfg, dict) or not cfg.get("domains"):
            continue
        EXTRACTORS.append(ConfigExtractor(cfg))


load_extractors()


def get_extractor(url: str) -> BaseExtractor:
    for ex in EXTRACTORS:
        if ex.matches(url):
            return ex
    raise ValueError(f"Không tìm thấy extractor phù hợp cho url: {url}")
