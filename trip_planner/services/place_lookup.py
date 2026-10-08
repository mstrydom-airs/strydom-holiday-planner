"""Look up public phone numbers and websites for saved places.

Confirmation numbers are private, so this search never invents one. It only
fills a phone number or website that appears in public search results.

Needs: REQ-006, SPEC-006, IMPL-006, TEST-020
"""

from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from html import unescape
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

SEARCH_URL = "https://html.duckduckgo.com/html/"
SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
SKIP_HOST_PARTS = (
    "duckduckgo.",
    "google.",
    "facebook.",
    "instagram.",
    "youtube.",
    "tripadvisor.",
    "booking.com",
    "expedia.",
    "whitepages.",
    "yellowpages.",
    "cylex",
    "cybo.",
    "mappaus.",
    "firmania.",
    "localitybiz.",
    "yelp.",
    "wikipedia.",
)
GENERIC_TOKENS = frozenset(
    {
        "hotel",
        "resort",
        "apartments",
        "apartment",
        "holiday",
        "holidays",
        "street",
        "parade",
        "road",
        "avenue",
        "australia",
        "queensland",
        "gold",
        "coast",
    }
)
STAY_CATEGORIES = frozenset({"Accommodation", "Caravan stand"})
PHONE_RE = re.compile(
    r"(?:\(\s*0[2378]\s*\)|\b0[2378]|\+61[\s-]*[2378])(?:[\s()-]*\d){8}"
    r"|\b(?:1300|1800)(?:[\s-]*\d){6}"
)

Opener = Callable[[str, bytes | None], str]


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One organic search result.

    Needs: REQ-006, TEST-020
    """

    url: str
    snippet: str


@dataclass(frozen=True, slots=True)
class PublicPlaceContact:
    """Phone and website found on the public web.

    Needs: REQ-006, TEST-020
    """

    phone: str
    website: str


def lookup_public_contact(
    name: str,
    address: str,
    opener: Opener | None = None,
) -> PublicPlaceContact:
    """Search the public web for a place phone number and website.

    Args:
        name: Place name, such as a hotel.
        address: Street address used to avoid a different property.
        opener: Optional HTTP reader so tests do not use the network.

    Returns:
        Any phone and website that matched. Either field may be blank.

    Needs: REQ-006, SPEC-006, TEST-020
    """

    if not name.strip():
        return PublicPlaceContact(phone="", website="")
    query = " ".join(part.strip() for part in (name, address, "phone") if part.strip())
    fetch = opener or _default_opener
    try:
        html = _fetch_search(query, fetch)
    except OSError:
        logger.warning("Public place lookup failed", extra={"place": name})
        return PublicPlaceContact(phone="", website="")
    hits = _parse_search_hits(html)
    phone, phone_url = _choose_phone(hits, _tokens(name, address))
    website = _choose_website(hits, _tokens(name), phone_url)
    return PublicPlaceContact(phone=phone, website=website)


def fill_missing_place_contacts(
    bookings: list[dict[str, Any]],
    opener: Opener | None = None,
) -> list[str]:
    """Fill empty stay phone numbers and websites from public search results.

    Args:
        bookings: Workspace booking rows. Matching rows are updated in place.
        opener: Optional HTTP reader so tests do not use the network.

    Returns:
        One short status line per stay that was searched.

    Needs: REQ-006, SPEC-006, TEST-020
    """

    messages: list[str] = []
    for booking in bookings:
        if booking.get("category") not in STAY_CATEGORIES:
            continue
        message = _fill_one_booking(booking, opener)
        if message:
            messages.append(message)
    return messages


def _fill_one_booking(booking: dict[str, Any], opener: Opener | None) -> str:
    """Search one stay and write any missing public contact fields."""
    needs_phone = "phone:" not in str(booking.get("notes") or "").lower()
    needs_site = not str(booking.get("website") or "").strip()
    if not needs_phone and not needs_site:
        return ""
    contact = lookup_public_contact(
        str(booking.get("name") or ""),
        str(booking.get("address") or ""),
        opener,
    )
    filled = _apply_contact(booking, contact, needs_phone=needs_phone, needs_site=needs_site)
    name = str(booking.get("name") or "Stay")
    if filled:
        return f"{name}: found {', '.join(filled)}."
    return f"{name}: no public phone or website found."


def _apply_contact(
    booking: dict[str, Any],
    contact: PublicPlaceContact,
    needs_phone: bool,
    needs_site: bool,
) -> list[str]:
    """Copy found contact fields onto a booking. Returns the fields written."""
    filled: list[str] = []
    if needs_site and contact.website:
        booking["website"] = contact.website
        filled.append("website")
    if needs_phone and contact.phone:
        note = f"Phone: {contact.phone}"
        existing = str(booking.get("notes") or "").strip()
        booking["notes"] = f"{existing}\n{note}".strip() if existing else note
        filled.append("phone")
    return filled


def _fetch_search(query: str, opener: Opener) -> str:
    """Download the HTML search page for ``query``."""
    body = urllib.parse.urlencode({"q": query, "kl": "au-en"}).encode()
    return opener(SEARCH_URL, body)


def _default_opener(url: str, data: bytes | None) -> str:
    """Read one DuckDuckGo HTML search. The host is fixed, not user input."""
    if urlparse(url).netloc != "html.duckduckgo.com":
        raise ValueError("Place lookup only searches DuckDuckGo")
    request = urllib.request.Request(url, data=data, headers=SEARCH_HEADERS)  # noqa: S310
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
        payload = response.read()
    return bytes(payload).decode("utf-8", "replace")


def _parse_search_hits(html: str) -> list[SearchHit]:
    """Return organic results and skip ads."""
    hits: list[SearchHit] = []
    for part in re.split(r'class="result__a"', html)[1:]:
        hit = _hit_from_part(part)
        if hit is not None:
            hits.append(hit)
    return hits[:12]


def _hit_from_part(part: str) -> SearchHit | None:
    """Parse one search-result fragment into a hit."""
    href = re.search(r'href="([^"]+)"', part)
    if href is None:
        return None
    url = unescape(href.group(1))
    if not url.startswith("http") or "duckduckgo.com" in url or "ad_domain=" in url:
        return None
    snippet = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', part, re.S)
    text = snippet.group(1) if snippet else ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", unescape(text)).strip()
    return SearchHit(url=url, snippet=text)


def _choose_phone(hits: list[SearchHit], tokens: set[str]) -> tuple[str, str]:
    """Pick a complete phone number from a snippet that matches the place."""
    best_phone = ""
    best_url = ""
    best_score = 0
    for hit in hits:
        match = PHONE_RE.search(hit.snippet)
        if match is None:
            continue
        score = _text_score(hit.snippet, tokens)
        if score > best_score:
            best_score = score
            best_phone = re.sub(r"\s+", " ", match.group(0)).strip()
            best_url = hit.url
    if best_score == 0:
        return "", ""
    return best_phone, best_url


def _choose_website(hits: list[SearchHit], tokens: set[str], phone_url: str) -> str:
    """Prefer the official-looking site, or the page that showed the phone."""
    if phone_url and _host_score(phone_url, tokens):
        return _clean_url(phone_url)
    best_url = ""
    best_score = 0
    for hit in hits:
        score = _host_score(hit.url, tokens)
        if score > best_score:
            best_score = score
            best_url = hit.url
    if best_score == 0:
        return ""
    return _clean_url(best_url)


def _host_score(url: str, tokens: set[str]) -> int:
    """Count place-name words contained in a result hostname."""
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if not host or any(part in host for part in SKIP_HOST_PARTS):
        return 0
    return sum(1 for token in tokens if token in host or token.rstrip("s") in host)


def _text_score(text: str, tokens: set[str]) -> int:
    """Count place or address words in a snippet."""
    lowered = text.lower()
    return sum(1 for token in tokens if token in lowered)


def _tokens(*parts: str) -> set[str]:
    """Meaningful words used to match a place, ignoring generic travel words."""
    words = re.findall(r"[a-z0-9]{5,}", " ".join(parts).lower())
    return {word for word in words if word not in GENERIC_TOKENS}


def _clean_url(url: str) -> str:
    """Keep the scheme, host, and path of a result link."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path or '/'}"
