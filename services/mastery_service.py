"""
services/mastery_service.py - Student Mastery Domain Facade
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Coordinates deterministic mastery policy, Bayesian score calculation, and misconception tracking.
"""
from typing import Optional, Dict, Any, List
from services.learning.mastery_policy import MasteryPolicy
from services.learning.misconception_service import MisconceptionService


class MasteryService:
    """High-level Student Mastery facade."""

    @staticmethod
    def get_mastery(conn, student_id: int, concept_id: str):
        return MasteryPolicy.get_or_create_mastery(conn, student_id, concept_id)

    @staticmethod
    def update_mastery(
        conn,
        student_id: int,
        concept_id: str,
        turn_perf: float,
        evidence_weight: float = 0.5,
        detected_misconceptions: Optional[List[str]] = None
    ):
        return MasteryPolicy.update_mastery(
            conn=conn,
            student_id=student_id,
            concept_id=concept_id,
            turn_perf=turn_perf,
            evidence_weight=evidence_weight,
            detected_misconceptions=detected_misconceptions
        )

    @staticmethod
    def get_active_misconceptions(conn, student_id: int, concept_id: str) -> List[Dict[str, Any]]:
        return MisconceptionService.get_active_misconceptions(conn, student_id, concept_id)

    @staticmethod
    def resolve_misconception(conn, student_id: int, misconception_id: str) -> bool:
        return MisconceptionService.resolve_misconception(conn, student_id, misconception_id)
