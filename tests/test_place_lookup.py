"""Tests for public phone and website lookup.

Needs: REQ-006, SPEC-006, TEST-020
"""

from __future__ import annotations

import urllib.request

from trip_planner.services import place_lookup
from trip_planner.services.place_lookup import (
    SEARCH_URL,
    fill_missing_place_contacts,
    lookup_public_contact,
)

BEACH_HTML = """
<a class="result__a" href="https://www.cylex-australia.com/company/beach-house.html">Cylex</a>
<a class="result__snippet">Coolangatta (07) 5590 2...</a>
<a class="result__a" href="https://www.timeshares.com.au/resorts/beach-house.php">Timeshare</a>
<a class="result__snippet">52 Marine Parade, Coolangatta (07) 5590 2111</a>
<a class="result__a" href="https://www.beachhouseseasideresort.com.au/">Official</a>
<a class="result__snippet">Beach House Seaside Resort contact</a>
<a class="result__a" href="https://example.com/other-stay">Other stay</a>
<a class="result__snippet">Different town (07) 4000 1111</a>
<a class="result__a">No link</a>
<a class="result__a" href="https://duckduckgo.com/y.js?ad_domain=booking.com">Ad</a>
<a class="result__snippet">Book a room (07) 5555 0000</a>
"""

LEGENDS_HTML = """
<a class="result__a" href="https://www.mantralegends.com.au/contact-us/">Contact</a>
<a class="result__snippet">25 Laycock Street Surfers Paradise P: (07) 5588 7888</a>
<a class="result__a" href="https://www.legendshotel.com.au/">Home</a>
<a class="result__snippet">Legends Hotel Surfers Paradise</a>
"""


def _opener(html: str):
    def fetch(_url: str, _data: bytes | None) -> str:
        return html

    return fetch


def test_trip_workspace__missing_hotel_contact__shows_internet_lookup(flask_client) -> None:  # type: ignore[no-untyped-def]
    """Show the internet lookup control when a stay has no public contact details.

    Pytest node:
    tests/test_place_lookup.py::
    test_trip_workspace__missing_hotel_contact__shows_internet_lookup
    Needs: REQ-006, TEST-020
    """

    # Arrange
    created = flask_client.post(
        "/smart-trip/new",
        data={"title": "Lookup stay", "plan_category": "Hotel", "trip_kind": "weekend"},
    )
    trip_id = created.headers["Location"].rstrip("/").split("/")[-1]
    flask_client.post(
        f"/trip/weekend/{trip_id}",
        data={
            "title": "Lookup stay",
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

    # Act
    page = flask_client.get(f"/trip/weekend/{trip_id}")

    # Assert
    assert b"Find contacts" in page.data
    assert b"missing phone, website, confirmation number" in page.data


def test_lookup_public_contact__beach_house_results__keeps_full_phone_and_official_site() -> None:
    """Use a complete public phone and skip directory and ad links.

    Pytest node:
    tests/test_place_lookup.py::
    test_lookup_public_contact__beach_house_results__keeps_full_phone_and_official_site
    Needs: REQ-006, TEST-020
    """

    # Act
    contact = lookup_public_contact(
        "Beach House Seaside Resort",
        "52 Marine Parade, Coolangatta QLD 4225",
        _opener(BEACH_HTML),
    )

    # Assert
    assert contact.phone == "(07) 5590 2111"
    assert contact.website == "https://www.beachhouseseasideresort.com.au/"


def test_lookup_public_contact__hotel_contact_page__uses_that_site() -> None:
    """Keep the website that published the matching phone number.

    Pytest node:
    tests/test_place_lookup.py::
    test_lookup_public_contact__hotel_contact_page__uses_that_site
    Needs: REQ-006, TEST-020
    """

    # Act
    contact = lookup_public_contact(
        "Legends Hotel Surfers Paradise",
        "Laycock Street, Surfers Paradise QLD 4217",
        _opener(LEGENDS_HTML),
    )

    # Assert
    assert contact.phone == "(07) 5588 7888"
    assert contact.website == "https://www.mantralegends.com.au/contact-us/"


def test_fill_missing_place_contacts__existing_details__leaves_them_unchanged() -> None:
    """Do not replace a phone, website, or confirmation already saved.

    Pytest node:
    tests/test_place_lookup.py::
    test_fill_missing_place_contacts__existing_details__leaves_them_unchanged
    Needs: REQ-006, TEST-020
    """

    # Arrange
    bookings = [
        {
            "category": "Accommodation",
            "name": "Beach House Seaside Resort",
            "address": "52 Marine Parade",
            "website": "https://already.example/",
            "reference": "SECRET",
            "notes": "Phone: (07) 0000 0000",
        },
        {"category": "Flight", "name": "CX156", "notes": ""},
    ]

    # Act
    messages = fill_missing_place_contacts(bookings, _opener(BEACH_HTML))

    # Assert
    assert messages == []
    assert bookings[0]["website"] == "https://already.example/"
    assert bookings[0]["reference"] == "SECRET"
    assert bookings[0]["notes"] == "Phone: (07) 0000 0000"


def test_fill_missing_place_contacts__search_down__reports_no_public_details() -> None:
    """Tell the user when the public search cannot be reached.

    Pytest node:
    tests/test_place_lookup.py::
    test_fill_missing_place_contacts__search_down__reports_no_public_details
    Needs: REQ-006, TEST-020
    """

    # Arrange
    bookings = [
        {
            "category": "Accommodation",
            "name": "Beach House Seaside Resort",
            "address": "52 Marine Parade",
            "website": "",
            "notes": "Check-in 3:00 PM",
        }
    ]

    def fail(_url: str, _data: bytes | None) -> str:
        raise TimeoutError("timed out")

    # Act
    messages = fill_missing_place_contacts(bookings, fail)

    # Assert
    assert messages == ["Beach House Seaside Resort: no public phone or website found."]
    assert bookings[0]["notes"] == "Check-in 3:00 PM"
    assert bookings[0]["website"] == ""


def test_fill_missing_place_contacts__public_result__saves_phone_and_website() -> None:
    """Write a found phone onto the existing notes and save the website.

    Pytest node:
    tests/test_place_lookup.py::
    test_fill_missing_place_contacts__public_result__saves_phone_and_website
    Needs: REQ-006, TEST-020
    """

    # Arrange
    bookings = [
        {
            "category": "Accommodation",
            "name": "Beach House Seaside Resort",
            "address": "52 Marine Parade, Coolangatta",
            "website": "",
            "reference": "",
            "notes": "Check-in 3:00 PM AEST.",
        }
    ]

    # Act
    messages = fill_missing_place_contacts(bookings, _opener(BEACH_HTML))

    # Assert
    assert messages == ["Beach House Seaside Resort: found website, phone."]
    assert bookings[0]["website"] == "https://www.beachhouseseasideresort.com.au/"
    assert bookings[0]["reference"] == ""
    assert "Phone: (07) 5590 2111" in bookings[0]["notes"]


def test_lookup_public_contact__blank_name__skips_search() -> None:
    """Do not search when the booking has no place name.

    Pytest node: tests/test_place_lookup.py::test_lookup_public_contact__blank_name__skips_search
    Needs: REQ-006, TEST-020
    """

    # Act
    contact = lookup_public_contact("  ", "52 Marine Parade", _opener(BEACH_HTML))

    # Assert
    assert contact.phone == ""
    assert contact.website == ""


def test_lookup_public_contact__unrelated_phone__leaves_contact_blank() -> None:
    """Ignore a phone number that does not mention this place.

    Pytest node:
    tests/test_place_lookup.py::test_lookup_public_contact__unrelated_phone__leaves_contact_blank
    Needs: REQ-006, TEST-020
    """

    # Arrange
    html = """
    <a class="result__a" href="https://example.com/other">Other</a>
    <a class="result__snippet">Somewhere else (07) 5555 1111</a>
    """

    # Act
    contact = lookup_public_contact("Beach House Seaside Resort", "Coolangatta", _opener(html))

    # Assert
    assert contact.phone == ""
    assert contact.website == ""


def test_clean_url__missing_host__returns_blank() -> None:
    """Drop a result link that is not a real web address.

    Pytest node: tests/test_place_lookup.py::test_clean_url__missing_host__returns_blank
    Needs: REQ-006, TEST-020
    """

    # Act / Assert
    assert place_lookup._clean_url("not-a-url") == ""


def test_default_opener__other_host__refuses_request() -> None:
    """Only send the search to DuckDuckGo.

    Pytest node: tests/test_place_lookup.py::test_default_opener__other_host__refuses_request
    Needs: REQ-006, TEST-020
    """

    # Act / Assert
    try:
        place_lookup._default_opener("https://evil.example/search", None)
    except ValueError as exc:
        assert "DuckDuckGo" in str(exc)
    else:
        raise AssertionError("expected the opener to refuse another host")


def test_default_opener__duckduckgo__reads_response(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Read the search page body from the fixed DuckDuckGo address.

    Pytest node: tests/test_place_lookup.py::test_default_opener__duckduckgo__reads_response
    Needs: REQ-006, TEST-020
    """

    # Arrange
    class _Response:
        def read(self) -> bytes:
            return b"<html>ok</html>"

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: _Response())

    # Act
    body = place_lookup._default_opener(SEARCH_URL, b"q=test")

    # Assert
    assert body == "<html>ok</html>"
