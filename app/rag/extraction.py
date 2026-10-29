"""Extract text from uploaded files: PDFs, images, plain text.

Handles three cases:
  - Plain text files (.txt, .md): read directly.
  - PDFs with extractable text: pypdf.
  - Image files OR scanned PDFs (pypdf returns nothing): a vision LLM.

Vision OCR is provider-aware: it routes by the active LLM_PROVIDER and uses
settings.active_vision_model, so the vision model shifts with the provider the
same way the agent model and ensemble models do.
  - groq:       Groq vision model        (settings.groq_vision_model)
  - openrouter: OpenRouter vision model   (settings.openrouter_vision_model)
                via the OpenAI client pointed at OpenRouter's base URL
  - ollama:     local vision model        (settings.ollama_vision_model) via the
                ollama client — requires `ollama pull llama3.2-vision`.

Groq and OpenRouter share the OpenAI chat-completions image-message format, so
their payloads are identical bar the client/base-url/model. Ollama uses its own
`images` field. Each backend raises a clear RuntimeError when its key/model
isn't configured OR when the vision model returns no text, surfaced to the user
as a 503 by the route (instead of silently returning an empty string, which
previously made a failed OCR look like a successful-but-empty extraction).

Images in formats some vision APIs don't accept (webp, gif) are normalized to
PNG before the OCR call so every provider receives a format it understands.
"""
import base64
import io
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

# Generous limits for portfolio use; tighten in production.
MAX_FILE_BYTES = 20 * 1024 * 1024   # 20 MB
MAX_PDF_PAGES_FOR_VISION = 10        # don't OCR entire books

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".tsv"}
PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# Mimes vision providers reliably accept. Anything else is converted to PNG.
_SAFE_OCR_MIMES = {"image/png", "image/jpeg"}

# The OCR instruction is identical across providers.
_OCR_INSTRUCTION = (
    "Extract all text from this image. Preserve the original structure: keep "
    "headings, paragraphs, lists, and tables in their original layout. If a "
    "table is present, format it as a markdown table. Output only the extracted "
    "text, no commentary."
)


def _read_text(data: bytes, filename: str) -> str:
    """Decode a plain text file. Tries utf-8 then falls back to latin-1."""
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {filename} as text")


def _normalize_image_for_ocr(image_bytes: bytes, mime: str) -> tuple[bytes, str]:
    """Ensure the image is in a format every vision provider accepts.

    png/jpeg pass through untouched. Anything else (webp, gif, etc.) is decoded
    and re-encoded as PNG via Pillow. Returns (bytes, mime).
    """
    if mime in _SAFE_OCR_MIMES:
        return image_bytes, mime
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError(
            "Pillow not installed but needed to convert this image format. "
            "Run: pip install pillow"
        ) from e
    try:
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        log.info("normalized image %s -> image/png (%d -> %d bytes)",
                 mime, len(image_bytes), buf.tell())
        return buf.getvalue(), "image/png"
    except Exception as e:
        raise RuntimeError(f"Failed to convert image ({mime}) to PNG for OCR: {e}") from e


def _extract_pdf_text(data: bytes) -> str:
    """Extract text from a PDF using pypdf. Returns '' for scanned PDFs."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as e:
            log.warning("pypdf failed on page %d: %s", i, e)
            text = ""
        if text.strip():
            pages.append(f"--- Page {i + 1} ---\n{text}")
    return "\n\n".join(pages).strip()


def _pdf_pages_to_pngs(data: bytes, max_pages: int = MAX_PDF_PAGES_FOR_VISION) -> list[bytes]:
    """Rasterize a PDF's pages to PNG bytes for vision OCR.

    Uses pypdfium2 because it's pure Python (no Poppler install needed on Windows).
    """
    try:
        import pypdfium2 as pdfium
    except ImportError as e:
        raise RuntimeError(
            "pypdfium2 not installed. Run: pip install pypdfium2"
        ) from e

    pdf = pdfium.PdfDocument(io.BytesIO(data))
    n = min(len(pdf), max_pages)
    pngs: list[bytes] = []
    for i in range(n):
        page = pdf[i]
        # 150 DPI is a good balance: readable, not too huge.
        pil_image = page.render(scale=150 / 72).to_pil()
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG")
        pngs.append(buf.getvalue())
    return pngs


# ---------------------------------------------------------------------------
# Vision OCR backends (one per provider). Each takes raw image bytes + mime
# and returns extracted text, or raises RuntimeError if not configured or if
# the model returns no text. All read the model name from
# settings.active_vision_model so the model shifts with LLM_PROVIDER.
# ---------------------------------------------------------------------------

def _ocr_groq(image_bytes: bytes, mime: str) -> str:
    """OCR via Groq's vision model. Requires GROQ_API_KEY."""
    if not settings.groq_api_key:
        raise RuntimeError(
            "OCR via Groq requires GROQ_API_KEY in .env. Get a free key at "
            "https://console.groq.com/keys"
        )
    try:
        from groq import Groq
    except ImportError as e:
        raise RuntimeError("groq package not installed") from e

    client = Groq(api_key=settings.groq_api_key)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    model = settings.active_vision_model
    log.info("Groq OCR: model=%s mime=%s bytes=%d", model, mime, len(image_bytes))
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _OCR_INSTRUCTION},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }],
            temperature=0.0,
        )
    except Exception as e:
        raise RuntimeError(f"Groq vision call failed (model={model}): {e}") from e

    text = response.choices[0].message.content or ""
    log.info("Groq OCR returned %d chars", len(text))
    if not text.strip():
        raise RuntimeError(
            f"Groq vision model {model!r} returned no text for this image. "
            f"Verify it is vision-capable and the slug is current at "
            f"https://console.groq.com/docs/models"
        )
    return text


def _ocr_openrouter(image_bytes: bytes, mime: str) -> str:
    """OCR via an OpenRouter vision model.

    OpenRouter speaks the OpenAI protocol, so we use the openai client pointed
    at OpenRouter's base URL with the same image-message format Groq uses.
    Requires OPENROUTER_API_KEY and a vision-capable active_vision_model.
    """
    if not settings.openrouter_api_key:
        raise RuntimeError(
            "OCR via OpenRouter requires OPENROUTER_API_KEY in .env. Get a key "
            "at https://openrouter.ai/keys"
        )
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError(
            "openai package not installed. Run: pip install openai"
        ) from e

    default_headers = {}
    if settings.openrouter_site_url:
        default_headers["HTTP-Referer"] = settings.openrouter_site_url
    if settings.openrouter_app_name:
        default_headers["X-Title"] = settings.openrouter_app_name

    client = OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        default_headers=default_headers or None,
    )
    b64 = base64.b64encode(image_bytes).decode("ascii")
    model = settings.active_vision_model
    log.info("OpenRouter OCR: model=%s mime=%s bytes=%d", model, mime, len(image_bytes))
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _OCR_INSTRUCTION},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }],
            temperature=0.0,
        )
    except Exception as e:
        raise RuntimeError(f"OpenRouter vision call failed (model={model}): {e}") from e

    text = response.choices[0].message.content or ""
    log.info("OpenRouter OCR returned %d chars", len(text))
    if not text.strip():
        raise RuntimeError(
            f"OpenRouter vision model {model!r} returned no text for this image. "
            f"Verify it is vision-capable at https://openrouter.ai/models?q=vision"
        )
    return text


def _ocr_ollama(image_bytes: bytes, mime: str) -> str:
    """OCR via a local Ollama vision model.

    Requires a vision-capable model pulled into the Ollama container first:
    `ollama pull llama3.2-vision` (or whatever settings.ollama_vision_model names).
    Slow on CPU.

    Ollama's chat API takes images as a list of base64 strings on the message
    (NOT the OpenAI image_url format), so this backend builds the payload
    differently from the Groq/OpenRouter ones.
    """
    try:
        from ollama import Client
    except ImportError as e:
        raise RuntimeError(
            "ollama package not installed. Run: pip install ollama"
        ) from e

    b64 = base64.b64encode(image_bytes).decode("ascii")
    model = settings.active_vision_model
    client = Client(host=settings.ollama_base_url)
    log.info("Ollama OCR: model=%s mime=%s bytes=%d", model, mime, len(image_bytes))
    try:
        response = client.chat(
            model=model,
            messages=[{
                "role": "user",
                "content": _OCR_INSTRUCTION,
                "images": [b64],
            }],
            options={"temperature": 0.0},
        )
    except Exception as e:
        raise RuntimeError(
            f"Ollama vision OCR failed (is '{model}' pulled? "
            f"run `ollama pull {model}`): {e}"
        ) from e
    text = (response.get("message", {}) or {}).get("content", "") or ""
    log.info("Ollama OCR returned %d chars", len(text))
    if not text.strip():
        raise RuntimeError(
            f"Ollama vision model {model!r} returned no text for this image."
        )
    return text


def _ocr_image(image_bytes: bytes, mime: str = "image/png") -> str:
    """Provider-aware OCR dispatcher.

    Normalizes the image to a provider-safe format (PNG) first, then routes to
    the vision backend for the active LLM_PROVIDER. Strict per-provider: no
    silent fallback to a different provider. Raises a clear RuntimeError when
    the active provider has no usable vision config or returns no text, which
    the attachment route surfaces to the user as a 503.
    """
    image_bytes, mime = _normalize_image_for_ocr(image_bytes, mime)
    provider = settings.llm_provider.lower()
    if provider == "groq":
        return _ocr_groq(image_bytes, mime)
    if provider == "openrouter":
        return _ocr_openrouter(image_bytes, mime)
    if provider == "ollama":
        return _ocr_ollama(image_bytes, mime)
    raise RuntimeError(
        f"OCR is not supported for LLM_PROVIDER={provider!r}. "
        f"Use 'groq', 'openrouter', or 'ollama' (with a vision model pulled)."
    )


def extract_attachment(filename: str, data: bytes) -> dict:
    """Top-level dispatcher.

    Returns: {
      "text": extracted text,
      "method": which path was used,
      "pages_processed": int (for PDFs),
      "size_bytes": original file size,
    }
    """
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(
            f"File too large: {len(data) / 1e6:.1f} MB (max {MAX_FILE_BYTES / 1e6:.0f} MB)"
        )

    suffix = Path(filename).suffix.lower()
    result: dict = {"size_bytes": len(data), "pages_processed": 0}

    if suffix in TEXT_EXTENSIONS:
        result["text"] = _read_text(data, filename)
        result["method"] = "text"
        return result

    if suffix in PDF_EXTENSIONS:
        text = _extract_pdf_text(data)
        if text:
            result["text"] = text
            result["method"] = "pypdf"
            return result
        # Scanned PDF — fall back to vision.
        log.info("PDF has no extractable text, falling back to vision OCR")
        pages = _pdf_pages_to_pngs(data)
        if not pages:
            raise ValueError("PDF appears empty")
        page_texts = []
        for i, png in enumerate(pages):
            log.info("OCR page %d/%d via vision (%s)", i + 1, len(pages), settings.llm_provider)
            page_texts.append(f"--- Page {i + 1} ---\n{_ocr_image(png)}")
        result["text"] = "\n\n".join(page_texts)
        result["method"] = "pdf+vision"
        result["pages_processed"] = len(pages)
        return result

    if suffix in IMAGE_EXTENSIONS:
        mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else f"image/{suffix.lstrip('.')}"
        result["text"] = _ocr_image(data, mime=mime)
        result["method"] = "vision"
        result["pages_processed"] = 1
        return result

    raise ValueError(
        f"Unsupported file type: {suffix}. "
        f"Allowed: {sorted(TEXT_EXTENSIONS | PDF_EXTENSIONS | IMAGE_EXTENSIONS)}"
    )
