# Task Queue

## P0 — Phase 0: System Inventory (COMPLETE)

- [x] INV-001 Route inventory (`docs/ROUTE_INVENTORY.md`)
- [x] INV-002 Feature inventory (`docs/FEATURE_INVENTORY.md`)
- [x] INV-003 Database inventory (`docs/DATABASE_INVENTORY.md`)
- [x] INV-004 External services inventory (`docs/EXTERNAL_SERVICES.md`)

## P0 — Phase 1: Production Safety Foundation (COMPLETE)

- [x] SAFE-001 Automated database backup script (`scripts/backup_db.py`)
- [x] SAFE-002 Backup restore verification script (`scripts/verify_backup_restore.py` & `docs/DATABASE_SAFETY.md`)
- [x] SAFE-003 Staging environment specification (`.env.staging.example` & `docs/STAGING_GUIDE.md`)
- [x] SAFE-004 Rollback plan (`docs/ROLLBACK_PLAN.md`)

## P1 — Phase 2: Active User Migration Framework (COMPLETE)

- [x] MIG-001 User lifecycle classification (`scripts/classify_user_lifecycle.py` & `docs/USER_LIFECYCLE_REPORT.md`)
- [x] MIG-002 Data preservation checklist (`scripts/verify_data_preservation.py` & `docs/USER_MIGRATION_PLAN.md`)
- [x] MIG-003 Migration dry-run harness (`scripts/migration_dry_run.py` & `docs/MIGRATION_DRY_RUN_REPORT.md`)
- [x] MIG-004 Data inconsistency reporter (`scripts/detect_data_inconsistencies.py` & `DATA_INCONSISTENCIES.csv`)

## P0 — Session 1: Setup & Baseline Establishment (COMPLETE)

- [x] S1-001 Preflight environment & target audit (`.agent/PREFLIGHT.md`)
- [x] S1-002 Environment safety scanner (`scripts/verify_env_safety.py`)
- [x] S1-003 Baseline test suite verification (32/32 tests passed, `.agent/BASELINE_TEST_RESULTS.md`)
- [x] S1-004 Remote alignment (`origin` -> `Internshipportal4.git`, upstream push disabled)
- [x] S1-005 Baseline commit & tag (`baseline/source-import`)

## P1 — Session 2: Phase 3 (Database, State Machine & Razorpay Infrastructure) (NEXT)

- [ ] APP-001 Central transition function (`transition_application()`)
- [ ] APP-002 Status history table (`application_status_history`)
- [ ] APP-003 Prevent direct status mutation in `app.py`
- [ ] APP-004 State transition automated test suite
- [ ] PAY-001 Razorpay client wrapper & config loader (`services/razorpay_client.py`)
- [ ] PAY-002 Razorpay order creation endpoints (`/api/razorpay/create-order`)
- [ ] PAY-003 Razorpay signature verification & webhook idempotency handler
- [ ] PAY-004 Dual payment UI (Razorpay button with dynamic QR fallback)
