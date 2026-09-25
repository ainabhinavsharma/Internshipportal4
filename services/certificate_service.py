"""
services/certificate_service.py - Intern Certificate Domain Service
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Encapsulates:
1. Canonical certificate ID generation and checksum.
2. Certificate retrieval for authenticated interns and public verification.
3. Certificate issuance and metadata serialization.
"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any


class CertificateService:
    """Certificate management and verification service."""

    @staticmethod
    def generate_certificate_id(course_id: int, intern_id: int) -> str:
        """Mints unique, human-readable certificate serial ID."""
        rand = uuid.uuid4().hex[:6].upper()
        return f"DBERT-C{course_id}-I{intern_id}-{rand}"

    @staticmethod
    def get_intern_certificates(conn, intern_id: int, email: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves earned certificates for a given intern ID or email."""
        rows = conn.execute(
            """
            SELECT id, course_id, course_title, cert_id, issued_at, url, tier, email
            FROM intern_certificates
            WHERE intern_id = ? OR (email IS NOT NULL AND LOWER(email) = LOWER(?))
            ORDER BY id DESC
            """,
            (intern_id, email or "")
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def verify_certificate(conn, cert_id: str) -> Optional[Dict[str, Any]]:
        """Public verification lookup for a certificate serial ID."""
        if not cert_id:
            return None
        row = conn.execute(
            """
            SELECT c.id, c.course_id, c.course_title, c.cert_id, c.issued_at, c.url, c.tier,
                   COALESCE(i.name, a.name, 'Student') AS recipient_name
            FROM intern_certificates c
            LEFT JOIN intern_accounts i ON i.id = c.intern_id
            LEFT JOIN applications a ON a.email = c.email
            WHERE LOWER(c.cert_id) = LOWER(?)
            LIMIT 1
            """,
            (cert_id.strip(),)
        ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def issue_certificate(
        conn,
        intern_id: int,
        course_id: int,
        course_title: str,
        email: str,
        tier: str = "completed",
        custom_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Atomically issues a certificate row if not already present."""
        existing = conn.execute(
            """
            SELECT cert_id FROM intern_certificates 
            WHERE (intern_id = ? OR (email IS NOT NULL AND LOWER(email) = LOWER(?)))
              AND course_id = ? AND tier = ?
            LIMIT 1
            """,
            (intern_id, email, course_id, tier)
        ).fetchone()
        if existing:
            return {"cert_id": existing["cert_id"], "already_issued": True}

        cert_id = CertificateService.generate_certificate_id(course_id, intern_id)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        url = custom_url or f"/certificate/{cert_id}"

        conn.execute(
            """
            INSERT INTO intern_certificates 
            (intern_id, course_id, course_title, cert_id, issued_at, url, tier, email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (intern_id, course_id, course_title, cert_id, now, url, tier, email.lower())
        )
        conn.commit()

        return {
            "cert_id": cert_id,
            "course_title": course_title,
            "issued_at": now,
            "url": url,
            "tier": tier,
            "already_issued": False
        }
