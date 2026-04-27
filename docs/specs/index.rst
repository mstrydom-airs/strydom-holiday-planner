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
   :status: draft
   :links: REQ-002

   Weekend plans are stored in SQLite via parameterised queries in
   ``database.py``. See :need:`ADR-0002` for the ORM-vs-raw decision.
