"""
Misconception Detection and Catalog Service.
Maintains known misconceptions, tags active misconceptions on student mastery records,
caps mastery scores while active flaws exist, and records resolutions.
"""
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any

class MisconceptionService:
    @staticmethod
    def register_misconception(
        conn,
        misconception_id: str,
        concept_id: str,
        label: str,
        pattern_description: str,
        remediation_strategy: str,
        example_trigger: Optional[str] = None
    ) -> Dict[str, Any]:
        """Registers a diagnostic misconception pattern in the catalog."""
        conn.execute(
            """
            INSERT INTO gl_misconception_catalog (
                misconception_id, concept_id, label, pattern_description, remediation_strategy, example_trigger
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(misconception_id) DO UPDATE SET
                concept_id = excluded.concept_id,
                label = excluded.label,
                pattern_description = excluded.pattern_description,
                remediation_strategy = excluded.remediation_strategy,
                example_trigger = excluded.example_trigger
            """,
            (misconception_id, concept_id, label, pattern_description, remediation_strategy, example_trigger)
        )
        conn.commit()
        return {
            "misconception_id": misconception_id,
            "concept_id": concept_id,
            "label": label,
            "pattern_description": pattern_description,
            "remediation_strategy": remediation_strategy,
            "example_trigger": example_trigger
        }

    @staticmethod
    def get_misconceptions_for_concept(conn, concept_id: str) -> List[Dict[str, Any]]:
        """Retrieves all registered misconceptions for a concept."""
        rows = conn.execute(
            "SELECT * FROM gl_misconception_catalog WHERE concept_id = ?",
            (concept_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def attach_misconception(
        conn,
        student_id: int,
        concept_id: str,
        misconception_id: str,
        trigger_context: str
    ) -> List[Dict[str, Any]]:
        """
        Attaches an active misconception to the student's mastery profile.
        Deduplicates if already active.
        """
        m_row = conn.execute(
            "SELECT misconceptions_json FROM gl_student_mastery WHERE student_id = ? AND concept_id = ?",
            (student_id, concept_id)
        ).fetchone()
        
        current_list = []
        if m_row and m_row["misconceptions_json"]:
            try:
                current_list = json.loads(m_row["misconceptions_json"])
            except Exception:
                current_list = []
                
        # Check if already present and active
        for item in current_list:
            if item.get("misconception_id") == misconception_id and not item.get("resolved"):
                item["occurrence_count"] = item.get("occurrence_count", 1) + 1
                item["last_triggered_at"] = datetime.now(timezone.utc).isoformat()
                item["latest_context"] = trigger_context
                break
        else:
            # New active misconception
            current_list.append({
                "misconception_id": misconception_id,
                "first_detected_at": datetime.now(timezone.utc).isoformat(),
                "last_triggered_at": datetime.now(timezone.utc).isoformat(),
                "occurrence_count": 1,
                "resolved": False,
                "trigger_context": trigger_context
            })
            
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE gl_student_mastery
            SET misconceptions_json = ?, updated_at = ?
            WHERE student_id = ? AND concept_id = ?
            """,
            (json.dumps(current_list), now_iso, student_id, concept_id)
        )
        conn.commit()
        return current_list

    @staticmethod
    def resolve_misconception(
        conn,
        student_id: int,
        concept_id: str,
        misconception_id: str,
        resolution_evidence: str
    ) -> List[Dict[str, Any]]:
        """Marks an active misconception as successfully remediated."""
        m_row = conn.execute(
            "SELECT misconceptions_json FROM gl_student_mastery WHERE student_id = ? AND concept_id = ?",
            (student_id, concept_id)
        ).fetchone()
        
        current_list = []
        if m_row and m_row["misconceptions_json"]:
            try:
                current_list = json.loads(m_row["misconceptions_json"])
            except Exception:
                current_list = []
                
        for item in current_list:
            if item.get("misconception_id") == misconception_id:
                item["resolved"] = True
                item["resolved_at"] = datetime.now(timezone.utc).isoformat()
                item["resolution_evidence"] = resolution_evidence
                
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE gl_student_mastery
            SET misconceptions_json = ?, updated_at = ?
            WHERE student_id = ? AND concept_id = ?
            """,
            (json.dumps(current_list), now_iso, student_id, concept_id)
        )
        conn.commit()
        return current_list

    @staticmethod
    def get_active_misconceptions(conn, student_id: int, concept_id: str) -> List[Dict[str, Any]]:
        """Returns currently unresolved misconceptions for the given student & concept."""
        m_row = conn.execute(
            "SELECT misconceptions_json FROM gl_student_mastery WHERE student_id = ? AND concept_id = ?",
            (student_id, concept_id)
        ).fetchone()
        if not m_row or not m_row["misconceptions_json"]:
            return []
        try:
            items = json.loads(m_row["misconceptions_json"])
            return [m for m in items if not m.get("resolved")]
        except Exception:
            return []
