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

Plan-a-weekend sequence
-----------------------

.. mermaid::

   sequenceDiagram
     actor User
     User->>Browser: fills weekend form
     Browser->>Flask: POST /weekend
     Flask->>Services: save_weekend(payload)
     Services->>SQLite: INSERT INTO weekend_plans ...
     SQLite-->>Services: row id
     Services-->>Flask: WeekendPlan
     Flask-->>Browser: 302 /weekend/{id}
