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
   :status: draft
   :links: SPEC-002
   :implements: REQ-002

   ``database.save_weekend_plan`` in ``database.py``.
