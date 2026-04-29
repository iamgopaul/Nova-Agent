from __future__ import annotations

import base64
import io
import mimetypes
from pathlib import Path
from typing import Callable, Iterable
import zipfile
import tempfile
import subprocess
import re
from PIL import ImageOps, ImageFilter
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import time

from PIL import Image
from pypdf import PdfReader

from config.settings import Settings
from gaaia.server.schemas import AttachmentInput
from gaaia.services.model_client import get_model_client

_TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".yaml", ".yml", ".log", ".py", ".js", ".ts", ".html", ".xml"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
_BINARY_EXTENSIONS = {".zip", ".7z", ".rar", ".gz", ".tar", ".tgz", ".bz2", ".xz", ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
_MAX_ATTACHMENT_CHARS = 12000
_MAX_TEXT_CHARS = 4000
_MAX_ZIP_FILES = 20
_MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES = 8 * 1024 * 1024
_MAX_ZIP_ENTRY_BYTES = 512 * 1024
_IMAGE_ANALYSIS_UNAVAILABLE_MARKER = "__IMAGE_ANALYSIS_UNAVAILABLE__"
_VISION_TIMEOUT_SECONDS = 20
_OCR_TIMEOUT_SECONDS = 4


async def build_attachment_context(
    attachments: Iterable[AttachmentInput],
    settings: Settings,
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    parts: list[str] = []
    total_chars = 0
    image_index = 0

    for attachment in attachments:
        name = attachment.name or "attachment"
        _emit_attachment_step(progress_callback, f"Inspecting attachment: {name}")
        raw = _decode_attachment_bytes(attachment.data)
        if not raw:
            _emit_attachment_step(progress_callback, f"Attachment is empty: {name}")
            parts.append(f"- {name}: empty file")
            continue

        mime = attachment.content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
        suffix = Path(name).suffix.lower()

        if mime.startswith("text/") or suffix in _TEXT_EXTENSIONS:
            _emit_attachment_step(progress_callback, f"Reading text attachment: {name}")
            content = _decode_text(raw)
            content = _limit_text(content, _MAX_TEXT_CHARS)
            parts.append(_format_text_attachment(name, mime, content))
            total_chars += len(content)
            _emit_attachment_step(progress_callback, f"Text extraction complete: {name}")
            continue

        if mime == "application/pdf" or suffix == ".pdf":
            _emit_attachment_step(progress_callback, f"Extracting PDF text: {name}")
            content = _extract_pdf_text(raw)
            content = _limit_text(content, _MAX_TEXT_CHARS)
            parts.append(_format_text_attachment(name, mime, content or "[No text could be extracted from the PDF.]"))
            total_chars += len(content)
            _emit_attachment_step(progress_callback, f"PDF extraction complete: {name}")
            continue

        if mime.startswith("image/") or suffix in _IMAGE_EXTENSIONS:
            image_index += 1
            _emit_attachment_step(progress_callback, f"Starting image analysis: {name}")
            description = _describe_image(name, mime, raw, settings, progress_callback=progress_callback)
            # Keep prompt neutral; avoid filename leakage that can cause guessing.
            parts.append(f"- attached_image_{image_index} ({mime}): {description}")
            total_chars += len(description)
            _emit_attachment_step(progress_callback, f"Image processing complete: {name}")
            continue

        if suffix == ".zip" or mime in {"application/zip", "application/x-zip-compressed"}:
            _emit_attachment_step(progress_callback, f"Opening zip archive: {name}")
            zip_context = _extract_zip_context(name, raw, progress_callback=progress_callback)
            parts.append(zip_context)
            total_chars += len(zip_context)
            _emit_attachment_step(progress_callback, f"Archive processing complete: {name}")
            continue

        if suffix in _BINARY_EXTENSIONS or mime in {
            "application/zip",
            "application/x-zip-compressed",
            "application/x-7z-compressed",
            "application/x-rar-compressed",
            "application/gzip",
            "application/x-tar",
        }:
            parts.append(
                f"- {name} ({mime}): binary archive/document attached; direct text extraction is not supported for this file type."
            )
            _emit_attachment_step(progress_callback, f"Unsupported binary attachment type: {name}")
            continue

        fallback_text = _decode_text(raw)
        if fallback_text.strip() and not _looks_like_binary(raw):
            _emit_attachment_step(progress_callback, f"Attempting fallback text read: {name}")
            fallback_text = _limit_text(fallback_text, _MAX_TEXT_CHARS)
            parts.append(_format_text_attachment(name, mime, fallback_text))
            total_chars += len(fallback_text)
            _emit_attachment_step(progress_callback, f"Fallback read complete: {name}")
        else:
            parts.append(f"- {name} ({mime}): binary file attached; unable to extract text directly.")
            _emit_attachment_step(progress_callback, f"No readable text found: {name}")

        if total_chars >= _MAX_ATTACHMENT_CHARS:
            parts.append("- Attachment context truncated to keep the prompt manageable.")
            _emit_attachment_step(progress_callback, "Attachment context reached prompt limit")
            break

    return "\n".join(parts)


def _format_text_attachment(name: str, mime: str, content: str) -> str:
    text = content.strip() or "[No readable text found.]"
    return f"- {name} ({mime}):\n{text}"


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _decode_attachment_bytes(data: str) -> bytes:
    try:
        return base64.b64decode(data.encode("ascii"), validate=True)
    except Exception:
        return b""


def _limit_text(text: str, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


def _looks_like_binary(raw: bytes) -> bool:
    if not raw:
        return False
    sample = raw[:2048]
    if b"\x00" in sample:
        return True
    control_bytes = sum(1 for b in sample if b < 9 or (13 < b < 32))
    return (control_bytes / max(len(sample), 1)) > 0.25


def _extract_zip_context(
    name: str,
    raw: bytes,
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except Exception:
        _emit_attachment_step(progress_callback, f"Failed to open zip archive: {name}")
        return f"- {name} (application/zip): invalid or unreadable zip archive."

    try:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if not infos:
            _emit_attachment_step(progress_callback, f"Zip archive is empty: {name}")
            return f"- {name} (application/zip): archive is empty."

        lines: list[str] = [f"- {name} (application/zip): extracted context from archive entries:"]
        processed = 0
        total_uncompressed = 0
        _emit_attachment_step(progress_callback, f"Scanning {len(infos)} zip entries")

        for info in infos:
            _emit_attachment_step(progress_callback, f"Reading zip entry: {info.filename}")
            if processed >= _MAX_ZIP_FILES:
                lines.append("  - [truncated] Too many files in archive; only the first entries were processed.")
                _emit_attachment_step(progress_callback, "Zip entry limit reached")
                break

            if total_uncompressed >= _MAX_ZIP_TOTAL_UNCOMPRESSED_BYTES:
                lines.append("  - [truncated] Archive size limit reached while extracting text.")
                _emit_attachment_step(progress_callback, "Zip size limit reached")
                break

            if info.flag_bits & 0x1:
                lines.append(f"  - {info.filename}: encrypted entry skipped.")
                _emit_attachment_step(progress_callback, f"Skipped encrypted entry: {info.filename}")
                continue

            if info.file_size > _MAX_ZIP_ENTRY_BYTES:
                lines.append(f"  - {info.filename}: skipped (file too large for inline analysis).")
                total_uncompressed += info.file_size
                _emit_attachment_step(progress_callback, f"Skipped large entry: {info.filename}")
                continue

            try:
                content_bytes = archive.read(info)
            except Exception:
                lines.append(f"  - {info.filename}: read failed.")
                _emit_attachment_step(progress_callback, f"Failed reading entry: {info.filename}")
                continue

            total_uncompressed += len(content_bytes)
            entry_suffix = Path(info.filename).suffix.lower()
            if entry_suffix not in _TEXT_EXTENSIONS and _looks_like_binary(content_bytes):
                lines.append(f"  - {info.filename}: binary or unsupported file type skipped.")
                _emit_attachment_step(progress_callback, f"Skipped binary entry: {info.filename}")
                continue

            content = _limit_text(_decode_text(content_bytes), _MAX_TEXT_CHARS)
            if not content.strip() or _looks_like_binary(content_bytes):
                lines.append(f"  - {info.filename}: no readable text extracted.")
                _emit_attachment_step(progress_callback, f"No readable text in entry: {info.filename}")
                continue

            lines.append(f"  - {info.filename}:\n{content}")
            processed += 1
            _emit_attachment_step(progress_callback, f"Extracted text from entry: {info.filename}")

        _emit_attachment_step(progress_callback, f"Zip extraction complete: {name}")
        return "\n".join(lines)
    finally:
        archive.close()


def _emit_attachment_step(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is None:
        return
    try:
        callback(message)
    except Exception:
        return


def _extract_pdf_text(raw: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(raw))
    except Exception:
        return ""

    pages: list[str] = []
    for page in reader.pages[:8]:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n\n".join(page.strip() for page in pages if page.strip())


def _describe_image(
    name: str,
    mime: str,
    raw: bytes,
    settings: Settings,
    progress_callback: Callable[[str], None] | None = None,
) -> str:
    show_progress = bool(settings.model.get("image_analysis_progress", True))
    started_at = time.perf_counter()
    _progress(show_progress, f"start {name} ({mime})", callback=progress_callback)

    try:
        with Image.open(io.BytesIO(raw)) as image:
            width, height = image.size
            mode = image.mode
            grayscale = image.convert("L")
            extrema = grayscale.getextrema()
            contrast = float(extrema[1] - extrema[0]) if extrema else 0.0
    except Exception:
        width, height, mode, contrast = 0, 0, "unknown", 0.0
    _progress(show_progress, f"image prepared {width}x{height} {mode}", callback=progress_callback)

    vision_model = settings.model.get("vision_model", "llama3.2-vision:11b")
    high_accuracy = bool(settings.model.get("image_high_accuracy_mode", True))
    ocr_enabled = bool(settings.model.get("image_ocr_enabled", True))

    scene_summary = ""
    vision_text = ""
    ocr_text = ""

    if not vision_model:
        _progress(show_progress, "vision model unavailable", callback=progress_callback)
        if ocr_enabled:
            _progress(show_progress, "ocr pass", callback=progress_callback)
            ocr_text = _ocr_text_extract(raw)
            _progress(show_progress, "scoring and formatting", callback=progress_callback)
            report = _format_image_report(
                scene_summary="",
                vision_text="",
                ocr_text=ocr_text,
                width=width,
                height=height,
                mode=mode,
                contrast=contrast,
                high_accuracy=high_accuracy,
            )
            if report:
                return report
        return f"{_IMAGE_ANALYSIS_UNAVAILABLE_MARKER} Image attached, but image analysis is not enabled right now."

    try:
        client = get_model_client(host=settings.ollama_host)
        image_b64 = base64.b64encode(raw).decode("ascii")
        _progress(show_progress, "vision summary pass", callback=progress_callback)
        scene_summary = _vision_scene_summary(client, vision_model, image_b64)
        if high_accuracy:
            _progress(show_progress, "vision text pass", callback=progress_callback)
            vision_text = _vision_text_extract(client, vision_model, image_b64)
            if ocr_enabled:
                _progress(show_progress, "ocr pass", callback=progress_callback)
                ocr_text = _ocr_text_extract(raw)
            else:
                _progress(show_progress, "ocr skipped (disabled)", callback=progress_callback)

        _progress(show_progress, "scoring and formatting", callback=progress_callback)
        report = _format_image_report(
            scene_summary=scene_summary,
            vision_text=vision_text,
            ocr_text=ocr_text,
            width=width,
            height=height,
            mode=mode,
            contrast=contrast,
            high_accuracy=high_accuracy,
        )
        if report:
            elapsed = time.perf_counter() - started_at
            _progress(show_progress, f"done in {elapsed:.1f}s", callback=progress_callback)
            return report
    except Exception:
        _progress(show_progress, "analysis failed; using fallback", callback=progress_callback)
        if ocr_enabled and not ocr_text:
            ocr_text = _ocr_text_extract(raw)
            report = _format_image_report(
                scene_summary="",
                vision_text=vision_text,
                ocr_text=ocr_text,
                width=width,
                height=height,
                mode=mode,
                contrast=contrast,
                high_accuracy=high_accuracy,
            )
            if report:
                return report

    return f"{_IMAGE_ANALYSIS_UNAVAILABLE_MARKER} Image attached, but I could not analyze it automatically right now."


def _progress(enabled: bool, message: str, callback: Callable[[str], None] | None = None) -> None:
    if not enabled:
        return
    print(f"[GAIA][Image] {message}", flush=True)
    if callback is not None:
        try:
            callback(message)
        except Exception:
            pass


def _vision_scene_summary(client, model: str, image_b64: str) -> str:
    prompt = (
        "Describe this image in 2-4 short sentences. "
        "State the main subject, objects, and actions. "
        "Avoid guessing identities if uncertain."
    )
    return _vision_chat_with_timeout(client, model, image_b64, prompt)


def _vision_text_extract(client, model: str, image_b64: str) -> str:
    prompt = (
        "Extract all visible text from this image exactly as written. "
        "Preserve line breaks. If no readable text, respond with NONE."
    )
    content = _vision_chat_with_timeout(client, model, image_b64, prompt)
    text = content.strip()
    if text.upper() == "NONE":
        return ""
    if "no visible text" in text.lower() or "no readable text" in text.lower():
        return ""
    return text


def _vision_chat_with_timeout(
    client,
    model: str,
    image_b64: str,
    prompt: str,
    timeout_seconds: int = _VISION_TIMEOUT_SECONDS,
) -> str:
    def _run() -> str:
        return client.chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }
            ],
        ).strip()

    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(_run)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeout:
        # Do not wait for a potentially stuck network call.
        future.cancel()
        return ""
    except Exception:
        return ""
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _ocr_text_extract(raw: bytes) -> str:
    tesseract_path = _which_tesseract()
    if not tesseract_path:
        return ""

    candidates = _build_ocr_candidates(raw)
    best_text = ""
    best_score = -1

    for candidate in candidates[:2]:
        for psm in (6, 11):
            text = _run_tesseract(tesseract_path, candidate, psm)
            score = _ocr_text_score(text)
            if score > best_score:
                best_score = score
                best_text = text

    return best_text if _is_meaningful_text(best_text) else ""


def _build_ocr_candidates(raw: bytes) -> list[bytes]:
    try:
        with Image.open(io.BytesIO(raw)) as img:
            base = img.convert("RGB")
            gray = ImageOps.grayscale(base)

            # Candidate 1: original bytes (some captures OCR better as-is)
            out: list[bytes] = [raw]

            # Candidate 2: grayscale + autocontrast + sharpen + upscale
            enhanced = ImageOps.autocontrast(gray)
            enhanced = enhanced.filter(ImageFilter.SHARPEN)
            enhanced = enhanced.resize(
                (max(1, enhanced.width * 2), max(1, enhanced.height * 2)),
                Image.Resampling.LANCZOS,
            )
            out.append(_image_to_png_bytes(enhanced))

            # Candidate 3: high-contrast threshold pass
            threshold = enhanced.point(lambda p: 255 if p > 165 else 0)
            out.append(_image_to_png_bytes(threshold))

            return out
    except Exception:
        return [raw]


def _image_to_png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _run_tesseract(tesseract_path: str, image_bytes: bytes, psm: int) -> str:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tmp:
        tmp.write(image_bytes)
        tmp.flush()
        try:
            proc = subprocess.run(
                [tesseract_path, tmp.name, "stdout", "--psm", str(psm)],
                capture_output=True,
                text=True,
                check=False,
                timeout=_OCR_TIMEOUT_SECONDS,
            )
        except Exception:
            return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _ocr_text_score(text: str) -> int:
    if not text:
        return 0
    tokens = _tokenize(text)
    alnum_chars = sum(1 for ch in text if ch.isalnum())
    return len(tokens) * 6 + min(alnum_chars, 300)


def _which_tesseract() -> str | None:
    proc = subprocess.run("command -v tesseract", shell=True, capture_output=True, text=True)
    path = (proc.stdout or "").strip()
    return path or None


def _format_image_report(
    scene_summary: str,
    vision_text: str,
    ocr_text: str,
    width: int,
    height: int,
    mode: str,
    contrast: float,
    high_accuracy: bool,
) -> str:
    cleaned_scene = scene_summary.strip()
    cleaned_vision_text = vision_text.strip()
    cleaned_ocr_text = ocr_text.strip()

    if not cleaned_scene and not cleaned_vision_text and not cleaned_ocr_text:
        return ""

    confidence = _compute_confidence(
        scene_summary=cleaned_scene,
        vision_text=vision_text,
        ocr_text=ocr_text,
        contrast=contrast,
        width=width,
        height=height,
        high_accuracy=high_accuracy,
    )

    lines = [
        f"Image analysis ({width}x{height}, {mode})",
        f"Confidence: {confidence}",
    ]

    if cleaned_scene:
        lines.append(f"Scene summary: {cleaned_scene}")
    elif cleaned_ocr_text:
        lines.append("Scene summary: Vision summary unavailable; OCR text extracted.")
    else:
        lines.append("Scene summary: Vision summary unavailable.")

    if high_accuracy:
        if vision_text:
            lines.append(f"Vision text read: {_shorten_inline_text(vision_text, 500)}")
        else:
            lines.append("Vision text read: none")

        if ocr_text:
            lines.append(f"OCR text read: {_shorten_inline_text(ocr_text, 500)}")
        else:
            lines.append("OCR text read: unavailable or none")

    return " ".join(lines)


def _compute_confidence(
    scene_summary: str,
    vision_text: str,
    ocr_text: str,
    contrast: float,
    width: int,
    height: int,
    high_accuracy: bool,
) -> str:
    score = 0
    vision_good = _is_meaningful_text(vision_text)
    ocr_good = _is_meaningful_text(ocr_text)

    if scene_summary:
        score += 1

    if width * height >= 640 * 480:
        score += 1

    if contrast >= 40:
        score += 1
    elif contrast < 20:
        score -= 1

    if high_accuracy:
        if vision_good:
            score += 1
        if ocr_good:
            score += 1
        if vision_good and ocr_good and _text_overlap_ratio(vision_text, ocr_text) >= 0.45:
            score += 2
        if vision_good and ocr_good and _text_overlap_ratio(vision_text, ocr_text) < 0.20:
            score -= 1

    if (not vision_good and not ocr_good) and (contrast < 28 or width * height < 700 * 400):
        score -= 1

    if score >= 6:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


def _text_overlap_ratio(a: str, b: str) -> float:
    a_tokens = set(_tokenize(a))
    b_tokens = set(_tokenize(b))
    if not a_tokens or not b_tokens:
        return 0.0
    inter = len(a_tokens.intersection(b_tokens))
    union = len(a_tokens.union(b_tokens))
    return inter / max(union, 1)


def _tokenize(text: str) -> list[str]:
    return [tok for tok in re.findall(r"[A-Za-z0-9']+", text.lower()) if len(tok) >= 2]


def _shorten_inline_text(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _is_meaningful_text(text: str) -> bool:
    normalized = " ".join(text.split())
    if not normalized:
        return False
    if len(normalized) < 8:
        return False
    tokens = _tokenize(normalized)
    if len(tokens) < 2:
        return False
    alnum = sum(1 for ch in normalized if ch.isalnum())
    punct = sum(1 for ch in normalized if not ch.isalnum() and not ch.isspace())
    if alnum == 0:
        return False
    # Discard OCR garbage dominated by symbols/noise.
    if punct > alnum:
        return False
    return True