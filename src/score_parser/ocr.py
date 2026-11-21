"""Apple Vision text OCR. macOS only: never import this from the text-layer path."""

import pymupdf

from .instruments import vocabulary
from .models import Token


def recognise(png: bytes, rect: pymupdf.Rect, page: int) -> list[Token]:
    """OCR a PNG that covers `rect` on the page; return word tokens in page coordinates."""
    import Foundation
    import Vision

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(False)
    request.setCustomWords_(vocabulary())
    data = Foundation.NSData.dataWithBytes_length_(png, len(png))
    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, {})
    ok, err = handler.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError(f"Vision OCR failed: {err}")

    tokens = []
    for obs in request.results() or []:
        cand = obs.topCandidates_(1)[0]
        text = str(cand.string())
        pos = 0
        for word in text.split():
            start = text.index(word, pos)
            pos = start + len(word)
            box_obs, _ = cand.boundingBoxForRange_error_((start, len(word)), None)
            if box_obs is None:
                continue
            b = box_obs.boundingBox()  # normalised, origin bottom-left
            x0 = rect.x0 + b.origin.x * rect.width
            x1 = rect.x0 + (b.origin.x + b.size.width) * rect.width
            y0 = rect.y0 + (1 - b.origin.y - b.size.height) * rect.height
            y1 = rect.y0 + (1 - b.origin.y) * rect.height
            tokens.append(Token(word, x0, y0, x1, y1, page, "", "ocr", float(cand.confidence())))
    return tokens
