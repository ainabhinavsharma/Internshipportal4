"""
Session Resume and Streaming Safety Service for Guided Learning 2.0.
Manages session persistence, browser reload resilience, turn idempotency keys,
and atomic commit lifecycle preventing partial state mutation during streaming.
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from services.learning.learning_models import LearningSession, Concept
from services.learning.concept_service import ConceptService
from services.learning.mastery_policy import MasteryPolicy
from services.learning.evaluator import StructuredEvaluator, EvaluationResult
from services.learning.adaptive_engine import AdaptiveActionEngine, NextActionRecommendation
from services.learning.spaced_review import SpacedReviewScheduler

class SessionResumeError(Exception):
    """Raised when resuming a session fails authorization or data integrity."""
    pass

class DuplicateTurnError(Exception):
    """Raised when an identical idempotency key is submitted consecutively."""
    pass

class LearningSessionService:
    @staticmethod
    def get_or_create_session(
        conn,
        student_id: int,
        course_id: int,
        subtopic_id: Optional[int] = None
    ) -> LearningSession:
        """
        Retrieves active session for student and course, or initializes a new persistent session.
        """
        # Find active session
        row = conn.execute(
            """
            SELECT * FROM gl_learning_sessions
            WHERE student_id = ? AND course_id = ? AND status = 'active'
            ORDER BY updated_at DESC LIMIT 1
            """,
            (student_id, course_id)
        ).fetchone()

        now_iso = datetime.now(timezone.utc).isoformat()

        if row:
            # Update heartbeat
            conn.execute(
                "UPDATE gl_learning_sessions SET last_heartbeat_at = ?, updated_at = ? WHERE session_id = ?",
                (now_iso, now_iso, row["session_id"])
            )
            conn.commit()
            return LearningSessionService._row_to_session(row)

        # Determine initial concept
        initial_concept_id = None
        if subtopic_id:
            c = ConceptService.get_concept_by_subtopic(conn, subtopic_id)
            if c:
                initial_concept_id = c.concept_id

        if not initial_concept_id:
            # Fallback to first concept of course domain
            course = conn.execute("SELECT domain FROM courses WHERE id = ?", (course_id,)).fetchone()
            domain = course["domain"] if course else "AI Agent Development"
            domain_concepts = ConceptService.list_concepts_for_domain(conn, domain)
            if domain_concepts:
                initial_concept_id = domain_concepts[0].concept_id

        new_session_id = f"gl_sess_{uuid.uuid4().hex[:16]}"
        conn.execute(
            """
            INSERT INTO gl_learning_sessions (
                session_id, student_id, course_id, subtopic_id,
                current_concept_id, current_action, action_state_json,
                idempotency_key, status, last_heartbeat_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'EXPLAIN', '{}', NULL, 'active', ?, ?, ?)
            """,
            (new_session_id, student_id, course_id, subtopic_id, initial_concept_id, now_iso, now_iso, now_iso)
        )
        conn.commit()

        # Record session_started event
        if initial_concept_id:
            MasteryPolicy._record_event(
                conn, student_id, initial_concept_id, new_session_id,
                "session_started", {"course_id": course_id, "subtopic_id": subtopic_id}
            )

        return LearningSession(
            session_id=new_session_id,
            student_id=student_id,
            course_id=course_id,
            subtopic_id=subtopic_id,
            current_concept_id=initial_concept_id,
            current_action="EXPLAIN",
            action_state={},
            status="active",
            last_heartbeat_at=now_iso,
            created_at=now_iso,
            updated_at=now_iso
        )

    @staticmethod
    def resume_session_state(conn, session_id: str, student_id: int) -> Dict[str, Any]:
        """
        Builds a complete, idempotent resume payload for returning learners or page reloads.
        """
        row = conn.execute(
            "SELECT * FROM gl_learning_sessions WHERE session_id = ? AND student_id = ?",
            (session_id, student_id)
        ).fetchone()

        if not row:
            raise SessionResumeError(f"Session {session_id} not found for student {student_id}")

        session = LearningSessionService._row_to_session(row)
        now_iso = datetime.now(timezone.utc).isoformat()

        # Update heartbeat
        conn.execute(
            "UPDATE gl_learning_sessions SET last_heartbeat_at = ? WHERE session_id = ?",
            (now_iso, session_id)
        )
        conn.commit()

        # Fetch current concept details
        concept_data = None
        mastery_data = None
        if session.current_concept_id:
            concept = ConceptService.get_concept(conn, session.current_concept_id)
            if concept:
                concept_data = concept.to_dict()
                mastery = MasteryPolicy.get_or_create_mastery(conn, student_id, concept.concept_id)
                mastery_data = mastery.to_dict()

        # Fetch last completed event
        last_event_row = conn.execute(
            """
            SELECT * FROM gl_learning_events
            WHERE session_id = ? ORDER BY id DESC LIMIT 1
            """,
            (session_id,)
        ).fetchone()
        last_event = dict(last_event_row) if last_event_row else None
        if last_event and last_event.get("payload_json"):
            try:
                last_event["payload"] = json.loads(last_event["payload_json"])
            except Exception:
                pass

        # Record session_resumed event
        if session.current_concept_id:
            MasteryPolicy._record_event(
                conn, student_id, session.current_concept_id, session_id,
                "session_resumed", {"resumed_at": now_iso}
            )

        # Check due reviews
        due_reviews = SpacedReviewScheduler.get_due_reviews_for_student(conn, student_id)

        return {
            "session": session.to_dict(),
            "concept": concept_data,
            "mastery": mastery_data,
            "last_event": last_event,
            "due_reviews_count": len(due_reviews),
            "due_reviews": due_reviews[:3],
            "resumed_at": now_iso
        }

    @staticmethod
    def process_turn_atomic(
        conn,
        session_id: str,
        student_id: int,
        student_input: str,
        idempotency_key: Optional[str] = None,
        llm_caller = None
    ) -> Dict[str, Any]:
        """
        Atomic Lifecycle execution:
        1. Check idempotency (reload protection)
        2. Evaluate response against concept criteria
        3. Deterministic mastery update
        4. Next-action selection
        5. Spaced review update
        6. Session state transition
        All wrapped in a single database transaction.
        """
        # 1. Idempotency Check
        row = conn.execute(
            "SELECT * FROM gl_learning_sessions WHERE session_id = ? AND student_id = ?",
            (session_id, student_id)
        ).fetchone()
        if not row:
            raise SessionResumeError(f"Session {session_id} not found")

        session = LearningSessionService._row_to_session(row)
        if idempotency_key and session.idempotency_key == idempotency_key:
            # Replay cached state to avoid double processing
            return {
                "idempotent_replay": True,
                "session": session.to_dict(),
                "action": session.current_action,
                "action_state": session.action_state
            }

        concept_id = session.current_concept_id
        if not concept_id:
            raise ValueError("No active concept associated with session")

        concept = ConceptService.get_concept(conn, concept_id)
        if not concept:
            raise ValueError(f"Concept {concept_id} not found")

        # 2. Record answer_submitted event
        MasteryPolicy._record_event(
            conn, student_id, concept_id, session_id,
            "answer_submitted", {"input_preview": student_input[:150]}
        )

        # 3. Evaluate response
        eval_result = StructuredEvaluator.evaluate(
            student_response=student_input,
            concept=concept,
            llm_caller=llm_caller
        )

        # 4. Record answer_evaluated event
        MasteryPolicy._record_event(
            conn, student_id, concept_id, session_id,
            "answer_evaluated", eval_result.to_dict()
        )

        # 5. Deterministically update mastery
        mastery, _ = MasteryPolicy.evaluate_and_update_mastery(
            conn=conn,
            student_id=student_id,
            concept=concept,
            evaluation=eval_result,
            session_id=session_id,
            student_input=student_input
        )

        # 6. Check review urgency
        due_reviews = SpacedReviewScheduler.get_due_reviews_for_student(conn, student_id)
        is_review_due = any(r["concept_id"] == concept_id for r in due_reviews)

        # 7. Select next action
        next_action_rec = AdaptiveActionEngine.select_next_action(
            conn=conn,
            student_id=student_id,
            concept=concept,
            mastery=mastery,
            latest_evaluation=eval_result,
            review_due=is_review_due
        )

        # 8. Schedule Spaced Review based on performance
        review_category = "NEW" if mastery.total_attempts <= 1 else (
            "REMEDIATION" if eval_result.detected_misconceptions else (
                "MASTERY_VALIDATION" if mastery.mastery_score >= 0.85 else "REINFORCEMENT"
            )
        )
        next_review_iso, next_interval = SpacedReviewScheduler.schedule_next_review(
            conn=conn,
            student_id=student_id,
            concept_id=concept_id,
            category=review_category,
            performance_rating=eval_result.correctness
        )

        # If ADVANCE and next concept exists, transition session current_concept
        target_concept_id = concept_id
        if next_action_rec.action == "ADVANCE" and next_action_rec.next_concept_id:
            target_concept_id = next_action_rec.next_concept_id

        # 9. Update Session State
        now_iso = datetime.now(timezone.utc).isoformat()
        action_state = {
            "evaluation": eval_result.to_dict(),
            "recommendation": next_action_rec.to_dict(),
            "next_review_at": next_review_iso,
            "review_interval_days": next_interval
        }

        conn.execute(
            """
            UPDATE gl_learning_sessions
            SET current_concept_id = ?,
                current_action = ?,
                action_state_json = ?,
                idempotency_key = ?,
                last_heartbeat_at = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                target_concept_id,
                next_action_rec.action,
                json.dumps(action_state),
                idempotency_key,
                now_iso,
                now_iso,
                session_id
            )
        )
        conn.commit()

        session.current_concept_id = target_concept_id
        session.current_action = next_action_rec.action
        session.action_state = action_state
        session.idempotency_key = idempotency_key

        return {
            "session": session.to_dict(),
            "evaluation": eval_result.to_dict(),
            "mastery": mastery.to_dict(),
            "recommendation": next_action_rec.to_dict(),
            "next_review_at": next_review_iso
        }

    @staticmethod
    def _row_to_session(row) -> LearningSession:
        return LearningSession(
            session_id=row["session_id"],
            student_id=row["student_id"],
            course_id=row["course_id"],
            subtopic_id=row["subtopic_id"],
            current_concept_id=row["current_concept_id"],
            current_action=row["current_action"] or "EXPLAIN",
            action_state=json.loads(row["action_state_json"] or "{}"),
            idempotency_key=row["idempotency_key"],
            status=row["status"] or "active",
            last_heartbeat_at=row["last_heartbeat_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )
