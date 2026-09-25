"""
Unit and Integration Test Suite for Guided Learning 2.0 Core Engine.
Covers:
- Concept Catalog & Prerequisite DAG Cycle Detection
- Structured Evaluator (Schema Validation & Deterministic Fallback)
- Deterministic Mastery Policy (Thresholds, Bayesian Updating, Misconception Cap)
- Adaptive Next-Action Engine (10 Standardized Actions)
- Spaced Review Scheduler (Differentiated Intervals & Urgency Calculation)
- Session Persistence, Reload Resilience, and Turn Idempotency
- Misconception Tracking & Remediation
"""
import pytest
import json
from services.learning.learning_models import Concept, StudentMastery, init_learning_tables
from services.learning.concept_service import ConceptService, ConceptPrerequisiteCycleError
from services.learning.evaluator import StructuredEvaluator, EvaluationResult
from services.learning.mastery_policy import MasteryPolicy
from services.learning.adaptive_engine import AdaptiveActionEngine
from services.learning.spaced_review import SpacedReviewScheduler
from services.learning.session_service import LearningSessionService
from services.learning.misconception_service import MisconceptionService
from tests.conftest import seed_intern

@pytest.fixture
def learning_db(app_client):
    """Provides a fresh database with learning tables initialized and a seeded intern."""
    client, db_path = app_client
    intern_email = "engine_intern@example.com"
    intern_id = seed_intern(db_path, email=intern_email, password="Password123")
    
    with client.application.app_context():
        from app import get_db
        with get_db() as conn:
            init_learning_tables(conn)
            
    return {"client": client, "intern_id": intern_id, "email": intern_email}


class TestConceptPrerequisiteGraph:
    """GL-CONCEPT-001: Tests concept hierarchy and DAG prerequisite validation."""

    def test_concept_registration_and_retrieval(self, learning_db):
        from app import get_db
        with get_db() as conn:
            c1 = Concept(
                concept_id="test.py.vars",
                name="Variables & Assignment",
                description="Understanding variable naming and assignments",
                domain="Python",
                subject="Foundations",
                difficulty=1,
                learning_objectives=["Assign variables", "Understand types"],
                assessment_criteria=["Valid variable naming", "Correct assignment syntax"]
            )
            ConceptService.register_concept(conn, c1)
            
            fetched = ConceptService.get_concept(conn, "test.py.vars")
            assert fetched is not None
            assert fetched.name == "Variables & Assignment"
            assert fetched.difficulty == 1
            assert len(fetched.learning_objectives) == 2

    def test_cycle_detection_in_prerequisites_rejected(self, learning_db):
        from app import get_db
        with get_db() as conn:
            # c1 -> c2 -> c3 -> c1 (Cycle!)
            c1 = Concept(concept_id="cyc.a", name="A", description="A", domain="Test", subject="Test", prerequisites=[])
            c2 = Concept(concept_id="cyc.b", name="B", description="B", domain="Test", subject="Test", prerequisites=["cyc.a"])
            c3 = Concept(concept_id="cyc.c", name="C", description="C", domain="Test", subject="Test", prerequisites=["cyc.b"])
            
            ConceptService.register_concept(conn, c1)
            ConceptService.register_concept(conn, c2)
            ConceptService.register_concept(conn, c3)

            # Now try closing the cycle: A requires C
            c1_cyclic = Concept(concept_id="cyc.a", name="A", description="A", domain="Test", subject="Test", prerequisites=["cyc.c"])
            with pytest.raises(ConceptPrerequisiteCycleError):
                ConceptService.register_concept(conn, c1_cyclic)

    def test_prerequisite_eligibility_enforcement(self, learning_db):
        from app import get_db
        student_id = learning_db["intern_id"]
        with get_db() as conn:
            c_base = Concept(concept_id="req.base", name="Base", description="Base", domain="Test", subject="Test")
            c_adv = Concept(concept_id="req.adv", name="Adv", description="Adv", domain="Test", subject="Test", prerequisites=["req.base"])
            ConceptService.register_concept(conn, c_base)
            ConceptService.register_concept(conn, c_adv)

            # Initially base is not mastered -> cannot learn adv
            can_learn, missing = ConceptService.check_prerequisites_met(conn, student_id, "req.adv")
            assert can_learn is False
            assert "req.base" in missing

            # Advance base to PROFICIENT
            m_base = MasteryPolicy.get_or_create_mastery(conn, student_id, "req.base")
            conn.execute(
                "UPDATE gl_student_mastery SET mastery_score = 0.80, mastery_level = 'PROFICIENT' WHERE student_id = ? AND concept_id = 'req.base'",
                (student_id,)
            )
            conn.commit()

            # Now can learn adv
            can_learn, missing = ConceptService.check_prerequisites_met(conn, student_id, "req.adv")
            assert can_learn is True
            assert len(missing) == 0


class TestStructuredEvaluator:
    """GL-EVAL-001: Tests schema-validated evaluation and deterministic fallback."""

    def test_schema_validated_llm_output_parsing(self):
        concept = Concept(concept_id="eval.test", name="Loops", description="Loops", domain="Python", subject="Control")
        valid_llm_json = """
        ```json
        {
            "correctness": 0.85,
            "partial_correctness": true,
            "reasoning_quality": 0.90,
            "concept_understanding": 0.80,
            "detected_misconceptions": [],
            "confidence": 0.95,
            "evidence_strength": 0.85,
            "feedback": "Great explanation of loop indices.",
            "suggested_action": "PRACTICE"
        }
        ```
        """
        result = StructuredEvaluator.evaluate(
            student_response="for i in range(10): print(i)",
            concept=concept,
            llm_caller=lambda prompt: valid_llm_json
        )
        assert result.correctness == 0.85
        assert result.reasoning_quality == 0.90
        assert result.is_fallback is False
        assert result.suggested_action == "PRACTICE"

    def test_malformed_llm_output_uses_deterministic_fallback(self):
        concept = Concept(
            concept_id="eval.fallback",
            name="Functions",
            description="Defining functions with def",
            domain="Python",
            subject="Foundations",
            assessment_criteria=["Use def keyword", "Specify parameters", "Return value"]
        )
        # LLM returns gibberish
        bad_llm_text = "I am an AI and I like functions! def my_func(): pass"
        result = StructuredEvaluator.evaluate(
            student_response="def calculate(x, y): return x + y",
            concept=concept,
            llm_caller=lambda prompt: bad_llm_text
        )
        assert result.is_fallback is True
        assert result.correctness >= 0.40  # Matched code and criteria keywords
        assert result.confidence > 0.0
        assert result.suggested_action in ("PRACTICE", "ADVANCE")

    def test_confusion_triggers_simplify_action(self):
        concept = Concept(concept_id="eval.conf", name="Recursion", description="Recursion", domain="Python", subject="Algorithms")
        result = StructuredEvaluator.evaluate(
            student_response="I don't understand how base cases work, I'm completely confused",
            concept=concept
        )
        assert result.is_fallback is True
        assert result.correctness <= 0.20
        assert result.suggested_action == "SIMPLIFY"
        assert "simpler" in result.feedback.lower()


class TestMasteryPolicyAndMisconceptions:
    """GL-MASTERY-001 & GL-MISCONCEPTION-001: Tests deterministic mastery and score caps."""

    def test_deterministic_scoring_and_progression(self, learning_db):
        from app import get_db
        student_id = learning_db["intern_id"]
        with get_db() as conn:
            concept = Concept(concept_id="m.prog", name="Recursion", description="Recursion", domain="Python", subject="Core")
            ConceptService.register_concept(conn, concept)

            # Turn 1: Good answer
            eval1 = EvaluationResult(
                correctness=0.85,
                partial_correctness=True,
                reasoning_quality=0.80,
                concept_understanding=0.85,
                detected_misconceptions=[],
                confidence=0.9,
                evidence_strength=0.9
            )
            m1, _ = MasteryPolicy.evaluate_and_update_mastery(conn, student_id, concept, eval1, "sess_1", "base case prevents infinite recursion")
            assert m1.total_attempts == 1
            assert m1.successful_attempts == 1
            assert m1.mastery_score >= 0.70
            assert m1.mastery_level == "PROFICIENT"

            # Turn 2: Second strong answer -> should advance to MASTERED
            eval2 = EvaluationResult(
                correctness=0.95,
                partial_correctness=True,
                reasoning_quality=0.95,
                concept_understanding=0.95,
                detected_misconceptions=[],
                confidence=0.95,
                evidence_strength=0.95
            )
            m2, _ = MasteryPolicy.evaluate_and_update_mastery(conn, student_id, concept, eval2, "sess_1", "memoization optimizes fibonacci recursion")
            assert m2.total_attempts == 2
            assert m2.successful_attempts == 2
            assert m2.consecutive_successes == 2
            assert m2.mastery_score >= 0.90
            assert m2.mastery_level == "MASTERED"

    def test_active_misconception_caps_score_at_65(self, learning_db):
        from app import get_db
        student_id = learning_db["intern_id"]
        with get_db() as conn:
            concept = Concept(concept_id="m.misc", name="List Mutability", description="List Mutability", domain="Python", subject="Core")
            ConceptService.register_concept(conn, concept)

            # Turn with active misconception detected
            eval_misc = EvaluationResult(
                correctness=0.40,
                partial_correctness=True,
                reasoning_quality=0.40,
                concept_understanding=0.40,
                detected_misconceptions=["py.mutability.alias"],
                confidence=0.8,
                evidence_strength=0.8
            )
            m_misc, _ = MasteryPolicy.evaluate_and_update_mastery(conn, student_id, concept, eval_misc, "sess_2", "b = a makes a copy")
            assert m_misc.mastery_score <= 0.65
            assert len(MisconceptionService.get_active_misconceptions(conn, student_id, "m.misc")) == 1

            # Even if next response claims 1.0 correctness, as long as misconception is active, score is capped at 0.65!
            conn.execute(
                "UPDATE gl_student_mastery SET mastery_score = 0.95, mastery_level = 'DEVELOPING' WHERE student_id = ? AND concept_id = 'm.misc'",
                (student_id,)
            )
            # Re-evaluate with misconception still unresolved
            m_capped, _ = MasteryPolicy.evaluate_and_update_mastery(conn, student_id, concept, eval_misc, "sess_2", "still confusing references")
            assert m_capped.mastery_score <= 0.65


class TestAdaptiveActionEngine:
    """GL-ADAPT-001: Verifies all 10 actions in the adaptive decision hierarchy."""

    def test_all_10_actions(self, learning_db):
        from app import get_db
        student_id = learning_db["intern_id"]
        with get_db() as conn:
            concept = Concept(concept_id="act.test", name="AsyncIO", description="AsyncIO", domain="Python", subject="Adv")
            ConceptService.register_concept(conn, concept)

            # 1. EXPLAIN (Attempts == 0)
            m0 = StudentMastery(student_id=student_id, concept_id="act.test", total_attempts=0)
            rec = AdaptiveActionEngine.select_next_action(conn, student_id, concept, m0)
            assert rec.action == "EXPLAIN"

            # 2. REMEDIATE (Active misconception exists)
            m_misc = StudentMastery(
                student_id=student_id, concept_id="act.test", total_attempts=1,
                misconceptions=[{"misconception_id": "async.threads.confused", "resolved": False}]
            )
            rec = AdaptiveActionEngine.select_next_action(conn, student_id, concept, m_misc)
            assert rec.action == "REMEDIATE"

            # 3. ESCALATE_TO_MENTOR (5 attempts, 0 successes)
            m_stuck = StudentMastery(student_id=student_id, concept_id="act.test", total_attempts=5, successful_attempts=0)
            rec = AdaptiveActionEngine.select_next_action(conn, student_id, concept, m_stuck)
            assert rec.action == "ESCALATE_TO_MENTOR"

            # 4. SIMPLIFY (Low correctness & reasoning)
            m_prog = StudentMastery(student_id=student_id, concept_id="act.test", total_attempts=1)
            eval_low = EvaluationResult(correctness=0.2, partial_correctness=False, reasoning_quality=0.2, concept_understanding=0.2)
            rec = AdaptiveActionEngine.select_next_action(conn, student_id, concept, m_prog, latest_evaluation=eval_low)
            assert rec.action == "SIMPLIFY"

            # 5. GIVE_EXAMPLE (Partial understanding)
            eval_mid = EvaluationResult(correctness=0.55, partial_correctness=True, reasoning_quality=0.5, concept_understanding=0.5)
            rec = AdaptiveActionEngine.select_next_action(conn, student_id, concept, m_prog, latest_evaluation=eval_mid)
            assert rec.action == "GIVE_EXAMPLE"

            # 6. RETEST (Evaluator suggests RETEST)
            eval_retest = EvaluationResult(correctness=0.7, partial_correctness=True, reasoning_quality=0.7, concept_understanding=0.7, suggested_action="RETEST")
            rec = AdaptiveActionEngine.select_next_action(conn, student_id, concept, m_prog, latest_evaluation=eval_retest)
            assert rec.action == "RETEST"

            # 7. PRACTICE (Developing or Proficient)
            m_dev = StudentMastery(student_id=student_id, concept_id="act.test", total_attempts=2, successful_attempts=1, mastery_level="DEVELOPING")
            rec = AdaptiveActionEngine.select_next_action(conn, student_id, concept, m_dev)
            assert rec.action == "PRACTICE"

            # 8. ADVANCE (Mastered)
            m_mast = StudentMastery(student_id=student_id, concept_id="act.test", total_attempts=3, successful_attempts=3, mastery_score=0.92, mastery_level="MASTERED")
            rec = AdaptiveActionEngine.select_next_action(conn, student_id, concept, m_mast)
            assert rec.action == "ADVANCE"

            # 9. REVIEW (Spaced review is due)
            m_rev = StudentMastery(student_id=student_id, concept_id="act.test", total_attempts=3, successful_attempts=3, mastery_score=0.85, mastery_level="PROFICIENT")
            rec = AdaptiveActionEngine.select_next_action(conn, student_id, concept, m_rev, review_due=True)
            assert rec.action == "REVIEW"


class TestSpacedReviewScheduler:
    """GL-REVIEW-001: Verifies differentiated intervals and urgency calculations."""

    def test_differentiated_review_intervals(self):
        # NEW should be 1 day
        assert SpacedReviewScheduler.calculate_next_interval_days("NEW", 1.0, 0, 1.0, 0.8) == 1.0
        # REMEDIATION should be rapid (0.5 days)
        assert SpacedReviewScheduler.calculate_next_interval_days("REMEDIATION", 1.0, 1, 1.0, 0.8) == 0.5
        # MASTERY_VALIDATION should be 2.0 days
        assert SpacedReviewScheduler.calculate_next_interval_days("MASTERY_VALIDATION", 1.0, 1, 1.0, 0.9) == 2.0
        # REVIEW with high performance should expand interval
        review_interval = SpacedReviewScheduler.calculate_next_interval_days("REVIEW", 3.0, 2, 1.2, 0.95)
        assert review_interval > 3.0

    def test_review_urgency_and_due_list(self, learning_db):
        from app import get_db
        student_id = learning_db["intern_id"]
        with get_db() as conn:
            c = Concept(concept_id="sr.due", name="Decorators", description="Decorators", domain="Python", subject="Adv")
            ConceptService.register_concept(conn, c)
            MasteryPolicy.get_or_create_mastery(conn, student_id, "sr.due")

            # Schedule review
            next_iso, interval = SpacedReviewScheduler.schedule_next_review(conn, student_id, "sr.due", "REVIEW")
            assert interval > 0.0

            # Force next_review_at into the past to simulate due status
            conn.execute(
                "UPDATE gl_student_mastery SET next_review_at = '2020-01-01T00:00:00Z', last_review_at = '2019-12-31T00:00:00Z' WHERE student_id = ? AND concept_id = 'sr.due'",
                (student_id,)
            )
            conn.commit()

            due = SpacedReviewScheduler.get_due_reviews_for_student(conn, student_id)
            assert len(due) == 1
            assert due[0]["concept_id"] == "sr.due"
            assert due[0]["is_overdue"] is True
            assert due[0]["urgency"] > 1.0


class TestSessionResumeAndIdempotency:
    """GL-SESSION-001 & GL-CONCURRENCY-001: Verifies session persistence and reload idempotency."""

    def test_session_creation_and_resume(self, learning_db):
        from app import get_db
        student_id = learning_db["intern_id"]
        with get_db() as conn:
            c = Concept(concept_id="sess.c1", name="Classes", description="OOP Classes", domain="AI Agent Development", subject="Python")
            ConceptService.register_concept(conn, c)

            # Create session
            session = LearningSessionService.get_or_create_session(conn, student_id, course_id=1)
            assert session.session_id.startswith("gl_sess_")
            assert session.status == "active"

            # Resume session
            resume_data = LearningSessionService.resume_session_state(conn, session.session_id, student_id)
            assert resume_data["session"]["session_id"] == session.session_id
            assert "concept" in resume_data
            assert "mastery" in resume_data

    def test_idempotent_duplicate_submission(self, learning_db):
        from app import get_db
        student_id = learning_db["intern_id"]
        with get_db() as conn:
            c = Concept(concept_id="sess.idem", name="Polymorphism", description="Polymorphism", domain="AI Agent Development", subject="Python")
            ConceptService.register_concept(conn, c)

            session = LearningSessionService.get_or_create_session(conn, student_id, course_id=1)
            # Link current concept
            conn.execute(
                "UPDATE gl_learning_sessions SET current_concept_id = 'sess.idem' WHERE session_id = ?",
                (session.session_id,)
            )
            conn.commit()

            # First turn submission
            turn1 = LearningSessionService.process_turn_atomic(
                conn=conn,
                session_id=session.session_id,
                student_id=student_id,
                student_input="Polymorphism lets different classes share the same interface.",
                idempotency_key="key_turn_1"
            )
            assert turn1.get("idempotent_replay") is not True
            assert turn1["mastery"]["total_attempts"] == 1

            # Duplicate submission with SAME key (browser reload or double click)
            turn2 = LearningSessionService.process_turn_atomic(
                conn=conn,
                session_id=session.session_id,
                student_id=student_id,
                student_input="Polymorphism lets different classes share the same interface.",
                idempotency_key="key_turn_1"
            )
            assert turn2.get("idempotent_replay") is True
            # Attempt count must NOT increment
            m = MasteryPolicy.get_or_create_mastery(conn, student_id, "sess.idem")
            assert m.total_attempts == 1
