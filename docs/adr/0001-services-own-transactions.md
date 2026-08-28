# ADR-0001: Services own transactions; the UI never commits

## Status

Accepted (2026-08-27)

## Context

Service modules (`services/tracking.py`, `services/repository.py`) mutated the database but never committed. Durability therefore depended on an invariant held in every UI handler: each of the 12 handlers across the three tabs had to remember `self.conn.commit()` after its single service call. One missed commit meant silent data loss on close, and every test of the services had to repeat the same commit ritual. The interface of every mutating service function silently carried the caveat "not durable yet".

## Decision

Every mutating service function owns its transaction: the implementation wraps its writes in `with conn:`, so sqlite3 commits on success and rolls back the whole transaction on exception. Failures that a user should see are raised as `ValueError` (domain errors) or `sqlite3.IntegrityError` (duplicate NWA codes); UI handlers catch these and show a messagebox — the status reaching the user. Silent no-ops (e.g. pausing with no open session) are successes and produce no message.

Functions that compose others (`save_work_item`, `reset_day`) rely on their callees' transactions; a nested `with conn:` commit only flushes already-complete work, and any exception rolls back the entire open transaction. `save_work_item` and `move_work_item`'s old `False`-at-boundary return are gone: `move_work_item` raises `ValueError` for unknown IDs and boundary moves alike — one failure protocol per interface.

## Consequences

- No `conn.commit()` exists outside `db.py` (schema) and raw-SQL tests.
- A caller that forgets to catch fails loudly instead of losing data silently.
- Multi-step operations (reset day, create-with-splits) are atomic per service call.
- Tests exercise the service interface exactly as callers do, with no commit in setup.
