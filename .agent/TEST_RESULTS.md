# Test Results Log

## Baseline Test Run — 2026-09-23 14:50
- **Command**: `pytest`
- **Total Tests**: 38 collected
- **Result**: 35 passed, 3 failed, 4 errors
- **Failures**:
  - `tests/e2e/test_phase10_workflows.py::test_intern_auth_workflow[chromium]` (timeout waiting for selector `#si_password` in auth overlay)
  - `tests/e2e/test_phase10_workflows.py::test_resilience_rate_limit[chromium]` (timeout waiting for selector `#si_password` in auth overlay)
  - `tests/e2e/test_phase9_a11y.py::test_a11y_courses_catalog[chromium]` (2 accessibility violations: contrast and heading order)
- **Errors**:
  - `tests/test_auth.py::test_public_routes_accessible` (Windows SQLite file locking on unlink `WinError 32`)
  - `tests/test_auth.py::test_admin_routes_protected` (Windows SQLite file locking on unlink `WinError 32`)
  - `tests/test_auth.py::test_intern_routes_protected` (Windows SQLite file locking on unlink `WinError 32`)
  - `tests/test_auth.py::test_admin_route_intern_block` (Windows SQLite file locking on unlink `WinError 32`)
