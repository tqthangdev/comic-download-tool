"""
core/pdf.py

Turn each downloaded chapter into a single PDF (one page per image).

Used by the "Convert to PDF" option: when it is on, a finished story keeps
`<story>/<chapter>.pdf` files instead of the per-chapter image folders — each
PDF replaces the folder of images it was built from.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from core.logger import logger

IMAGE_SUFFIXES = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".tif", ".tiff",
}

# Outcome of trying to produce one chapter's PDF.
PDF_BUILT = "built"      # a new PDF was written
PDF_CURRENT = "current"  # an up-to-date PDF was already in place
PDF_FAILED = "failed"    # nothing usable (no images, or the conversion failed)


def _chapter_images(chapter_dir: Path) -> list[Path]:
    """The chapter's images, in filename order (0000.jpg, 0001.jpg, ...)."""
    return sorted(
        (
            p
            for p in chapter_dir.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
        ),
        key=lambda p: p.name,
    )


def build_chapter_pdf(chapter_dir: Path, pdf_path: Path) -> str:
    """Make sure `pdf_path` holds the images of `chapter_dir`, in filename order.

    A PDF that is already newer than every image is kept, so re-running a job
    does not rebuild it — while a chapter that gained images later is rebuilt.
    """
    images = _chapter_images(chapter_dir)
    if not images:
        return PDF_CURRENT if pdf_path.exists() else PDF_FAILED

    try:
        newest_image = max(p.stat().st_mtime for p in images)
        if pdf_path.exists() and pdf_path.stat().st_mtime >= newest_image:
            return PDF_CURRENT
    except OSError:
        pass

    try:
        import img2pdf

        # JPEG pages are embedded as-is (lossless); other formats are handled
        # through Pillow, which img2pdf uses as its backend for them.
        data = img2pdf.convert([str(p) for p in images])

        tmp_path = pdf_path.with_name(pdf_path.name + ".tmp")
        tmp_path.write_bytes(data)
        tmp_path.replace(pdf_path)
        return PDF_BUILT
    except Exception as e:
        logger.error(f"[pdf] Failed to build '{pdf_path}': {type(e).__name__}: {e}")
        return PDF_FAILED


def chapter_folders(story_dir: Path) -> list[Path]:
    """The chapter image folders under a story directory, in name order."""
    if not story_dir.is_dir():
        return []
    return sorted(p for p in story_dir.iterdir() if p.is_dir())


def convert_chapter(chapter_dir: Path, story_dir: Path) -> str:
    """Write `<story>/<chapter>.pdf` from `chapter_dir` and drop that folder.

    Returns one of PDF_BUILT / PDF_CURRENT / PDF_FAILED. The images are kept
    when nothing usable could be written.
    """
    result = build_chapter_pdf(chapter_dir, story_dir / f"{chapter_dir.name}.pdf")
    if result == PDF_FAILED:
        return result

    try:
        shutil.rmtree(chapter_dir)
    except OSError as e:
        logger.error(f"[pdf] Could not remove '{chapter_dir}' after writing its PDF: {e}")

    return result
