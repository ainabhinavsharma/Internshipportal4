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


