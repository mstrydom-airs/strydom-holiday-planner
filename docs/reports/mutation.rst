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

Latest run status
-----------------

Command attempted:
``$env:PYTHONUTF8='1'; .\.venv\Scripts\Activate.ps1; python -m mutmut run``

Result:
Blocked before mutant execution on Python 3.14. The baseline pytest command ran,
but ``mutmut==2.5.0`` failed while preparing source-file line metadata through
``pony`` with ``TypeError: cannot pickle 'itertools.count' object``.

Follow-up:
Run mutation testing under Python 3.11 or 3.12, matching the project standard
runtime, or upgrade the pinned mutation tooling after validating compatibility.
No mutation score is claimed for this run.

Surviving mutants:
*(not available because mutation execution did not start)*
