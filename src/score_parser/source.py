"""Source stage: PDF pages to Pages of Tokens, from the text layer or by OCR."""

from pathlib import Path

import pymupdf

from .models import Page, Token

# A page with at most this many words and a mostly-covering image is a scan.
MAX_TEXT_WORDS = 5
MIN_IMAGE_COVERAGE = 0.5
# Pages below this resolution are upscaled to it before OCR.
TARGET_DPI = 300
# Below this resolution, or this mean OCR confidence, results can't be trusted.
MIN_USEFUL_DPI = 150
MIN_CONFIDENCE = 0.5


def read_pages(path: Path, force_ocr: bool = False) -> list[Page]:
    pages = []
    with pymupdf.open(path) as doc:
        for i, pg in enumerate(doc, start=1):
            image = _page_image(doc, pg)
            if force_ocr or (_is_image_only(pg) and image):
                pages.append(_ocr_page(doc, pg, i, image))
            else:
                pages.append(_text_page(pg, i))
    return pages


def scan_warnings(page: Page) -> list[str]:
    out = []
    if page.dpi is not None and page.dpi < MIN_USEFUL_DPI:
        out.append(f"page {page.number}: low resolution ({page.dpi:.0f} dpi), results unreliable")
    if page.ocr_confidence is not None and page.ocr_confidence < MIN_CONFIDENCE:
        out.append(f"page {page.number}: low OCR confidence ({page.ocr_confidence:.2f})")
    return out


def _text_page(pg: pymupdf.Page, number: int) -> Page:
    chars = [
        (pymupdf.Point((c["bbox"][0] + c["bbox"][2]) / 2, (c["bbox"][1] + c["bbox"][3]) / 2), s["font"])
        for b in pg.get_text("rawdict")["blocks"]
        for ln in b.get("lines", [])
        for s in ln["spans"]
        for c in s["chars"]
        if c["c"].strip()
    ]
    tokens = []
    for x0, y0, x1, y1, text, *_ in pg.get_text("words"):
        box = pymupdf.Rect(x0, y0, x1, y1)
        tokens.append(Token(text, x0, y0, x1, y1, number, _word_font(box, chars)))
    return Page(number, pg.rect.width, pg.rect.height, tokens)


def _word_font(box: pymupdf.Rect, chars: list[tuple[pymupdf.Point, str]]) -> str:
    """The font of a word's own characters; "" when they are not all in one font."""
    fonts = {f for centre, f in chars if centre in box}
    return fonts.pop() if len(fonts) == 1 else ""


def _page_image(doc: pymupdf.Document, pg: pymupdf.Page) -> tuple[int, pymupdf.Rect] | None:
    """The largest embedded image as (xref, rect on page), or None."""
    best = None
    for img in pg.get_images(full=True):
        for rect in pg.get_image_rects(img[0]):
            if best is None or rect.get_area() > best[1].get_area():
                best = (img[0], rect)
    return best


def _is_image_only(pg: pymupdf.Page) -> bool:
    image = _page_image(pg.parent, pg)
    if image is None:
        return False
    covered = image[1].get_area() / pg.rect.get_area()
    return covered >= MIN_IMAGE_COVERAGE and len(pg.get_text("words")) <= MAX_TEXT_WORDS


def _ocr_page(
    doc: pymupdf.Document,
    pg: pymupdf.Page,
    number: int,
    image: tuple[int, pymupdf.Rect] | None,
) -> Page:
    from .ocr import recognise  # macOS-only; imported lazily

    if image is None:  # forced OCR on a page with no image: render it
        rect, dpi = pg.rect, float(TARGET_DPI)
        png = pg.get_pixmap(dpi=TARGET_DPI, alpha=False).tobytes("png")
    else:
        xref, rect = image
        pix = pymupdf.Pixmap(doc, xref)
        dpi = pix.width / (rect.width / 72)
        if dpi >= TARGET_DPI:  # native resolution
            if pix.colorspace is None or pix.n - pix.alpha > 3 or pix.alpha:
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            png = pix.tobytes("png")
        else:  # upscale by rendering the image region at the target dpi
            png = pg.get_pixmap(dpi=TARGET_DPI, clip=rect, alpha=False).tobytes("png")
    tokens = recognise(png, rect, number)
    confidences = [t.confidence for t in tokens if t.confidence is not None]
    mean = sum(confidences) / len(confidences) if confidences else 0.0
    return Page(
        number, pg.rect.width, pg.rect.height, tokens, "ocr", ocr_confidence=mean, dpi=dpi
    )
