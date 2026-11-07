# ADR-0001: Services own transactions; the UI never commits

## Status

Accepted (2026-08-27)

## Context

Service modules (`services/tracking.py`, `services/repository.py`) mutated the database but never committed. Durability therefore depended on an invariant held in every UI handler: each of the 12 handlers across the three tabs had to remember `self.conn.commit()` after its single service call. One missed commit meant silent data loss on close, and every test of the services had to repeat the same commit ritual. The interface of every mutating service function silently carried the caveat "not durable yet".

## Decision

Every mutating service function owns its transaction: the implementation wraps its writes in `db.transaction(conn)`, which commits on success and rolls back the whole transaction on exception. Failures that a user should see are raised as `ValueError` (domain errors) or `sqlite3.IntegrityError` (duplicate NWA codes); UI handlers catch these and show a messagebox — the status reaching the user. Silent no-ops (e.g. pausing with no open session) are successes and produce no message.

Functions that compose others (`reset_day`, `start_or_switch`, `import_public_list`) call services that open their own transactions. `db.transaction` makes that safe: the outermost block owns BEGIN/COMMIT, and a block entered inside an open transaction runs as a SAVEPOINT, so nothing commits until the outermost block finishes and any exception escaping it rolls back everything. `save_work_item` and `move_work_item`'s old `False`-at-boundary return are gone: `move_work_item` raises `ValueError` for unknown IDs and boundary moves alike — one failure protocol per interface.

## Consequences

- No `conn.commit()` exists outside `db.py` (schema) and raw-SQL tests.
- A caller that forgets to catch fails loudly instead of losing data silently.
- Multi-step operations (reset day, create-with-splits) are atomic per service call.
- Tests exercise the service interface exactly as callers do, with no commit in setup.
- Services never use a bare `with conn:`: on exit it commits whatever transaction is open, including a caller's half-finished one. An earlier version of this ADR claimed a nested `with conn:` was harmless; it is not, and it let a failed public list import leave a partial list behind (fixed 2026-11-07).
- File reads and writes can also fail with `OSError` (a locked, read-only, or missing target). UI handlers that export or import a file catch it alongside the service errors and show a messagebox, because the windowed build has no console to show an uncaught traceback.
