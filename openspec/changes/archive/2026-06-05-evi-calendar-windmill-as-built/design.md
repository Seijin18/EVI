# Design: evi-calendar-windmill-as-built

## Approach

Document and test existing flow: agent `schedule_event` → Windmill HTTP trigger (Bearer `WINDMILL_TOKEN`) → `schedule_event.py` → Google Calendar API with `$res:` gcal resource and `WINDMILL_CALENDAR_ID`.

## Ports / RAM

No new containers. Windmill 8001, agent 8002 (host).

## Out of scope

Tasks, Gmail, commitment inbox.
