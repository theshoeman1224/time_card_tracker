# Architecture Plan — Deepening Opportunities

Companion to [docs/architecture-review-2026-08-27.html](docs/architecture-review-2026-08-27.html) (open it in a browser for the before/after diagrams).

Vocabulary: **module** (interface + implementation), **interface** (everything a caller must know), **deep/shallow** (behaviour per unit of interface), **seam** (where an interface lives), **adapter** (concrete occupant of a seam), **leverage** (caller payoff of depth), **locality** (maintainer payoff of depth).

No `CONTEXT.md` or ADRs exist yet; domain terms below are the code's own (work item, NWA, session, work day, splits, snapshot).

## Candidates

| # | Candidate | Strength | Files |
|---|-----------|----------|-------|
| 1 | Transaction ownership — services own `commit()` | **Strong** | `work_items_tab.py`, `saved_nwas_tab.py`, `settings_reports_tab.py`, `services/*` |
| 2 | Day-totals module — one place for "open session ends now" | **Strong** | `work_items_tab.py:114–144`, `services/reports.py`, `util/time_utils.py` |
| 3 | Dialog intake seam — pure `validate(form) → draft` | **Strong** | `ui/dialogs.py`, `services/validation.py` |
| 4 | Repository interface narrowed to domain-shaped returns | Worth exploring | `services/repository.py`, `work_items_tab.py:97` |
| 5 | Pin invariant holes with tests through the deepened interfaces | Speculative | `services/tracking.py`, `services/repository.py`, `tests/` |
| 6 | `paths.py` — pure getters, explicit `ensure_app_dirs` | Speculative | `paths.py`, `db.py`, `app.py` |

## Execution order

1. ✅ **Done (373901e) — Candidate 1: transaction ownership.** Durability moved behind the tracking and repository modules' interfaces: every mutating service function commits via `with conn:` and rolls back on failure; all 12 `conn.commit()` sites removed from the UI; `move_work_item` raises `ValueError` at boundaries (one failure protocol). Recorded as ADR-0001; term pinned in `CONTEXT.md`.
2. ✅ **Done — Candidate 2: day totals.** The "open session ends now" rule moved into the tracking module as `session_seconds`/`work_day_seconds`; `reports.generate_report` and the sessions toolbar/elapsed label consume the same interface; `seconds_between` restored to pure two-arg time math. Behavior preserved (reports include the open session up to now).
3. **Candidate 5 (first half) — invariant tests.** With 1–2 in place, add tests through the tracking module's interface: `update_session(end_at=None)` on a closed session must not re-open it (currently a hole in the one-open-session invariant, `tracking.py:131–133`).
4. **Candidate 3 — dialog intake seam.** Extract pure `validate(form) → draft` per dialog; dialogs become thin Tk adapters that collect fields and render errors. Options passed in, not re-queried from the DB in `__init__`.
5. **Candidate 4 — repository narrowing.** Domain-shaped returns (percent strings, tag lists) absorb SQL artifacts (GROUP_CONCAT, basis points, `sort_order` guarantees). Retires the divergent second percent formatter at `work_items_tab.py:97`.
6. **Candidate 5 (second half) + 6.** Happy-path test for `move_work_item` (one failure protocol, not two); pure `paths.py` if `db.connect`/`app.main` ever get tests.

## Deletion test notes

- `tracking`, `reports`, `exports`, `validation` pass — deleting them concentrates complexity back into callers. Keep and deepen.
- `repository.get_setting/set_setting/remove_*/get_work_item` fail — pass-throughs. Absorb during candidate 4.
- The UI copies of day-total aggregation fail — concentrate into the day-totals module (candidate 2).

## Verification

- `python -m unittest discover` after each step; no test may gain a `conn.commit()` in setup.
- New tests cross the same interface as callers (the interface is the test surface) — no test reaches past an interface.
- One adapter = hypothetical seam; two adapters = real. Candidate 3's seam is justified by NWA + work item + session forms; candidate 6's is not — skip it until something varies.
