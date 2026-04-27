Security Scans
==============

Two scans are run before every merge.

pip-audit
---------

Checks installed dependencies against the PyPA advisory database.

.. code-block:: bash

   pip-audit -r requirements.txt -r requirements-dev.txt

bandit
------

Static analysis for common Python security issues.

.. code-block:: bash

   bandit -r app/ database.py

Latest summary
--------------

* *(refresh after running the scans)*
