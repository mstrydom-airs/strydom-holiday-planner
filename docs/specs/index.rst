Specifications
==============

Detailed designs that elaborate one or more requirements.

.. spec:: Landing page
   :id: SPEC-001
   :status: implemented
   :links: REQ-001

   The landing page is rendered by ``app.index`` and uses ``templates/index.html``.
   It loads in under 200 ms on a development laptop.

.. spec:: Weekend plan persistence
   :id: SPEC-002
   :status: implemented
   :links: REQ-002

   Weekend plans are stored in SQLite via parameterised queries in
   ``database.py``. See :need:`ADR-0002` for the ORM-vs-raw decision.

.. spec:: Holiday planning launch flow
   :id: SPEC-003
   :status: implemented
   :links: REQ-003, UC-001

   ``app.holiday_planning`` renders a holiday hub populated by
   ``app._plans_payload_for_holiday_json``. The payload lists saved trips in
   soonest-first order, adds a holiday-type suffix when duplicate labels would
   be ambiguous, and exposes unique destination names for quick creation.

   Trip routes accept ``?new=1`` to create blank plans and ``?duplicate=1`` with
   ``from=<trip id>`` to copy an existing plan. Duplicates keep travellers,
   transport, accommodation, notes, and activities, but clear trip dates and
   day-planner entries.

.. spec:: Searchable reusable planning aids
   :id: SPEC-004
   :status: implemented
   :links: REQ-004

   Shared checklist content is stored in the Flask session by
   transport/accommodation pair. Saved trip selections build an automatic header
   while preserving numbered user checklist items. ``app.search`` scans saved
   trip dictionaries plus reusable checklist and things-to-do session data.

.. spec:: At a glance timeline service and layout
   :id: SPEC-005
   :status: implemented
   :links: REQ-005

   ``trip_planner.services.timeline`` maps ``sort_key`` values to month sections
   and builds the ordered rail. ``templates/partials/glance_trips.html`` renders
   the two-column layout; ``static/js/glance-timeline.js`` highlights the active
   month; ``static/css/style.css`` styles the sticky rail (hidden below 640px
   width).

.. spec:: Smart trip workspace
   :id: SPEC-006
   :status: implemented
   :links: REQ-006, UC-003

   ``app.smart_trip_new`` creates a blank saved plan and opens
   ``app.trip_workspace``. The workspace stores extra JSON fields on the existing
   trip payload: ``plan_category``, ``planner_profile``, ``booking_items``
   (check-in date, check-out date, check-in time, and check-out time per stay),
   ``task_items``, ``budget_items``, ``document_items``,
   ``booking_import_text``, ``important_links``, ``packing_items``, and
   ``assistant_notes``. Deterministic assistant helpers in
   Uploaded images and emails are scanned, and a booking number in the file fills
   the matching stay. ``trip_planner.services.place_lookup`` can search the public web for a stay's
   phone number and website. Confirmation numbers are not searched.
   On mobile, the workspace keeps its title and actions on one compact row and
   uses a short, horizontally scrolling tab bar that stays below the site
   header while itinerary content scrolls. The overview groups timeline
   rows into native expandable day sections whose summary contains the date and
   named event. Times and activities stay on one line inside each day. The
   overview does not repeat the trip title. Bookings also include accommodation
   legs that have not yet been imported as confirmation records and clearly
   identify selected flights whose details are still missing. Important links
   use one compact label-and-address row. Packing text and daily planner editors
   are collapsed until requested, while their checklists and day labels remain
   visible. Budget lines are the cost stored on each booking.
   ``trip_planner.services.smart_trip`` suggest packing and booking prompts from
   trip category, planner profile, transport, accommodation, and previous saved
   packing items. ``app.trip_pack`` renders a printable family trip pack.

.. spec:: Separate family copies and selective delete
   :id: SPEC-007
   :status: implemented
   :links: REQ-007, UC-004

   ``trip_planner.services.households`` tags a plan from the traveler names saved
   on it. The home list for Mario & Esme or Reuben & Vanessa shows only that
   family's trips. Plan a Trip selects one of those two family groups and stores
   optional companion names in ``travelers_other``. The home list shows a
   companion line only when that field has a value. Home Assistant shows the NUC copy of this app at
   ``/travel-hub/`` and reads ``/calendar/mario-esme.ics`` and
   ``/calendar/reuben-vanessa.ics`` from ``/config/trip_planner/travel_hub.db``.
   ``scripts/sync_ha_planner.py`` reads trips from the NUC into this repo, then
   copies this repo's planner and ``travel_hub.db`` to the NUC and restarts the
   app. This repo is the copy Home Assistant serves after that sync.
   ``app.clear_plans`` deletes only posted trip ids.
   ``app.clear_session`` redirects there and deletes nothing.
