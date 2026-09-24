"""
tests/test_enrollment_state_machine.py - Comprehensive Unit & Integration Tests
for Enrollment State Machine (Phase 7, ENR-001 - ENR-002)
"""

import pytest
import sqlite3
import json
from services.enrollment_service import (
    transition_enrollment,
    get_enrollment_history,
    EnrollmentStateMachineError,
    EnrollmentNotFoundError,
    InvalidEnrollmentTransitionError,
    UnauthorizedEnrollmentError,
    ConcurrentEnrollmentModificationError,
    ENROLLMENT_STATUS_PENDING,
    ENROLLMENT_STATUS_ACCEPTED,
    ENROLLMENT_STATUS_REJECTED,
    ENROLLMENT_STATUS_REFUNDED
)
from services.application_service import (
    STATUS_SELECTED,
    STATUS_ENROLLMENT_PENDING,
    STATUS_ENROLLED,
    STATUS_ACCEPTED
)


@pytest.fixture
def db_conn():
    """Provides an isolated in-memory SQLite database initialized with necessary tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            name TEXT,
            domain TEXT,
            status TEXT DEFAULT 'Apply Pending',
            rejected_at TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE application_status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_by TEXT,
            changed_at TEXT DEFAULT (datetime('now','localtime')),
            reason TEXT,
            request_id TEXT,
            metadata TEXT
        );

        CREATE TABLE enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER,
            email TEXT NOT NULL,
            name TEXT,
            domain TEXT,
            payment_status TEXT DEFAULT 'Pending Verification',
            admin_note TEXT,
            product TEXT DEFAULT 'free_deposit',
            amount INTEGER DEFAULT 499,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE enrollment_status_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enrollment_id INTEGER NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            changed_by TEXT,
            changed_at TEXT DEFAULT (datetime('now','localtime')),
            reason TEXT,
            request_id TEXT,
            metadata TEXT
        );
    """)
    yield conn
    conn.close()


def create_sample_enrollment(conn, email="candidate@test.com", initial_status=ENROLLMENT_STATUS_PENDING, app_id=None):
    cur = conn.execute(
        "INSERT INTO enrollments (application_id, email, name, domain, payment_status) VALUES (?, ?, ?, ?, ?)",
        (app_id, email, "Candidate Name", "AI Agent Development", initial_status)
    )
    conn.commit()
    return cur.lastrowid


def create_sample_app(conn, email="candidate@test.com", initial_status=STATUS_ENROLLMENT_PENDING):
    cur = conn.execute(
        "INSERT INTO applications (email, name, domain, status) VALUES (?, ?, ?, ?)",
        (email, "Candidate Name", "AI Agent Development", initial_status)
    )
    conn.commit()
    return cur.lastrowid


class TestEnrollmentStateMachine:
    def test_valid_sequential_enrollment(self, db_conn):
        """Standard lifecycle: Pending Verification -> Accepted -> Refunded."""
        enr_id = create_sample_enrollment(db_conn, initial_status=ENROLLMENT_STATUS_PENDING)

        # 1. Admin accepts payment
        res1 = transition_enrollment(db_conn, enr_id, ENROLLMENT_STATUS_ACCEPTED, actor="admin_user", actor_role="admin", sync_application=False)
        assert res1["success"] is True
        assert res1["old_status"] == ENROLLMENT_STATUS_PENDING
        assert res1["new_status"] == ENROLLMENT_STATUS_ACCEPTED

        # 2. Admin processes refund
        res2 = transition_enrollment(db_conn, enr_id, ENROLLMENT_STATUS_REFUNDED, actor="admin_user", actor_role="admin", reason="Candidate requested refund", sync_application=False)
        assert res2["success"] is True
        assert res2["old_status"] == ENROLLMENT_STATUS_ACCEPTED
        assert res2["new_status"] == ENROLLMENT_STATUS_REFUNDED

        # Verify history entries
        history = get_enrollment_history(db_conn, enr_id)
        assert len(history) == 2
        assert history[0]["new_status"] == ENROLLMENT_STATUS_ACCEPTED
        assert history[1]["new_status"] == ENROLLMENT_STATUS_REFUNDED

    def test_illegal_jump_from_terminal_state_rejected(self, db_conn):
        """Transitioning from Refunded is blocked."""
        enr_id = create_sample_enrollment(db_conn, initial_status=ENROLLMENT_STATUS_REFUNDED)

        with pytest.raises(InvalidEnrollmentTransitionError):
            transition_enrollment(db_conn, enr_id, ENROLLMENT_STATUS_ACCEPTED, actor="admin")

    def test_unauthorized_intern_attempt_blocked(self, db_conn):
        """Intern cannot approve their own payment."""
        enr_id = create_sample_enrollment(db_conn, initial_status=ENROLLMENT_STATUS_PENDING)

        with pytest.raises(UnauthorizedEnrollmentError):
            transition_enrollment(db_conn, enr_id, ENROLLMENT_STATUS_ACCEPTED, actor="candidate@test.com", actor_role="intern")

    def test_mentor_attempt_blocked(self, db_conn):
        """Mentors do not have financial approval authority."""
        enr_id = create_sample_enrollment(db_conn, initial_status=ENROLLMENT_STATUS_PENDING)

        with pytest.raises(UnauthorizedEnrollmentError):
            transition_enrollment(db_conn, enr_id, ENROLLMENT_STATUS_ACCEPTED, actor="mentor@test.com", actor_role="mentor")

    def test_concurrent_enrollment_conflict_detected(self, db_conn):
        """Optimistic locking detects concurrent modifications when expected_status is provided."""
        enr_id = create_sample_enrollment(db_conn, initial_status=ENROLLMENT_STATUS_PENDING)

        # Simulate concurrent worker changing status out-of-band
        db_conn.execute("UPDATE enrollments SET payment_status='Accepted' WHERE id=?", (enr_id,))
        db_conn.commit()

        # Concurrent attempt from stale UI that expects 'Pending Verification'
        with pytest.raises(ConcurrentEnrollmentModificationError):
            transition_enrollment(
                db_conn, enr_id, ENROLLMENT_STATUS_REJECTED,
                actor="admin", expected_status=ENROLLMENT_STATUS_PENDING
            )

    def test_idempotent_duplicate_call(self, db_conn):
        """Re-transitioning to current payment status is an idempotent no-op."""
        enr_id = create_sample_enrollment(db_conn, initial_status=ENROLLMENT_STATUS_PENDING)

        res = transition_enrollment(db_conn, enr_id, ENROLLMENT_STATUS_PENDING, actor="admin")
        assert res["success"] is True
        assert res["idempotent"] is True
        assert res["history_id"] is None

    def test_sync_with_application(self, db_conn):
        """Accepting an enrollment synchronizes application status to Accepted."""
        email = "applicant_sync@test.com"
        app_id = create_sample_app(db_conn, email=email, initial_status=STATUS_ENROLLED)
        enr_id = create_sample_enrollment(db_conn, email=email, initial_status=ENROLLMENT_STATUS_PENDING, app_id=app_id)

        res = transition_enrollment(db_conn, enr_id, ENROLLMENT_STATUS_ACCEPTED, actor="admin", actor_role="admin", sync_application=True)
        assert res["success"] is True
        assert res["synced_application_id"] == app_id

        # Verify application status was updated to Accepted
        app_row = db_conn.execute("SELECT status FROM applications WHERE id=?", (app_id,)).fetchone()
        assert app_row["status"] == STATUS_ACCEPTED
