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
