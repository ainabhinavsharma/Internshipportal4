"""
Spaced Review Scheduler for Guided Learning 2.0.
Calculates individualized spaced repetition intervals using SuperMemo-inspired
adaptive decay factors, velocity adjustments, and differentiated categories:
- NEW
- REINFORCEMENT
- REVIEW
- REMEDIATION
- MASTERY_VALIDATION
"""
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple, Any

class SpacedReviewScheduler:
    CATEGORIES = [
        "NEW",
        "REINFORCEMENT",
        "REVIEW",
        "REMEDIATION",
        "MASTERY_VALIDATION"
    ]

    @staticmethod
    def calculate_next_interval_days(
        category: str,
        current_interval_days: float,
        review_count: int,
        learning_velocity: float,
        performance_rating: float  # 0.0 to 1.0
    ) -> float:
        """
        Calculates the next spaced repetition interval in fractional days.
        """
        cat = category.upper()

        if cat == "NEW":
            return 1.0

        if cat == "REMEDIATION":
            # Recently corrected misconception needs rapid follow-up
            return 0.5  # 12 hours

        if cat == "REINFORCEMENT":
            # Developing skill reinforcement
            return max(1.0, round(1.5 * learning_velocity, 1))

        if cat == "MASTERY_VALIDATION":
            # Validating near-mastery
            return max(1.5, round(2.0 * learning_velocity, 1))

        # Standard REVIEW category (SM-2 adapted for engineering concepts)
        if review_count == 0:
            next_interval = 1.0
        elif review_count == 1:
            next_interval = 3.0
        else:
            # Multiplier between 1.4 and 2.5 depending on performance & velocity
            ease_factor = 1.6 + (performance_rating * 0.4) + ((learning_velocity - 1.0) * 0.2)
            ease_factor = max(1.3, min(2.6, ease_factor))
            next_interval = current_interval_days * ease_factor

        # If performance was weak, contract the interval
        if performance_rating < 0.6:
            next_interval = max(1.0, next_interval * 0.5)

        return round(next_interval, 2)

    @staticmethod
    def schedule_next_review(
        conn,
        student_id: int,
        concept_id: str,
        category: str,
        performance_rating: float = 0.8
    ) -> Tuple[str, float]:
        """
        Updates gl_student_mastery with newly computed next_review_at and review_interval_days.
        Returns: (next_review_iso: str, interval_days: float)
        """
        row = conn.execute(
            "SELECT review_interval_days, review_count, learning_velocity FROM gl_student_mastery WHERE student_id = ? AND concept_id = ?",
            (student_id, concept_id)
        ).fetchone()

        cur_interval = row["review_interval_days"] if (row and row["review_interval_days"]) else 1.0
        rev_count = row["review_count"] if (row and row["review_count"]) else 0
        velocity = row["learning_velocity"] if (row and row["learning_velocity"]) else 1.0

        next_interval = SpacedReviewScheduler.calculate_next_interval_days(
            category=category,
            current_interval_days=cur_interval,
            review_count=rev_count,
            learning_velocity=velocity,
            performance_rating=performance_rating
        )

        now = datetime.now(timezone.utc)
        next_review_dt = now + timedelta(days=next_interval)
        next_review_iso = next_review_dt.isoformat()
        now_iso = now.isoformat()

        conn.execute(
            """
            UPDATE gl_student_mastery
            SET review_interval_days = ?,
                review_count = review_count + 1,
                last_review_at = ?,
                next_review_at = ?,
                updated_at = ?
            WHERE student_id = ? AND concept_id = ?
            """,
            (next_interval, now_iso, next_review_iso, now_iso, student_id, concept_id)
        )
        conn.commit()

        return next_review_iso, next_interval

    @staticmethod
    def get_due_reviews_for_student(conn, student_id: int) -> List[Dict[str, Any]]:
        """
        Fetches all concepts for a student where review is due (next_review_at <= now).
        Calculates urgency score: (elapsed_seconds / interval_seconds).
        """
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        rows = conn.execute(
            """
            SELECT m.*, c.name as concept_name, c.domain, c.difficulty
            FROM gl_student_mastery m
            JOIN gl_concepts c ON c.concept_id = m.concept_id
            WHERE m.student_id = ?
              AND m.next_review_at IS NOT NULL
              AND m.next_review_at <= ?
            ORDER BY m.next_review_at ASC
            """,
            (student_id, now_iso)
        ).fetchall()

        due_list = []
        for r in rows:
            m_dict = dict(r)
            # Calculate urgency
            try:
                next_dt = datetime.fromisoformat(r["next_review_at"])
                last_dt = datetime.fromisoformat(r["last_review_at"]) if r["last_review_at"] else (next_dt - timedelta(days=1))
                total_duration = max(1.0, (next_dt - last_dt).total_seconds())
                elapsed = max(0.0, (now - last_dt).total_seconds())
                urgency = round(elapsed / total_duration, 2)
            except Exception:
                urgency = 1.0

            m_dict["urgency"] = urgency
            m_dict["is_overdue"] = urgency >= 1.5
            due_list.append(m_dict)

        return sorted(due_list, key=lambda x: x["urgency"], reverse=True)
