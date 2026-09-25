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

## P1 — Session 2: State Machine & Razorpay Infrastructure (COMPLETE)

- [x] APP-001 Central transition function (`transition_application()` in `services/application_service.py`)
- [x] APP-002 Status history table (`application_status_history` in `init_db()`)
- [x] APP-003 Prevent direct status mutation in `app.py` (`mentor_update_status`, `admin_update_application_status`, `/enroll`, `/paid/enroll`)
- [x] APP-004 State transition automated test suite (`tests/test_application_state_machine.py`)
- [x] PAY-001 Razorpay client wrapper & config loader (`services/razorpay_client.py`)
- [x] PAY-002 Razorpay order creation endpoints (`/api/payment/razorpay/create-order`)
- [x] PAY-003 Razorpay signature verification & webhook idempotency handler (`/api/payment/razorpay/verify-payment`, `/api/payment/razorpay/webhook`, `payment_events`)
- [x] PAY-004 Dual payment UI (Razorpay button with dynamic QR fallback in `static/js/payment_gateway.js`)

## P1 — Session 3: Database Integrity Engine & Enrollment State Machine (COMPLETE)

- [x] INT-001 Database integrity detector script (`scripts/check_data_integrity.py`)
- [x] INT-002 Automatic integrity report generation (`docs/DATA_INTEGRITY_REPORT.md`)
- [x] ENR-001 Enrollment lifecycle transition service (`services/enrollment_service.py`)
- [x] ENR-002 Audit history table `enrollment_status_history` in `init_db()`
- [x] ENR-003 Stale request & optimistic concurrency protection (`expected_status`)
- [x] ENR-004 Enrollment state machine automated test suite (`tests/test_enrollment_state_machine.py`)

## P1 — Session 4: Authentication Regression & IDOR Authorization (COMPLETE)

- [x] AUTH-DOC Role Permission and IDOR Matrix specification (`docs/ROLE_PERMISSION_MATRIX.md`)
- [x] AUTH-001 End-to-end multi-role authentication regression suite (`tests/test_auth_regression.py`)
- [x] AUTH-002 Duplicate identity guards (email & phone uniqueness) in `app.py`
- [x] AUTH-003 Password reset lifecycle (neutral enumeration, expiry, replay, old session revocation)
- [x] AUTH-004 Back-button cache-control denial & session revocation in `app.py`
- [x] IDOR-001 Horizontal authorization enforcement audit across all user routes
- [x] IDOR-002 IDOR test suite covering intern profiles, documents, tasks, and payments (`tests/test_idor_matrix.py`)
- [x] IDOR-003 Vertical privilege escalation defenses (intern/company/mentor blocks from admin/staff)

## P1 — Session 5: Golden Applicant Journey (COMPLETE)

- [x] GOLD-001 Complete applicant lifecycle E2E automation (Visitor -> Signup -> Application -> Review -> Selection -> Enrollment -> Payment -> Course -> Task -> Certificate -> Public Verification) (`tests/test_golden_journey.py`)
- [x] GOLD-002 Golden path test suite with strict state gates and non-existent cert verification checks

## P1 — Session 6: Marketplace / Job Board Verification (COMPLETE)

- [x] MKT-001 Company registration, approval, suspension, and authorization controls (`tests/test_marketplace.py`)
- [x] MKT-002 Job listing lifecycle: draft, Google-for-Jobs 100-character description completeness gate, publish, atomic max 3 live posts guard, unpublish, expire
- [x] MKT-003 Candidate job application flow: anonymous 401 guard, candidate apply, idempotent re-apply, company applicant review, status progression (Shortlisted, Hired)
- [x] MKT-004 Live database-backed inventory counts (`live_openings_total()`), draft/suspension exclusions, expired listing CTA suppression (410 Gone)
## P1 — Session 7: Email / Event Outbox & Failure Resilience (COMPLETE)

- [x] OUT-001 Email/Event outbox table & transaction-safe decoupled queuing (`services/outbox_service.py`, `app.py`)
- [x] OUT-002 Outbox worker daemon with exponential backoff & dead-letter queue (`tests/test_outbox_resilience.py`)
- [x] OUT-003 Failure isolation: critical user transactions succeed even when SMTP fails

## P1 — Session 8: File Security & Upload Sandbox Audit (COMPLETE)

- [x] FILE-001 Upload sandbox validation audit (CVs, payment screenshots, avatar photos, capstone files) (`services/file_security_service.py`, `app.py`)
- [x] FILE-002 MIME type, magic bytes, file size limits, polyglot/script rejection, and CSV formula injection sanitization (`tests/test_upload_sandbox.py`)
- [x] FILE-003 Path traversal prevention & private file download object-level authorization (IDOR defense on `/uploads/<path:filename>`)

## P1 — Session 9: Privacy & Field Classification (COMPLETE)

- [x] PRIV-001 Field classification engine (PUBLIC, PRIVATE, ADMIN_ONLY, SENSITIVE) (`services/privacy_service.py`)
- [x] PRIV-002 API response serializer hardening & default sensitive field stripping in `row_to_dict` (prevent raw user/database model leaks to public endpoints) (`app.py`, `services/privacy_service.py`)
- [x] PRIV-003 Multi-role privacy access test suite (anonymous, other intern, mentor, company, admin) (`tests/test_privacy_field_classification.py`)

## P1 — Session 10: UX Dead-End & Error Resolution Audit (COMPLETE)

- [x] UX-001 Navigation and empty state consistency audit with active recovery CTAs across public listings and role dashboards (`templates/post_listings.html`, `services/ux_audit_service.py`)
- [x] UX-002 Comprehensive error handler audit (400, 401, 403, 404, 410, 500) answering what happened, why, and what the user can do (`app.py`, `templates/error.html`)
- [x] UX-003 Dead-end detection test suite verifying error pages, recovery links, and no unhandled 500s or loops (`tests/test_ux_dead_ends.py`)

## P1 — Session 11: Mobile & Accessibility Responsive Audit (COMPLETE)

- [x] MOB-001 Viewport matrix verification (360x800, 390x844, 412x915, 768x1024, 1366x768, 1920x1080) (`services/accessibility_service.py`, `scripts/audit_mobile_accessibility.py`)
- [x] MOB-002 Critical workflow accessibility audit (keyboard focus visible, WCAG AA contrast, form labels, ARIA dialog roles, skip links across signup, login, portal, jobs, courses, tasks, payments, admin, company)
- [x] MOB-003 Responsive layout and touch targets automated test suite (18/18 passed in `tests/test_mobile_accessibility.py`, 3/3 passed in `tests/e2e/test_phase9_a11y.py`)
## P1 — Session 12: Performance & Production Readiness Audit (COMPLETE)

- [x] PERF-001 Endpoint Latency SLA & Baseline Benchmarks (`services/performance_service.py`, `scripts/benchmark_performance.py`, `docs/PERFORMANCE_BASELINE.md`)
- [x] PERF-002 Database Query Optimization & N+1 / Unbounded Query Profiling (`app.py` indexes, server-side pagination on `/admin/applications`, `/admin/enrollments`, `/admin/users`, query profiler)
- [x] PERF-003 Static Asset Audit & High-Performance Caching Strategy (Static asset inventory, Cache-Control: immutable, 1-year max-age, test suite `tests/test_performance_baseline.py` 16/16 passed, test password hashing speedup)

## P1 — Session 13: Security Regression & Vulnerability Audit (COMPLETE)

- [x] SEC-REG-001 Automated Dependency Audit with `pip-audit` (Zero known CVEs across pinned production dependencies)
- [x] SEC-REG-002 Bandit AST Security Linter (`bandit.yaml`, 0 High, 0 Medium, 0 Low with audited `# nosec B608` justifications)
- [x] SEC-REG-003 CSRF Protection Architecture & Verification (Timing-safe digest verification, body/header extraction, webhook/cron exemptions)
- [x] SEC-REG-004 Session & Cookie Security Architecture (HttpOnly, SameSite=Lax, Path=/, token rotation on login, server-side DB purge on logout)
- [x] SEC-REG-005 Security Regression Test Suite (`tests/security/test_security_regression.py`, 27/27 tests passed; full test suite 217/217 passed; `scripts/audit_security.py` & `docs/SECURITY_AUDIT_REPORT.md`)

## P1 — Session 14: Observability, Telemetry & Incident Response (COMPLETE)

- [x] OBS-001 Request ID Tracing & Latency Header Injection (`g.request_id`, `X-Request-ID`, `X-Request-Duration-Ms`, status history propagation)
- [x] OBS-002 Centralized Telemetry & Metrics Service (`services/telemetry_service.py`, thread-safe collection of requests, status code buckets, failure categorizations, latency percentiles)
- [x] OBS-003 Upgraded Liveness (`/health`) and Readiness (`/ready`) Probes with DB, WAL mode, tables, and outbox checks
- [x] OBS-004 Production Incident Runbook (`docs/INCIDENT_RUNBOOK.md` covering all 9 disaster scenarios with DETECT, CONTAIN, MITIGATE, RESOLVE, POST-MORTEM lifecycle)
- [x] OBS-005 Observability & Telemetry Test Suite (`tests/test_observability.py` 12/12 passed, 229/229 full suite passed)


