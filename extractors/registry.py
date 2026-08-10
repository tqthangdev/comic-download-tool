import importlib
import pkgutil
from pathlib import Path
from core.base_extractor import BaseExtractor

EXTRACTORS = []


def load_extractors():
    global EXTRACTORS
    EXTRACTORS.clear()

    package_dir = Path(__file__).parent
    for _, module_name, is_pkg in pkgutil.iter_modules([str(package_dir)]):
        if module_name in ("registry", "base") or is_pkg:
            continue

        try:
            module = importlib.import_module(f"extractors.{module_name}")
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseExtractor)
                    and attr is not BaseExtractor
                    and getattr(attr, "__module__", None) == module.__name__
                ):
                    instance = attr()
                    if not any(type(e) is type(instance) for e in EXTRACTORS):
                        EXTRACTORS.append(instance)
        except Exception as e:
            from core.logger import logger
            logger.error(f"[Registry] Lỗi khi load extractor '{module_name}': {e}")


load_extractors()


def get_extractor(url: str) -> BaseExtractor:
    for ex in EXTRACTORS:
        if ex.matches(url):
            return ex
    raise ValueError(f"Không tìm thấy extractor phù hợp cho url: {url}")
