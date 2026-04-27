Accessibility Report
====================

Manual + automated a11y verification for any page that changed.

axe-core
--------

Run the axe-core browser extension or ``pytest-axe`` against each affected
page. Record any serious/critical findings here, with a link to the issue
that tracks the fix.

The home page month rail uses native ``button`` elements with
``aria-current`` updates from ``static/js/glance-timeline.js``; verify focus
order and labels when changing this layout (``REQ-005``, ``UC-002``).

Lighthouse
----------

Record the latest Lighthouse scores per page (target ≥ 90 each):

.. list-table::
   :header-rows: 1

   * - Page
     - Performance
     - Accessibility
     - Best Practices
     - SEO
   * - ``/``
     - —
     - —
     - —
     - —
