Tests
=====

Each ``TEST-`` is a single pytest case identified by its node id. Tests are
linked back to the ``REQ-`` they verify.

.. test:: Home page returns 200
   :id: TEST-001
   :status: implemented
   :links: IMPL-001
   :verifies: REQ-001

   ``tests/test_smoke.py::test_home_page_returns_200``

.. test:: Holiday planning page returns 200
   :id: TEST-002
   :status: implemented
   :links: IMPL-003
   :verifies: REQ-003

   ``tests/test_app.py::test_holiday_planning__empty_database__renders_start_panel``

.. test:: SQLite schema creates trips table
   :id: TEST-003
   :status: implemented
   :links: IMPL-002
   :verifies: REQ-002

   ``tests/test_database.py::test_ensure_trips_schema__fresh_database__creates_trips_table``

.. test:: SQLite trip round trip
   :id: TEST-004
   :status: implemented
   :links: IMPL-002
   :verifies: REQ-002

   ``tests/test_database.py::test_upsert_and_fetch_plan__valid_plan__round_trips_json``

.. test:: Duplicate extended plan clears dates
   :id: TEST-005
   :status: implemented
   :links: IMPL-003
   :verifies: REQ-003, UC-001

   ``tests/test_app.py::test_duplicate_plan_without_dates__extended_trip__clears_dates_and_keeps_details``

.. test:: Holiday payload disambiguates duplicate labels
   :id: TEST-006
   :status: implemented
   :links: IMPL-003
   :verifies: REQ-003

   ``tests/test_app.py::test_plans_payload_for_holiday_json__duplicate_labels__adds_trip_type_suffix``

.. test:: New extended plan starts blank
   :id: TEST-007
   :status: implemented
   :links: IMPL-003
   :verifies: REQ-003

   ``tests/test_app.py::test_new_empty_plan__extended_trip__starts_with_blank_leg``

.. test:: Calendar dates derive from extended legs
   :id: TEST-008
   :status: implemented
   :links: IMPL-004
   :verifies: REQ-004

   ``tests/test_app.py::test_calendar_dates_for_plan__extended_legs_without_overall_dates__uses_leg_span``

.. test:: Checklist sync stores numbered reusable text
   :id: TEST-009
   :status: implemented
   :links: IMPL-004
   :verifies: REQ-004

   ``tests/test_app.py::test_checklist_sync__selected_transport_and_hotel__stores_numbered_items_with_auto_header``

.. test:: Corrupt trip JSON is skipped
   :id: TEST-010
   :status: implemented
   :links: IMPL-002, IMPL-004
   :verifies: REQ-004

   ``tests/test_database.py::test_fetch_plans_for_kind__corrupt_json__skips_bad_rows``

.. test:: Search route finds saved trips
   :id: TEST-011
   :status: implemented
   :links: IMPL-004
   :verifies: REQ-004, UC-001

   ``tests/test_app.py::test_search_route__saved_trip_matches_query__shows_result``

.. test:: Date-based trip routes cover lifecycle branches
   :id: TEST-012
   :status: implemented
   :links: IMPL-002, IMPL-003, IMPL-004
   :verifies: REQ-002, REQ-003, REQ-004, UC-001

   ``tests/test_app_routes.py::test_trip_routes__new_post_duplicate_and_invalid_paths__preserve_expected_redirects``

.. test:: Extended route covers legs and duplication
   :id: TEST-013
   :status: implemented
   :links: IMPL-003, IMPL-004
   :verifies: REQ-003, REQ-004, UC-001

   ``tests/test_app_routes.py::test_extended_route__post_duplicate_and_render__handles_legs_and_overall_dates``

.. test:: Save checklist validates allowed pairs
   :id: TEST-014
   :status: implemented
   :links: IMPL-004
   :verifies: REQ-004

   ``tests/test_app_routes.py::test_save_checklist__valid_and_invalid_pairs__updates_only_allowed_pairs``

.. test:: Search shows empty and checklist-only states
   :id: TEST-015
   :status: implemented
   :links: IMPL-004
   :verifies: REQ-004, UC-001

   ``tests/test_app_routes.py::test_search_route__empty_query_and_checklist_match__show_expected_messages``

.. needtable::
   :types: test
   :columns: id;title;status;verifies
   :style: table
