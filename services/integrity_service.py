"""Data Integrity & Health Analytics Service.

Implements Phase 26 requirements (§53 of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md).
Provides admin visibility into all platform entity clusters (users, applications, enrollments,
payments, active interns, completed interns, certificates) and detects the 6 required integrity
anomalies with safe remediation / self-healing capabilities.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("integrity_service")


class IntegrityService:
    """Central engine for computing platform entity metrics and detecting data anomalies."""

    @staticmethod
    def _table_exists(conn: Any, table_name: str) -> bool:
        cur = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        )
        return cur.fetchone() is not None

    @staticmethod
    def get_platform_metrics(conn: Any) -> Dict[str, Any]:
        """Gathers quantitative metrics across all 7 platform entity clusters."""
        metrics: Dict[str, Any] = {}

        # 1. Users
        interns_count = conn.execute("SELECT COUNT(*) FROM intern_accounts").fetchone()[0]
        companies_count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        approved_companies = conn.execute(
            "SELECT COUNT(*) FROM companies WHERE is_approved = 1 AND is_active = 1"
        ).fetchone()[0]
        mentors_count = conn.execute("SELECT COUNT(*) FROM mentors").fetchone()[0]
        staff_count = conn.execute(
            "SELECT COUNT(*) FROM staff_accounts WHERE is_active = 1"
        ).fetchone()[0]

        metrics["users"] = {
            "total_interns": interns_count,
            "total_companies": companies_count,
            "approved_companies": approved_companies,
            "total_mentors": mentors_count,
            "total_staff": staff_count,
            "total_users": interns_count + companies_count + mentors_count + staff_count,
        }

        # 2. Applications
        total_apps = conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        status_rows = conn.execute(
            "SELECT status, COUNT(*) FROM applications GROUP BY status"
        ).fetchall()
        app_by_status = {r[0]: r[1] for r in status_rows}

        metrics["applications"] = {
            "total": total_apps,
            "apply_pending": app_by_status.get("Apply Pending", 0),
            "under_review": app_by_status.get("Under Review", 0),
            "selected": app_by_status.get("Selected", 0),
            "enrollment_pending": app_by_status.get("Enrollment Pending", 0),
            "accepted": app_by_status.get("Accepted", 0),
            "rejected": app_by_status.get("Rejected", 0),
            "by_status": app_by_status,
        }

        # 3. Enrollments
        total_enr = conn.execute("SELECT COUNT(*) FROM enrollments").fetchone()[0]
        enr_status_rows = conn.execute(
            "SELECT payment_status, COUNT(*) FROM enrollments GROUP BY payment_status"
        ).fetchall()
        enr_by_status = {r[0]: r[1] for r in enr_status_rows}

        metrics["enrollments"] = {
            "total": total_enr,
            "verified": enr_by_status.get("Verified", 0) + enr_by_status.get("Accepted", 0),
            "pending": enr_by_status.get("Pending", 0) + enr_by_status.get("Pending Verification", 0) + enr_by_status.get("Under Review", 0),
            "rejected": enr_by_status.get("Rejected", 0),
            "by_status": enr_by_status,
        }

        # 4. Payments
        total_payments = 0
        verified_volume = 0
        payment_events_count = 0

        # Course payments
        if IntegrityService._table_exists(conn, "course_payments"):
            cp_count = conn.execute("SELECT COUNT(*) FROM course_payments").fetchone()[0]
            cp_vol_row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM course_payments WHERE status IN ('Verified', 'success', 'paid')"
            ).fetchone()
            total_payments += cp_count
            verified_volume += (cp_vol_row[0] if cp_vol_row else 0)

        # Legacy payments table (if present)
        if IntegrityService._table_exists(conn, "payments"):
            p_count = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
            p_vol_row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status IN ('Verified', 'Accepted', 'success')"
            ).fetchone()
            total_payments += p_count
            verified_volume += (p_vol_row[0] if p_vol_row else 0)

        # Enrollments payments
        enr_cols = [r["name"] for r in conn.execute("PRAGMA table_info(enrollments)").fetchall()]
        if "amount_paid" in enr_cols:
            enr_vol_row = conn.execute(
                "SELECT COALESCE(SUM(amount_paid), 0) FROM enrollments WHERE payment_status IN ('Verified', 'Accepted')"
            ).fetchone()
            verified_volume += (enr_vol_row[0] if enr_vol_row else 0)

        if IntegrityService._table_exists(conn, "payment_events"):
            payment_events_count = conn.execute("SELECT COUNT(*) FROM payment_events").fetchone()[0]

        metrics["payments"] = {
            "total_records": total_payments,
            "verified_volume_inr": verified_volume,
            "events_logged": payment_events_count,
        }

        # 5. Active Interns (Accepted applications with enrolled cohorts or tasks)
        active_interns = conn.execute(
            "SELECT COUNT(DISTINCT ia.id) FROM intern_accounts ia "
            "JOIN applications a ON LOWER(ia.email) = LOWER(a.email) "
            "WHERE a.status = 'Accepted'"
        ).fetchone()[0]

        metrics["active_interns"] = {
            "count": active_interns,
        }

        # 6. Completed Interns (Interns who have earned certificates or finished required coursework)
        completed_interns = conn.execute(
            "SELECT COUNT(DISTINCT intern_id) FROM intern_certificates"
        ).fetchone()[0]

        metrics["completed_interns"] = {
            "count": completed_interns,
        }

        # 7. Certificates
        total_certs = conn.execute("SELECT COUNT(*) FROM intern_certificates").fetchone()[0]
        metrics["certificates"] = {
            "total_issued": total_certs,
        }

        return metrics

    @staticmethod
    def get_integrity_anomalies(conn: Any) -> Dict[str, Any]:
        """Audits the database across all 6 Master Plan anomaly categories."""
        anomalies: Dict[str, Any] = {}
        critical_count = 0
        warning_count = 0
        info_count = 0

        # 1. Orphan applications (blank email, or no domain)
        orphan_apps_rows = conn.execute(
            "SELECT id, name, email, domain, status, created_at FROM applications "
            "WHERE email IS NULL OR TRIM(email) = '' OR domain IS NULL OR TRIM(domain) = ''"
        ).fetchall()
        orphan_apps = [
            {"id": r["id"], "name": r["name"], "email": r["email"], "domain": r["domain"], "status": r["status"]}
            for r in orphan_apps_rows
        ]
        anomalies["orphan_applications"] = {
            "count": len(orphan_apps),
            "items": orphan_apps[:20],
            "severity": "WARNING" if orphan_apps else "CLEAN",
        }
        warning_count += len(orphan_apps)

        # 2. Orphan enrollments (application_id missing or not in applications table)
        orphan_enr_rows = conn.execute(
            "SELECT id, email, domain, payment_status, created_at FROM enrollments "
            "WHERE application_id IS NOT NULL AND application_id NOT IN (SELECT id FROM applications)"
        ).fetchall()
        orphan_enr = [
            {"id": r["id"], "email": r["email"], "domain": r["domain"], "payment_status": r["payment_status"]}
            for r in orphan_enr_rows
        ]
        anomalies["orphan_enrollments"] = {
            "count": len(orphan_enr),
            "items": orphan_enr[:20],
            "severity": "WARNING" if orphan_enr else "CLEAN",
        }
        warning_count += len(orphan_enr)

        # 3. Duplicate active applications (same email with >1 concurrent in-flight application)
        dup_apps_rows = conn.execute(
            "SELECT email, COUNT(*) as cnt, GROUP_CONCAT(status) as statuses, GROUP_CONCAT(domain) as domains "
            "FROM applications "
            "WHERE status NOT IN ('Rejected', 'Accepted', 'Completed') "
            "GROUP BY email HAVING cnt > 1"
        ).fetchall()
        dup_apps = [
            {"email": r["email"], "count": r["cnt"], "statuses": r["statuses"], "domains": r["domains"]}
            for r in dup_apps_rows
        ]
        anomalies["duplicate_active_applications"] = {
            "count": len(dup_apps),
            "items": dup_apps[:20],
            "severity": "INFO" if dup_apps else "CLEAN",
        }
        info_count += len(dup_apps)

        # 4. Impossible lifecycle states
        # Contradiction: Application rejected but enrollment accepted/verified
        impossible_rows = conn.execute(
            "SELECT e.id as enrollment_id, a.id as application_id, a.email, a.status as app_status, e.payment_status "
            "FROM enrollments e "
            "JOIN applications a ON (e.application_id = a.id OR LOWER(e.email) = LOWER(a.email)) "
            "WHERE a.status = 'Rejected' AND e.payment_status IN ('Accepted', 'Verified')"
        ).fetchall()
        # Contradiction: Certificate issued to intern whose application was never Accepted
        cert_contradiction_rows = conn.execute(
            "SELECT c.id, c.cert_id, c.intern_id, ia.email "
            "FROM intern_certificates c "
            "LEFT JOIN intern_accounts ia ON c.intern_id = ia.id "
            "WHERE ia.id IS NULL OR LOWER(ia.email) NOT IN (SELECT LOWER(email) FROM applications WHERE status = 'Accepted')"
        ).fetchall()

        impossible_items = []
        for r in impossible_rows:
            impossible_items.append({
                "type": "REJECTED_APP_VERIFIED_ENROLLMENT",
                "application_id": r["application_id"],
                "enrollment_id": r["enrollment_id"],
                "email": r["email"],
                "detail": f"Application status is 'Rejected' but enrollment is '{r['payment_status']}'",
            })
        for r in cert_contradiction_rows:
            email_val = r["email"] or f"Unknown (intern_id={r['intern_id']})"
            impossible_items.append({
                "type": "CERTIFICATE_WITHOUT_ACCEPTED_APPLICATION",
                "certificate_id": r["id"],
                "cert_id": r["cert_id"],
                "email": email_val,
                "detail": f"Certificate #{r['cert_id']} issued to {email_val} but no application in 'Accepted' state exists",
            })


        anomalies["impossible_states"] = {
            "count": len(impossible_items),
            "items": impossible_items[:20],
            "severity": "CRITICAL" if impossible_items else "CLEAN",
        }
        critical_count += len(impossible_items)

        # 5. Expired live listings (published posts past expiry date or belonging to suspended company)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        expired_posts_rows = conn.execute(
            "SELECT p.id, p.title, p.company_id, p.status, p.expires_at, "
            "c.name as company_name, c.is_approved, c.is_active "
            "FROM posts p "
            "LEFT JOIN companies c ON p.company_id = c.id "
            "WHERE p.status = 'published' AND ("
            "  (p.expires_at IS NOT NULL AND p.expires_at < ?) "
            "  OR (c.is_approved = 0 OR c.is_active = 0)"
            ")",
            (now_str,),
        ).fetchall()

        expired_listings = [
            {
                "post_id": r["id"],
                "title": r["title"],
                "company_id": r["company_id"],
                "company_name": r["company_name"] or "Unknown",
                "expires_at": r["expires_at"],
                "reason": "Passed expiration date" if r["expires_at"] and r["expires_at"] < now_str else "Company inactive or unapproved",
            }
            for r in expired_posts_rows
        ]
        anomalies["expired_live_listings"] = {
            "count": len(expired_listings),
            "items": expired_listings[:20],
            "severity": "WARNING" if expired_listings else "CLEAN",
        }
        warning_count += len(expired_listings)

        # 6. Failed critical jobs (Dead-letter outbox events)
        failed_jobs: List[Dict[str, Any]] = []
        if IntegrityService._table_exists(conn, "event_outbox"):
            failed_jobs_rows = conn.execute(
                "SELECT id, event_type, aggregate_type, aggregate_id, retry_count, max_retries, last_error, created_at "
                "FROM event_outbox "
                "WHERE status = 'DEAD_LETTER' OR retry_count >= max_retries"
            ).fetchall()

            failed_jobs = [
                {
                    "id": r["id"],
                    "event_type": r["event_type"],
                    "aggregate_type": r["aggregate_type"],
                    "aggregate_id": r["aggregate_id"],
                    "retry_count": r["retry_count"],
                    "last_error": r["last_error"],
                    "created_at": r["created_at"],
                }
                for r in failed_jobs_rows
            ]

        anomalies["failed_critical_jobs"] = {
            "count": len(failed_jobs),
            "items": failed_jobs[:20],
            "severity": "CRITICAL" if failed_jobs else "CLEAN",
        }
        critical_count += len(failed_jobs)

        # Overall Health Score calculation
        score = 100.0 - (critical_count * 15.0) - (warning_count * 2.0) - (info_count * 0.5)
        score = max(0.0, min(100.0, round(score, 1)))

        if critical_count > 0:
            status = "CRITICAL"
        elif warning_count > 0:
            status = "WARNING"
        else:
            status = "HEALTHY"

        anomalies["summary"] = {
            "health_score": score,
            "status": status,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "total_anomalies": critical_count + warning_count + info_count,
        }

        return anomalies

    @staticmethod
    def heal_anomalies(conn: Any, action: str, dry_run: bool = True) -> Dict[str, Any]:
        """Performs safe self-healing / remediation on detected anomalies.
        
        Supported actions:
          - 'expire_stale_listings': Transitions published posts past expiry or from suspended companies to 'expired'.
          - 'archive_dead_letters': Archives failed dead-letter outbox events.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        if action == "expire_stale_listings":
            rows = conn.execute(
                "SELECT p.id, p.title FROM posts p "
                "LEFT JOIN companies c ON p.company_id = c.id "
                "WHERE p.status = 'published' AND ("
                "  (p.expires_at IS NOT NULL AND p.expires_at < ?) "
                "  OR (c.is_approved = 0 OR c.is_active = 0)"
                ")",
                (now_str,),
            ).fetchall()
            post_ids = [r["id"] for r in rows]

            if not dry_run and post_ids:
                placeholders = ",".join("?" for _ in post_ids)
                # Safe parameterized placeholder expansion
                conn.execute(
                    f"UPDATE posts SET status = 'expired', updated_at = ? WHERE id IN ({placeholders})",  # nosec B608
                    [now_str] + post_ids,
                )
                conn.commit()
                logger.info(f"[IntegrityService] Expired {len(post_ids)} stale marketplace listings.")

            return {
                "action": action,
                "dry_run": dry_run,
                "affected_count": len(post_ids),
                "affected_ids": post_ids,
                "message": f"{'Dry run: would expire' if dry_run else 'Successfully expired'} {len(post_ids)} stale listing(s).",
            }

        elif action == "archive_dead_letters":
            if not IntegrityService._table_exists(conn, "event_outbox"):
                return {
                    "action": action,
                    "dry_run": dry_run,
                    "affected_count": 0,
                    "affected_ids": [],
                    "message": "event_outbox table does not exist.",
                }

            rows = conn.execute(
                "SELECT id FROM event_outbox WHERE status = 'DEAD_LETTER' OR retry_count >= max_retries"
            ).fetchall()
            event_ids = [r["id"] for r in rows]

            if not dry_run and event_ids:
                placeholders = ",".join("?" for _ in event_ids)
                # Safe parameterized placeholder expansion
                conn.execute(
                    f"UPDATE event_outbox SET status = 'ARCHIVED', updated_at = ? WHERE id IN ({placeholders})",  # nosec B608
                    [now_str] + event_ids,
                )
                conn.commit()


                logger.info(f"[IntegrityService] Archived {len(event_ids)} dead-letter outbox events.")

            return {
                "action": action,
                "dry_run": dry_run,
                "affected_count": len(event_ids),
                "affected_ids": event_ids,
                "message": f"{'Dry run: would archive' if dry_run else 'Successfully archived'} {len(event_ids)} dead-letter event(s).",
            }

        else:
            return {
                "action": action,
                "dry_run": dry_run,
                "affected_count": 0,
                "error": f"Unknown remediation action '{action}'. Supported: 'expire_stale_listings', 'archive_dead_letters'.",
            }
