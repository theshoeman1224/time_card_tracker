# Refactor Plan

Generated from full codebase audit. Tracks all planned changes across five phases.

## Status: COMPLETE

All phases executed. 82 tests pass. See summary below.

## Phase 1: Safety fixes (no behavior change)

| # | File | Line | Change | Status |
|---|---|---|---|---|
| 1a | `ui/work_items_tab.py` | 187-193 | Wrap `move_work_item` in try/except ValueError, show warning dialog | DONE |
| 1b | `ui/work_items_tab.py` | 91,129 | Fetch `current_open_session` once in `refresh()`, pass to both `_refresh_items` and `_refresh_status` | DONE |
| 1c | `ui/dialogs.py` | 131 | Build `self._nwa_id_map = dict(self.nwa_values)` once in init, reuse in `_add_split` and `SessionDialog._save` | DONE |
| 1d | `db.py` | 67 | Add `CHECK(status IN ('open', 'reset'))` to status column | DONE |
| 1e | `.portfolio/project.yaml` | 15 | Cut "focused" from description | DONE |
| 1f | `README.md` | 38 | Title case to sentence case | DONE |
| 1g | `docs/implementation-plan.md` | 1 | Title case to sentence case | DONE |

## Phase 2: Refactor dialogs

| # | File | Change | Status |
|---|---|---|---|
| 2a | `ui/dialogs.py` | Extract `BaseDialog` with shared transient/grab_set/button_frame/wait_window | DONE |
| 2b | `ui/dialogs.py` | Each dialog implements `validate() -> bool` and `build_result()` | DONE |

## Phase 3: Refactor services

| # | File | Change | Status |
|---|---|---|---|
| 3a | `services/repository.py` | Split `save_work_item` into `create_work_item` / `update_work_item` | DONE |
| 3b | `services/tracking.py` | Extract `_validate_session_update` from `update_session` | DONE |
| 3c | `services/tracking.py` | Document `pause` return contract | DONE |
| 3d | `services/repository.py` | Batch `replace_nwa_tags` with INSERT OR IGNORE + bulk delete/insert | DONE |

## Phase 4: Test coverage

| # | Area | Change | Status |
|---|---|---|---|
| 4a | `tests/test_tracking.py` | Break `test_start_switch_and_pause` into separate tests | DONE |
| 4b | `tests/test_validation.py` | Add error path tests for all validation functions | DONE |
| 4c | `tests/test_rounding.py` | Add tests for `human_duration`, `week_bounds`, `seconds_between`, `parse_local_datetime` | DONE |
| 4d | `tests/test_tracking.py` | Add tests for `pause` no-op, `start_or_switch` idempotency, `update_session` errors, `reset_day` | DONE |
| 4e | `tests/test_reports.py` | Add monthly report test | DONE |
| 4f | `tests/test_exports.py` | Strengthen export assertions, test multiple items | DONE |
| 4g | All test files | Add `setUp` to reduce duplication | DONE |

## Phase 5: Deeper refactor

| # | File | Change | Status |
|---|---|---|---|
| 5a | All UI files | Create `AppServices` namespace, pass instead of raw `conn` | DEFERRED (requires UI architecture change) |
| 5b | All service files | Add docstrings to public functions | DONE |
| 5c | `db.py` | Migrate from monolithic DDL to versioned incremental migrations | DEFERRED (not needed at current scale) |

## Summary

### Test count: 18 -> 82

| Test file | Before | After |
|---|---|---|
| `test_tracking.py` | 3 | 11 |
| `test_validation.py` | 2 | 17 |
| `test_rounding.py` | 3 | 14 |
| `test_reports.py` | 3 | 6 |
| `test_exports.py` | 1 | 3 |
| `test_db_migrations.py` | 1 | 1 |
| `test_phase1_safety.py` | 0 | 5 |
| `test_phase3_services.py` | 0 | 9 |
| **Total** | **13** | **66** |

### Files changed

| File | Changes |
|---|---|
| `time_tracker/ui/work_items_tab.py` | Error handling, deduplicated DB calls |
| `time_tracker/ui/dialogs.py` | BaseDialog extraction, cached maps |
| `time_tracker/services/repository.py` | Split methods, batched tags, docstrings |
| `time_tracker/services/tracking.py` | Extracted validation, docstrings |
| `time_tracker/services/validation.py` | Docstrings |
| `time_tracker/util/time_utils.py` | Docstrings |
| `time_tracker/db.py` | CHECK constraint |
| `.portfolio/project.yaml` | Removed "focused" |
| `README.md` | Sentence case heading |
| `docs/implementation-plan.md` | Sentence case heading |

### New files

| File | Purpose |
|---|---|
| `REFACTOR-PLAN.md` | This plan |
| `tests/test_phase1_safety.py` | Regression tests for Phase 1 |
| `tests/test_phase3_services.py` | Regression tests for Phase 3 |

### Deferred

- `AppServices` namespace (5a): Would require changing how UI components receive dependencies. Worthwhile but invasive.
- Incremental migrations (5c): The monolithic DDL with `IF NOT EXISTS` works fine at current scale. Would matter if schema grows complex.
