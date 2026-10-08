"""Read uploaded travel files and fill missing booking details.

Image text uses Tesseract when it is installed, then Windows OCR. A booking
number found in the file is written onto the matching stay.

Needs: REQ-006, SPEC-006, IMPL-006, TEST-020
"""

from __future__ import annotations

import io
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytesseract  # type: ignore[import-untyped]
from PIL import Image

logger = logging.getLogger(__name__)

_NAME_SKIP = frozenset({"hotel", "resort", "apartments", "apartment", "holiday", "holidays"})
_MIN_REFERENCE_LENGTH = 5
_MIN_OCR_WIDTH = 1400
_KEYWORD_REFERENCE = re.compile(
    r"(?:confirmation|reservation|booking|reference|conf|pnr|ref)"
    r"(?:\s*(?:number|no\.?|num|#|code))?"
    r"\s*[:.#-]?\s*([A-Z0-9][A-Z0-9-]{3,})",
    re.IGNORECASE,
)
_CODE_REFERENCE = re.compile(r"\b([A-Z]{1,5}\d{4,})\b")
_NUMBER_REFERENCE = re.compile(r"\b(\d{6,10})\b")
_PHONE_TEXT = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
_OCR_SCRIPT_PATH = Path(__file__).with_name("windows_ocr.ps1")


def image_text(payload: bytes) -> str:
    """Read text from an uploaded image.

    Args:
        payload: Raw image bytes.

    Returns:
        Extracted text, or an empty string when nothing could be read.

    Needs: REQ-006, TEST-020
    """

    text = _tesseract_text(payload)
    if text:
        return text
    return _windows_ocr_text(payload)


def apply_missing_booking_details(
    plan: dict[str, Any],
    raw_text: str,
    filename: str = "",
) -> list[str]:
    """Copy a booking number from scanned text onto the matching stay.

    Args:
        plan: Trip payload. Accommodation rows may be updated in place.
        raw_text: Text read from the uploaded file.
        filename: Original file name, used when the photo name names the stay.

    Returns:
        Short messages describing each booking number that was filled in.

    Needs: REQ-006, SPEC-006, TEST-020
    """

    blob = "\n".join(part for part in (filename, raw_text) if str(part).strip())
    if not blob.strip():
        return []
    stays = [
        booking
        for booking in plan.get("booking_items") or []
        if booking.get("category") in {"Accommodation", "Caravan stand"}
        and not str(booking.get("reference") or "").strip()
    ]
    mentioned = [
        booking
        for booking in stays
        if _mentions_stay(blob, str(booking.get("name") or ""))
    ]
    if len(mentioned) == 1:
        return _fill_reference(mentioned[0], _reference_in_text(blob))
    messages: list[str] = []
    for booking in mentioned:
        window = _window_around_name(blob, booking)
        messages.extend(_fill_reference(booking, _reference_in_text(window)))
    return messages


def _fill_reference(booking: dict[str, Any], reference: str) -> list[str]:
    """Store one booking number and describe the change."""
    if not reference:
        return []
    booking["reference"] = reference
    name = str(booking.get("name") or "Stay")
    return [f"Added booking number {reference} to {name}."]


def _reference_in_text(text: str) -> str:
    """Return the first plausible booking number in ``text``."""
    keyword = _KEYWORD_REFERENCE.search(text)
    if keyword and _plausible_reference(keyword.group(1)):
        return keyword.group(1)
    without_phones = _PHONE_TEXT.sub(" ", text)
    for pattern in (_CODE_REFERENCE, _NUMBER_REFERENCE):
        for match in pattern.finditer(without_phones):
            if _plausible_reference(match.group(1)):
                return match.group(1)
    return ""


def _plausible_reference(value: str) -> bool:
    """True when a token looks like a booking number rather than a year or postcode."""
    token = value.strip(" .-")
    if len(token) < _MIN_REFERENCE_LENGTH or re.fullmatch(r"20\d{2}", token):
        return False
    return not bool(re.fullmatch(r"0\d{8,}", token))


def _mentions_stay(blob: str, name: str) -> bool:
    """True when the file name or text is about this stay."""
    tokens = _name_tokens(name)
    if not tokens:
        return False
    lowered = blob.lower()
    hits = sum(1 for token in tokens if token in lowered)
    return hits >= min(2, len(tokens))


def _name_tokens(name: str) -> set[str]:
    """Distinctive words from a stay name."""
    words = re.findall(r"[a-z0-9]{5,}", name.lower())
    return {word for word in words if word not in _NAME_SKIP}


def _window_around_name(blob: str, booking: dict[str, Any]) -> str:
    """Return the part of the scan closest to this stay's name."""
    lowered = blob.lower()
    positions = [lowered.find(token) for token in _name_tokens(str(booking.get("name") or ""))]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return blob
    anchor = min(positions)
    return blob[max(0, anchor - 500) : anchor + 500]


def _tesseract_text(payload: bytes) -> str:
    """Read an image with Tesseract when the engine is installed."""
    try:
        image = Image.open(io.BytesIO(payload))
        return str(pytesseract.image_to_string(image)).strip()
    except (OSError, RuntimeError, pytesseract.TesseractError, pytesseract.TesseractNotFoundError):
        return ""


def _windows_ocr_text(payload: bytes) -> str:
    """Read an image with the Windows OCR engine."""
    image_path = _prepare_ocr_image(payload)
    if image_path is None:
        return ""
    try:
        completed = subprocess.run(  # noqa: S603
            ["powershell", "-NoProfile", "-File", str(_OCR_SCRIPT_PATH)],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env={**os.environ, "TRIP_OCR_IMAGE": str(image_path)},
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("Windows OCR could not read an uploaded image")
        return ""
    finally:
        image_path.unlink(missing_ok=True)
    if completed.returncode != 0:
        logger.warning("Windows OCR failed", extra={"returncode": completed.returncode})
        return ""
    return completed.stdout.strip()


def _prepare_ocr_image(payload: bytes) -> Path | None:
    """Save a larger PNG for OCR. Small screenshots are scaled up first."""
    try:
        image = Image.open(io.BytesIO(payload)).convert("RGB")
    except OSError:
        return None
    if image.width < _MIN_OCR_WIDTH:
        image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
    descriptor, name = tempfile.mkstemp(suffix=".png")
    os.close(descriptor)
    path = Path(name)
    image.save(path, "PNG")
    return path
