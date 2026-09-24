# Decision Log

## DEC-001 — Adherence to Phase-Gated Safety Protocol
- **Date**: 2026-09-23
- **Decision**: Strictly follow the 28-phase lifecycle defined in `DBERT_PORTAL_NEXT_PHASE_MASTER_PLAN.md` starting with Phase 0 (Inventory) and Phase 1 (Safety Foundation). Do not modify business logic or schemas prior to passing safety gates.
- **Reason**: The application has active users and live data in production. Skipping to feature work or unverified migrations creates unacceptable risk of downtime or data loss.
- **Alternatives Considered**: Immediate refactoring of monolithic `app.py`. Rejected due to risk of untracked regression.
- **Impact**: Ensures deterministic, auditable evolution of the codebase.
- **Rollback**: N/A.

## DEC-002 — Remote Repository Push Restriction
- **Date**: 2026-09-23
- **Decision**: Restrict all git pushes strictly to `personal` (`https://github.com/ainabhinavsharma/Internshipportal.git`). Never push to `origin`.
- **Reason**: Required workspace rule.
- **Impact**: Protects organization repository from unintended direct commits.

## DEC-003 — Dynamic Razorpay Gateway with Zero-Downtime QR Fallback
- **Date**: 2026-09-23
- **Decision**: Architect Razorpay payment gateway integration across all checkout places (Security Deposit, Wizard, Job Deposit, Paid Program, LMS Courses) with dynamic fallback logic:
  - If `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` are configured: Turn off static QR code and screenshot uploads; display Razorpay Checkout modal with server-side order creation, HMAC signature verification, and instant state transition.
  - If keys are absent or revoked: Fall back to existing manual UPI QR code and screenshot verification queue in `/admin/enrollments`.
- **Reason**: Streamlines candidate onboarding and removes manual verification friction, while ensuring zero downtime or payment outages if gateway credentials are not yet provisioned.
- **Impact**: Added PAY-004 through PAY-010 to Phase 5 in `DBERT_PORTAL_NEXT_PHASE_MASTER_PLAN.md` and created `docs/PAYMENT_GATEWAY_PLAN.md`.
