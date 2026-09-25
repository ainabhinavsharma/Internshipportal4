# DBERT Internship Portal - Production Incident Runbook
**Document ID**: `INC-RUNBOOK-2026-PHASE21`  
**Execution Date**: September 25, 2026  
**Auditor**: Antigravity Local AI Agent (Session 14 / Phase 21)  
**Target Repository**: `ainabhinavsharma/Internshipportal4` (Branch: `main`)

---

## 1. Incident Management Lifecycle & Protocol

Every production incident follows a strict 5-stage response lifecycle:

```text
    ┌──────────┐     ┌───────────┐     ┌────────────┐     ┌───────────┐     ┌──────────────┐
    │  DETECT  │ ──> │  CONTAIN  │ ──> │  MITIGATE  │ ──> │  RESOLVE  │ ──> │ POST-MORTEM  │
    └──────────┘     └───────────┘     └────────────┘     └───────────┘     └──────────────┘
```

1. **DETECT**: Identify symptoms through alerts, telemetry rates (5xx/4xx), liveness/readiness probes (`/health`, `/ready`), and customer reports.
2. **CONTAIN**: Isolate the blast radius, activate kill switches, enable circuit breakers, or divert traffic to prevent further damage.
3. **MITIGATE**: Restore critical customer workflows immediately via fallbacks, secondary channels, or rollbacks.
4. **RESOLVE**: Identify the root cause, apply durable fixes, verify system health, and clear incident state.
5. **POST-MORTEM**: Document the incident timeline, impact, root cause, and preventative action items.

---

## 2. Telemetry & Observability Health Probes

The portal provides dual observability probes:
- **Liveness Probe** (`/health`): Returns HTTP 200 `{"status": "ok", "service": "dbert-portal", "uptime_seconds": ...}` indicating the application process is running and accepting HTTP connections.
- **Readiness Probe** (`/ready`): Returns HTTP 200 `{"status": "ready", "checks": {"database_connected": true, "wal_mode": true, "tables_accessible": true, "outbox_healthy": true}}` indicating the database is accessible, WAL mode is active, core tables exist, and the outbox dead-letter queue is below alert thresholds.
- **Admin Metrics API** (`/admin/telemetry`): Provides real-time request counts, 4xx/5xx error rates, failure categorizations, and latency percentiles (p50, p95, p99).

---

## 3. Incident Scenarios & Standard Operating Procedures (SOPs)

---

### Incident 1: Site Down / 502 Bad Gateway / Web Process Crash
- **DETECT**:
  - Load balancer or uptime checker reports `/health` probe failure (502 / 503 / connection refused).
  - Telemetry `5xx_error_rate_pct` spikes above 1%.
  - Systemd / Gunicorn status shows `failed` or high worker restarts.
- **CONTAIN**:
  - Check system resources: `free -m`, `top -b -n 1`, `df -h`.
  - Check Nginx reverse proxy logs: `tail -n 100 /var/log/nginx/error.log`.
  - Check Gunicorn application logs: `journalctl -u dbert-portal -n 100 --no-pager`.
- **MITIGATE**:
  - Restart application process: `sudo systemctl restart dbert-portal`.
  - Verify process binds properly to local socket/port 5000: `curl -I http://127.0.0.1:5000/health`.
  - If process fails due to memory exhaustion, temporarily increase swap or restart idle background daemons.
- **RESOLVE**:
  - Inspect structured logs for unhandled exception or circular import crashing workers on startup.
  - Test `/health` and `/ready` endpoints until both return HTTP 200.
- **POST-MORTEM**:
  - File issue detailing root cause (e.g. OOM, worker timeout, bad dependency) and adjust Gunicorn worker count / memory limits.

---

### Incident 2: Database Corruption / Lock Contention / Operational Error
- **DETECT**:
  - `/ready` returns HTTP 503 `{"status": "not_ready", "error": "database is locked"}` or operational error.
  - Telemetry logs increment `db_failures` metric.
  - Log records show `sqlite3.OperationalError: database is locked` or `database disk image is malformed`.
- **CONTAIN**:
  - Terminate any long-running uncommitted processes or zombie background workers:
    ```bash
    fuser -v internship.db
    ```
  - Put site in temporary read-only or maintenance mode if writes are corrupted.
- **MITIGATE**:
  - Run database integrity check:
    ```bash
    sqlite3 internship.db "PRAGMA integrity_check;"
    sqlite3 internship.db "PRAGMA quick_check;"
    ```
  - If locked, check if WAL files (`internship.db-wal`, `internship.db-shm`) are bloated. Run WAL checkpoint:
    ```bash
    sqlite3 internship.db "PRAGMA wal_checkpoint(TRUNCATE);"
    ```
  - If corrupted, restore from latest automated backup:
    ```bash
    python scripts/verify_backup_restore.py --latest
    python scripts/backup_db.py --restore-latest
    ```
- **RESOLVE**:
  - Run `python scripts/check_data_integrity.py` to confirm zero critical data inconsistencies.
  - Verify `/ready` returns HTTP 200.
- **POST-MORTEM**:
  - Audit database connection lifecycles in `get_db()`; ensure all connections use context managers (`with get_db() as conn:`) and commit/close cleanly.

---

### Incident 3: Email Outage / SMTP Failure / Outbox Backlog
- **DETECT**:
  - Telemetry `email_failures` counter increases.
  - `event_outbox` table shows accumulating `pending` or `dead_letter` status rows.
  - SMTP connection timeouts logged in `log_error("smtp", e)`.
- **CONTAIN**:
  - The portal's transactional outbox architecture prevents user business transactions from failing when SMTP is down.
  - Application submissions, enrollments, and payments will continue to succeed and record into `event_outbox`.
- **MITIGATE**:
  - Inspect outbox health via SQL:
    ```sql
    SELECT status, COUNT(*) FROM event_outbox GROUP BY status;
    SELECT * FROM event_outbox WHERE status='dead_letter' ORDER BY id DESC LIMIT 5;
    ```
  - Check SMTP credentials and port connectivity (`smtp.gmail.com:587` or SES).
  - If provider is experiencing global outage, temporarily switch `SMTP_HOST` to backup relay.
- **RESOLVE**:
  - Once SMTP connectivity is restored, trigger outbox batch processing:
    ```bash
    python -c "from app import get_db; from services.outbox_service import process_outbox_batch; conn = get_db(); print(process_outbox_batch(conn, limit=100))"
    ```
  - Replay dead-letter events after root cause fix:
    ```bash
    python -c "from app import get_db; from services.outbox_service import replay_dead_letters; conn = get_db(); print(replay_dead_letters(conn))"
    ```
- **POST-MORTEM**:
  - Review SMTP quota limits, bounce rates, and dead-letter alert thresholds.

---

### Incident 4: Payment Problem / Webhook Delivery Failure / Signature Errors
- **DETECT**:
  - Telemetry `payment_failures` counter increases.
  - Users report payment deduction but enrollment remains in `Pending Verification`.
  - Logs show `RazorpaySignatureVerificationError` or webhook 400 responses.
- **CONTAIN**:
  - Check `/api/payment/config` to verify whether Razorpay gateway is active or has fallen back to Dynamic UPI QR.
  - If Razorpay API is down, activate UPI QR fallback mode automatically by setting `RAZORPAY_KEY_ID=""` in environment.
- **MITIGATE**:
  - Check `payment_events` table for unhandled or duplicate webhook events:
    ```sql
    SELECT event_id, event_type, status, created_at FROM payment_events ORDER BY id DESC LIMIT 10;
    ```
  - Compare transaction reference numbers against Razorpay Dashboard.
  - If payment verified on Razorpay but webhook missed, manually transition enrollment via admin portal or CLI:
    ```bash
    python -c "from app import get_db; from services.enrollment_service import transition_enrollment; conn = get_db(); transition_enrollment(conn, enrollment_id=123, new_status='Accepted', actor='admin', actor_role='admin', reason='Manual reconciliation')"
    ```
- **RESOLVE**:
  - Re-verify webhook secret `RAZORPAY_WEBHOOK_SECRET` matches Razorpay developer console.
  - Verify webhook signature verification test passes: `pytest tests/test_payment_razorpay.py`.
- **POST-MORTEM**:
  - Reconcile all payments in the incident window with `enrollments` records.

---

### Incident 5: AI Outage / Tutor Token Degradation / Provider Downtime
- **DETECT**:
  - Telemetry `ai_failures` counter increases.
  - Users report AI tutor response errors or timeout spinners on lesson pages.
  - Gemini / OpenAI API responses return 429 (quota exceeded) or 503 (service unavailable).
- **CONTAIN**:
  - Lessons and quiz questions must degrade gracefully to static curated content.
  - Ensure student progress is never blocked if AI hint or tutor generation is unavailable.
- **MITIGATE**:
  - Verify API keys and rate quotas in provider console.
  - If primary model is down, switch model fallback configuration (e.g. `gemini-1.5-pro` -> `gemini-1.5-flash`).
- **RESOLVE**:
  - Update API key or restore provider balance.
  - Verify `/generate-tutor-token` or AI tutor endpoints respond within SLA.
- **POST-MORTEM**:
  - Implement client-side exponential backoff and cached responses for standard lesson prompts.

---

### Incident 6: Authentication Failure / Mass Lockout / Password Reset Issues
- **DETECT**:
  - Telemetry `login_failures` or `auth_failures` rate spikes.
  - Users report "Invalid credentials" or repeated lockouts.
  - Rate limiting table `rate_events` shows abnormal IP / bucket counts.
- **CONTAIN**:
  - Check if a credential stuffing or brute force attack is occurring:
    ```sql
    SELECT ip, route, reason, COUNT(*) FROM abuse_log WHERE timestamp > datetime('now', '-1 hour') GROUP BY ip ORDER BY COUNT(*) DESC LIMIT 10;
    ```
  - If a distributed attack is occurring, block offending IPs at Nginx or Cloudflare firewall level.
- **MITIGATE**:
  - If legitimate users are locked out due to strict rate limiting, clear rate events for specific accounts:
    ```sql
    DELETE FROM rate_events WHERE bucket='loginfail:email:user@example.com';
    ```
  - Verify password hashing and session tokens:
    ```bash
    pytest tests/security/test_phase1_auth.py
    ```
- **RESOLVE**:
  - Ensure Werkzeug password hashing verification is intact.
  - Verify session cookie issuance (`AUTH_COOKIE`, `HttpOnly`, `SameSite=Lax`).
- **POST-MORTEM**:
  - Tune lockout threshold windows (`RL_LOGIN_EMAIL`) and rate-limiting multipliers.

---

### Incident 7: File Storage Outage / Upload Corruption
- **DETECT**:
  - Telemetry `upload_failures` counter increases.
  - Users report 400 "Invalid file type" or 413 "File too large" errors on CV or payment proof uploads.
  - Storage disk space alerts (`df -h`).
- **CONTAIN**:
  - Inspect `uploads/` directory disk space: `du -sh uploads/`.
  - Check file permissions: `ls -ld uploads/` (must be writable by web process user).
- **MITIGATE**:
  - If disk space is full, safely purge old temporary files or compress stale assets.
  - Verify magic byte sniffer is accepting legitimate PNG, JPEG, and PDF documents:
    ```bash
    pytest tests/security/test_phase6_uploads.py
    ```
- **RESOLVE**:
  - Restore required disk space and fix directory write permissions.
- **POST-MORTEM**:
  - Set up disk space monitoring alerts at 80% and 90% utilization.

---

### Incident 8: Bad Deployment / Failed Migration / Schema Breakage
- **DETECT**:
  - Immediately following a `git pull` or service restart, `/ready` returns 503 or routes crash.
  - Unhandled 500 exceptions logged across newly deployed routes.
- **CONTAIN**:
  - Immediately stop forward deployment actions.
- **MITIGATE**:
  - Execute the rollback runbook (`docs/ROLLBACK_PLAN.md`):
    ```bash
    # 1. Revert to previous release git commit tag
    git log -n 5 --oneline
    git checkout <LAST_KNOWN_GOOD_TAG>

    # 2. Restore database schema if migrations modified tables
    python scripts/verify_backup_restore.py --latest
    python scripts/backup_db.py --restore-latest

    # 3. Restart application service
    sudo systemctl restart dbert-portal
    ```
- **RESOLVE**:
  - Verify system returns to green on `/health` and `/ready`.
  - Run regression test suite: `pytest -v -k "not chromium"`.
- **POST-MORTEM**:
  - Investigate the failing commit in an isolated local staging branch. Add missing migration scripts or compatibility layers before attempting release again.

---

### Incident 9: Security Incident / Credential Leak / Unauthorized Access
- **DETECT**:
  - Alert triggered by `scripts/verify_env_safety.py` detecting sensitive strings or databases.
  - Abuse log reports abnormal admin route probes from non-whitelisted IPs.
  - Unexplained modifications to `intern_accounts` or `companies`.
- **CONTAIN**:
  - Invalidate all active user and admin sessions immediately:
    ```sql
    DELETE FROM user_sessions;
    ```
  - Rotate all administrative passwords and secrets (`FLASK_SECRET_KEY`, `ADMIN_PASSWORD`, `ADMIN_KEY`, `CRON_SECRET`, `RAZORPAY_KEY_SECRET`).
  - Block attacker IP addresses at the firewall / Nginx level.
- **MITIGATE**:
  - Inspect git history and tracked files:
    ```bash
    python scripts/verify_env_safety.py
    ```
  - Review `abuse_log` and `application_status_history` for unauthorized actions during the incident window.
- **RESOLVE**:
  - Deploy rotated secrets to environment configuration files.
  - Require affected users to reset their passwords via `/forgot-password`.
- **POST-MORTEM**:
  - Complete security vulnerability assessment report and implement defense-in-depth countermeasures.

---

## 4. Post-Mortem Template

Every P0 or P1 incident must produce a post-mortem document within 24 hours:

```markdown
# Incident Post-Mortem: [Incident Title]
**Date**: [YYYY-MM-DD]  
**Severity**: [P0 - Critical / P1 - Major / P2 - Moderate]  
**Lead Responder**: [Name / Agent]  

### Summary
[Brief description of what happened, customer impact, and duration]

### Timeline (UTC)
- HH:MM - First anomaly detected
- HH:MM - Responder acknowledged incident
- HH:MM - Blast radius contained
- HH:MM - Mitigation applied
- HH:MM - Full resolution confirmed

### Root Cause
[Technical explanation of the underlying failure mechanism]

### Action Items
- [ ] [Preventative Fix 1] (Owner, Target Date)
- [ ] [Monitoring / Alerting Enhancement] (Owner, Target Date)
- [ ] [Documentation / Runbook Update] (Owner, Target Date)
```
