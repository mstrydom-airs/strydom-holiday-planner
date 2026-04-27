Implementation
==============

Pointers from requirements/specs into the actual code. Each ``IMPL-`` names a
file and symbol; the corresponding source docstring echoes the ID in its
``Needs:`` footer.

.. impl:: Flask landing page route
   :id: IMPL-001
   :status: implemented
   :links: SPEC-001
   :implements: REQ-001

   ``app.index`` in ``app.py`` — renders ``templates/index.html``.

.. impl:: Weekend plan persistence
   :id: IMPL-002
   :status: implemented
   :links: SPEC-002
   :implements: REQ-002

   ``database.ensure_trips_schema``, ``database.upsert_trip``,
   ``database.fetch_plan``, and ``database.fetch_plans_for_kind`` in
   ``database.py``.

.. impl:: Holiday planning hub
   :id: IMPL-003
   :status: implemented
   :links: SPEC-003
   :implements: REQ-003, UC-001

   ``app.holiday_planning``, ``app._plans_payload_for_holiday_json``,
   ``app._new_empty_plan``, and ``app._duplicate_plan_without_dates`` in
   ``app.py``.

.. impl:: Reusable checklist and search helpers
   :id: IMPL-004
   :status: implemented
   :links: SPEC-004
   :implements: REQ-004

   ``app._sync_checklist_auto_headers``, ``app._normalize_checklist_text``,
   ``app._calendar_dates_for_plan``, ``app.search``, and
   ``app._trip_matches`` in ``app.py``.

.. impl:: At a glance timeline service
   :id: IMPL-005
   :status: implemented
   :links: SPEC-005
   :implements: REQ-005

   ``trip_planner.services.timeline.glance_section_meta`` and
   ``trip_planner.services.timeline.enrich_glance_timeline`` in
   ``trip_planner/services/timeline.py``. The ``home`` view in ``app.py`` passes
   ``glance_enriched`` and ``glance_rail`` to ``templates/index.html``.
