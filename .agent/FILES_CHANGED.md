# Files Changed Log

| File | Change | Reason | Phase | Risk | Tests |
|---|---|---|---|---|---|
| `tests/test_auth.py` | Close `db_fd` immediately upon `mkstemp` and safe `gc.collect()` before `unlink` | Fix Windows SQLite file-lock `WinError 32` during fixture teardown | Harness | Very Low | `pytest tests/test_auth.py` (4/4 passed) |
| `.gitignore` | Add `backups/` to ignored folders | Prevent committing database dumps and checksum files | Safety | Zero | `git status` |
| `scripts/backup_db.py` | New WAL-safe automated SQLite backup script | Safe timestamped backups with SHA-256 (SAFE-001) | Phase 1 | Zero | `python scripts/backup_db.py --reason pre-migration` |
| `scripts/verify_backup_restore.py` | New backup restoration and integrity verification script | Test restoration in isolated sandbox (SAFE-002) | Phase 1 | Zero | `python scripts/verify_backup_restore.py --latest` |
| `.env.staging.example` | New staging configuration template | Mirror production with isolated resources (SAFE-003) | Phase 1 | Zero | Config inspection |
| `docs/ROUTE_INVENTORY.md` | New complete route inventory (231 routes) | Catalog every route, role, tables, services (INV-001) | Phase 0 | Zero | Inspection |
| `docs/FEATURE_INVENTORY.md` | New feature inventory across 20 domains | Classify features into operational status (INV-002) | Phase 0 | Zero | Inspection |
| `docs/DATABASE_INVENTORY.md` | New schema and table inventory (57 tables) | Document all schemas, FKs, indexes, counts (INV-003) | Phase 0 | Zero | Inspection |
| `docs/EXTERNAL_SERVICES.md` | New external services inventory | Map integrations, credentials, fallbacks (INV-004) | Phase 0 | Zero | Inspection |
| `docs/DEPENDENCY_MAP.md` | New dependency map | Track Python packages and static assets | Phase 0 | Zero | Inspection |
| `docs/PROJECT_STATE.md` | New project state document | Track phase gates and operational health | Phase 0 | Zero | Inspection |
| `docs/DATABASE_SAFETY.md` | New database safety guide | Operational policies for backups and restore (SAFE-002) | Phase 1 | Zero | Inspection |
| `docs/STAGING_GUIDE.md` | New staging guide | Staging isolation policies (SAFE-003) | Phase 1 | Zero | Inspection |
| `docs/ROLLBACK_PLAN.md` | New 6-vector rollback plan | Disaster recovery and emergency procedures (SAFE-004) | Phase 1 | Zero | Inspection |
| `DBERT_PORTAL_NEXT_PHASE_MASTER_PLAN.md` | Added PAY-004 to PAY-010 | Razorpay gateway integration and dynamic QR fallback | Phase 5 | Zero | Document inspection |
| `docs/PAYMENT_GATEWAY_PLAN.md` | New Razorpay architecture blueprint | Full technical design and API contracts | Phase 5 | Zero | Document inspection |
| `scripts/classify_user_lifecycle.py` | User lifecycle classifier script | Classify 2,230 accounts into A-L tiers (MIG-001) | Phase 2 | Zero | Execution verified |
| `docs/USER_LIFECYCLE_REPORT.md` | User lifecycle distribution report | Full categorization of all accounts | Phase 2 | Zero | Document inspection |
| `scripts/verify_data_preservation.py` | Active user preservation audit script | Audit all 18 user dimensions (MIG-002) | Phase 2 | Zero | Execution verified |
| `docs/USER_MIGRATION_PLAN.md` | Active user preservation plan | Preservation guarantees and checklist | Phase 2 | Zero | Document inspection |
| `scripts/migration_dry_run.py` | Automated migration dry-run engine | Sandbox testing with zero row loss (MIG-003) | Phase 2 | Zero | Execution verified |
| `docs/MIGRATION_DRY_RUN_REPORT.md` | Dry-run audit report | Sandbox execution metrics | Phase 2 | Zero | Document inspection |
| `scripts/detect_data_inconsistencies.py` | Data anomaly detection script | Audit inconsistencies (MIG-004) | Phase 2 | Zero | Execution verified |
| `DATA_INCONSISTENCIES.csv` | Exported data inconsistencies CSV | 82 tracked anomalies with recommendations | Phase 2 | Zero | CSV inspection |
| `services/application_service.py` | New Application State Machine service | Central transition function, validation, and optimistic locking (APP-001) | Phase 6 | Low | `pytest tests/test_application_state_machine.py` (7/7 passed) |
| `services/razorpay_client.py` | New Razorpay client wrapper & verifier | Server-side order creation, HMAC signature verification, webhook validation (PAY-001) | Phase 8 | Low | `pytest tests/test_payment_razorpay.py` (11/11 passed) |
| `static/js/payment_gateway.js` | New client payment gateway handler | Razorpay modal checkout with automatic dynamic QR fallback (PAY-004) | Phase 8 | Low | Frontend inspection |
| `app.py` | DDL for `application_status_history` & `payment_events`, column migrations for `enrollments`/`post_hire_deposits`/`course_payments`, endpoints `/api/payment/...` | Integrate state machine and Razorpay endpoints (APP-002, PAY-002, PAY-003) | Phase 6 & 8 | Medium | Full pytest suite (50/50 passed) |
| `tests/test_application_state_machine.py` | New unit & integration test suite | Verify state machine transitions, invalid jumps, unauthorized actors, concurrency (APP-004) | Phase 6 | Zero | 7/7 passed |
| `tests/test_payment_razorpay.py` | New payment unit & integration test suite | Verify config, signature verification, order creation, webhook idempotency (PAY-003) | Phase 8 | Zero | 11/11 passed |
| `tests/conftest.py` | Added Razorpay endpoints to CSRF exemptions in test harness | Ensure API endpoints can be tested cleanly without browser sessions | Test | Zero | Full test suite passed |
| `scripts/check_data_integrity.py` | New database integrity audit scanner script | Comprehensive multi-dimensional scanner across 12 dimensions (INT-001) | Phase 9 | Zero | Execution verified |
| `docs/DATA_INTEGRITY_REPORT.md` | New database integrity report | Full breakdown of database health and anomalies (INT-002) | Phase 9 | Zero | Document inspection |
| `services/enrollment_service.py` | New Enrollment State Machine service | Central transition function, state validation, and application sync (ENR-001) | Phase 7 | Low | `pytest tests/test_enrollment_state_machine.py` (7/7 passed) |
| `tests/test_enrollment_state_machine.py` | New enrollment unit & integration test suite | Verify enrollment transitions, invalid jumps, unauthorized roles, concurrency (ENR-004) | Phase 7 | Zero | 7/7 passed |
| `docs/ROLE_PERMISSION_MATRIX.md` | Role permission & anti-IDOR specification | Map all 5 roles, authorization checks, ownership constraints across all endpoints | Phase 11 | Zero | Document inspection |
| `tests/test_auth_regression.py` | Multi-role authentication regression test suite | 20 test cases covering intern (email/phone), company, mentor, staff, admin login, password reset, back-button cache denial | Phase 10 | Zero | 20/20 passed |
| `tests/test_idor_matrix.py` | Horizontal authorization and IDOR test suite | 14 test cases covering intern cross-user isolation, company isolation, and admin privilege escalation blocks | Phase 11 | Zero | 14/14 passed |
| `app.py` | Added duplicate phone registration validation to `/signup/stage1`, `/apply`, `/company/signup`; added anti-back-button `Cache-Control: no-store` headers to authenticated paths; testing timing-token bypass | Prevent duplicate phone account collision, history cache leaks, and enable automated testing | Phase 10 & 11 | Low | 91/91 passed |
| `tests/conftest.py` | Added `seed_mentor` / `login_as_mentor`, added signup & mutation endpoints to CSRF exemption list | Standardize mentor testing and allow direct test client requests | Harness | Zero | 91/91 passed |
| `tests/test_golden_journey.py` | New Golden Applicant Journey test suite | Automates 15-step end-to-end lifecycle and strict gate checks (GOLD-001, GOLD-002) | Phase 12 | Zero | 2/2 passed |
| `services/application_service.py` | Updated `VALID_APP_TRANSITIONS` for `STATUS_ENROLLMENT_PENDING` | Allow `STATUS_ACCEPTED` directly from `STATUS_ENROLLMENT_PENDING` upon admin verification | Phase 6 & 12 | Low | 93/93 passed |
| `app.py` | Updated `VALID_APP_TRANSITIONS` for `Enrollment Pending` | Keep transition map consistent with `application_service.py` | Phase 6 & 12 | Low | 93/93 passed |
| `tests/conftest.py` | Added `enroll` and `intern_save_wizard_step` to CSRF exemption list | Facilitates clean E2E testing of applicant enrollment and wizard state progression | Test | Zero | 93/93 passed |
| `tests/test_marketplace.py` | New Marketplace & Job Board test suite | 7 test cases covering company lifecycle, post lifecycle, candidate applications, live inventory counts (MKT-001 - MKT-004) | Phase 13 | Zero | 7/7 passed |
| `app.py` | Updated `_is_live_post()` to enforce `is_approved=1` and `is_active=1` on company | Closes security loophole where suspended companies' posts could still be accessed or applied to directly | Phase 13 | Low | 100/100 passed |
| `tests/conftest.py` | Added marketplace endpoints to CSRF exemptions and `is_approved`/`is_active` to `seed_company` | Enables automated company approval/suspension lifecycle testing | Test | Zero | 100/100 passed |
| `services/outbox_service.py` | New Transactional Event Outbox service | Implements outbox enqueuing, batch processor daemon, exponential backoff, dead-letter tracking, and replay for all 11 Master Plan event types (OUT-001, OUT-002) | Phase 14 | Low | `pytest tests/test_outbox_resilience.py` (11/11 passed) |
| `app.py` | Added `event_outbox` DDL in `init_db()`; decoupled email dispatching from user transactions; enqueued outbox events on application, enrollment, and staff task reviews | Guarantees business transaction durability regardless of SMTP health (OUT-001, OUT-003) | Phase 14 | Low | Full pytest suite (111/111 passed) |
| `services/application_service.py` | Enqueued `application.selected` and `application.rejected` in `transition_application()` | Emits transactional outbox events upon application state machine transitions | Phase 14 | Very Low | Full pytest suite (111/111 passed) |
| `services/enrollment_service.py` | Enqueued `payment.accepted` and `payment.rejected` in `transition_enrollment()`; fixed `name` in SELECT columns | Emits transactional outbox events upon enrollment state transitions | Phase 14 | Very Low | Full pytest suite (111/111 passed) |
| `tests/test_outbox_resilience.py` | New Outbox & Failure Resilience test suite | 11 test cases covering transactional decoupling, batch processing, exponential backoff, dead-letter replay, and email failure isolation (OUT-001 - OUT-003) | Phase 14 | Zero | 11/11 passed |



