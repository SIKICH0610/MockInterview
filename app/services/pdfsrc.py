"""Question PDFs: render pages to pictures, cut out a region, read the text in it.

A selection ("rect") is four fractions of the page as shown: x0,y0,x1,y1 with
(0,0) the top-left corner, so it does not depend on the preview size.
Text is read from the PDF's own text layer (Word / Canva exports); scanned PDFs
have none — the AI reading in phase 3 covers those.
"""

import io
import threading
from collections import OrderedDict

import pypdfium2 as pdfium
from PIL import Image

MAX_PDF_BYTES = 60 * 1024 * 1024
PREVIEW_WIDTH = 1100  # px, page shown in the viewer
CROP_PAGE_WIDTH = 2400  # px, page rendered at this width before cutting (sharp crops)

_lock = threading.Lock()  # pdfium is not thread-safe
_cache = OrderedDict()  # pdf id -> bytes (a few recent PDFs)


def is_pdf(data):
    return data[:5] == b"%PDF-"


def page_count(data):
    with _lock:
        doc = pdfium.PdfDocument(data)
        try:
            return len(doc)
        finally:
            doc.close()


def remember(pid, data):
    _cache[pid] = data
    _cache.move_to_end(pid)
    while len(_cache) > 4:
        _cache.popitem(last=False)


def cached(pid):
    if pid in _cache:
        _cache.move_to_end(pid)
        return _cache[pid]
    return None


def parse_rect(text):
    """'0.1,0.2,0.5,0.6' -> (x0, y0, x1, y1) clamped to the page, or None."""
    try:
        x0, y0, x1, y1 = (min(1.0, max(0.0, float(v))) for v in str(text).split(","))
    except (TypeError, ValueError):
        return None
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    if x1 - x0 < 0.01 or y1 - y0 < 0.01:
        return None
    return (x0, y0, x1, y1)


def _render(data, page_no, width):
    doc = pdfium.PdfDocument(data)
    try:
        if not 1 <= page_no <= len(doc):
            raise ValueError("no such page")
        page = doc[page_no - 1]
        w, _h = page.get_size()
        img = page.render(scale=width / w).to_pil().convert("RGB")
        page.close()
        return img
    finally:
        doc.close()


def page_jpeg(data, page_no, width=PREVIEW_WIDTH):
    with _lock:
        img = _render(data, page_no, width)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82, optimize=True)
    return buf.getvalue()


def crop_image(data, page_no, rect):
    """The selected region as a picture -> (bytes, mime). PNG keeps line drawings
    crisp; large photo-like crops fall back to JPEG."""
    with _lock:
        img = _render(data, page_no, CROP_PAGE_WIDTH)
    W, H = img.size
    x0, y0, x1, y1 = rect
    part = img.crop((round(x0 * W), round(y0 * H), round(x1 * W), round(y1 * H)))
    buf = io.BytesIO()
    part.save(buf, "PNG", optimize=True)
    if buf.tell() <= 1_500_000:
        return buf.getvalue(), "image/png"
    buf = io.BytesIO()
    part.save(buf, "JPEG", quality=88, optimize=True)
    return buf.getvalue(), "image/jpeg"


def text_in(data, page_no, rect=None):
    """Text of the page, or of the characters whose centre lies inside rect."""
    with _lock:
        doc = pdfium.PdfDocument(data)
        try:
            if not 1 <= page_no <= len(doc):
                return ""
            page = doc[page_no - 1]
            w, h = page.get_size()
            tp = page.get_textpage()
            n = tp.count_chars()
            full = tp.get_text_range() if n else ""
            if len(full) != n:
                full = ""
            if rect is None:
                text = full
            else:
                x0, y0, x1, y1 = rect
                left, right, top, bottom = x0 * w, x1 * w, h - y0 * h, h - y1 * h
                runs, start, start_y, end_y, prev_y = [], None, 0.0, 0.0, 0.0
                for i in range(n):
                    l, b, r, t = tp.get_charbox(i)
                    if t - b < 1.0 or r - l < 0.2 or full[i:i + 1].isspace():
                        continue  # spaces / generated chars: they belong to the run around them
                    cx, cy = (l + r) / 2, (b + t) / 2
                    inside = left <= cx <= right and bottom <= cy <= top
                    if inside:
                        end_y = b
                    if inside and start is None:
                        start, start_y = i, b
                    elif not inside and start is not None:
                        runs.append((tp.get_text_range(start, i - start), start_y, prev_y))
                        start = None
                    prev_y = end_y
                if start is not None:
                    runs.append((tp.get_text_range(start, n - start), start_y, end_y))
                # pieces of one printed line (cut by the selection edge) stay on one line
                text, last_y = "", None
                for piece, y0_, y1_ in runs:
                    piece = piece.strip()
                    if not piece:
                        continue
                    if last_y is None:
                        text = piece
                    elif abs(y0_ - last_y) < 3:
                        text += " " + piece
                    else:
                        text += "\n" + piece
                    last_y = y1_
            tp.close()
            page.close()
        finally:
            doc.close()
    lines = [" ".join(line.split()) for line in text.replace("\r", "").split("\n")]
    return "\n".join(line for line in lines if line)
