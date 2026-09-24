"""
tests/test_application_state_machine.py - Comprehensive Unit & Integration Tests
for Application State Machine (Phase 6, APP-001 - APP-004)
"""

import pytest
import sqlite3
import json
from services.application_service import (
    transition_application,
    get_application_history,
    ApplicationStateMachineError,
    ApplicationNotFoundError,
    InvalidTransitionError,
    UnauthorizedTransitionError,
    ConcurrentModificationError,
    STATUS_APPLY_PENDING,
    STATUS_UNDER_REVIEW,
    STATUS_ON_HOLD,
    STATUS_SELECTED,
    STATUS_ENROLLMENT_PENDING,
    STATUS_ENROLLED,
    STATUS_ACCEPTED,
    STATUS_REJECTED,
    STATUS_PAID_ENROLLED
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
    """)
    yield conn
    conn.close()


def create_sample_app(conn, email="test@example.com", initial_status=STATUS_APPLY_PENDING):
    cur = conn.execute(
        "INSERT INTO applications (email, name, domain, status) VALUES (?, ?, ?, ?)",
        (email, "Test Candidate", "AI Agent Development", initial_status)
    )
    conn.commit()
    return cur.lastrowid


class TestApplicationStateMachine:
    def test_valid_sequential_transitions(self, db_conn):
        """Tests standard golden path: Apply Pending -> Under Review -> Selected -> Enrollment Pending -> Enrolled -> Accepted."""
        app_id = create_sample_app(db_conn, initial_status=STATUS_APPLY_PENDING)

        # 1. Under Review by Admin
        res = transition_application(db_conn, app_id, STATUS_UNDER_REVIEW, actor="admin_user", actor_role="admin")
        assert res["success"] is True
        assert res["old_status"] == STATUS_APPLY_PENDING
        assert res["new_status"] == STATUS_UNDER_REVIEW

        # 2. Selected by Mentor
        res = transition_application(db_conn, app_id, STATUS_SELECTED, actor="mentor_user", actor_role="mentor")
        assert res["success"] is True
        assert res["old_status"] == STATUS_UNDER_REVIEW
        assert res["new_status"] == STATUS_SELECTED

        # 3. Enrollment Pending by Intern (uploading receipt)
        res = transition_application(
            db_conn, app_id, STATUS_ENROLLMENT_PENDING,
            actor="test@example.com", actor_role="intern", actor_email="test@example.com"
        )
        assert res["success"] is True
        assert res["old_status"] == STATUS_SELECTED
        assert res["new_status"] == STATUS_ENROLLMENT_PENDING

        # 4. Enrolled by Gateway/Admin
        res = transition_application(db_conn, app_id, STATUS_ENROLLED, actor="gateway", actor_role="system")
        assert res["success"] is True
        assert res["old_status"] == STATUS_ENROLLMENT_PENDING
        assert res["new_status"] == STATUS_ENROLLED

        # 5. Accepted by Admin
        res = transition_application(db_conn, app_id, STATUS_ACCEPTED, actor="admin_user", actor_role="admin")
        assert res["success"] is True
        assert res["old_status"] == STATUS_ENROLLED
        assert res["new_status"] == STATUS_ACCEPTED

        # Verify history log contains all 5 transitions
        history = get_application_history(db_conn, app_id)
        assert len(history) == 5
        assert history[0]["new_status"] == STATUS_UNDER_REVIEW
        assert history[4]["new_status"] == STATUS_ACCEPTED

    def test_invalid_transition_jump_rejected(self, db_conn):
        """Illegal jumps (e.g. Apply Pending -> Accepted) must be rejected."""
        app_id = create_sample_app(db_conn, initial_status=STATUS_APPLY_PENDING)

        with pytest.raises(InvalidTransitionError) as exc_info:
            transition_application(db_conn, app_id, STATUS_ACCEPTED, actor="admin")
        assert "Cannot transition application" in str(exc_info.value)

        # Status in DB must remain unmodified
        row = db_conn.execute("SELECT status FROM applications WHERE id=?", (app_id,)).fetchone()
        assert row["status"] == STATUS_APPLY_PENDING

    def test_unauthorized_actor_transition_blocked(self, db_conn):
        """Intern cannot unilaterally promote application to Selected or Accepted."""
        app_id = create_sample_app(db_conn, initial_status=STATUS_UNDER_REVIEW)

        with pytest.raises(UnauthorizedTransitionError):
            transition_application(
                db_conn, app_id, STATUS_SELECTED,
                actor="test@example.com", actor_role="intern", actor_email="test@example.com"
            )

        # Intern cannot touch another intern's application
        with pytest.raises(UnauthorizedTransitionError):
            transition_application(
                db_conn, app_id, STATUS_UNDER_REVIEW,
                actor="other@example.com", actor_role="intern", actor_email="other@example.com"
            )

    def test_concurrent_modification_detected(self, db_conn):
        """Simulates race condition: status changed concurrently in another transaction."""
        app_id = create_sample_app(db_conn, initial_status=STATUS_UNDER_REVIEW)

        # Simulate concurrent worker changing status out of band
        db_conn.execute("UPDATE applications SET status='On Hold' WHERE id=?", (app_id,))
        db_conn.commit()

        # Stale UI attempt with expected_status='Under Review'
        with pytest.raises(ConcurrentModificationError):
            transition_application(db_conn, app_id, STATUS_SELECTED, actor="admin", expected_status=STATUS_UNDER_REVIEW)

    def test_idempotent_duplicate_request(self, db_conn):
        """Re-transitioning to the current status is an idempotent no-op."""
        app_id = create_sample_app(db_conn, initial_status=STATUS_UNDER_REVIEW)

        res = transition_application(db_conn, app_id, STATUS_UNDER_REVIEW, actor="admin")
        assert res["success"] is True
        assert res["idempotent"] is True
        assert res["history_id"] is None

        # Verify no bogus history row created for no-op
        history = get_application_history(db_conn, app_id)
        assert len(history) == 0

    def test_application_not_found(self, db_conn):
        """Nonexistent application ID raises ApplicationNotFoundError."""
        with pytest.raises(ApplicationNotFoundError):
            transition_application(db_conn, 99999, STATUS_UNDER_REVIEW, actor="admin")

    def test_audit_history_metadata_and_request_id(self, db_conn):
        """Metadata dict and request_id are properly stored and queryable."""
        app_id = create_sample_app(db_conn, initial_status=STATUS_APPLY_PENDING)

        meta = {"score": 92, "source": "campus_drive"}
        transition_application(
            db_conn, app_id, STATUS_UNDER_REVIEW,
            actor="recruiter@dbert.org",
            actor_role="admin",
            reason="High aptitude test score",
            request_id="req-abc-123",
            metadata=meta
        )

        history = get_application_history(db_conn, app_id)
        assert len(history) == 1
        entry = history[0]
        assert entry["reason"] == "High aptitude test score"
        assert entry["request_id"] == "req-abc-123"
        parsed_meta = json.loads(entry["metadata"])
        assert parsed_meta["score"] == 92
