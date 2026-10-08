# Trip Planning Sources

Keep source itineraries, confirmations, screenshots, and planning documents in
the family folder that owns the trip:

- `MarioEsme/`
- `ReubenVanessa/`

These source files may contain passport numbers, booking references, addresses,
or other private information. They stay on this PC and are ignored by Git. The
planner stores only the useful trip details and a local reference to the source.

Whenever a source document is added or revised:

1. Read the document and identify the matching trip.
2. Update dates, daily activities, bookings, tasks, links, packing, and notes in
   `travel_hub.db`.
3. Preserve confirmed details and clearly label proposed or unverified items.
4. Do not copy passport numbers or other unnecessary identifiers into the
   planner.
5. Run `python scripts/sync_ha_planner.py` so the NUC planner matches this repo.
