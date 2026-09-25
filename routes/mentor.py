"""
routes/mentor.py - Mentor Portal & Availability Routing Blueprint
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Endpoints:
- POST /mentors/slots/<int:slot_id>/book
"""
from flask import Blueprint, jsonify, request
from services.auth_service import AuthService
from app import (
    get_db, current_intern, is_enrolled_or_accepted,
    check_mentor_pacing, log_error
)

mentor_bp = Blueprint("mentor", __name__)


@mentor_bp.route("/mentors/slots/<int:slot_id>/book", methods=["POST"])
def intern_book_slot(slot_id):
    """Enrolls an active intern into a 1-on-1 mentor session with race condition prevention."""
    with get_db() as conn:
        intern = AuthService.current_intern(conn)
    if not intern:
        return jsonify({"status": "error", "message": "Authentication required"}), 401
    if not is_enrolled_or_accepted(intern["email"]):
        return jsonify({"status": "error", "message": "Internship enrollment required to book mentor sessions."}), 403

    try:
        with get_db() as conn:
            if not check_mentor_pacing(intern["id"]):
                return jsonify({
                    "status": "error",
                    "message": "You already have an active mentor session booked. Please complete or cancel your existing session before booking another."
                }), 400

            meeting_link = f"https://meet.google.com/dbert-mentor-slot-{slot_id}"
            res = conn.execute(
                "UPDATE mentor_availability_slots SET is_booked = 1 WHERE id = ? AND is_booked = 0",
                (slot_id,)
            )
            if res.rowcount == 0:
                return jsonify({"status": "error", "message": "Slot is no longer available."}), 400

            conn.execute(
                "INSERT INTO mentor_session_bookings (slot_id, intern_id, meeting_link, status) VALUES (?, ?, ?, 'booked')",
                (slot_id, intern["id"], meeting_link)
            )
            conn.commit()

        return jsonify({
            "status": "success",
            "message": "1-on-1 Mentor session booked successfully!",
            "meeting_link": meeting_link
        })
    except Exception as e:
        log_error("intern-book-slot", e)
        return jsonify({"status": "error", "message": "Failed to book mentor slot"}), 500
