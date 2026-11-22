"""Source stage: PDF pages to Pages of Tokens, from the text layer or by OCR."""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pymupdf

from .models import Page, PageReason, Token

# A page with at most this many words and a mostly-covering image is a scan.
MAX_TEXT_WORDS = 5
MIN_IMAGE_COVERAGE = 0.5
# A drawn vertical rule at least this long (points) may be a barline.
MIN_BARLINE_LENGTH = 20.0
MAX_BARLINE_WIDTH = 3.0
# Pages below this resolution are upscaled to it before OCR.
TARGET_DPI = 300
# Below this resolution, or this mean OCR confidence, results can't be trusted.
MIN_USEFUL_DPI = 150
MIN_CONFIDENCE = 0.5
# Orientations tried on a scan, as degrees clockwise the content is printed rotated.
CANDIDATE_ROTATIONS = (0, 90, 270)

# Recognises text in a PNG covering a rect on a page (see ocr.recognise).
Recogniser = Callable[[bytes, pymupdf.Rect, int], list[Token]]
# Rates how plausible OCR tokens are as an upright page: (hits in the left
# half, all hits), compared before OCR confidence. The caller supplies it so
# this stage knows nothing of instrument vocabulary.
OrientationScorer = Callable[[list[Token], pymupdf.Rect], tuple[int, int]]


def _no_vocabulary(tokens: list[Token], frame: pymupdf.Rect) -> tuple[int, int]:
    return 0, 0


def read_pages(
    path: Path, force_ocr: bool = False, score_orientation: OrientationScorer = _no_vocabulary
) -> list[Page]:
    pages = []
    with pymupdf.open(path) as doc:
        for i, pg in enumerate(doc, start=1):
            reason = classify_page(pg)
            if force_ocr or reason != "text":
                pages.append(_ocr_page(doc, pg, i, _page_image(doc, pg), reason, score_orientation))
            else:
                pages.append(_text_page(pg, i))
    return pages


def classify_page(pg: pymupdf.Page) -> PageReason:
    """Why a page is read the way it is.

    "text": it has a text layer. With almost no text words it is instead "image"
    (a page-sized embedded image), "pattern" (a tiling-pattern fill, which image
    detection cannot see) or "empty" (no text at all). A page with a few words
    and no scan keeps its text layer. Anything but "text" is rendered and sent
    to OCR.
    """
    if len(pg.get_text("words")) > MAX_TEXT_WORDS:
        return "text"
    image = _page_image(pg.parent, pg)
    if image and image[1].get_area() / pg.rect.get_area() >= MIN_IMAGE_COVERAGE:
        return "image"
    if b"/Pattern" in pg.read_contents():
        return "pattern"
    return "text" if pg.get_text("words") else "empty"


def scan_warnings(page: Page) -> list[str]:
    out = []
    if not page.tokens:
        unavailable = "; OCR unavailable" if page.source == "text" and page.reason != "text" else ""
        out.append(f"page {page.number}: no text found ({page.reason}, read by {page.source}{unavailable})")
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
    return Page(number, pg.rect.width, pg.rect.height, tokens, reason="text", barlines=_barlines(pg))


def _barlines(pg: pymupdf.Page) -> list[tuple[float, float, float]]:
    """Vertical rules (drawn lines, or thin filled rectangles) as (x, y0, y1), sorted."""
    found = []
    for drawing in pg.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l":
                a, b = item[1], item[2]
                if abs(a.x - b.x) < 1 and abs(a.y - b.y) >= MIN_BARLINE_LENGTH:
                    found.append((a.x, min(a.y, b.y), max(a.y, b.y)))
            elif item[0] == "re":
                r = item[1]
                if r.width <= MAX_BARLINE_WIDTH and r.height >= MIN_BARLINE_LENGTH:
                    found.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
    return sorted(found)


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


def _ocr_page(
    doc: pymupdf.Document,
    pg: pymupdf.Page,
    number: int,
    image: tuple[int, pymupdf.Rect] | None,
    reason: PageReason,
    score_orientation: OrientationScorer,
) -> Page:
    try:
        from .ocr import recognise  # macOS-only; imported lazily

        import Vision  # noqa: F401
    except ImportError:
        return replace(_text_page(pg, number), reason=reason)  # no OCR here: keep the text layer

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
    tokens, mean, rotation = _best_orientation(png, rect, number, recognise, score_orientation)
    width, height = (pg.rect.width, pg.rect.height) if rotation == 0 else (pg.rect.height, pg.rect.width)
    return Page(
        number,
        width,
        height,
        tokens,
        "ocr",
        ocr_confidence=mean,
        dpi=dpi,
        reason=reason,
        rotation=rotation,
    )


def _best_orientation(
    png: bytes,
    rect: pymupdf.Rect,
    number: int,
    recognise: Recogniser,
    score_orientation: OrientationScorer,
) -> tuple[list[Token], float, int]:
    """OCR the image in each candidate rotation and keep the best: the highest
    `score_orientation`, then the highest mean confidence. Tokens come back
    upright; for a rotated scan they are in a frame of the image's height by
    its width."""
    best = None
    for rotation in CANDIDATE_ROTATIONS:
        if rotation == 0:
            upright, frame = png, rect
        else:
            upright, frame = _turn_upright(png, rect, rotation), pymupdf.Rect(0, 0, rect.height, rect.width)
        tokens = recognise(upright, frame, number)
        confidences = [t.confidence for t in tokens if t.confidence is not None]
        mean = sum(confidences) / len(confidences) if confidences else 0.0
        score = (*score_orientation(tokens, frame), mean)
        if best is None or score > best[0]:
            best = (score, tokens, mean, rotation)
    return best[1], best[2], best[3]


def _turn_upright(png: bytes, rect: pymupdf.Rect, rotation: int) -> bytes:
    """The PNG turned back from content printed `rotation` degrees clockwise,
    at the same pixel density."""
    pixel_width = pymupdf.Pixmap(png).width
    scale = pixel_width / rect.width
    turned = pymupdf.open()
    page = turned.new_page(width=rect.height, height=rect.width)
    page.insert_image(page.rect, stream=png, rotate=rotation)  # counter-clockwise
    return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png")
