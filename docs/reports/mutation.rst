Mutation Testing Report
=======================

We use `mutmut <https://mutmut.readthedocs.io/>`_ to verify that our tests
actually catch regressions. Configuration lives in ``pyproject.toml``.

How to refresh
--------------

.. code-block:: bash

   mutmut run
   mutmut html

The HTML report is written to ``html/`` (gitignored). Target mutation score is
**≥ 70%**; surviving mutants must either be killed by new tests or recorded
below with a rationale.

Surviving mutants — rationale log
---------------------------------

* *(none yet)*
