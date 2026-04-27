Requirements
============

All requirements live here as ``req`` directives. Each requirement should be
linked to at least one specification (``SPEC-``) and one test (``TEST-``).

.. req:: Home page renders
   :id: REQ-001
   :status: implemented
   :tags: web; smoke
   :links: SPEC-001
   :verifies: TEST-001

   When a user visits ``/`` they must see the landing page within 2 seconds.

.. req:: Save a weekend plan
   :id: REQ-002
   :status: implemented
   :priority: high
   :source: feature plan
   :owner: Trip Planner maintainer
   :tags: planning
   :links: SPEC-002
   :verifies: TEST-003, TEST-004, TEST-012

   The user can fill in a weekend planning form and persist it to SQLite.

.. req:: Start and reuse holiday plans
   :id: REQ-003
   :status: implemented
   :priority: high
   :source: feature plan
   :owner: Trip Planner maintainer
   :tags: holiday-planning; persistence
   :links: SPEC-003
   :verifies: TEST-002, TEST-005, TEST-006, TEST-007, TEST-012, TEST-013

   A user can open ``/holiday-planning`` to start a new holiday plan, reuse an
   existing destination name, or duplicate a saved plan. Duplicate plans must
   receive a fresh identifier, keep useful planning details, and clear dates so
   the copied plan can be scheduled independently.

.. req:: Keep trip planning aids searchable and reusable
   :id: REQ-004
   :status: implemented
   :priority: medium
   :source: feature plan
   :owner: Trip Planner maintainer
   :tags: search; checklist; usability
   :links: SPEC-004
   :verifies: TEST-008, TEST-009, TEST-010, TEST-011, TEST-012, TEST-013, TEST-014, TEST-015

   Saved trips, traveller notes, things to do, and shared
   transport/accommodation checklists remain reusable across holiday types and
   discoverable through the search page.

.. uc:: Guided holiday planning hub
   :id: UC-001
   :status: implemented
   :priority: high
   :source: feature plan
   :owner: Trip Planner maintainer
   :tags: holiday-planning; accessibility
   :links: REQ-003, REQ-004
   :verifies: TEST-005, TEST-011, TEST-012, TEST-013, TEST-015

   The planning hub presents clear destination and trip-length controls, visible
   labels, holiday imagery, and copy that explains when dates will be set on the
   destination-specific trip page.

.. req:: At a glance month timeline and rail
   :id: REQ-005
   :status: implemented
   :priority: medium
   :source: feature plan
   :owner: Trip Planner maintainer
   :tags: home; glance; timeline
   :links: SPEC-005
   :verifies: TEST-016, TEST-017

   The home At a glance list groups saved trips by calendar month with section
   headings, a sticky month rail (similar to Google Photos), scroll-synced
   highlighting, and jump-to-month on click. Undated trips appear under an
   Undated section at the end.

.. uc:: At a glance month navigation
   :id: UC-002
   :status: implemented
   :priority: medium
   :source: feature plan
   :owner: Trip Planner maintainer
   :tags: home; accessibility; keyboard
   :links: REQ-005
   :verifies: TEST-017

   Users can see which month they are viewing, use a vertical month rail to jump
   to that month, and activate controls with the keyboard. On narrow viewports the
   rail hides and month headings remain in the main column.
