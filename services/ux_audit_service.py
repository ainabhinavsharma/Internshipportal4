"""
Phase 17: UX Dead-End Audit Service.
Ensures every user-facing surface answers:
  1. Where am I? (Contextual title, breadcrumb, role identity)
  2. What can I do? (Clear primary and secondary actions)
  3. What happens next? (Explanatory state messages, progress indicators, empty state recovery links)

Errors must explain:
  - What happened
  - Why
  - What the user can do
"""

from typing import Dict, Any, List, Optional


ROLE_HOME_ROUTES: Dict[str, str] = {
    "visitor": "/",
    "intern": "/portal",
    "company": "/company",
    "mentor": "/mentor",
    "staff": "/staff/dashboard",
    "admin": "/admin",
}

ROLE_DASHBOARD_NAMES: Dict[str, str] = {
    "visitor": "Public Portal",
    "intern": "Intern Dashboard",
    "company": "Company Dashboard",
    "mentor": "Mentor Portal",
    "staff": "Staff Review Console",
    "admin": "Admin Control Center",
}

RECOVERY_ACTIONS: Dict[int, Dict[str, str]] = {
    400: {
        "what_happened": "Invalid or incomplete request",
        "why": "Some required form fields or query parameters were missing or incorrectly formatted.",
        "action": "Return to the form, verify your inputs, and submit again.",
    },
    401: {
        "what_happened": "Authentication required",
        "why": "You attempted to access a private area without an active session, or your session expired.",
        "action": "Please sign in with your email and password to continue.",
    },
    403: {
        "what_happened": "Access forbidden",
        "why": "Your account does not have permission to view this resource or perform this action.",
        "action": "Sign in with an authorized account or contact support if you believe this is an error.",
    },
    404: {
        "what_happened": "Page or resource not found",
        "why": "The link you followed may be broken, mistyped, or the resource has been removed.",
        "action": "Check the URL, return to the homepage, or browse open opportunities.",
    },
    410: {
        "what_happened": "Listing no longer available",
        "why": "The application deadline has passed or the company closed this position.",
        "action": "Browse currently live job and internship openings to discover active roles.",
    },
    413: {
        "what_happened": "Uploaded file is too large",
        "why": "The maximum allowed file upload size is 6 MB.",
        "action": "Compress your file or select a file under 6 MB and try uploading again.",
    },
    500: {
        "what_happened": "Unexpected server error",
        "why": "An internal error occurred while processing your request. The issue has been logged.",
        "action": "Please wait a few moments and refresh the page. Contact support if the problem persists.",
    },
}


def get_error_context(code: int, custom_message: Optional[str] = None) -> Dict[str, str]:
    """Returns structured explanations answering what happened, why, and what to do next."""
    info = RECOVERY_ACTIONS.get(code, RECOVERY_ACTIONS[500])
    return {
        "code": str(code),
        "what_happened": info["what_happened"],
        "why": info["why"],
        "action": info["action"],
        "message": custom_message or info["what_happened"],
    }


def get_role_home(role: str) -> str:
    """Returns the primary landing route for a specific user role."""
    return ROLE_HOME_ROUTES.get(role, "/")
