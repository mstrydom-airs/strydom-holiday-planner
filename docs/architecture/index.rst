Architecture
============

System architecture is captured here as Mermaid diagrams plus narrative.
See :doc:`../decisions/index` for the decisions behind each diagram.

C4 Context
----------

.. mermaid::

   flowchart LR
     User([Trip planner user])
     Browser[Browser]
     Flask[Flask app]
     DB[(SQLite\ntravel_hub.db)]

     User --> Browser --> Flask --> DB

Container view
--------------

.. mermaid::

   flowchart TB
     subgraph Flask app
       Routes[Blueprints / routes]
       Services[Services layer]
       Models[Models / DAO]
     end
     Routes --> Services --> Models --> DB[(SQLite)]

At a glance home page
---------------------

.. mermaid::

   sequenceDiagram
     participant User
     participant Browser
     participant Flask
     participant Timeline as trip_planner.timeline
     participant Jinja
     User->>Browser: open /
     Browser->>Flask: GET /
     Flask->>Flask: _all_glance_groups_sorted
     Flask->>Timeline: enrich_glance_timeline
     Timeline-->>Flask: enriched rows plus rail
     Flask->>Jinja: render index + glance partial
     Jinja-->>Browser: HTML with glance-layout
     User->>Browser: scroll or click month rail
     Browser->>Browser: IntersectionObserver and scrollIntoView

Plan-a-holiday sequence
-----------------------

.. mermaid::

   sequenceDiagram
     actor User
     User->>Browser: chooses destination and trip length
     Browser->>Flask: GET /holiday-planning
     Flask->>SQLite: SELECT saved trips
     SQLite-->>Flask: plans by holiday type
     Flask-->>Browser: holiday hub with new/reuse/duplicate choices
     User->>Browser: opens or duplicates a plan
     Browser->>Flask: GET /weekend?new=1 or ?duplicate=1
     Flask->>SQLite: INSERT OR REPLACE copied plan
     Flask-->>Browser: 302 destination trip page

Detailed holiday flow
---------------------

.. toctree::
   :maxdepth: 1

   ../diagrams/holiday-planning
