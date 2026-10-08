"""Shared option lists for Strydom Travel Hub forms.

Keeping these lists outside ``app.py`` makes the older route module smaller
while giving the new trip workspace one source of truth for pick lists.

Needs: REQ-003, REQ-004, REQ-006, TEST-018
"""

from __future__ import annotations

# Checkboxes on trip forms (no Hotel - use named places field instead).
ACCOMMODATION_CHECKBOXES = ["Caravan", "Tent", "Timeshares", "Accor"]

# Full list for checklist pairing (includes Hotel when named places are filled).
ACCOMMODATION_OPTIONS = ACCOMMODATION_CHECKBOXES + ["Hotel"]

TRANSPORT_OPTIONS = ["Flights", "train", "Ute", "Car", "Boat Trip"]

HOLIDAY_TYPE_OPTIONS = [
    "Show",
    "Movie",
    "Walk",
    "Bike ride",
    "Camping",
    "Caravan trip",
    "Timeshare",
    "Accor",
    "Hotel",
]

THINGS_TO_DO_OPTIONS = [
    "Swimming",
    "Beach",
    "Hiking",
    "Walk",
    "Bike ride",
    "Shopping",
    "Restaurants",
    "Sightseeing",
    "Museums / galleries",
    "Events / shows",
    "Show",
    "Movie",
    "Camping",
    "Caravan trip",
    "Timeshare",
    "Accor",
    "Hotel",
    "Relaxing",
]

STANDARD_THINGS = frozenset(THINGS_TO_DO_OPTIONS)

TRAVELER_OPTIONS = [
    ("mario_esme", "Mario & Esme"),
    ("reuben_vanessa", "Reuben & Vanessa"),
    ("noah", "Noah"),
    ("family", "Family"),
    ("friends", "Friends"),
]

TRAVELER_LABELS = dict(TRAVELER_OPTIONS)

TRIP_CATEGORY_OPTIONS = [
    "Holiday overseas",
    "Caravan trip",
    "Accor Unit",
    "Hotel",
    "Beachhouse",
    "Beachcomber",
    "Noosa Spa",
    "Movie",
    "Theatre / show",
    "Restaurant booking",
    "Tour / activity",
    "Other booking",
]

TRIP_LENGTH_OPTIONS = [
    ("day_trip", "Day trip"),
    ("weekend", "Weekend"),
    ("long_weekend", "Long weekend"),
    ("extended", "Extended trip"),
]

STAY_SIZE_OPTIONS = [
    "Studio",
    "One bedroom",
    "Two bedroom",
    "Three bedroom",
]

GOING_PERSON_OPTIONS = [
    ("mario_esme", "Mario & Esme"),
    ("reuben_vanessa", "Reuben & Vanessa"),
]

TRAVELER_LABELS.update(dict(GOING_PERSON_OPTIONS))

PLANNER_PROFILE_OPTIONS = [
    ("mario", "Mario"),
    ("esme", "Esme"),
    ("reuben", "Reuben"),
    ("vanessa", "Vanessa"),
    ("noah", "Noah"),
    ("mario_esme", "Mario & Esme"),
    ("reuben_family", "Reuben Family"),
    ("all_of_us", "All of us"),
]

BOOKING_CATEGORY_OPTIONS = [
    "Accommodation",
    "Caravan stand",
    "Flight",
    "Train",
    "Car hire",
    "Restaurant",
    "Movie",
    "Theatre / show",
    "Tour / activity",
    "Insurance",
    "Document / visa",
    "Other",
]
