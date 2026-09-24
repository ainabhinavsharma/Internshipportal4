import io
import os
import json
import pytest
import datetime
from unittest.mock import patch

from app import get_db
from services.outbox_service import (
    enqueue_outbox_event,
    fetch_pending_outbox_events,
    mark_event_sent,
    mark_event_failed,
    process_outbox_batch,
    replay_dead_letters,
    ALL_OUTBOX_EVENTS,
    STATUS_PENDING,
    STATUS_SENT,
    STATUS_RETRYING,
    STATUS_DEAD_LETTER,
    EVENT_APPLICATION_SUBMITTED,
    EVENT_APPLICATION_SELECTED,
    EVENT_APPLICATION_REJECTED,
    EVENT_ENROLLMENT_CREATED,
    EVENT_PAYMENT_SUBMITTED,
    EVENT_PAYMENT_ACCEPTED,
    EVENT_PAYMENT_REJECTED,
    EVENT_MENTOR_ASSIGNED,
    EVENT_TASK_ASSIGNED,
    EVENT_TASK_REVIEWED,
    EVENT_CERTIFICATE_ISSUED,
)
from services.application_service import transition_application
from services.enrollment_service import transition_enrollment
from tests.conftest import seed_intern, login_as_intern, logout


class TestOutboxTransactionalDecoupling:
    """Verifies that outbox events are atomically coupled to DB transactions and cover all Master Plan events."""

    def test_outbox_event_enqueued_in_transaction(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        with get_db() as conn:
            event_id = enqueue_outbox_event(
                conn=conn,
                event_type=EVENT_APPLICATION_SUBMITTED,
                aggregate_type="application",
                aggregate_id=101,
                payload={"email": "candidate@example.com", "name": "Candidate One"}
            )
            conn.commit()

        assert event_id is not None and event_id > 0

        with get_db() as conn:
            row = conn.execute("SELECT * FROM event_outbox WHERE id = ?", (event_id,)).fetchone()
            assert row is not None
            assert row["event_type"] == EVENT_APPLICATION_SUBMITTED
            assert row["aggregate_type"] == "application"
            assert row["aggregate_id"] == "101"
            assert row["status"] == STATUS_PENDING
            assert row["retry_count"] == 0
            payload = json.loads(row["payload_json"])
            assert payload["email"] == "candidate@example.com"

    def test_outbox_atomic_rollback(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        # Simulate a rolled-back transaction
        with get_db() as conn:
            event_id = enqueue_outbox_event(
                conn=conn,
                event_type=EVENT_APPLICATION_SELECTED,
                aggregate_type="application",
                aggregate_id=102,
                payload={"email": "aborted@example.com"}
            )
            conn.rollback()

        with get_db() as conn:
            row = conn.execute("SELECT * FROM event_outbox WHERE id = ?", (event_id,)).fetchone()
            assert row is None

    def test_all_11_master_plan_events_supported(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        required_events = [
            EVENT_APPLICATION_SUBMITTED,
            EVENT_APPLICATION_SELECTED,
            EVENT_APPLICATION_REJECTED,
            EVENT_ENROLLMENT_CREATED,
            EVENT_PAYMENT_SUBMITTED,
            EVENT_PAYMENT_ACCEPTED,
            EVENT_PAYMENT_REJECTED,
            EVENT_MENTOR_ASSIGNED,
            EVENT_TASK_ASSIGNED,
            EVENT_TASK_REVIEWED,
            EVENT_CERTIFICATE_ISSUED,
        ]

        with get_db() as conn:
            for idx, ev_type in enumerate(required_events):
                eid = enqueue_outbox_event(
                    conn=conn,
                    event_type=ev_type,
                    aggregate_type="aggregate",
                    aggregate_id=idx + 1,
                    payload={"event_index": idx}
                )
                assert eid > 0
            conn.commit()

        with get_db() as conn:
            count = conn.execute("SELECT COUNT(*) FROM event_outbox").fetchone()[0]
            assert count >= 11

    def test_invalid_event_type_rejected(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        with get_db() as conn:
            with pytest.raises(ValueError) as exc_info:
                enqueue_outbox_event(
                    conn=conn,
                    event_type="invalid.custom.event",
                    aggregate_type="unknown",
                    aggregate_id=999,
                    payload={}
                )
            assert "Unknown outbox event type" in str(exc_info.value)


class TestOutboxWorkerAndStateTransitions:
    """Verifies batch processing, state transitions (PENDING -> SENT / RETRYING / DEAD_LETTER), and replay."""

    def test_batch_processing_success_transitions_to_sent(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        dispatched_events = []
        def mock_dispatcher(event_type, payload):
            dispatched_events.append((event_type, payload))
            return True

        with get_db() as conn:
            eid = enqueue_outbox_event(
                conn=conn,
                event_type=EVENT_PAYMENT_ACCEPTED,
                aggregate_type="enrollment",
                aggregate_id=50,
                payload={"email": "paid@example.com"}
            )
            conn.commit()

            metrics = process_outbox_batch(conn, dispatcher_func=mock_dispatcher)
            conn.commit()

        assert metrics["processed"] >= 1
        assert metrics["sent"] >= 1
        assert len(dispatched_events) >= 1

        with get_db() as conn:
            ev = conn.execute("SELECT * FROM event_outbox WHERE id = ?", (eid,)).fetchone()
            assert ev["status"] == STATUS_SENT
            assert ev["processed_at"] is not None
            assert ev["last_error"] is None

    def test_batch_processing_failure_retries_with_exponential_backoff(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        def failing_dispatcher(event_type, payload):
            raise ConnectionError("SMTP gateway unreachable")

        with get_db() as conn:
            eid = enqueue_outbox_event(
                conn=conn,
                event_type=EVENT_CERTIFICATE_ISSUED,
                aggregate_type="certificate",
                aggregate_id="CERT-101",
                payload={"email": "cert@example.com"},
                max_retries=3
            )
            conn.commit()

            metrics = process_outbox_batch(conn, dispatcher_func=failing_dispatcher, base_backoff_seconds=10)
            conn.commit()

        assert metrics["processed"] >= 1
        assert metrics["retrying"] >= 1

        with get_db() as conn:
            ev = conn.execute("SELECT * FROM event_outbox WHERE id = ?", (eid,)).fetchone()
            assert ev["status"] == STATUS_RETRYING
            assert ev["retry_count"] == 1
            assert "SMTP gateway unreachable" in ev["last_error"]
            assert ev["next_retry_at"] is not None

    def test_max_retries_exhaustion_transitions_to_dead_letter(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        with get_db() as conn:
            # Set max_retries=2
            eid = enqueue_outbox_event(
                conn=conn,
                event_type=EVENT_TASK_REVIEWED,
                aggregate_type="task_submission",
                aggregate_id=77,
                payload={"email": "task@example.com"},
                max_retries=2
            )
            conn.commit()

            # Attempt 1: fails -> RETRYING (retry_count=1)
            mark_event_failed(conn, eid, "First failure")
            row1 = conn.execute("SELECT status, retry_count FROM event_outbox WHERE id = ?", (eid,)).fetchone()
            assert row1["status"] == STATUS_RETRYING
            assert row1["retry_count"] == 1

            # Attempt 2: fails -> DEAD_LETTER (retry_count=2 == max_retries)
            mark_event_failed(conn, eid, "Second fatal failure")
            row2 = conn.execute("SELECT status, retry_count, last_error FROM event_outbox WHERE id = ?", (eid,)).fetchone()
            assert row2["status"] == STATUS_DEAD_LETTER
            assert row2["retry_count"] == 2
            assert "Second fatal failure" in row2["last_error"]
            conn.commit()

    def test_replay_dead_letters(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        with get_db() as conn:
            eid = enqueue_outbox_event(
                conn=conn,
                event_type=EVENT_PAYMENT_REJECTED,
                aggregate_type="enrollment",
                aggregate_id=88,
                payload={"email": "rejected@example.com"},
                max_retries=1
            )
            mark_event_failed(conn, eid, "Fatal delivery failure")
            conn.commit()

        with get_db() as conn:
            row = conn.execute("SELECT status FROM event_outbox WHERE id = ?", (eid,)).fetchone()
            assert row["status"] == STATUS_DEAD_LETTER

            # Replay dead letters
            replayed_count = replay_dead_letters(conn, event_ids=[eid])
            conn.commit()

        assert replayed_count == 1

        with get_db() as conn:
            row_replayed = conn.execute("SELECT status, retry_count, next_retry_at, last_error FROM event_outbox WHERE id = ?", (eid,)).fetchone()
            assert row_replayed["status"] == STATUS_PENDING
            assert row_replayed["retry_count"] == 0
            assert row_replayed["last_error"] is None


class TestBusinessTransactionFailureIsolation:
    """Verifies that user business transactions succeed even if external email/SMTP services completely fail."""

    def test_application_submission_succeeds_even_when_email_fails(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        email = "unbreakable_candidate@example.com"

        # Mock send_application_received_email to crash with connection error
        with patch("app.send_application_received_email", side_effect=ConnectionRefusedError("SMTP server down: port 587")):
            resp = client.post("/apply", json={
                "name": "Unbreakable Candidate",
                "email": email,
                "phone": "9876543219",
                "city": "Mumbai",
                "college": "IIT Bombay",
                "course": "B.Tech",
                "semester": "7th Semester",
                "year_of_passing": "2026",
                "domain": "AI Agent Development",
                "why_join": "I am deeply passionate about building resilient distributed multi-agent systems and mission-critical cloud infrastructure.",
                "password": "Password123!"
            })

            # Business transaction MUST NOT fail
            assert resp.status_code == 200
            assert resp.get_json()["status"] == "success"

        # Application was created and committed
        with get_db() as conn:
            app_row = conn.execute("SELECT * FROM applications WHERE email = ?", (email,)).fetchone()
            assert app_row is not None
            assert app_row["domain"] == "AI Agent Development"
            app_id = app_row["id"]

            # Outbox event was captured in the same commit
            outbox_ev = conn.execute(
                "SELECT * FROM event_outbox WHERE event_type = ? AND aggregate_id = ?",
                (EVENT_APPLICATION_SUBMITTED, str(app_id))
            ).fetchone()
            assert outbox_ev is not None
            assert outbox_ev["status"] == STATUS_PENDING

    def test_application_state_machine_selected_emits_outbox_event(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        email = "selected_outbox@example.com"
        seed_intern(db_path, email=email, password="Pass123456!", name="Selected Outbox", status="Under Review")

        with get_db() as conn:
            app_row = conn.execute("SELECT id FROM applications WHERE email = ?", (email,)).fetchone()
            app_id = app_row["id"]

            # Admin selects candidate
            res = transition_application(
                conn=conn,
                application_id=app_id,
                target_status="Selected",
                actor="admin",
                actor_role="admin"
            )
            conn.commit()

        assert res["success"] is True

        with get_db() as conn:
            ev = conn.execute(
                "SELECT * FROM event_outbox WHERE event_type = ? AND aggregate_id = ?",
                (EVENT_APPLICATION_SELECTED, str(app_id))
            ).fetchone()
            assert ev is not None
            payload = json.loads(ev["payload_json"])
            assert payload["status"] == "Selected"
            assert payload["email"] == email

    def test_enrollment_state_machine_payment_accepted_emits_outbox_event(self, app_client):
        client, db_path = app_client
        os.environ["DB_FILE"] = db_path

        email = "enr_outbox@example.com"
        intern_id = seed_intern(db_path, email=email, password="Pass123456!", name="Enr Outbox", status="Enrollment Pending")

        with get_db() as conn:
            app_row = conn.execute("SELECT id FROM applications WHERE email = ?", (email,)).fetchone()
            cur = conn.execute("""
                INSERT INTO enrollments (application_id, name, email, phone, city, college, course, semester,
                                         year_of_passing, domain, joining_date, payment_status, created_at, updated_at, timestamp)
                VALUES (?, 'Enr Outbox', ?, '9876543210', 'City', 'College', 'B.Tech', '6', '2026',
                        'AI Agent Development', '2026-10-05', 'Pending Verification', datetime('now'), datetime('now'), datetime('now'))
            """, (app_row["id"], email))
            enr_id = cur.lastrowid

            # Admin verifies payment
            trans = transition_enrollment(
                conn=conn,
                enrollment_id=enr_id,
                target_status="Accepted",
                actor="admin",
                actor_role="admin"
            )
            conn.commit()

        assert trans["success"] is True

        with get_db() as conn:
            ev = conn.execute(
                "SELECT * FROM event_outbox WHERE event_type = ? AND aggregate_id = ?",
                (EVENT_PAYMENT_ACCEPTED, str(enr_id))
            ).fetchone()
            assert ev is not None
            payload = json.loads(ev["payload_json"])
            assert payload["status"] == "Accepted"
            assert payload["email"] == email
