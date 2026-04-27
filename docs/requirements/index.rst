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
   :status: draft
   :tags: planning
   :links: SPEC-002

   The user can fill in a weekend planning form and persist it to SQLite.
