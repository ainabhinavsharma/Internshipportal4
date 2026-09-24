import json
import datetime
from typing import Optional, Dict, Any, List, Union, Callable

# -----------------------------------------------------------------------------
# PHASE 14 — Transactional Event Outbox Service
# Master Plan: INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md (§23)
# -----------------------------------------------------------------------------

# Supported Event Types
EVENT_APPLICATION_SUBMITTED = "application.submitted"
EVENT_APPLICATION_SELECTED  = "application.selected"
EVENT_APPLICATION_REJECTED  = "application.rejected"
EVENT_ENROLLMENT_CREATED    = "enrollment.created"
EVENT_PAYMENT_SUBMITTED     = "payment.submitted"
EVENT_PAYMENT_ACCEPTED      = "payment.accepted"
EVENT_PAYMENT_REJECTED      = "payment.rejected"
EVENT_MENTOR_ASSIGNED       = "mentor.assigned"
EVENT_TASK_ASSIGNED         = "task.assigned"
EVENT_TASK_REVIEWED         = "task.reviewed"
EVENT_CERTIFICATE_ISSUED    = "certificate.issued"

ALL_OUTBOX_EVENTS = {
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
}

# Notification / Outbox States
STATUS_PENDING     = "PENDING"
STATUS_SENT        = "SENT"
STATUS_FAILED      = "FAILED"
STATUS_RETRYING    = "RETRYING"
STATUS_DEAD_LETTER = "DEAD_LETTER"

ALL_OUTBOX_STATUSES = {
    STATUS_PENDING,
    STATUS_SENT,
    STATUS_FAILED,
    STATUS_RETRYING,
    STATUS_DEAD_LETTER,
}


def _now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def enqueue_outbox_event(
    conn,
    event_type: str,
    aggregate_type: str,
    aggregate_id: Union[int, str],
    payload: Dict[str, Any],
    max_retries: int = 3
) -> int:
    """
    Enqueues an outbox event inside the active database transaction.
    Atomic with business logic — if the transaction rolls back, this event rolls back.
    """
    if event_type not in ALL_OUTBOX_EVENTS:
        raise ValueError(f"Unknown outbox event type: '{event_type}'. Must be one of {ALL_OUTBOX_EVENTS}")

    payload_json = json.dumps(payload, default=str)
    now = _now_str()

    cur = conn.execute(
        """
        INSERT INTO event_outbox (
            event_type, aggregate_type, aggregate_id, payload_json,
            status, retry_count, max_retries, next_retry_at,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
        """,
        (
            event_type,
            aggregate_type,
            str(aggregate_id),
            payload_json,
            STATUS_PENDING,
            max_retries,
            now,
            now,
            now
        )
    )
    return cur.lastrowid


def fetch_pending_outbox_events(conn, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Fetches up to `limit` outbox events that are eligible for processing:
    status is 'PENDING' or 'RETRYING', and next_retry_at <= now.
    """
    now = _now_str()
    rows = conn.execute(
        """
        SELECT id, event_type, aggregate_type, aggregate_id, payload_json,
               status, retry_count, max_retries, next_retry_at, last_error, created_at
        FROM event_outbox
        WHERE status IN (?, ?)
          AND (next_retry_at IS NULL OR next_retry_at <= ?)
        ORDER BY id ASC
        LIMIT ?
        """,
        (STATUS_PENDING, STATUS_RETRYING, now, limit)
    ).fetchall()

    results = []
    for r in rows:
        item = dict(r)
        try:
            item["payload"] = json.loads(item["payload_json"])
        except Exception:
            item["payload"] = {}
        results.append(item)
    return results


def mark_event_sent(conn, event_id: int) -> bool:
    """Marks an outbox event as SENT with timestamp."""
    now = _now_str()
    cur = conn.execute(
        """
        UPDATE event_outbox
        SET status = ?, processed_at = ?, updated_at = ?, last_error = NULL
        WHERE id = ?
        """,
        (STATUS_SENT, now, now, event_id)
    )
    return cur.rowcount > 0


def mark_event_failed(
    conn,
    event_id: int,
    error_message: str,
    base_backoff_seconds: int = 30
) -> str:
    """
    Marks an outbox event as failed. Computes exponential backoff.
    Transitions to RETRYING if retry_count < max_retries, otherwise DEAD_LETTER.
    Returns the new status.
    """
    row = conn.execute(
        "SELECT retry_count, max_retries FROM event_outbox WHERE id = ?", (event_id,)
    ).fetchone()
    if not row:
        return STATUS_FAILED

    new_retry_count = row["retry_count"] + 1
    max_retries = row["max_retries"]
    now = datetime.datetime.now()

    if new_retry_count >= max_retries:
        new_status = STATUS_DEAD_LETTER
        next_retry_str = None
    else:
        new_status = STATUS_RETRYING
        # Exponential backoff: 2^(retry_count) * base_backoff_seconds
        backoff_sec = (2 ** new_retry_count) * base_backoff_seconds
        next_retry_str = (now + datetime.timedelta(seconds=backoff_sec)).strftime("%Y-%m-%d %H:%M:%S")

    conn.execute(
        """
        UPDATE event_outbox
        SET status = ?, retry_count = ?, next_retry_at = ?, last_error = ?, updated_at = ?
        WHERE id = ?
        """,
        (new_status, new_retry_count, next_retry_str, error_message[:1000], _now_str(), event_id)
    )
    return new_status


def process_outbox_batch(
    conn,
    dispatcher_func: Callable[[str, Dict[str, Any]], bool],
    batch_size: int = 50,
    base_backoff_seconds: int = 30
) -> Dict[str, int]:
    """
    Processes a batch of outbox events using the provided dispatcher function.
    Dispatcher must return True on success or raise/return False on failure.
    Guarantees that individual dispatcher failures never abort the batch or caller.
    """
    events = fetch_pending_outbox_events(conn, limit=batch_size)
    metrics = {
        "processed": 0,
        "sent": 0,
        "retrying": 0,
        "dead_letter": 0
    }

    for ev in events:
        metrics["processed"] += 1
        event_id = ev["id"]
        event_type = ev["event_type"]
        payload = ev["payload"]

        try:
            success = dispatcher_func(event_type, payload)
            if success:
                mark_event_sent(conn, event_id)
                metrics["sent"] += 1
            else:
                st = mark_event_failed(
                    conn, event_id, "Dispatcher returned non-success result.", base_backoff_seconds
                )
                if st == STATUS_RETRYING:
                    metrics["retrying"] += 1
                elif st == STATUS_DEAD_LETTER:
                    metrics["dead_letter"] += 1
        except Exception as e:
            st = mark_event_failed(conn, event_id, str(e), base_backoff_seconds)
            if st == STATUS_RETRYING:
                metrics["retrying"] += 1
            elif st == STATUS_DEAD_LETTER:
                metrics["dead_letter"] += 1

    return metrics


def replay_dead_letters(conn, event_ids: Optional[List[int]] = None) -> int:
    """
    Resets DEAD_LETTER events to PENDING with reset retry count and immediate next_retry_at.
    If event_ids is provided, resets only those; otherwise resets all DEAD_LETTER events.
    """
    now = _now_str()
    if event_ids:
        placeholders = ",".join("?" for _ in event_ids)
        cur = conn.execute(
            f"""
            UPDATE event_outbox
            SET status = ?, retry_count = 0, next_retry_at = ?, last_error = NULL, updated_at = ?
            WHERE status = ? AND id IN ({placeholders})
            """,
            (STATUS_PENDING, now, now, STATUS_DEAD_LETTER, *event_ids)
        )
    else:
        cur = conn.execute(
            """
            UPDATE event_outbox
            SET status = ?, retry_count = 0, next_retry_at = ?, last_error = NULL, updated_at = ?
            WHERE status = ?
            """,
            (STATUS_PENDING, now, now, STATUS_DEAD_LETTER)
        )
    return cur.rowcount
