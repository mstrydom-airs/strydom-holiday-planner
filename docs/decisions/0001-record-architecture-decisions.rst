ADR-0001 — Record architecture decisions
========================================

.. adr:: Record architecture decisions as ADRs in Sphinx
   :id: ADR-0001
   :status: approved

   **Context.** We need a low-ceremony way to capture significant architectural
   choices so future contributors (and our future selves) understand the *why*.

   **Decision.** Each significant decision is recorded as a short ADR
   (``docs/decisions/NNNN-short-title.rst``) using the ``adr`` sphinx-needs
   directive. ADRs are linked to the requirements and specs they affect.

   **Consequences.** Adds a small documentation step to each architectural
   change, but unlocks full traceability from requirement → decision →
   implementation → test, and the Sphinx build fails if links break.
