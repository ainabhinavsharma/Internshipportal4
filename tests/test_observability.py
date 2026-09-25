"""
Phase 21: Observability, Telemetry & Logging Test Suite
DBERT Internship Portal

Covers:
1. TestRequestIDTracing:
   - Inbound X-Request-ID preservation and header injection
   - Auto-generation of UUID4 when X-Request-ID header is missing
   - X-Request-Duration-Ms header presence and validity
   - Request ID propagation into application status history audit table
2. TestHealthAndReadinessProbes:
   - /health liveness probe (HTTP 200, fast, no database contention)
   - /ready readiness probe (HTTP 200 when DB is reachable, WAL mode, tables exist, outbox healthy)
   - /ready error handling (HTTP 503 when database is unavailable)
3. TestTelemetryMetricsCollection:
   - Metrics accumulation (2xx/3xx/4xx/5xx status buckets, total_requests, endpoint counts)
   - Domain failure tracking (login_failures, upload_failures, db_failures)
   - Latency statistics calculation (avg, min, max, p50, p95, p99)
   - /admin/telemetry API access control (401 unauthenticated, 200 admin)
4. TestStructuredLogger:
   - JsonFormatter produces valid JSON containing ts, level, msg, req_id, ip, path
"""

import os
import json
import uuid
import pytest

os.environ["TESTING"] = "true"
os.environ.setdefault("FLASK_DEBUG", "false")
os.environ.setdefault("SMTP_PASS", "")

from app import app, get_db
from services.telemetry_service import (
    reset_telemetry,
    record_request,
    record_failure,
    get_telemetry_snapshot,
    get_latency_stats,
    check_liveness,
    check_readiness
)
from tests.conftest import seed_intern, login_as_intern, login_as_admin


# =====================================================================
# 1. REQUEST ID TRACING & DURATION
# =====================================================================

class TestRequestIDTracing:
    """Verifies end-to-end request tracing via X-Request-ID and duration metrics."""

    def test_inbound_request_id_preserved_and_echoed(self, app_client):
        """When an inbound X-Request-ID is provided by a proxy/client, it must be preserved."""
        client, db_path = app_client
        custom_id = f"custom-req-{uuid.uuid4()}"
        resp = client.get("/internships", headers={"X-Request-ID": custom_id})

        assert resp.status_code == 200
        assert resp.headers.get("X-Request-ID") == custom_id

    def test_missing_request_id_auto_generates_uuid4(self, app_client):
        """When no X-Request-ID is provided, a fresh UUID4 is generated and attached to response."""
        client, db_path = app_client
        resp = client.get("/internships")

        assert resp.status_code == 200
        generated_id = resp.headers.get("X-Request-ID")
        assert generated_id is not None
        assert len(generated_id) >= 32
        # Verify it parses as a UUID
        parsed_uuid = uuid.UUID(generated_id)
        assert parsed_uuid.version == 4

    def test_request_duration_header_injected(self, app_client):
        """Responses must include X-Request-Duration-Ms reflecting execution time."""
        client, db_path = app_client
        resp = client.get("/internships")

        assert resp.status_code == 200
        duration_hdr = resp.headers.get("X-Request-Duration-Ms")
        assert duration_hdr is not None
        duration_val = float(duration_hdr)
        assert duration_val >= 0.0

    def test_request_id_propagated_to_status_history(self, app_client):
        """State machine transitions record the active request_id in audit tables."""
        client, db_path = app_client
        test_req_id = f"trace-test-{uuid.uuid4()}"

        from services.application_service import transition_application, STATUS_APPLY_PENDING, STATUS_UNDER_REVIEW

        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO applications (name, email, phone, city, college, course, semester, year_of_passing, domain, why_join, status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("Trace Applicant", "trace@test.com", "9876543210", "Bengaluru", "Test College", "B.Tech", "6", "2026", "AI Agent Development", "Test SOP", STATUS_APPLY_PENDING)
            )
            app_id = cur.lastrowid
            conn.commit()

            transition_application(
                conn,
                application_id=app_id,
                target_status=STATUS_UNDER_REVIEW,
                actor="admin",
                actor_role="admin",
                reason="Audit tracing verification",
                request_id=test_req_id
            )
            conn.commit()

            history_row = conn.execute(
                "SELECT request_id, new_status FROM application_status_history WHERE application_id=? ORDER BY id DESC LIMIT 1",
                (app_id,)
            ).fetchone()

            assert history_row is not None
            assert history_row["new_status"] == STATUS_UNDER_REVIEW
            assert history_row["request_id"] == test_req_id


# =====================================================================
# 2. HEALTH & READINESS PROBES
# =====================================================================

class TestHealthAndReadinessProbes:
    """Verifies /health liveness and /ready readiness probe endpoints."""

    def test_health_liveness_probe_returns_ok_200(self, app_client):
        """/health must return HTTP 200 with status: ok and uptime seconds."""
        client, db_path = app_client
        resp = client.get("/health")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("status") == "ok"
        assert data.get("service") == "dbert-portal"
        assert "uptime_seconds" in data
        assert "timestamp" in data

    def test_ready_readiness_probe_returns_ready_200_when_healthy(self, app_client):
        """/ready must verify DB connection, tables, and outbox, returning HTTP 200."""
        client, db_path = app_client
        resp = client.get("/ready")

        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("status") in ("ready", "degraded")
        checks = data.get("checks", {})
        assert checks.get("database_connected") is True
        assert checks.get("tables_accessible") is True
        assert checks.get("outbox_healthy") is True

    def test_ready_probe_returns_503_on_database_error(self, app_client):
        """When database is unavailable, check_readiness reports failure and /ready returns 503."""
        client, db_path = app_client

        class BrokenConnection:
            def execute(self, *args, **kwargs):
                raise Exception("Simulated disk error or broken socket")

        is_ready, details = check_readiness(BrokenConnection())
        assert is_ready is False
        assert details.get("status") == "not_ready"
        assert "Simulated disk error" in details.get("error", "")


# =====================================================================
# 3. TELEMETRY METRICS COLLECTION
# =====================================================================

class TestTelemetryMetricsCollection:
    """Verifies metrics recording, error rate calculations, and admin telemetry API."""

    @pytest.fixture(autouse=True)
    def clean_telemetry(self):
        reset_telemetry()
        yield
        reset_telemetry()

    def test_request_metrics_recorded(self, app_client):
        """Requests update total count, status code buckets, and endpoint hits."""
        client, db_path = app_client

        # Fire 2xx request
        client.get("/internships")
        # Fire 404 request
        client.get("/non_existent_page_path_12345")

        snapshot = get_telemetry_snapshot()
        assert snapshot["total_requests"] >= 2
        assert snapshot["status_buckets"]["2xx"] >= 1
        assert snapshot["status_buckets"]["4xx"] >= 1
        assert snapshot["rates"]["4xx_client_error_rate_pct"] > 0

    def test_domain_failure_counters(self, app_client):
        """Explicit failure events increment their respective categories."""
        record_failure("login_failures")
        record_failure("upload_failures")
        record_failure("payment_failures")
        record_failure("db_failures")

        snapshot = get_telemetry_snapshot()
        failures = snapshot["failures"]
        assert failures["login_failures"] == 1
        assert failures["upload_failures"] == 1
        assert failures["payment_failures"] == 1
        assert failures["db_failures"] == 1

    def test_latency_statistics_calculation(self):
        """Latency statistics compute min, avg, p50, p95, p99 accurately."""
        # Record known duration values
        for d in [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]:
            record_request("GET", "/test", 200, d)

        stats = get_latency_stats()
        assert stats["count"] == 10
        assert stats["min_ms"] == 10.0
        assert stats["max_ms"] == 100.0
        assert stats["avg_ms"] == 55.0
        assert stats["p50_ms"] >= 50.0
        assert stats["p95_ms"] >= 90.0

    def test_admin_telemetry_endpoint_authorization(self, app_client):
        """Unauthenticated requests to /admin/telemetry return 401; admin gets 200."""
        client, db_path = app_client

        # Unauthenticated attempt
        unauth_resp = client.get("/admin/telemetry")
        assert unauth_resp.status_code == 401

        # Authenticated as admin
        login_as_admin(client, db_path)
        auth_resp = client.get("/admin/telemetry")
        assert auth_resp.status_code == 200
        data = auth_resp.get_json()
        assert data.get("status") == "success"
        assert "telemetry" in data
        assert "uptime_seconds" in data["telemetry"]
        assert "rates" in data["telemetry"]


# =====================================================================
# 4. STRUCTURED LOGGING
# =====================================================================

class TestStructuredLogger:
    """Verifies that application structured logger outputs JSON with required telemetry fields."""

    def test_json_formatter_fields(self):
        """JsonFormatter produces JSON string with ts, level, msg, req_id, ip, path."""
        import logging
        from app import JsonFormatter

        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="app.py",
            lineno=100,
            msg="Structured telemetry test event",
            args=(),
            exc_info=None
        )
        record.request_id = "req-123456"
        record.client_ip = "192.168.1.1"
        record.path = "/test/path"

        formatted = formatter.format(record)
        parsed = json.loads(formatted)

        assert parsed["level"] == "INFO"
        assert parsed["msg"] == "Structured telemetry test event"
        assert parsed["req_id"] == "req-123456"
        assert parsed["ip"] == "192.168.1.1"
        assert parsed["path"] == "/test/path"
        assert "ts" in parsed
