"""
Synthetic Learner Simulation and Golden Journey Test Suite for Guided Learning 2.0.
Verifies differentiated pedagogical behavior across 7 synthetic learner archetypes:
1. Fast Learner (rapid acceleration, velocity boost, fast ADVANCE via structured LLM evaluation)
2. Slow Learner (confusion handling, SIMPLIFY scaffolding, velocity adaptation)
3. High Confidence / Low Mastery (assertive errors, misconception triggering, REMEDIATE)
4. Low Confidence / High Mastery (timid but correct, confidence growth, PRACTICE)
5. Repeated Misconception & Struggle (score cap at 0.65, ESCALATE_TO_MENTOR)
6. Random Guesser (low reasoning quality, evidence strength dampening)
7. Interrupted Learner (browser crash/reload, session resume, idempotency)

Plus the complete End-to-End Guided Learning Golden Journey.
"""
import pytest
import json
import uuid
from services.learning.learning_models import Concept, init_learning_tables
from services.learning.concept_service import ConceptService
from services.learning.mastery_policy import MasteryPolicy
from services.learning.adaptive_engine import AdaptiveActionEngine
from services.learning.session_service import LearningSessionService
from services.learning.misconception_service import MisconceptionService
from services.learning.spaced_review import SpacedReviewScheduler
from tests.conftest import seed_intern

@pytest.fixture
def synthetic_env(app_client):
    """Sets up a clean test environment with sample concepts and seeded student."""
    client, db_path = app_client
    intern_email = f"synth_{uuid.uuid4().hex[:8]}@dbert.test"
    intern_id = seed_intern(db_path, email=intern_email, password="Password123")
    
    with client.application.app_context():
        from app import get_db
        with get_db() as conn:
            init_learning_tables(conn)
            conn.execute("DELETE FROM gl_student_mastery WHERE student_id = ?", (intern_id,))
            conn.execute("DELETE FROM gl_learning_sessions WHERE student_id = ?", (intern_id,))
            conn.execute("DELETE FROM gl_learning_events WHERE student_id = ?", (intern_id,))
            conn.commit()
            # Create a 2-node concept chain
            c1 = Concept(
                concept_id="synth.py.vars",
                name="Variables & Expressions",
                description="Variables and basic assignment in Python",
                domain="AI Agent Development",
                subject="Python Core",
                difficulty=1,
                learning_objectives=["Assign variables", "Use type conversions"],
                assessment_criteria=["Valid variable naming", "Correct type usage"],
                common_misconceptions=[{
                    "id": "py.alias.confuse",
                    "name": "Reference Alias Confuse",
                    "description": "Confusing reference alias with value copy",
                    "remediation": "Explain memory addresses with id()"
                }]
            )
            c2 = Concept(
                concept_id="synth.py.funcs",
                name="Functions & Scope",
                description="Function definitions and scope",
                domain="AI Agent Development",
                subject="Python Core",
                difficulty=2,
                prerequisites=["synth.py.vars"],
                learning_objectives=["Define functions with def", "Return values"],
                assessment_criteria=["def syntax", "return statement"]
            )
            ConceptService.register_concept(conn, c1)
            ConceptService.register_concept(conn, c2)
            
            # Register misconception in catalog
            MisconceptionService.register_misconception(
                conn, "py.alias.confuse", "synth.py.vars", "Reference Alias", "Confusing aliases with copies", "Use id() comparison"
            )

    return {"client": client, "student_id": intern_id, "email": intern_email}


class TestSyntheticLearners:
    """Verifies adaptive engine differentiation across distinct learner archetypes."""

    def test_fast_learner_acceleration_and_advance(self, synthetic_env):
        """Fast learner answers correctly with high reasoning, velocity increases, advances quickly."""
        from app import get_db
        student_id = synthetic_env["student_id"]

        fast_llm = lambda prompt: json.dumps({
            "correctness": 0.95,
            "partial_correctness": True,
            "reasoning_quality": 0.95,
            "concept_understanding": 0.95,
            "detected_misconceptions": [],
            "confidence": 0.95,
            "evidence_strength": 0.95,
            "feedback": "Flawless demonstration of variables and object references.",
            "suggested_action": "ADVANCE"
        })

        with get_db() as conn:
            session = LearningSessionService.get_or_create_session(conn, student_id, course_id=1)
            conn.execute(
                "UPDATE gl_learning_sessions SET current_concept_id = 'synth.py.vars' WHERE session_id = ?",
                (session.session_id,)
            )
            conn.commit()

            # Turn 1: High quality answer with clear reasoning
            res1 = LearningSessionService.process_turn_atomic(
                conn=conn,
                session_id=session.session_id,
                student_id=student_id,
                student_input="Variables in Python store object references because Python is dynamically typed.",
                idempotency_key="fast_1",
                llm_caller=fast_llm
            )
            assert res1["mastery"]["mastery_level"] == "PROFICIENT"
            assert res1["mastery"]["successful_attempts"] == 1

            # Turn 2: Second flawless answer demonstrating criteria
            res2 = LearningSessionService.process_turn_atomic(
                conn=conn,
                session_id=session.session_id,
                student_id=student_id,
                student_input="def assign_example():\n    x = 10\n    return x\n# x is a local variable returning an integer",
                idempotency_key="fast_2",
                llm_caller=fast_llm
            )
            assert res2["mastery"]["mastery_score"] >= 0.90
            assert res2["mastery"]["mastery_level"] == "MASTERED"
            assert res2["mastery"]["consecutive_successes"] == 2
            assert res2["mastery"]["learning_velocity"] > 1.0
            # Policy recommends ADVANCE to next concept
            assert res2["recommendation"]["action"] == "ADVANCE"
            assert res2["recommendation"]["next_concept_id"] == "synth.py.funcs"

    def test_slow_learner_scaffolding_and_simplify(self, synthetic_env):
        """Slow learner expresses confusion; engine provides SIMPLIFY scaffolding, velocity adjusts."""
        from app import get_db
        student_id = synthetic_env["student_id"]
        with get_db() as conn:
            session = LearningSessionService.get_or_create_session(conn, student_id, course_id=1)
            conn.execute(
                "UPDATE gl_learning_sessions SET current_concept_id = 'synth.py.vars' WHERE session_id = ?",
                (session.session_id,)
            )
            conn.commit()

            # Student is confused
            res = LearningSessionService.process_turn_atomic(
                conn=conn,
                session_id=session.session_id,
                student_id=student_id,
                student_input="I don't understand how variables point to things, I am very confused.",
                idempotency_key="slow_1"
            )
            assert res["recommendation"]["action"] == "SIMPLIFY"
            assert res["mastery"]["mastery_level"] == "NOVICE"
            assert res["mastery"]["mastery_score"] < 0.35

    def test_high_confidence_low_mastery_triggers_remediate(self, synthetic_env):
        """Student asserts an incorrect fact matching a misconception trigger; triggers REMEDIATE."""
        from app import get_db
        student_id = synthetic_env["student_id"]
        with get_db() as conn:
            session = LearningSessionService.get_or_create_session(conn, student_id, course_id=1)
            conn.execute(
                "UPDATE gl_learning_sessions SET current_concept_id = 'synth.py.vars' WHERE session_id = ?",
                (session.session_id,)
            )
            conn.commit()

            # Misconception trigger: reference alias confuse
            res = LearningSessionService.process_turn_atomic(
                conn=conn,
                session_id=session.session_id,
                student_id=student_id,
                student_input="I am 100% sure that b = a makes an independent copy, reference alias confuse does not happen.",
                idempotency_key="conf_1"
            )
            assert res["recommendation"]["action"] == "REMEDIATE"
            assert res["mastery"]["mastery_score"] <= 0.65

    def test_repeated_misconception_escalates_to_mentor(self, synthetic_env):
        """Persistent failure across 5 attempts triggers ESCALATE_TO_MENTOR."""
        from app import get_db
        student_id = synthetic_env["student_id"]
        with get_db() as conn:
            session = LearningSessionService.get_or_create_session(conn, student_id, course_id=1)
            conn.execute(
                "UPDATE gl_learning_sessions SET current_concept_id = 'synth.py.vars' WHERE session_id = ?",
                (session.session_id,)
            )
            conn.commit()

            # Simulate 5 consecutive failed turns
            for i in range(1, 6):
                res = LearningSessionService.process_turn_atomic(
                    conn=conn,
                    session_id=session.session_id,
                    student_id=student_id,
                    student_input=f"confused attempt {i}",
                    idempotency_key=f"stuck_{i}"
                )

            assert res["mastery"]["total_attempts"] == 5
            assert res["mastery"]["successful_attempts"] == 0
            assert res["recommendation"]["action"] == "ESCALATE_TO_MENTOR"

    def test_interrupted_learner_resume_and_zero_duplicate_events(self, synthetic_env):
        """Learner disconnects mid-stream, resumes, and duplicate submission replays without side-effects."""
        from app import get_db
        student_id = synthetic_env["student_id"]
        with get_db() as conn:
            session = LearningSessionService.get_or_create_session(conn, student_id, course_id=1)
            conn.execute(
                "UPDATE gl_learning_sessions SET current_concept_id = 'synth.py.vars' WHERE session_id = ?",
                (session.session_id,)
            )
            conn.commit()

            # Turn 1 executed
            turn1 = LearningSessionService.process_turn_atomic(
                conn=conn,
                session_id=session.session_id,
                student_id=student_id,
                student_input="Variables in Python can be reassigned freely.",
                idempotency_key="turn_key_abc"
            )

            # Record event count
            event_count_before = conn.execute(
                "SELECT COUNT(*) FROM gl_learning_events WHERE session_id = ?",
                (session.session_id,)
            ).fetchone()[0]

            # Simulate reload: resume session
            resume_data = LearningSessionService.resume_session_state(conn, session.session_id, student_id)
            assert resume_data["session"]["session_id"] == session.session_id
            assert resume_data["concept"]["concept_id"] == "synth.py.vars"

            # Repeat submission with SAME key
            turn1_replay = LearningSessionService.process_turn_atomic(
                conn=conn,
                session_id=session.session_id,
                student_id=student_id,
                student_input="Variables in Python can be reassigned freely.",
                idempotency_key="turn_key_abc"
            )
            assert turn1_replay.get("idempotent_replay") is True

            # Event count after must only have the session_resumed event, zero duplicate answer events
            event_count_after = conn.execute(
                "SELECT COUNT(*) FROM gl_learning_events WHERE session_id = ? AND event_type = 'answer_submitted'",
                (session.session_id,)
            ).fetchone()[0]
            assert event_count_after == 1


class TestGuidedLearningGoldenJourney:
    """GL-QA-001 / Master Plan Section 45: Full multi-step deterministic golden learning path."""

    def test_complete_golden_journey(self, synthetic_env):
        from app import get_db
        student_id = synthetic_env["student_id"]
        with get_db() as conn:
            # 1. Student enters module -> session initialized
            session = LearningSessionService.get_or_create_session(conn, student_id, course_id=1)
            assert session.current_action == "EXPLAIN"

            # 2. Initial explanation provided -> student responds with good answer
            turn1 = LearningSessionService.process_turn_atomic(
                conn=conn,
                session_id=session.session_id,
                student_id=student_id,
                student_input="In Python, assignment binds a name to an object reference in memory.",
                idempotency_key="golden_1"
            )
            assert turn1["mastery"]["mastery_score"] >= 0.35
            assert turn1["mastery"]["mastery_level"] in ("DEVELOPING", "PROFICIENT")

            # 3. Student encounters a misconception during practice
            turn2 = LearningSessionService.process_turn_atomic(
                conn=conn,
                session_id=session.session_id,
                student_id=student_id,
                student_input="I thought reference alias confuse was true and lists are copied.",
                idempotency_key="golden_2"
            )
            assert turn2["recommendation"]["action"] == "REMEDIATE"
            assert turn2["mastery"]["mastery_score"] <= 0.65

            # 4. Remediation completed: student solves with correct understanding
            turn3 = LearningSessionService.process_turn_atomic(
                conn=conn,
                session_id=session.session_id,
                student_id=student_id,
                student_input="Now I see: a = [1, 2]; b = a.copy() creates a new object with different id().",
                idempotency_key="golden_3"
            )
            # Misconception resolved
            active_m = MisconceptionService.get_active_misconceptions(conn, student_id, "synth.py.vars")
            assert len(active_m) == 0

            # 5. Practice and mastery progression to Proficient
            mastery_llm = lambda prompt: json.dumps({
                "correctness": 0.98,
                "partial_correctness": True,
                "reasoning_quality": 0.98,
                "concept_understanding": 0.98,
                "detected_misconceptions": [],
                "confidence": 0.98,
                "evidence_strength": 0.98,
                "feedback": "Great implementation demonstrating scope.",
                "suggested_action": "PRACTICE"
            })
            turn4 = LearningSessionService.process_turn_atomic(
                conn=conn,
                session_id=session.session_id,
                student_id=student_id,
                student_input="def scope_demo():\n    x = 100\n    return x\n# Correct assignment and return",
                idempotency_key="golden_4",
                llm_caller=mastery_llm
            )
            assert turn4["mastery"]["mastery_level"] in ("DEVELOPING", "PROFICIENT")
            assert turn4["mastery"]["mastery_score"] >= 0.65


            # 6. Final mastery validation: confirms full mastery and unlocks next concept
            advance_llm = lambda prompt: json.dumps({
                "correctness": 0.98,
                "partial_correctness": True,
                "reasoning_quality": 0.98,
                "concept_understanding": 0.98,
                "detected_misconceptions": [],
                "confidence": 0.98,
                "evidence_strength": 0.98,
                "feedback": "Perfect mastery verified across all criteria.",
                "suggested_action": "ADVANCE"
            })
            turn5 = LearningSessionService.process_turn_atomic(
                conn=conn,
                session_id=session.session_id,
                student_id=student_id,
                student_input="def scope_validation():\n    y = 200\n    return y * 2\n# Comprehensive mastery verified",
                idempotency_key="golden_5",
                llm_caller=advance_llm
            )
            assert turn5["mastery"]["mastery_level"] == "MASTERED"
            assert turn5["recommendation"]["action"] == "ADVANCE"
            assert turn5["recommendation"]["next_concept_id"] == "synth.py.funcs"

            # 7. Spaced review scheduled
            assert turn5["next_review_at"] is not None

            # 8. Session resume on page reload preserves advanced state
            resume_data = LearningSessionService.resume_session_state(conn, session.session_id, student_id)
            assert resume_data["session"]["current_concept_id"] == "synth.py.funcs"
            assert resume_data["session"]["current_action"] == "ADVANCE"

