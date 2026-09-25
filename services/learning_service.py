"""
services/learning_service.py - Unified Guided Learning Domain Facade
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Coordinates concept graph, adaptive turn execution, spaced review, and session persistence.
"""
from typing import Optional, Dict, Any, List
from services.learning.concept_service import ConceptService
from services.learning.session_service import LearningSessionService
from services.learning.adaptive_engine import AdaptiveActionEngine
from services.learning.spaced_review import SpacedReviewScheduler
from services.learning.rag_tutor import GroundedRAGTutor


class LearningService:
    """High-level Guided Learning facade."""

    @staticmethod
    def get_or_create_session(conn, student_id: int, course_id: int, concept_id: Optional[str] = None):
        return LearningSessionService.get_or_create_session(conn, student_id, course_id, concept_id)

    @staticmethod
    def process_turn(
        conn,
        session_id: str,
        student_id: int,
        student_input: str,
        idempotency_key: Optional[str] = None,
        llm_caller=None
    ) -> Dict[str, Any]:
        return LearningSessionService.process_turn_atomic(
            conn=conn,
            session_id=session_id,
            student_id=student_id,
            student_input=student_input,
            idempotency_key=idempotency_key,
            llm_caller=llm_caller
        )

    @staticmethod
    def resume_session(conn, session_id: str, student_id: int) -> Dict[str, Any]:
        return LearningSessionService.resume_session_state(conn, session_id, student_id)

    @staticmethod
    def get_due_reviews(conn, student_id: int) -> List[Dict[str, Any]]:
        return SpacedReviewScheduler.get_due_reviews_for_student(conn, student_id)

    @staticmethod
    def get_domain_concept_tree(conn, domain: str) -> List[Dict[str, Any]]:
        concepts = ConceptService.list_concepts_for_domain(conn, domain)
        return [c.to_dict() for c in concepts]

    @staticmethod
    def build_tutor_prompt(concept: dict, current_action: str, student_mastery_level: str) -> str:
        return GroundedRAGTutor.build_grounded_system_prompt(concept, current_action, student_mastery_level)
