"""Real image conversion and PDF handling in app/rag/extraction.py (Pillow, pypdf, pypdfium2)."""
import io

import pytest
from PIL import Image

from app.rag.extraction import (
    _extract_pdf_text,
    _normalize_image_for_ocr,
    _pdf_pages_to_pngs,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _pdf_with_text(text: str) -> bytes:
    """Minimal single-page PDF whose page content draws `text`."""
    stream = f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)
    return out


def _image_bytes(fmt: str, mode: str = "RGB") -> bytes:
    buf = io.BytesIO()
    Image.new(mode, (8, 8), "red" if mode == "RGB" else 0).save(buf, format=fmt)
    return buf.getvalue()


@pytest.mark.parametrize(("fmt", "mime"), [("WEBP", "image/webp"), ("GIF", "image/gif")])
def test_other_image_formats_are_converted_to_png(fmt, mime):
    data, out_mime = _normalize_image_for_ocr(_image_bytes(fmt), mime)
    assert out_mime == "image/png"
    assert data.startswith(PNG_MAGIC)
    assert Image.open(io.BytesIO(data)).size == (8, 8)


def test_palette_and_alpha_images_are_converted_to_rgb():
    buf = io.BytesIO()
    Image.new("RGBA", (4, 4), (255, 0, 0, 128)).save(buf, format="WEBP")
    data, _ = _normalize_image_for_ocr(buf.getvalue(), "image/webp")
    assert Image.open(io.BytesIO(data)).mode == "RGB"


def test_png_and_jpeg_pass_through_untouched():
    png = _image_bytes("PNG")
    assert _normalize_image_for_ocr(png, "image/png") == (png, "image/png")


def test_corrupt_image_is_a_clean_runtime_error():
    with pytest.raises(RuntimeError, match="Failed to convert image"):
        _normalize_image_for_ocr(b"not an image", "image/webp")


def test_pdf_text_is_extracted():
    assert "Hello CloudNest" in _extract_pdf_text(_pdf_with_text("Hello CloudNest"))


def test_pdf_pages_rasterize_to_png():
    pngs = _pdf_pages_to_pngs(_pdf_with_text("Hello"))
    assert len(pngs) == 1 and pngs[0].startswith(PNG_MAGIC)
    assert Image.open(io.BytesIO(pngs[0])).width > 100
