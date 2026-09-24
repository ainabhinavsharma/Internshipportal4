"""
Phase 16: Privacy & Field Classification Service.
Classifies all data fields across the platform into:
  - PUBLIC: Safe for unauthenticated visitors and general public display.
  - PRIVATE: PII and user-specific data accessible only to the owner or authorized staff/admin.
  - ADMIN_ONLY: Internal administrative, telemetry, and moderation notes.
  - SENSITIVE: Passwords, salts, security tokens that must NEVER be serialized or returned in any API response.
"""

from typing import Any, Dict, List, Optional, Set


class FieldClassification:
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    ADMIN_ONLY = "ADMIN_ONLY"
    SENSITIVE = "SENSITIVE"


# Universal blacklisted sensitive keys that must never appear in any response dictionary
SENSITIVE_KEYS: Set[str] = frozenset({
    "password_hash",
    "password",
    "salt",
    "token_hash",
    "secret_key",
    "api_key",
    "cron_secret",
})


FIELD_CLASSIFICATION_REGISTRY: Dict[str, Dict[str, str]] = {
    "intern_accounts": {
        "id": FieldClassification.PRIVATE,
        "name": FieldClassification.PUBLIC,
        "email": FieldClassification.PRIVATE,
        "phone": FieldClassification.PRIVATE,
        "city": FieldClassification.PRIVATE,
        "college": FieldClassification.PRIVATE,
        "course": FieldClassification.PRIVATE,
        "semester": FieldClassification.PRIVATE,
        "year_of_passing": FieldClassification.PRIVATE,
        "domain": FieldClassification.PRIVATE,
        "password_hash": FieldClassification.SENSITIVE,
        "password_set": FieldClassification.ADMIN_ONLY,
        "is_active": FieldClassification.ADMIN_ONLY,
        "signup_stage": FieldClassification.PRIVATE,
        "tutor_completion_pct": FieldClassification.PRIVATE,
        "learning_completion_pct": FieldClassification.PRIVATE,
        "created_at": FieldClassification.PRIVATE,
        "updated_at": FieldClassification.PRIVATE,
    },
    "companies": {
        "id": FieldClassification.PUBLIC,
        "name": FieldClassification.PUBLIC,
        "email": FieldClassification.PRIVATE,
        "phone": FieldClassification.PRIVATE,
        "website": FieldClassification.PUBLIC,
        "about": FieldClassification.PUBLIC,
        "password_hash": FieldClassification.SENSITIVE,
        "is_approved": FieldClassification.ADMIN_ONLY,
        "is_active": FieldClassification.ADMIN_ONLY,
        "created_at": FieldClassification.PUBLIC,
        "updated_at": FieldClassification.ADMIN_ONLY,
    },
    "applications": {
        "id": FieldClassification.PRIVATE,
        "name": FieldClassification.PRIVATE,
        "email": FieldClassification.PRIVATE,
        "phone": FieldClassification.PRIVATE,
        "city": FieldClassification.PRIVATE,
        "college": FieldClassification.PRIVATE,
        "course": FieldClassification.PRIVATE,
        "semester": FieldClassification.PRIVATE,
        "year_of_passing": FieldClassification.PRIVATE,
        "domain": FieldClassification.PRIVATE,
        "why_join": FieldClassification.PRIVATE,
        "portfolio": FieldClassification.PRIVATE,
        "status": FieldClassification.PRIVATE,
        "mentor_note": FieldClassification.ADMIN_ONLY,
        "mentor_email": FieldClassification.ADMIN_ONLY,
        "admin_note": FieldClassification.ADMIN_ONLY,
        "rejected_at": FieldClassification.PRIVATE,
        "created_at": FieldClassification.PRIVATE,
        "updated_at": FieldClassification.ADMIN_ONLY,
    },
    "enrollments": {
        "id": FieldClassification.PRIVATE,
        "application_id": FieldClassification.PRIVATE,
        "intern_id": FieldClassification.PRIVATE,
        "name": FieldClassification.PRIVATE,
        "email": FieldClassification.PRIVATE,
        "phone": FieldClassification.PRIVATE,
        "city": FieldClassification.PRIVATE,
        "college": FieldClassification.PRIVATE,
        "course": FieldClassification.PRIVATE,
        "semester": FieldClassification.PRIVATE,
        "year_of_passing": FieldClassification.PRIVATE,
        "domain": FieldClassification.PRIVATE,
        "joining_date": FieldClassification.PRIVATE,
        "batch_label": FieldClassification.PRIVATE,
        "payment_screenshot": FieldClassification.ADMIN_ONLY,
        "payment_status": FieldClassification.PRIVATE,
        "admin_note": FieldClassification.ADMIN_ONLY,
        "created_at": FieldClassification.PRIVATE,
        "updated_at": FieldClassification.ADMIN_ONLY,
    },
    "posts": {
        "id": FieldClassification.PUBLIC,
        "company_id": FieldClassification.PUBLIC,
        "post_type": FieldClassification.PUBLIC,
        "domain": FieldClassification.PUBLIC,
        "title": FieldClassification.PUBLIC,
        "slug": FieldClassification.PUBLIC,
        "description": FieldClassification.PUBLIC,
        "responsibilities": FieldClassification.PUBLIC,
        "skills": FieldClassification.PUBLIC,
        "location": FieldClassification.PUBLIC,
        "work_mode": FieldClassification.PUBLIC,
        "stipend_min": FieldClassification.PUBLIC,
        "stipend_max": FieldClassification.PUBLIC,
        "pay_period": FieldClassification.PUBLIC,
        "is_unpaid": FieldClassification.PUBLIC,
        "status": FieldClassification.PUBLIC,
        "created_at": FieldClassification.PUBLIC,
        "expires_at": FieldClassification.PUBLIC,
    },
    "post_applications": {
        "id": FieldClassification.PRIVATE,
        "post_id": FieldClassification.PRIVATE,
        "intern_id": FieldClassification.PRIVATE,
        "email": FieldClassification.PRIVATE,
        "comment": FieldClassification.PRIVATE,
        "cv_id": FieldClassification.PRIVATE,
        "status": FieldClassification.PRIVATE,
        "decision_note": FieldClassification.PRIVATE,
        "created_at": FieldClassification.PRIVATE,
    },
    "mentors": {
        "id": FieldClassification.PUBLIC,
        "name": FieldClassification.PUBLIC,
        "email": FieldClassification.PRIVATE,
        "domain": FieldClassification.PUBLIC,
        "password_hash": FieldClassification.SENSITIVE,
        "is_active": FieldClassification.ADMIN_ONLY,
        "created_at": FieldClassification.ADMIN_ONLY,
        "updated_at": FieldClassification.ADMIN_ONLY,
    },
    "staff_accounts": {
        "id": FieldClassification.ADMIN_ONLY,
        "name": FieldClassification.ADMIN_ONLY,
        "email": FieldClassification.ADMIN_ONLY,
        "password_hash": FieldClassification.SENSITIVE,
        "is_active": FieldClassification.ADMIN_ONLY,
        "created_at": FieldClassification.ADMIN_ONLY,
    },
    "intern_certificates": {
        "id": FieldClassification.ADMIN_ONLY,
        "intern_id": FieldClassification.PRIVATE,
        "course_id": FieldClassification.PUBLIC,
        "course_title": FieldClassification.PUBLIC,
        "cert_id": FieldClassification.PUBLIC,
        "email": FieldClassification.PRIVATE,
        "issued_at": FieldClassification.PUBLIC,
        "tier": FieldClassification.PUBLIC,
        "url": FieldClassification.PUBLIC,
    },
    "device_profiles": {
        "id": FieldClassification.ADMIN_ONLY,
        "visitor_id": FieldClassification.ADMIN_ONLY,
        "intern_id": FieldClassification.ADMIN_ONLY,
        "email": FieldClassification.ADMIN_ONLY,
        "ip_address": FieldClassification.SENSITIVE,
        "user_agent": FieldClassification.SENSITIVE,
        "screen_res": FieldClassification.ADMIN_ONLY,
        "timezone": FieldClassification.ADMIN_ONLY,
        "language": FieldClassification.ADMIN_ONLY,
        "device_type": FieldClassification.ADMIN_ONLY,
        "referrer": FieldClassification.ADMIN_ONLY,
        "intent_score": FieldClassification.ADMIN_ONLY,
        "created_at": FieldClassification.ADMIN_ONLY,
    },
}


def classify_field(entity_name: str, field_name: str) -> str:
    """Returns the FieldClassification for a specific entity attribute."""
    if field_name in SENSITIVE_KEYS:
        return FieldClassification.SENSITIVE

    entity_map = FIELD_CLASSIFICATION_REGISTRY.get(entity_name, {})
    return entity_map.get(field_name, FieldClassification.PRIVATE)


def strip_sensitive_fields(data: Any) -> Any:
    """
    Recursively inspects dicts and lists, stripping any key matching SENSITIVE_KEYS.
    Provides bulletproof defense against credential leakage.
    """
    if isinstance(data, dict):
        return {
            k: strip_sensitive_fields(v)
            for k, v in data.items()
            if k not in SENSITIVE_KEYS
        }
    if isinstance(data, list):
        return [strip_sensitive_fields(item) for item in data]
    return data


def mask_email(email: Optional[str]) -> str:
    """Masks email address PII, e.g., 'john.doe@example.com' -> 'j*****e@example.com'."""
    if not email or "@" not in email:
        return ""
    local_part, domain = email.strip().split("@", 1)
    if len(local_part) <= 2:
        masked_local = local_part[0] + "*"
    else:
        masked_local = local_part[0] + ("*" * (len(local_part) - 2)) + local_part[-1]
    return f"{masked_local}@{domain}"


def mask_phone(phone: Optional[str]) -> str:
    """Masks phone number PII, e.g., '9876543210' -> '******3210'."""
    if not phone:
        return ""
    digits = phone.strip()
    if len(digits) <= 4:
        return "****"
    return ("*" * (len(digits) - 4)) + digits[-4:]


def filter_fields(
    entity_name: str,
    data: Optional[Dict[str, Any]],
    viewer_role: str = "anonymous",
    is_owner: bool = False
) -> Dict[str, Any]:
    """
    Filters a data dictionary based on field classifications and viewer privileges:
      - SENSITIVE: Never included.
      - ADMIN_ONLY: Included only if viewer_role in ('admin', 'staff').
      - PRIVATE: Included if viewer_role in ('admin', 'staff') OR is_owner is True.
      - PUBLIC: Included for everyone.
    """
    if not data or not isinstance(data, dict):
        return {}

    cleaned: Dict[str, Any] = {}
    is_admin_or_staff = viewer_role in ("admin", "staff")

    for key, value in data.items():
        classification = classify_field(entity_name, key)

        if classification == FieldClassification.SENSITIVE:
            continue

        if classification == FieldClassification.ADMIN_ONLY:
            if is_admin_or_staff:
                cleaned[key] = value
            continue

        if classification == FieldClassification.PRIVATE:
            if is_admin_or_staff or is_owner:
                cleaned[key] = value
            continue

        if classification == FieldClassification.PUBLIC:
            cleaned[key] = value

    return cleaned


def serialize_public_certificate(cert_row: Dict[str, Any], recipient_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Serializes a certificate for public verification, ensuring no private PII or
    internal database IDs are leaked to the public internet.
    """
    name = recipient_name or cert_row.get("recipient_name") or cert_row.get("name") or "Verified Intern"
    return {
        "cert_id": cert_row.get("cert_id"),
        "name": name,
        "recipient_name": name,
        "course_title": cert_row.get("course_title"),
        "issued_at": (cert_row.get("issued_at") or "")[:10],
        "tier": cert_row.get("tier") or "standard",
        "status": "valid" if cert_row.get("cert_id") else "invalid",
    }


def serialize_public_company(company_row: Dict[str, Any]) -> Dict[str, Any]:
    """Serializes company profile for public listing pages without exposing phone or password_hash."""
    return {
        "id": company_row.get("id"),
        "name": company_row.get("name"),
        "website": company_row.get("website"),
        "about": company_row.get("about"),
    }


def serialize_public_post(post_row: Dict[str, Any], company_row: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Serializes job/internship post for public view without exposing internal operational data."""
    out = {
        "id": post_row.get("id"),
        "title": post_row.get("title"),
        "slug": post_row.get("slug"),
        "post_type": post_row.get("post_type"),
        "domain": post_row.get("domain"),
        "description": post_row.get("description"),
        "responsibilities": post_row.get("responsibilities"),
        "skills": post_row.get("skills"),
        "location": post_row.get("location"),
        "work_mode": post_row.get("work_mode"),
        "stipend_min": post_row.get("stipend_min"),
        "stipend_max": post_row.get("stipend_max"),
        "pay_period": post_row.get("pay_period"),
        "is_unpaid": post_row.get("is_unpaid"),
        "created_at": post_row.get("created_at"),
    }
    if company_row:
        out["company"] = serialize_public_company(company_row)
    elif "company_name" in post_row:
        out["company"] = {
            "name": post_row.get("company_name"),
            "website": post_row.get("company_website"),
        }
    return out
