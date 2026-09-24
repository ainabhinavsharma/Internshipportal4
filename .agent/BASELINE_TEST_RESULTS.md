# Baseline Test Results

**Date**: 2026-09-25  
**Platform**: Win32 (Python 3.12.10, Pytest 7.4.4, Flask 1.3.0, AnyIO 4.14.2)  
**Target Baseline**: `Internshipportal4` Clean Verified Import  
**Status**: **100% PASSED (32/32 tests passed)**

---

## 1. Test Execution Summary

```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-7.4.4, pluggy-1.6.0
cachedir: .pytest_cache
rootdir: C:\Users\user\Desktop\internship
configfile: pytest.ini
collected 32 items

tests/test_auth.py::test_public_routes_accessible PASSED                 [  3%]
tests/test_auth.py::test_admin_routes_protected PASSED                   [  6%]
tests/test_auth.py::test_intern_routes_protected PASSED                  [  9%]
tests/test_auth.py::test_admin_route_intern_block PASSED                 [ 12%]
tests/test_5_stage_lifecycle.py::Test5StageLifecycle::test_domain_course_catalog_isolation PASSED [ 15%]
tests/test_5_stage_lifecycle.py::Test5StageLifecycle::test_full_5_stage_sequential_lifecycle PASSED [ 18%]
tests/test_5_stage_lifecycle.py::Test5StageLifecycle::test_seeded_domain_courses PASSED [ 21%]
tests/test_phase5_ui.py::test_format_inr PASSED                          [ 25%]
tests/test_phase5_ui.py::test_live_sql_consistency PASSED                [ 28%]
tests/security/test_phase1_auth.py::TestSEC001RoleCorrectReset::test_intern_reset_creates_intern_session PASSED [ 31%]
tests/security/test_phase1_auth.py::TestSEC001RoleCorrectReset::test_company_reset_creates_company_session PASSED [ 34%]
tests/security/test_phase1_auth.py::TestSEC001RoleCorrectReset::test_expired_token_rejected PASSED [ 37%]
tests/security/test_phase1_auth.py::TestSEC001RoleCorrectReset::test_used_token_rejected PASSED [ 40%]
tests/security/test_phase1_auth.py::TestSEC001RoleCorrectReset::test_nonexistent_token_rejected PASSED [ 43%]
tests/security/test_phase1_auth.py::TestSEC001RoleCorrectReset::test_old_sessions_revoked_after_reset PASSED [ 46%]
tests/security/test_phase1_auth.py::TestSEC001RoleCorrectReset::test_account_type_stored_explicitly PASSED [ 50%]
tests/security/test_phase1_auth.py::TestSEC002NoTokenLeakage::test_forgot_password_never_returns_token_normal PASSED [ 53%]
tests/security/test_phase1_auth.py::TestSEC002NoTokenLeakage::test_forgot_password_no_token_when_smtp_missing PASSED [ 56%]
tests/security/test_phase1_auth.py::TestSEC002NoTokenLeakage::test_response_is_neutral_for_both_found_and_not_found PASSED [ 59%]
tests/security/test_phase1_auth.py::TestSEC003NoTokenLogging::test_reset_token_not_in_stdout PASSED [ 62%]
tests/security/test_phase1_auth.py::TestAUTH002Enumeration::test_forgot_password_neutral_for_unknown_email PASSED [ 65%]
tests/security/test_phase1_auth.py::TestAUTH002Enumeration::test_check_email_reveals_account_state PASSED [ 68%]
tests/security/test_phase1_auth.py::TestAUTH002Enumeration::test_forgot_password_indistinguishable_intern_company_unknown PASSED [ 71%]
tests/security/test_phase1_auth.py::TestAUTH003DebugSecurity::test_token_not_exposed_when_flask_debug_true PASSED [ 75%]
tests/security/test_phase2_concurrency.py::test_pay001_mentor_slot_atomic_booking PASSED [ 78%]
tests/security/test_phase2_concurrency.py::test_pay002_cohort_capacity_atomic_enrollment PASSED [ 81%]
tests/security/test_phase2_concurrency.py::test_data001_project_submission_atomic_review PASSED [ 84%]
tests/security/test_phase6_uploads.py::test_allowed_file PASSED          [ 87%]
tests/security/test_phase6_uploads.py::test_sniff_upload_type PASSED     [ 90%]
tests/security/test_phase6_uploads.py::test_task_submit_rejects_spoofed_file PASSED [ 93%]
tests/e2e/test_phase11_observability.py::test_request_id_injected PASSED [ 96%]
tests/e2e/test_phase11_observability.py::test_structured_logging PASSED  [100%]

============================= 32 passed in 44.36s =============================
```

---

## 2. Issues Discovered and Resolved During Baseline
- **`post_applications` DDL Discrepancy**:
  - `CREATE TABLE IF NOT EXISTS post_applications` lacked an explicit `email TEXT` column definition, and `init_db()` migration loop `ensure_column` lacked `("email", "TEXT")`.
  - In fresh databases used in tests, queries such as `/intern/me` triggered `sqlite3.OperationalError: no such column: pa.email`.
  - Resolution: Updated `CREATE TABLE post_applications` and added `ensure_column(conn, "post_applications", "email", "TEXT")` in `app.py`.
  - Result: 100% passing across all 32 unit, security, and lifecycle tests.
