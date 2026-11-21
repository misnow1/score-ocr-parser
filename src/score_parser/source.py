"""Source stage: PDF pages to Pages of Tokens, from the text layer or by OCR."""

from pathlib import Path

import pymupdf

from .models import Page, PageReason, Token

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
            reason = classify_page(pg)
            if force_ocr or reason != "text":
                pages.append(_ocr_page(doc, pg, i, _page_image(doc, pg), reason))
            else:
                pages.append(_text_page(pg, i))
    return pages


def classify_page(pg: pymupdf.Page) -> PageReason:
    """Why a page is read the way it is.

    "text": it has a text layer. With almost no text words it is instead "image"
    (a page-sized embedded image), "pattern" (a tiling-pattern fill, which image
    detection cannot see) or "empty" (nothing readable). Anything but "text" is
    rendered and sent to OCR.
    """
    if len(pg.get_text("words")) > MAX_TEXT_WORDS:
        return "text"
    image = _page_image(pg.parent, pg)
    if image and image[1].get_area() / pg.rect.get_area() >= MIN_IMAGE_COVERAGE:
        return "image"
    if b"/Pattern" in pg.read_contents():
        return "pattern"
    return "empty"


def scan_warnings(page: Page) -> list[str]:
    out = []
    if not page.tokens:
        out.append(f"page {page.number}: no text found ({page.reason}, read by {page.source})")
    if page.dpi is not None and page.dpi < MIN_USEFUL_DPI:
        out.append(f"page {page.number}: low resolution ({page.dpi:.0f} dpi), results unreliable")
    if page.ocr_confidence is not None and page.ocr_confidence < MIN_CONFIDENCE:
        out.append(f"page {page.number}: low OCR confidence ({page.ocr_confidence:.2f})")
    return out


def _text_page(pg: pymupdf.Page, number: int) -> Page:
    spans = [
        (pymupdf.Rect(s["bbox"]), s["font"])
        for b in pg.get_text("dict")["blocks"]
        for ln in b.get("lines", [])
        for s in ln["spans"]
    ]
    tokens = []
    for x0, y0, x1, y1, text, *_ in pg.get_text("words"):
        centre = pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)
        font = next((f for r, f in spans if centre in r), "")
        tokens.append(Token(text, x0, y0, x1, y1, number, font))
    return Page(number, pg.rect.width, pg.rect.height, tokens, reason="text")


def _page_image(doc: pymupdf.Document, pg: pymupdf.Page) -> tuple[int, pymupdf.Rect] | None:
    """The largest embedded image as (xref, rect on page), or None."""
    best = None
    for img in pg.get_images(full=True):
        for rect in pg.get_image_rects(img[0]):
            if best is None or rect.get_area() > best[1].get_area():
                best = (img[0], rect)
    return best


def _ocr_page(
    doc: pymupdf.Document,
    pg: pymupdf.Page,
    number: int,
    image: tuple[int, pymupdf.Rect] | None,
    reason: PageReason,
) -> Page:
    from .ocr import recognise  # macOS-only; imported lazily

    if reason in ("pattern", "empty") or image is None:  # no usable image: render the page
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
        number,
        pg.rect.width,
        pg.rect.height,
        tokens,
        "ocr",
        ocr_confidence=mean,
        dpi=dpi,
        reason=reason,
    )
