# CONTEXT

Domain glossary for the time card tracker. Terms are added as the domain model sharpens; ADRs in `docs/adr/` record decisions that should not be re-litigated.

## Domain terms

- **NWA** — a charge code (code + name + notes + tags) that work time is billed against.
- **Public list** — the team-shared catalog of NWAs and work items supplied by a team lead or manager. Only one public list is active at a time; importing a new one replaces it. See ADR-0002.
- **Obsolete** — dropped by a newer public list. Distinct from *deleted* (removed by the user): obsolete rows stay readable so stale splits and history still resolve, and the UI can show why something vanished.
- **Stale** — a work item split that points at an NWA the user can no longer pick: one they removed, or an obsolete public one. Shown in red with a warning banner; fixed by editing the task to relink its splits (or re-adding the removed code). A public list import reports only the splits it left stale.
- **Work item** — a reusable task template with one or more **NWA splits** (basis-point percentages, entered with at most two decimal places, that must total 100%).
- **Split snapshot** — a frozen JSON copy of a work item's splits taken when a session starts (or when its work item changes), so historical sessions are charged by the splits in force at the time.
- **Work day** — the calendar day a session *starts* on; sessions that span midnight belong to the starting day.
- **Rounded hours** — a time rounded to the rounding increment (setting, in minutes) and shown as decimal hours: one decimal place when the increment is a multiple of 6 minutes (exact tenths), otherwise two (15 minutes = 0.25). Rounding applies per work item per work day; weekly and monthly reports sum the daily rounded values, so they always match the daily reports they cover. Each work item's daily time, raw and rounded, is split across its NWAs by largest remainder, so NWA totals always equal work item totals.
- **Session** — a span of tracked time on one work item within a work day. At most one session is open at a time; an open session is treated as ending "now" whenever its elapsed time is needed.

## Architecture terms

- **Transaction ownership** — mutating service functions own durability: they commit on success and roll back on failure (via `db.transaction`, which nests as savepoints so composed calls stay atomic), raising `ValueError`/`IntegrityError` for user-facing failures. The UI never commits; it catches those exceptions and shows the user a messagebox. Silent no-ops (e.g. pausing with nothing running) are successes, not errors. See ADR-0001.
