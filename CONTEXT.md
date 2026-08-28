# CONTEXT

Domain glossary for the time card tracker. Terms are added as the domain model sharpens; ADRs in `docs/adr/` record decisions that should not be re-litigated.

## Domain terms

- **NWA** — a charge code (code + name + notes + tags) that work time is billed against.
- **Work item** — a reusable task template with one or more **NWA splits** (basis-point percentages that must total 100%).
- **Split snapshot** — a frozen JSON copy of a work item's splits taken when a session starts (or when its work item changes), so historical sessions are charged by the splits in force at the time.
- **Work day** — the calendar day a session *starts* on; sessions that span midnight belong to the starting day.
- **Session** — a span of tracked time on one work item within a work day. At most one session is open at a time; an open session is treated as ending "now" whenever its elapsed time is needed.

## Architecture terms

- **Transaction ownership** — mutating service functions own durability: they commit on success and roll back on failure (via `with conn:`), raising `ValueError`/`IntegrityError` for user-facing failures. The UI never commits; it catches those exceptions and shows the user a messagebox. Silent no-ops (e.g. pausing with nothing running) are successes, not errors. See ADR-0001.
