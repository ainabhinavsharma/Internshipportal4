"""
routes/__init__.py - Central Blueprint Registration Hub
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Modularizes all route domains into cohesive Flask Blueprints.
"""
from routes.ambassador import ambassador_bp
from routes.auth import auth_bp
from routes.applications import applications_bp
from routes.enrollment import enrollment_bp
from routes.payment import payment_bp
from routes.marketplace import marketplace_bp
from routes.admin import admin_bp
from routes.mentor import mentor_bp
from routes.company import company_bp
from routes.intern import intern_bp
from routes.learning import learning_bp

ALL_BLUEPRINTS = [
    ambassador_bp,
    auth_bp,
    applications_bp,
    enrollment_bp,
    payment_bp,
    marketplace_bp,
    admin_bp,
    mentor_bp,
    company_bp,
    intern_bp,
    learning_bp,
]


def register_blueprints(app):
    """Registers all modular domain blueprints onto the core Flask app instance."""
    for bp in ALL_BLUEPRINTS:
        if bp.name not in app.blueprints:
            app.register_blueprint(bp)
