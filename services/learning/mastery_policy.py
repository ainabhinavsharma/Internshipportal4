"""
Deterministic Mastery Policy Service for Guided Learning 2.0.
Computes authoritative mastery scores and levels strictly via deterministic rules.
Arbitrary LLM prose is NEVER permitted to directly set student mastery.
"""
from datetime import datetime, timezone
import json
from typing import Optional, Dict, Any, Tuple
from services.learning.learning_models import Concept, StudentMastery, LearningEvent
from services.learning.evaluator import EvaluationResult
from services.learning.misconception_service import MisconceptionService

class MasteryPolicy:
    # Thresholds for mastery classification
    THRESHOLD_DEVELOPING = 0.35
    THRESHOLD_PROFICIENT = 0.70
    THRESHOLD_MASTERED = 0.90

    # Max score permitted when an unresolved misconception exists
    MISCONCEPTION_SCORE_CAP = 0.65

    @staticmethod
    def get_or_create_mastery(conn, student_id: int, concept_id: str) -> StudentMastery:
        """Retrieves or initializes a student's mastery record for a concept."""
        row = conn.execute(
            "SELECT * FROM gl_student_mastery WHERE student_id = ? AND concept_id = ?",
            (student_id, concept_id)
        ).fetchone()

        if row:
            return MasteryPolicy._row_to_mastery(row)

        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO gl_student_mastery (
                student_id, concept_id, mastery_score, mastery_level,
                confidence, learning_velocity, total_attempts,
                successful_attempts, consecutive_successes,
                misconceptions_json, last_evidence_json,
                review_interval_days, review_count, created_at, updated_at
            ) VALUES (?, ?, 0.0, 'NOVICE', 0.0, 1.0, 0, 0, 0, '[]', '{}', 1.0, 0, ?, ?)
            """,
            (student_id, concept_id, now_iso, now_iso)
        )
        conn.commit()

        return StudentMastery(
            student_id=student_id,
            concept_id=concept_id,
            mastery_score=0.0,
            mastery_level="NOVICE",
            confidence=0.0,
            learning_velocity=1.0,
            total_attempts=0,
            successful_attempts=0,
            consecutive_successes=0,
            misconceptions=[],
            last_evidence={},
            created_at=now_iso,
            updated_at=now_iso
        )

    @staticmethod
    def evaluate_and_update_mastery(
        conn,
        student_id: int,
        concept: Concept,
        evaluation: EvaluationResult,
        session_id: str,
        student_input: str
    ) -> Tuple[StudentMastery, Optional[LearningEvent]]:
        """
        Deterministially updates student mastery using validated evaluation evidence.
        Emits durable learning events into gl_learning_events.
        """
        mastery = MasteryPolicy.get_or_create_mastery(conn, student_id, concept.concept_id)
        
        # 1. Process detected misconceptions
        for m_id in evaluation.detected_misconceptions:
            MisconceptionService.attach_misconception(
                conn, student_id, concept.concept_id, m_id, trigger_context=student_input[:200]
            )
            # Emit misconception event
            MasteryPolicy._record_event(
                conn, student_id, concept.concept_id, session_id,
                "misconception_detected", {"misconception_id": m_id, "evidence": evaluation.to_dict()}
            )

        active_misconceptions = MisconceptionService.get_active_misconceptions(conn, student_id, concept.concept_id)

        # 2. Check if a previously active misconception was resolved by this turn
        if not evaluation.detected_misconceptions and evaluation.correctness >= 0.60 and active_misconceptions:


            # High quality answer after misconception -> resolve the most recent active one
            for active in active_misconceptions:
                MisconceptionService.resolve_misconception(
                    conn, student_id, concept.concept_id, active["misconception_id"], resolution_evidence="Correct answer demonstrated"
                )
            active_misconceptions = MisconceptionService.get_active_misconceptions(conn, student_id, concept.concept_id)

        # 3. Calculate turn performance score (0.0 to 1.0)
        # 40% correctness, 30% reasoning, 20% concept understanding, 10% evaluator confidence
        turn_perf = (
            (evaluation.correctness * 0.40) +
            (evaluation.reasoning_quality * 0.30) +
            (evaluation.concept_understanding * 0.20) +
            (evaluation.confidence * 0.10)
        )

        # 4. Update attempt counters and streak
        total_attempts = mastery.total_attempts + 1
        is_success = evaluation.correctness >= 0.70
        successful_attempts = mastery.successful_attempts + (1 if is_success else 0)
        consecutive_successes = (mastery.consecutive_successes + 1) if is_success else 0

        # 5. Adapt learning velocity
        velocity = mastery.learning_velocity
        if consecutive_successes >= 2:
            velocity = min(2.0, velocity * 1.1)
        elif not is_success and total_attempts > 2:
            velocity = max(0.5, velocity * 0.9)

        # 6. Calculate new mastery score via Bayesian / exponential integration
        prior_score = mastery.mastery_score
        evidence_weight = max(0.5, min(1.0, evaluation.evidence_strength))

        if total_attempts == 1:
            raw_new_score = turn_perf * evidence_weight
        else:
            # Dynamic momentum: faster velocity students accelerate faster
            momentum = 0.35 if velocity > 1.0 else 0.45
            raw_new_score = (prior_score * momentum) + (turn_perf * (1.0 - momentum) * evidence_weight)

        # Streak boost (reward for consistent multi-turn accuracy)
        if consecutive_successes >= 2:
            raw_new_score += 0.07

        # 7. Apply Misconception Cap
        if active_misconceptions:
            raw_new_score = min(raw_new_score, MasteryPolicy.MISCONCEPTION_SCORE_CAP)

        final_score = round(max(0.0, min(1.0, raw_new_score)), 3)


        # 8. Determine Mastery Level
        if final_score < MasteryPolicy.THRESHOLD_DEVELOPING:
            level = "NOVICE"
        elif final_score < MasteryPolicy.THRESHOLD_PROFICIENT:
            level = "DEVELOPING"
        elif final_score < MasteryPolicy.THRESHOLD_MASTERED:
            level = "PROFICIENT"
        else:
            # Requires at least 2 successful evaluations and 0 active misconceptions to achieve MASTERED
            if successful_attempts >= 2 and not active_misconceptions:
                level = "MASTERED"
            else:
                level = "PROFICIENT"

        # 9. Update Confidence
        confidence = round(max(0.1, min(1.0, (final_score * 0.7) + (evaluation.confidence * 0.3))), 2)

        now_iso = datetime.now(timezone.utc).isoformat()
        evidence_summary = {
            "evaluation": evaluation.to_dict(),
            "turn_performance": round(turn_perf, 3),
            "updated_at": now_iso
        }

        # 10. Persist to gl_student_mastery
        conn.execute(
            """
            UPDATE gl_student_mastery
            SET mastery_score = ?,
                mastery_level = ?,
                confidence = ?,
                learning_velocity = ?,
                total_attempts = ?,
                successful_attempts = ?,
                consecutive_successes = ?,
                last_evidence_json = ?,
                last_interaction_at = ?,
                updated_at = ?
            WHERE student_id = ? AND concept_id = ?
            """,
            (
                final_score,
                level,
                confidence,
                round(velocity, 2),
                total_attempts,
                successful_attempts,
                consecutive_successes,
                json.dumps(evidence_summary),
                now_iso,
                now_iso,
                student_id,
                concept.concept_id
            )
        )
        conn.commit()

        # Update model in-memory
        mastery.mastery_score = final_score
        mastery.mastery_level = level
        mastery.confidence = confidence
        mastery.learning_velocity = round(velocity, 2)
        mastery.total_attempts = total_attempts
        mastery.successful_attempts = successful_attempts
        mastery.consecutive_successes = consecutive_successes
        mastery.last_interaction_at = now_iso
        mastery.updated_at = now_iso
        mastery.misconceptions = active_misconceptions


        # 11. Emit durable learning event
        event = MasteryPolicy._record_event(
            conn, student_id, concept.concept_id, session_id,
            "mastery_updated",
            {
                "previous_score": prior_score,
                "new_score": final_score,
                "mastery_level": level,
                "consecutive_successes": consecutive_successes,
                "turn_performance": round(turn_perf, 3)
            }
        )

        return mastery, event

    @staticmethod
    def _record_event(conn, student_id: int, concept_id: str, session_id: str, event_type: str, payload: Dict[str, Any]) -> LearningEvent:
        event = LearningEvent(
            student_id=student_id,
            concept_id=concept_id,
            session_id=session_id,
            event_type=event_type,
            payload=payload
        )
        conn.execute(
            """
            INSERT INTO gl_learning_events (event_uuid, student_id, concept_id, session_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_uuid,
                event.student_id,
                event.concept_id,
                event.session_id,
                event.event_type,
                json.dumps(event.payload),
                event.created_at
            )
        )
        conn.commit()
        return event

    @staticmethod
    def _row_to_mastery(row) -> StudentMastery:
        return StudentMastery(
            student_id=row["student_id"],
            concept_id=row["concept_id"],
            mastery_score=row["mastery_score"] or 0.0,
            mastery_level=row["mastery_level"] or "NOVICE",
            confidence=row["confidence"] or 0.0,
            learning_velocity=row["learning_velocity"] or 1.0,
            total_attempts=row["total_attempts"] or 0,
            successful_attempts=row["successful_attempts"] or 0,
            consecutive_successes=row["consecutive_successes"] or 0,
            misconceptions=json.loads(row["misconceptions_json"] or "[]"),
            last_evidence=json.loads(row["last_evidence_json"] or "{}"),
            last_interaction_at=row["last_interaction_at"],
            last_review_at=row["last_review_at"],
            next_review_at=row["next_review_at"],
            review_interval_days=row["review_interval_days"] or 1.0,
            review_count=row["review_count"] or 0,
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )
