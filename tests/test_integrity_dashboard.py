"""Automated Test Suite for Platform Data Integrity Dashboard & Health Analytics.

Fulfills Phase 26 requirements (§53 of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md).
Covers:
  1. Platform metrics aggregation across all 7 entity clusters
  2. Detection for all 6 required integrity anomalies
  3. Safe remediation / self-healing framework (dry-run and execution)
  4. Admin dashboard routes (JSON and HTML) & RBAC security gates
"""

from datetime import datetime, timedelta, timezone
import json
import pytest

from services.integrity_service import IntegrityService
from app import get_db, set_password_hash
from tests.conftest import (
    seed_intern,
    seed_company,
    seed_staff,
    seed_mentor,
    login_as_intern,
    login_as_admin,
    logout,
)


class TestIntegrityMetrics:
    """Verifies metrics aggregation across all 7 platform entity clusters."""

    def test_platform_metrics_aggregation(self, app_client):
        client, db_path = app_client

        with get_db() as conn:
            # 1. Users
            conn.execute("INSERT INTO intern_accounts (name, email, password_hash) VALUES ('I1', 'i1@test.com', 'h')")
            conn.execute("INSERT INTO intern_accounts (name, email, password_hash) VALUES ('I2', 'i2@test.com', 'h')")
            conn.execute("INSERT INTO companies (name, email, password_hash, is_approved, is_active) VALUES ('C1', 'c1@test.com', 'h', 1, 1)")
            conn.execute("INSERT INTO mentors (name, email, domain, password_hash, is_active) VALUES ('M1', 'm1@test.com', 'AI', 'h', 1)")
            conn.execute("INSERT INTO staff_accounts (name, email, password_hash, is_active) VALUES ('S1', 's1@test.com', 'h', 1)")

            # 2. Applications
            conn.execute(
                "INSERT INTO applications (name, email, phone, city, college, course, semester, year_of_passing, domain, why_join, status) "
                "VALUES ('I1', 'i1@test.com', '111', 'City', 'Coll', 'BTech', '6', '2026', 'AI', 'why', 'Accepted'), "
                "       ('I2', 'i2@test.com', '222', 'City', 'Coll', 'BTech', '6', '2026', 'FS', 'why', 'Selected')"
            )

            # 3. Enrollments
            conn.execute(
                "INSERT INTO enrollments (application_id, name, email, phone, domain, timestamp, payment_status) "
                "VALUES (1, 'I1', 'i1@test.com', '111', 'AI', '2026-09-25 18:00:00', 'Verified')"
            )


            # 4. Payments
            conn.execute(
                "INSERT INTO course_payments (intern_id, course_id, amount, status) "
                "VALUES (1, 1, 499, 'Verified')"
            )


            # 5. Certificates
            conn.execute(
                "INSERT INTO intern_certificates (intern_id, cert_id, course_title, issued_at) "
                "VALUES (1, 'DBERT-TEST-1', 'AI', '2026-09-25')"
            )

            conn.commit()

            metrics = IntegrityService.get_platform_metrics(conn)

        assert metrics["users"]["total_interns"] == 2
        assert metrics["users"]["total_companies"] == 1
        assert metrics["users"]["total_mentors"] == 1
        assert metrics["users"]["total_staff"] >= 1
        assert metrics["users"]["total_users"] >= 5


        assert metrics["applications"]["total"] == 2
        assert metrics["applications"]["accepted"] == 1
        assert metrics["applications"]["selected"] == 1

        assert metrics["enrollments"]["total"] == 1
        assert metrics["enrollments"]["verified"] == 1

        assert metrics["payments"]["total_records"] == 1
        assert metrics["payments"]["verified_volume_inr"] == 499

        assert metrics["active_interns"]["count"] == 1
        assert metrics["completed_interns"]["count"] == 1
        assert metrics["certificates"]["total_issued"] == 1


class TestIntegrityAnomalies:
    """Verifies detection of the 6 required platform data anomaly categories."""

    def test_clean_database_has_zero_anomalies(self, app_client):
        client, db_path = app_client
        with get_db() as conn:
            anomalies = IntegrityService.get_integrity_anomalies(conn)

        assert anomalies["summary"]["critical_count"] == 0
        assert anomalies["summary"]["warning_count"] == 0
        assert anomalies["summary"]["status"] == "HEALTHY"
        assert anomalies["summary"]["health_score"] == 100.0

    def test_detect_orphan_applications(self, app_client):
        client, db_path = app_client
        with get_db() as conn:
            # Insert application with blank email
            conn.execute(
                "INSERT INTO applications (name, email, phone, city, college, course, semester, year_of_passing, domain, why_join, status) "
                "VALUES ('Ghost User', '', '000', 'City', 'Coll', 'BTech', '6', '2026', 'AI', 'why', 'Apply Pending')"
            )
            conn.commit()
            anomalies = IntegrityService.get_integrity_anomalies(conn)

        assert anomalies["orphan_applications"]["count"] >= 1
        assert anomalies["summary"]["warning_count"] >= 1

    def test_detect_orphan_enrollments(self, app_client):
        client, db_path = app_client
        with get_db() as conn:
            # Enrollment pointing to non-existent application_id 9999 (simulating legacy data)
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute(
                "INSERT INTO enrollments (application_id, name, email, phone, domain, timestamp, payment_status) "
                "VALUES (9999, 'Orphan', 'orphan@test.com', '000', 'AI', '2026-09-25 18:00:00', 'Pending')"
            )
            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()

            anomalies = IntegrityService.get_integrity_anomalies(conn)

        assert anomalies["orphan_enrollments"]["count"] >= 1
        assert any(item["email"] == "orphan@test.com" for item in anomalies["orphan_enrollments"]["items"])

    def test_detect_duplicate_active_applications(self, app_client):
        client, db_path = app_client
        with get_db() as conn:
            conn.execute(
                "INSERT INTO applications (name, email, phone, city, college, course, semester, year_of_passing, domain, why_join, status) "
                "VALUES ('Multi App', 'multi@test.com', '123', 'City', 'Coll', 'BTech', '6', '2026', 'AI', 'why', 'Under Review'), "
                "       ('Multi App', 'multi@test.com', '123', 'City', 'Coll', 'BTech', '6', '2026', 'FS', 'why', 'Apply Pending')"
            )
            conn.commit()
            anomalies = IntegrityService.get_integrity_anomalies(conn)

        assert anomalies["duplicate_active_applications"]["count"] >= 1
        assert any(item["email"] == "multi@test.com" for item in anomalies["duplicate_active_applications"]["items"])

    def test_detect_impossible_states(self, app_client):
        client, db_path = app_client
        with get_db() as conn:
            # Contradiction: Application rejected but enrollment verified
            conn.execute(
                "INSERT INTO applications (id, name, email, phone, city, college, course, semester, year_of_passing, domain, why_join, status) "
                "VALUES (501, 'Contradict', 'contra@test.com', '999', 'C', 'C', 'B', '6', '2026', 'AI', 'why', 'Rejected')"
            )
            conn.execute(
                "INSERT INTO enrollments (application_id, name, email, phone, domain, timestamp, payment_status) "
                "VALUES (501, 'Contradict', 'contra@test.com', '999', 'AI', '2026-09-25 18:00:00', 'Verified')"
            )

            conn.commit()
            anomalies = IntegrityService.get_integrity_anomalies(conn)

        assert anomalies["impossible_states"]["count"] >= 1
        assert anomalies["impossible_states"]["severity"] == "CRITICAL"
        assert anomalies["summary"]["status"] == "CRITICAL"
        assert anomalies["summary"]["health_score"] < 100.0

    def test_detect_expired_live_listings(self, app_client):
        client, db_path = app_client
        past_date = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")

        with get_db() as conn:
            conn.execute("INSERT INTO companies (id, name, email, password_hash, is_approved, is_active) VALUES (10, 'Comp', 'comp@test.com', 'h', 1, 1)")
            conn.execute(
                "INSERT INTO posts (id, company_id, post_type, domain, title, description, location, status, expires_at) "
                "VALUES (101, 10, 'internship', 'AI', 'Expired Job', 'Description 100 chars required description text here ...', 'Remote', 'published', ?)",
                (past_date,)
            )

            conn.commit()
            anomalies = IntegrityService.get_integrity_anomalies(conn)

        assert anomalies["expired_live_listings"]["count"] >= 1
        assert any(item["post_id"] == 101 for item in anomalies["expired_live_listings"]["items"])

    def test_detect_failed_critical_jobs(self, app_client):
        client, db_path = app_client
        with get_db() as conn:
            conn.execute(
                "INSERT INTO event_outbox (event_type, aggregate_type, aggregate_id, payload_json, status, retry_count, max_retries, last_error) "
                "VALUES ('payment.verified', 'payment', 'pay_123', '{}', 'DEAD_LETTER', 3, 3, 'Fatal SMTP Connection Timeout')"
            )
            conn.commit()
            anomalies = IntegrityService.get_integrity_anomalies(conn)

        assert anomalies["failed_critical_jobs"]["count"] >= 1
        assert anomalies["summary"]["critical_count"] >= 1


class TestIntegrityRemediation:
    """Verifies self-healing / remediation actions with dry-run and execution modes."""

    def test_heal_stale_listings_dry_run_and_execution(self, app_client):
        client, db_path = app_client
        past_date = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")

        with get_db() as conn:
            conn.execute("INSERT INTO companies (id, name, email, password_hash, is_approved, is_active) VALUES (20, 'C20', 'c20@test.com', 'h', 1, 1)")
            conn.execute(
                "INSERT INTO posts (id, company_id, post_type, domain, title, description, location, status, expires_at) "
                "VALUES (201, 20, 'internship', 'AI', 'Stale Post', 'Valid long description text goes here ...', 'Remote', 'published', ?)",
                (past_date,)
            )

            conn.commit()

            # 1. Dry Run: does NOT mutate database
            dry_report = IntegrityService.heal_anomalies(conn, action="expire_stale_listings", dry_run=True)
            assert dry_report["affected_count"] == 1
            assert dry_report["dry_run"] is True

            check_row = conn.execute("SELECT status FROM posts WHERE id = 201").fetchone()
            assert check_row["status"] == "published"  # Still published

            # 2. Execution: mutates database
            exec_report = IntegrityService.heal_anomalies(conn, action="expire_stale_listings", dry_run=False)
            assert exec_report["affected_count"] == 1
            assert exec_report["dry_run"] is False

            check_after = conn.execute("SELECT status FROM posts WHERE id = 201").fetchone()
            assert check_after["status"] == "expired"  # Successfully transitioned

    def test_heal_dead_letters_dry_run_and_execution(self, app_client):
        client, db_path = app_client

        with get_db() as conn:
            conn.execute(
                "INSERT INTO event_outbox (id, event_type, aggregate_type, aggregate_id, payload_json, status, retry_count, max_retries) "
                "VALUES (301, 'test.fail', 'app', '1', '{}', 'DEAD_LETTER', 3, 3)"
            )
            conn.commit()

            # Dry run
            dry_report = IntegrityService.heal_anomalies(conn, action="archive_dead_letters", dry_run=True)
            assert dry_report["affected_count"] == 1
            assert conn.execute("SELECT status FROM event_outbox WHERE id = 301").fetchone()["status"] == "DEAD_LETTER"

            # Execution
            exec_report = IntegrityService.heal_anomalies(conn, action="archive_dead_letters", dry_run=False)
            assert exec_report["affected_count"] == 1
            assert conn.execute("SELECT status FROM event_outbox WHERE id = 301").fetchone()["status"] == "ARCHIVED"


class TestAdminIntegrityRoutes:
    """Verifies RBAC security and dual JSON/HTML responses on admin endpoints."""

    def test_dashboard_unauthenticated_blocked(self, app_client):
        client, db_path = app_client
        # JSON request returns 401
        resp = client.get("/admin/integrity-dashboard", headers={"Accept": "application/json"})
        assert resp.status_code == 401

        # Browser HTML request redirects to /admin/login
        resp_html = client.get("/admin/integrity-dashboard")
        assert resp_html.status_code in (302, 401)

    def test_dashboard_non_admin_blocked(self, app_client):
        client, db_path = app_client
        login_as_intern(client, db_path, email="intern_user@test.com")

        resp = client.get("/admin/integrity-dashboard", headers={"Accept": "application/json"})
        assert resp.status_code == 401

    def test_dashboard_admin_access_json(self, app_client):
        client, db_path = app_client
        login_as_admin(client, db_path, email="admin_chief@test.com")

        resp = client.get("/admin/integrity-dashboard?format=json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert "metrics" in data
        assert "anomalies" in data
        assert "summary" in data["anomalies"]
        assert "users" in data["metrics"]

    def test_dashboard_admin_access_html(self, app_client):
        client, db_path = app_client
        login_as_admin(client, db_path, email="admin_chief@test.com")

        resp = client.get("/admin/integrity-dashboard")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Platform Data Integrity &amp; Health Analytics" in html or "Platform Data Integrity & Health Analytics" in html
        assert "INTEGRITY SCORE" in html.upper()
        assert "IMPOSSIBLE LIFECYCLE STATES" in html.upper()

    def test_admin_heal_endpoint_execution(self, app_client):
        client, db_path = app_client
        login_as_admin(client, db_path, email="admin_chief@test.com")

        # Test dry-run POST
        resp = client.post(
            "/admin/integrity/heal",
            json={"action": "expire_stale_listings", "dry_run": True},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["report"]["dry_run"] is True
        assert "affected_count" in data["report"]
