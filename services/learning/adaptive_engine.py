"""
Adaptive Next-Action Engine for Guided Learning 2.0.
Implements the 10 deterministic actions:
- EXPLAIN
- SIMPLIFY
- GIVE_EXAMPLE
- ASK_GUIDED_QUESTION
- PRACTICE
- REMEDIATE
- RETEST
- REVIEW
- ADVANCE
- ESCALATE_TO_MENTOR

Considers mastery, confidence, recent performance, prerequisites, misconceptions,
review urgency, velocity, and session history in a strictly deterministic decision hierarchy.
"""
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List
from services.learning.learning_models import Concept, StudentMastery
from services.learning.evaluator import EvaluationResult
from services.learning.concept_service import ConceptService

@dataclass
class NextActionRecommendation:
    action: str  # One of the 10 standardized actions
    concept_id: str
    target_misconception_id: Optional[str] = None
    reason: str = ""
    suggested_prompt: str = ""
    next_concept_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AdaptiveActionEngine:
    ACTIONS = [
        "EXPLAIN",
        "SIMPLIFY",
        "GIVE_EXAMPLE",
        "ASK_GUIDED_QUESTION",
        "PRACTICE",
        "REMEDIATE",
        "RETEST",
        "REVIEW",
        "ADVANCE",
        "ESCALATE_TO_MENTOR"
    ]

    @staticmethod
    def select_next_action(
        conn,
        student_id: int,
        concept: Concept,
        mastery: StudentMastery,
        latest_evaluation: Optional[EvaluationResult] = None,
        review_due: bool = False,
        consecutive_remediation_failures: int = 0
    ) -> NextActionRecommendation:
        """
        Determines the single best next pedagogical action using strict decision hierarchy.
        """
        cid = concept.concept_id

        # 1. ESCALATE_TO_MENTOR check (Severe struggle)
        if (
            (mastery.total_attempts >= 5 and mastery.successful_attempts == 0) or
            consecutive_remediation_failures >= 3
        ):
            return NextActionRecommendation(
                action="ESCALATE_TO_MENTOR",
                concept_id=cid,
                reason="Student demonstrates persistent difficulty after multiple interventions. Human mentor guidance requested.",
                suggested_prompt="A senior engineering mentor has been notified to provide 1-on-1 assistance with this concept."
            )

        # 2. REVIEW check (Spaced review is due for an established concept)
        if review_due and mastery.mastery_score >= 0.70:
            return NextActionRecommendation(
                action="REVIEW",
                concept_id=cid,
                reason="Spaced review schedule indicates recall interval is due.",
                suggested_prompt=f"Welcome back! Let's do a quick spaced review check on {concept.name} to reinforce long-term memory."
            )

        # 3. REMEDIATE check (Active unresolved misconception detected)
        active_misconceptions = [m for m in mastery.misconceptions if not m.get("resolved")]
        if active_misconceptions:
            target_misc = active_misconceptions[0]
            m_id = target_misc.get("misconception_id", "MISC")
            return NextActionRecommendation(
                action="REMEDIATE",
                concept_id=cid,
                target_misconception_id=m_id,
                reason=f"Active misconception detected: {m_id}. Targeted remediation required.",
                suggested_prompt=f"Let's focus on a common point of confusion: {m_id}. Here is why that intuition differs in practice."
            )

        # 4. Brand New Concept Check -> EXPLAIN
        if mastery.total_attempts == 0:
            return NextActionRecommendation(
                action="EXPLAIN",
                concept_id=cid,
                reason="Student has not yet engaged with this concept. Provide initial motivation and intuition.",
                suggested_prompt=f"Welcome to {concept.name}! Let's start with why this is critical and how it functions."
            )

        # 5. RETEST check (Completed remediation or simplify, now verify)
        if latest_evaluation and latest_evaluation.suggested_action == "RETEST":
            return NextActionRecommendation(
                action="RETEST",
                concept_id=cid,
                reason="Validating comprehension after targeted correction.",
                suggested_prompt="Now that we've walked through the key distinction, try solving this new variation."
            )

        # 6. SIMPLIFY check (Struggling with low correctness and low reasoning)
        if latest_evaluation and (
            latest_evaluation.correctness < 0.40 and
            latest_evaluation.reasoning_quality < 0.40
        ):
            return NextActionRecommendation(
                action="SIMPLIFY",
                concept_id=cid,
                reason="Low correctness and reasoning. Break down the concept into smaller, simpler building blocks.",
                suggested_prompt=f"Let's step back and look at {concept.name} from a simpler angle with a tangible analogy."
            )

        # 7. GIVE_EXAMPLE check (Partial understanding, needs code or concrete illustration)
        if latest_evaluation and 0.40 <= latest_evaluation.correctness < 0.70:
            return NextActionRecommendation(
                action="GIVE_EXAMPLE",
                concept_id=cid,
                reason="Partial grasp identified. Concrete code example needed to clarify implementation details.",
                suggested_prompt=f"Here is a concrete, line-by-line implementation demonstrating {concept.name}."
            )

        # 8. ADVANCE check (Concept is mastered, find next unlocked concept in domain DAG)
        if mastery.mastery_level == "MASTERED" or (mastery.mastery_score >= 0.90 and mastery.successful_attempts >= 2):
            eligible = ConceptService.get_eligible_concepts_in_domain(conn, mastery.student_id, concept.domain)
            next_concept = eligible[0] if eligible else None
            next_cid = next_concept.concept_id if next_concept else None

            return NextActionRecommendation(
                action="ADVANCE",
                concept_id=cid,
                next_concept_id=next_cid,
                reason=f"Student has mastered {concept.name}. Advancing to next topic in curriculum graph.",
                suggested_prompt=f"Outstanding work! You have mastered {concept.name}." + (f" Next up: {next_concept.name}." if next_concept else " All module concepts completed!")
            )

        # 9. PRACTICE check (Concept developing or proficient, reinforce with active challenge)
        if mastery.mastery_level in ("DEVELOPING", "PROFICIENT"):
            return NextActionRecommendation(
                action="PRACTICE",
                concept_id=cid,
                reason="Student is progressing well. Present an active hands-on coding challenge.",
                suggested_prompt="You've got the basics down. Let's tackle a practical challenge to solidify your skills."
            )

        # 10. ASK_GUIDED_QUESTION (Default conversational check)
        return NextActionRecommendation(
            action="ASK_GUIDED_QUESTION",
            concept_id=cid,
            reason="Check understanding with a targeted guided question.",
            suggested_prompt=f"Based on what we just covered about {concept.name}, how would you approach this scenario?"
        )
