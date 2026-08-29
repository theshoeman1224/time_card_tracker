# ADR-0002: Public lists as a scope on shared tables, imported as one transaction

## Status

Accepted (2026-08-28)

## Context

Teams need a shared "public" catalog of NWAs and work items, supplied by a team lead or manager and refreshed every few months. Users keep personal NWAs and tasks alongside it, and personal tasks may bill against public NWAs. When a new public list arrives, old public entries may disappear; the app must not break, users must not lose tasks, and historical time must not re-charge.

Design questions: how to represent public vs personal data, what an import replaces, what happens to tasks whose public NWA vanished, and who may edit public entries.

## Decision

**Scope is a column, not a table.** `nwas` and `work_item_templates` carry `scope` (`personal` | `public`) plus `is_obsolete`. `is_deleted` keeps its meaning (the user removed it); `is_obsolete` means a newer public list dropped the entry. Keeping the two flags separate lets the UI explain *why* something disappeared and lets reports and stale-split queries still read dropped rows — nothing is ever hard-deleted, so session foreign keys never dangle.

**Import is one transaction (per ADR-0001).** `import_public_list` validates the file (structure, format version, duplicate codes/names, split totals, self-containment, collisions with personal NWA codes) and then, inside a single `with conn:` block, obsoletes the current public set and upserts the file's entries — NWAs matched by `code`, work items matched by `name`. Any failure rolls back everything: the old list stays intact. Re-importing the same file is a no-op, and a manager's local edits propagate because surviving entries are updated in place, not recreated.

**Auto-relink is structural.** Because upsert revives the *same row* for a surviving code, any work item split pointing at that row keeps working with no relinking step. Only codes that vanished leave stale splits behind, and there is no code to relink them to — the user edits the task manually, guided by red highlighting and a warning banner. An explicit relink pass would be dead code.

**Historical sessions are already safe.** Session charging uses the split snapshot frozen at session start (`split_snapshot_json`), so imports cannot re-charge or break past sessions. An open session on a dropped item keeps running and charges by its snapshot; the item just can't be started again.

**Public entries are read-only by default**, with an `allow_public_edits` setting for managers who need to edit and re-export their list. Public NWAs removed by a user but present in a new file are revived by import.

## Consequences

- Obsolete public work items are hidden from the active list, but stay visible in red for the rest of the app session after an import (until-restart display), so users can see what was dropped.
- Exported files are self-contained: every split references a code defined in the same file. Export refuses to run while a public work item still references an obsolete public NWA.
- A personal NWA's code colliding with an imported public code aborts the import with a message naming the code; personal data is never mutated or claimed.
- Schema version 2 introduced the first incremental migration step (`MIGRATION_STEPS` in `db.py`); steps must stay idempotent because `SCHEMA_SQL` runs before them on every open.
