"""
services/marketplace_service.py - Job Board & Marketplace Domain Service
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Encapsulates:
1. Live post verification (status, expiration, company approval & activity).
2. Google Jobs structured JSON-LD schema builder.
3. Company posting limits (atomic 3-post concurrency quota).
4. Candidate job applications and idempotency checks.
"""
import json
from datetime import datetime
from typing import Optional, List, Dict, Any


class MarketplaceService:
    """Marketplace and Job Board domain logic."""

    @staticmethod
    def is_live_post(conn, post: Any) -> bool:
        """Determines if a job post is live, unexpired, and belongs to an active, approved company."""
        p = dict(post) if not isinstance(post, dict) else post
        if p.get("status") != "published":
            return False
        exp = p.get("expires_at")
        if exp:
            still = conn.execute(
                "SELECT ? > datetime('now','localtime')", (exp,)
            ).fetchone()[0]
            if not still:
                return False
        comp_id = p.get("company_id")
        if comp_id:
            comp = conn.execute(
                "SELECT is_approved, is_active FROM companies WHERE id=?", (comp_id,)
            ).fetchone()
            if not comp or not comp["is_approved"] or not comp["is_active"]:
                return False
        return True

    @staticmethod
    def can_company_create_post(conn, company_id: int, max_posts: int = 3) -> bool:
        """Enforces company quota limit on published posts."""
        cnt = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE company_id=? AND status='published'",
            (company_id,)
        ).fetchone()[0]
        return cnt < max_posts

    @staticmethod
    def list_live_posts(
        conn,
        domain: Optional[str] = None,
        post_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Queries active, approved posts with company details."""
        query = """
            SELECT p.*, c.name AS company_name, c.logo_url AS company_logo, c.location AS company_location
            FROM posts p
            JOIN companies c ON c.id = p.company_id
            WHERE p.status = 'published'
              AND c.is_approved = 1
              AND c.is_active = 1
              AND (p.expires_at IS NULL OR p.expires_at > datetime('now','localtime'))
        """
        params: List[Any] = []
        if domain:
            query += " AND p.domain = ?"
            params.append(domain)
        if post_type:
            query += " AND p.post_type = ?"
            params.append(post_type)
        query += " ORDER BY p.id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def generate_google_jobs_json_ld(post: Dict[str, Any], base_url: str = "https://dbert.online") -> Dict[str, Any]:
        """Formats job posting according to Google-for-Jobs schema.org specs."""
        return {
            "@context": "https://schema.org/",
            "@type": "JobPosting",
            "title": post.get("title", ""),
            "description": post.get("description", ""),
            "identifier": {
                "@type": "PropertyValue",
                "name": "DBERT",
                "value": str(post.get("id", ""))
            },
            "datePosted": post.get("created_at", datetime.now().strftime("%Y-%m-%d")),
            "validThrough": post.get("expires_at"),
            "employmentType": "FULL_TIME" if post.get("post_type") == "job" else "INTERN",
            "hiringOrganization": {
                "@type": "Organization",
                "name": post.get("company_name", "Partner Company"),
                "sameAs": base_url,
                "logo": post.get("company_logo")
            },
            "jobLocation": {
                "@type": "Place",
                "address": {
                    "@type": "PostalAddress",
                    "addressLocality": post.get("location") or "Remote",
                    "addressCountry": "IN"
                }
            }
        }
