"""
routes/learning.py - Guided Learning 2.0 & Course Learning Blueprint
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Endpoints:
- POST /api/learning/v2/session
- POST /api/learning/v2/turn
- GET  /api/learning/v2/reviews-due
- GET  /api/learning/v2/concept-tree/<int:course_id>
"""
from flask import Blueprint, jsonify, request
from app import get_db, current_intern
from services.learning.concept_service import ConceptService
from services.learning.mastery_policy import MasteryPolicy
from services.learning.session_service import LearningSessionService
from services.learning.spaced_review import SpacedReviewScheduler

learning_bp = Blueprint("learning", __name__)


@learning_bp.route("/api/learning/v2/session", methods=["POST"])
def api_learning_v2_session():
    """Initializes or resumes a persistent Guided Learning 2.0 session."""
    intern = current_intern()
    if not intern:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    course_id = data.get("course_id")
    subtopic_id = data.get("subtopic_id")

    if not course_id:
        return jsonify({"status": "error", "message": "course_id is required"}), 400

    with get_db() as conn:
        enrollment = conn.execute(
            "SELECT id FROM course_enrollments WHERE (intern_id = ? OR (email IS NOT NULL AND LOWER(email) = LOWER(?))) AND course_id = ?",
            (intern["id"], intern.get("email") or "", course_id)
        ).fetchone()
        if not enrollment:
            return jsonify({"status": "error", "message": "Not enrolled in this course"}), 403

        session_obj = LearningSessionService.get_or_create_session(conn, intern["id"], course_id, subtopic_id)
        state = LearningSessionService.resume_session_state(conn, session_obj.session_id, intern["id"])

    return jsonify({"status": "success", "data": state})


@learning_bp.route("/api/learning/v2/turn", methods=["POST"])
def api_learning_v2_turn():
    """Executes a single atomic learning turn with structured evaluation and mastery update."""
    intern = current_intern()
    if not intern:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    message = (data.get("message") or "").strip()
    idempotency_key = data.get("idempotency_key")

    if not session_id or not message:
        return jsonify({"status": "error", "message": "session_id and message are required"}), 400

    with get_db() as conn:
        turn_result = LearningSessionService.process_turn_atomic(
            conn=conn,
            session_id=session_id,
            student_id=intern["id"],
            student_input=message,
            idempotency_key=idempotency_key
        )

    return jsonify({"status": "success", "data": turn_result})


@learning_bp.route("/api/learning/v2/reviews-due", methods=["GET"])
def api_learning_v2_reviews_due():
    """Lists concepts scheduled for spaced repetition review."""
    intern = current_intern()
    if not intern:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    with get_db() as conn:
        due = SpacedReviewScheduler.get_due_reviews_for_student(conn, intern["id"])

    return jsonify({"status": "success", "count": len(due), "reviews": due})


@learning_bp.route("/api/learning/v2/concept-tree/<int:course_id>", methods=["GET"])
def api_learning_v2_concept_tree(course_id):
    """Returns domain concept DAG with student's current mastery levels."""
    intern = current_intern()
    if not intern:
        return jsonify({"status": "error", "message": "Authentication required"}), 401

    with get_db() as conn:
        course = conn.execute("SELECT domain FROM courses WHERE id = ?", (course_id,)).fetchone()
        if not course:
            return jsonify({"status": "error", "message": "Course not found"}), 404

        concepts = ConceptService.list_concepts_for_domain(conn, course["domain"])

        tree_nodes = []
        for c in concepts:
            m = MasteryPolicy.get_or_create_mastery(conn, intern["id"], c.concept_id)
            tree_nodes.append({
                "concept_id": c.concept_id,
                "name": c.name,
                "difficulty": c.difficulty,
                "subject": c.subject,
                "subtopic_id": c.subtopic_id,
                "prerequisites": c.prerequisites,
                "mastery_score": m.mastery_score,
                "mastery_level": m.mastery_level,
                "total_attempts": m.total_attempts,
                "next_review_at": m.next_review_at
            })

    return jsonify({"status": "success", "course_id": course_id, "domain": course["domain"], "concepts": tree_nodes})
