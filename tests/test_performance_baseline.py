"""
tests/test_performance_baseline.py - Automated Performance Baseline & Production Readiness Suite
Covers: PERF-001 (SLA Latency Benchmarks), PERF-002 (N+1 Query & Index Optimization),
and PERF-003 (Static Asset Auditing & Caching Headers).
"""

import os
import sqlite3
import pytest
from app import get_db, set_password_hash
from services.performance_service import (
    QueryProfiler,
    benchmark_endpoint,
    audit_static_assets,
    SLA_THRESHOLDS_MS,
)
from tests.conftest import (
    seed_intern,
    seed_staff,
    login_as_admin,
    login_as_intern,
)


class TestEndpointLatencySLAs:
    """PERF-001: Validate that critical endpoints respond within SLA thresholds."""

    @pytest.mark.parametrize(
        "endpoint,sla_key",
        [
            ("/", "public_page"),
            ("/courses", "public_page"),
            ("/jobs", "public_page"),
            ("/internships", "public_page"),
            ("/admin-login", "auth_action"),
            ("/api/public/courses", "api_json"),
        ],
    )
    def test_endpoint_sla_compliance(self, app_client, endpoint, sla_key):
        client, _ = app_client
        result = benchmark_endpoint(client, endpoint, iterations=5)

        # Basic HTTP sanity
        assert result["status_code"] == 200, f"Endpoint {endpoint} returned status {result['status_code']}"
        assert result["payload_bytes"] > 0, f"Endpoint {endpoint} returned empty body"
        assert len(result["samples"]) == 5

        # SLA compliance check
        threshold_ms = SLA_THRESHOLDS_MS[sla_key]
        assert result["avg_ms"] <= threshold_ms, (
            f"Endpoint {endpoint} avg latency {result['avg_ms']:.2f}ms exceeded SLA of {threshold_ms}ms"
        )


class TestAdminPaginationAndQueryLimits:
    """PERF-002: Validate server-side pagination and bounded query sets for admin tables."""

    @pytest.fixture(autouse=True)
    def seed_bulk_records(self, app_client):
        _, db_path = app_client
        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            # Seed 30 applications
            for i in range(1, 31):
                conn.execute(
                    "INSERT OR IGNORE INTO applications (name, email, phone, city, college, course, semester, year_of_passing, domain, why_join, status, created_at) "
                    "VALUES (?, ?, '9999999999', 'City', 'College', 'B.Tech', '6', '2026', 'AI Agent Development', 'Motivation statement', 'Under Review', datetime('now', '-' || ? || ' minutes'))",
                    (f"Student {i}", f"student_perf_{i:02d}@example.com", i)
                )

            # Seed 30 enrollments
            for i in range(1, 31):
                conn.execute(
                    "INSERT OR IGNORE INTO enrollments (timestamp, name, email, phone, payment_status, created_at) "
                    "VALUES (datetime('now'), ?, ?, '9999999999', 'paid', datetime('now', '-' || ? || ' minutes'))",
                    (f"Enrollee {i}", f"enrollee_perf_{i:02d}@example.com", i)
                )

            # Seed 30 intern accounts (precompute hash once for speed)
            pw_hash = set_password_hash("TestPass123")
            for i in range(1, 31):
                conn.execute(
                    "INSERT OR IGNORE INTO intern_accounts (name, email, password_hash, password_set, is_active, created_at) "
                    "VALUES (?, ?, ?, 1, 1, datetime('now', '-' || ? || ' minutes'))",
                    (f"Intern User {i}", f"intern_user_perf_{i:02d}@example.com", pw_hash, i)
                )
            conn.commit()

    def test_admin_applications_pagination(self, app_client):
        client, db_path = app_client
        login_as_admin(client, db_path)

        # Page 1, limit 10
        resp1 = client.get("/admin/applications?page=1&limit=10")
        assert resp1.status_code == 200
        data1 = resp1.get_json()
        assert "applications" in data1
        assert len(data1["applications"]) == 10
        assert data1["total_count"] >= 30
        assert data1["page"] == 1
        assert data1["limit"] == 10

        # Page 2, limit 10
        resp2 = client.get("/admin/applications?page=2&limit=10")
        assert resp2.status_code == 200
        data2 = resp2.get_json()
        assert len(data2["applications"]) == 10
        assert data2["page"] == 2

        # Verify page 1 and page 2 return different items
        p1_emails = [app["email"] for app in data1["applications"]]
        p2_emails = [app["email"] for app in data2["applications"]]
        assert set(p1_emails).isdisjoint(set(p2_emails))

    def test_admin_enrollments_pagination(self, app_client):
        client, db_path = app_client
        login_as_admin(client, db_path)

        resp = client.get("/admin/enrollments?page=1&limit=15")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "enrollments" in data
        assert len(data["enrollments"]) == 15
        assert data["total_count"] >= 30
        assert data["page"] == 1
        assert data["limit"] == 15

    def test_admin_users_pagination(self, app_client):
        client, db_path = app_client
        login_as_admin(client, db_path)

        resp = client.get("/admin/users?page=1&limit=12")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "users" in data
        assert len(data["users"]) == 12
        assert data["total_count"] >= 30
        assert data["page"] == 1
        assert data["limit"] == 12

    def test_backward_compatibility_without_page_params(self, app_client):
        client, db_path = app_client
        login_as_admin(client, db_path)

        # Default query without params should return all records (backward compatibility)
        resp = client.get("/admin/applications")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "applications" in data
        assert len(data["applications"]) >= 30
        assert data["total_count"] >= 30


class TestStaticAssetCachingHeaders:
    """PERF-003: Validate HTTP cache control headers for static assets and private portal."""

    def test_static_asset_cache_headers(self, app_client):
        client, _ = app_client
        # Request static theme css
        resp = client.get("/static/css/dbert-theme.css")
        assert resp.status_code == 200
        cc = resp.headers.get("Cache-Control", "")
        assert "public" in cc, f"Expected public Cache-Control, got '{cc}'"
        assert "max-age=31536000" in cc, f"Expected 1 year max-age, got '{cc}'"
        assert "immutable" in cc, f"Expected immutable directive, got '{cc}'"

    def test_authenticated_route_no_cache_headers(self, app_client):
        client, db_path = app_client
        login_as_intern(client, db_path)

        # Request authenticated portal route
        resp = client.get("/portal")
        assert resp.status_code == 200
        cc = resp.headers.get("Cache-Control", "")
        assert "no-store" in cc, f"Expected no-store Cache-Control, got '{cc}'"
        assert "no-cache" in cc, f"Expected no-cache Cache-Control, got '{cc}'"
        assert resp.headers.get("Pragma") == "no-cache"


class TestDatabaseIndexesAndQueryPlanner:
    """PERF-002: Validate that core performance indexes exist and are actively used by SQLite."""

    def test_expected_indexes_exist(self, app_client):
        _, db_path = app_client
        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            indexes = [
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                ).fetchall()
            ]

        expected_indexes = [
            "idx_applications_status_created",
            "idx_applications_email",
            "idx_enrollments_status_created",
            "idx_enrollments_email",
            "idx_course_enr_email",
            "idx_attendance_intern_week",
            "idx_course_day_quizzes_course",
            "idx_posts_expires",
        ]

        for expected in expected_indexes:
            assert expected in indexes, f"Expected index '{expected}' not found in database"

    def test_query_planner_uses_indexes(self, app_client):
        _, db_path = app_client
        os.environ["DB_FILE"] = db_path
        with get_db() as conn:
            # Check application status + created_at query plan
            plan_app_status = conn.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM applications WHERE status = 'Selected' ORDER BY created_at DESC"
            ).fetchall()
            plan_app_status_str = " ".join([row["detail"] for row in plan_app_status])
            assert "idx_applications_status_created" in plan_app_status_str

            # Check application email lookup query plan
            plan_app_email = conn.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM applications WHERE email = 'test@example.com'"
            ).fetchall()
            plan_app_email_str = " ".join([row["detail"] for row in plan_app_email])
            assert "idx_applications_email" in plan_app_email_str

            # Check enrollments status + created_at query plan
            plan_enr_status = conn.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM enrollments WHERE payment_status = 'paid' ORDER BY created_at DESC"
            ).fetchall()
            plan_enr_status_str = " ".join([row["detail"] for row in plan_enr_status])
            assert "idx_enrollments_status_created" in plan_enr_status_str

            # Check course_enrollments email lookup query plan
            plan_course_enr = conn.execute(
                "EXPLAIN QUERY PLAN SELECT * FROM course_enrollments WHERE email = 'test@example.com'"
            ).fetchall()
            plan_course_enr_str = " ".join([row["detail"] for row in plan_course_enr])
            assert "idx_course_enr_email" in plan_course_enr_str


class TestPerformanceServiceComponents:
    """Unit test performance profiling and auditing utility functions."""

    def test_audit_static_assets(self):
        audit = audit_static_assets()
        assert "total_assets" in audit
        assert "total_size_bytes" in audit
        assert "large_assets" in audit
        assert audit["total_assets"] > 0
        assert audit["total_size_bytes"] > 0
        # Check structure of asset entries
        first_asset = audit["assets"][0]
        assert "name" in first_asset
        assert "path" in first_asset
        assert "size_bytes" in first_asset
        assert "size_kb" in first_asset
        assert "category" in first_asset

    def test_query_profiler_n_plus_one_detection(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO users (name) VALUES ('Alice'), ('Bob')")

        with QueryProfiler(conn) as profiler:
            conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
            conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
            conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
            conn.execute("SELECT * FROM users WHERE id = 2").fetchone()

        assert profiler.query_count == 4
        assert len(profiler.queries) == 4

        duplicates = profiler.find_n_plus_one_candidates(threshold=2)
        assert len(duplicates) == 1
        query_sql, count = duplicates[0]
        assert "WHERE id = 1" in query_sql
        assert count == 3
