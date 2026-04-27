# Holiday Planning Flow

The holiday hub keeps trip planning simple: pick a destination, choose a holiday
length, then either open a fresh plan or duplicate a saved one with dates reset.

```{mermaid}
flowchart TD
  Hub["/holiday-planning holiday hub"]
  Payload["_plans_payload_for_holiday_json()"]
  SQLite[("SQLite trips table")]
  NewChoice{"User choice"}
  NewPlan["Create blank plan"]
  Duplicate["Copy saved plan without dates"]
  TripPage["Destination trip page"]
  Checklist["Reusable checklist pairs"]
  Search["/search saved-trip lookup"]

  Hub --> Payload
  Payload --> SQLite
  Hub --> NewChoice
  NewChoice -->|New destination| NewPlan
  NewChoice -->|Reuse name| NewPlan
  NewChoice -->|Duplicate saved plan| Duplicate
  NewPlan --> SQLite
  Duplicate --> SQLite
  SQLite --> TripPage
  TripPage --> Checklist
  SQLite --> Search
```

Traceability: :need:`REQ-003`, :need:`REQ-004`, :need:`SPEC-003`,
:need:`SPEC-004`, :need:`IMPL-003`, :need:`IMPL-004`.
