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

.. needtable::
   :types: test
   :columns: id;title;status;verifies
   :style: table
