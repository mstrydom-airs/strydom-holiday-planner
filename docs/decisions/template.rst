ADR Template
============

Copy an existing ADR (for example :doc:`0001-record-architecture-decisions`) to
a new file ``NNNN-short-title.rst`` (next free number, lowercase, dashes) and
fill in the sections. Keep ADRs short (one screen if possible).

In the new file, use the ``.. adr::`` directive with a real **ADR-** id (not a
placeholder), link to the correct **REQ-** / **SPEC-** needs, and set status.

**Context.** What is the situation that forces a decision?

**Decision.** What did we decide to do?

**Consequences.** What becomes easier or harder because of this decision? Note
any follow-up **IMPL-** or **TEST-** work.
