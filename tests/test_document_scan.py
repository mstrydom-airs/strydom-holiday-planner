"""Tests for filling booking numbers from uploaded files.

Needs: REQ-006, SPEC-006, TEST-020
"""

from __future__ import annotations

import io
from pathlib import Path

import app as app_module
from PIL import Image
from trip_planner.services import document_scan
from trip_planner.services.document_scan import apply_missing_booking_details, image_text


def _stay(name: str, reference: str = "") -> dict[str, str]:
    return {
        "category": "Accommodation",
        "name": name,
        "reference": reference,
        "date": "2026-12-11",
        "address": "Coolangatta",
    }


def test_apply_missing_booking_details__photo_name_and_number__fills_that_stay() -> None:
    """Put the booking number from a beach-house photo onto that stay only.

    Pytest node:
    tests/test_document_scan.py::
    test_apply_missing_booking_details__photo_name_and_number__fills_that_stay
    Needs: REQ-006, TEST-020
    """

    # Arrange
    plan = {
        "booking_items": [
            _stay("Beach House Seaside Resort"),
            _stay("Legends Hotel Surfers Paradise"),
        ]
    }

    # Act
    messages = apply_missing_booking_details(
        plan,
        "Booking number: BH482910",
        "Beach house bookings.png",
    )

    # Assert
    assert messages == ["Added booking number BH482910 to Beach House Seaside Resort."]
    assert plan["booking_items"][0]["reference"] == "BH482910"
    assert plan["booking_items"][1]["reference"] == ""


def test_apply_missing_booking_details__saved_reference__is_left_unchanged() -> None:
    """Do not replace a booking number already stored on the stay.

    Pytest node:
    tests/test_document_scan.py::
    test_apply_missing_booking_details__saved_reference__is_left_unchanged
    Needs: REQ-006, TEST-020
    """

    # Arrange
    plan = {"booking_items": [_stay("Beach House Seaside Resort", "KEEPME")]}

    # Act
    messages = apply_missing_booking_details(plan, "Booking number: BH482910", "Beach house.png")

    # Assert
    assert messages == []
    assert plan["booking_items"][0]["reference"] == "KEEPME"


def test_import_image__booking_number__saves_it_on_the_matching_stay(  # type: ignore[no-untyped-def]
    flask_client, monkeypatch
) -> None:
    """Scan an image upload and store the booking number on the stay.

    Pytest node:
    tests/test_document_scan.py::
    test_import_image__booking_number__saves_it_on_the_matching_stay
    Needs: REQ-006, TEST-020
    """

    # Arrange
    created = flask_client.post(
        "/smart-trip/new",
        data={"title": "Dec XMAS 2026", "plan_category": "Hotel", "trip_kind": "weekend"},
    )
    trip_id = created.headers["Location"].rstrip("/").split("/")[-1]
    flask_client.post(
        f"/trip/weekend/{trip_id}",
        data={
            "title": "Dec XMAS 2026",
            "plan_category": "Hotel",
            "start_date": "2026-12-11",
            "end_date": "2026-12-18",
            "booking_category": ["Accommodation"],
            "booking_name": ["Beach House Seaside Resort"],
            "booking_date": ["2026-12-11"],
            "booking_end_date": ["2026-12-18"],
            "booking_address": ["52 Marine Parade, Coolangatta"],
        },
    )

    def fake_extract(upload) -> str:  # type: ignore[no-untyped-def]
        assert upload.filename == "Beach house bookings.png"
        return "Booking number: BH482910"

    monkeypatch.setattr(app_module, "_extract_document_text", fake_extract)

    # Act
    imported = flask_client.post(
        f"/trip/weekend/{trip_id}/import-itinerary",
        data={"note": "", "file": (io.BytesIO(b"png-bytes"), "Beach house bookings.png")},
        content_type="multipart/form-data",
    )
    page = flask_client.get(f"/trip/weekend/{trip_id}")

    # Assert
    assert imported.status_code == 200
    assert b"BH482910" in imported.data
    assert b"BH482910" in page.data


def test_apply_missing_booking_details__two_stays__keeps_each_number_with_its_name() -> None:
    """Match each booking number to the stay named beside it.

    Pytest node:
    tests/test_document_scan.py::
    test_apply_missing_booking_details__two_stays__keeps_each_number_with_its_name
    Needs: REQ-006, TEST-020
    """

    # Arrange
    plan = {
        "booking_items": [
            _stay("Beach House Seaside Resort"),
            _stay("Legends Hotel Surfers Paradise"),
        ]
    }
    gap = " " * 900
    text = (
        "Beach House Seaside Resort Booking number: BH111111"
        + gap
        + "Legends Hotel Surfers Paradise Booking number: LG222222"
    )

    # Act
    messages = apply_missing_booking_details(plan, text, "")

    # Assert
    assert plan["booking_items"][0]["reference"] == "BH111111"
    assert plan["booking_items"][1]["reference"] == "LG222222"
    assert len(messages) == 2


def test_apply_missing_booking_details__year_only__does_not_invent_a_number() -> None:
    """Ignore a year when the file has no booking number.

    Pytest node:
    tests/test_document_scan.py::
    test_apply_missing_booking_details__year_only__does_not_invent_a_number
    Needs: REQ-006, TEST-020
    """

    # Arrange
    plan = {"booking_items": [_stay("Beach House Seaside Resort"), _stay("Inn")]}

    # Act
    messages = apply_missing_booking_details(plan, "", "")
    year_messages = apply_missing_booking_details(plan, "Booking number: 2026", "Beach house.txt")

    # Assert
    assert messages == []
    assert year_messages == []
    assert plan["booking_items"][0]["reference"] == ""


def test_image_text__tesseract_reads_text__returns_that_text(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Use Tesseract text when the engine can read the image.

    Pytest node: tests/test_document_scan.py::test_image_text__tesseract_reads_text__returns_that_text
    Needs: REQ-006, TEST-020
    """

    # Arrange
    monkeypatch.setattr(document_scan.pytesseract, "image_to_string", lambda _image: " Booking number BH482910 ")

    # Act
    text = image_text(_png_bytes())

    # Assert
    assert text == "Booking number BH482910"


def test_image_text__tesseract_missing__uses_windows_ocr(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Fall back to Windows OCR when Tesseract is not installed.

    Pytest node: tests/test_document_scan.py::test_image_text__tesseract_missing__uses_windows_ocr
    Needs: REQ-006, TEST-020
    """

    # Arrange
    def fail(_image: object) -> str:
        raise document_scan.pytesseract.TesseractNotFoundError()

    class _Completed:
        returncode = 0
        stdout = " Booking number BH482910\n"

    monkeypatch.setattr(document_scan.pytesseract, "image_to_string", fail)
    monkeypatch.setattr(document_scan.subprocess, "run", lambda *_args, **_kwargs: _Completed())
    monkeypatch.setattr(document_scan.tempfile, "mkstemp", lambda suffix: (0, str(tmp_path / "ocr.png")))
    monkeypatch.setattr(document_scan.os, "close", lambda _descriptor: None)

    # Act
    text = image_text(_png_bytes())

    # Assert
    assert "BH482910" in text


def test_image_text__ocr_failures__return_blank(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Return blank text when the image cannot be read or OCR fails.

    Pytest node: tests/test_document_scan.py::test_image_text__ocr_failures__return_blank
    Needs: REQ-006, TEST-020
    """

    # Arrange
    monkeypatch.setattr(document_scan.pytesseract, "image_to_string", lambda _image: "")

    def time_out(*_args: object, **_kwargs: object) -> object:
        raise document_scan.subprocess.TimeoutExpired(cmd="powershell", timeout=30)

    monkeypatch.setattr(document_scan.subprocess, "run", time_out)

    # Act / Assert
    assert image_text(_png_bytes()) == ""
    assert image_text(b"not-an-image") == ""
    assert document_scan._window_around_name("hello", {"name": "Inn"}) == "hello"

    class _Failed:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(document_scan.subprocess, "run", lambda *_args, **_kwargs: _Failed())
    assert image_text(_png_bytes()) == ""


def test_apply_missing_booking_details__bare_code__fills_the_named_stay() -> None:
    """Accept a booking code even when it is not labelled 'booking number'.

    Pytest node:
    tests/test_document_scan.py::
    test_apply_missing_booking_details__bare_code__fills_the_named_stay
    Needs: REQ-006, TEST-020
    """

    # Arrange
    plan = {"booking_items": [_stay("Beach House Seaside Resort")]}

    # Act
    messages = apply_missing_booking_details(plan, "BH482910", "Beach house bookings.png")

    # Assert
    assert messages == ["Added booking number BH482910 to Beach House Seaside Resort."]


def _png_bytes() -> bytes:
    image = Image.new("RGB", (80, 40), "white")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()
