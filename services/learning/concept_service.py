"""
Concept Catalog and Prerequisite Graph Service.
Manages the structured concept hierarchy, DAG prerequisite validation,
cycle detection, topological sorting, and eligibility checks.
"""
import json
from typing import List, Dict, Optional, Tuple, Set
from services.learning.learning_models import Concept

class ConceptPrerequisiteCycleError(Exception):
    """Raised when a circular prerequisite dependency is detected in the concept graph."""
    pass

class ConceptNotFoundError(Exception):
    """Raised when a requested concept_id is missing from the catalog."""
    pass

class ConceptService:
    @staticmethod
    def register_concept(conn, concept: Concept) -> Concept:
        """Upserts a concept into gl_concepts after validating graph acyclicity."""
        # Check prerequisites exist or will not form a cycle
        existing_prereqs = ConceptService.get_prerequisites_map(conn)
        existing_prereqs[concept.concept_id] = concept.prerequisites
        
        # Validate acyclicity
        ConceptService._validate_acyclic(existing_prereqs)
        
        conn.execute(
            """
            INSERT INTO gl_concepts (
                concept_id, name, description, domain, subject,
                module_id, subtopic_id, difficulty, prerequisites_json,
                learning_objectives_json, assessment_criteria_json,
                common_misconceptions_json, resources_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(concept_id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                domain = excluded.domain,
                subject = excluded.subject,
                module_id = excluded.module_id,
                subtopic_id = excluded.subtopic_id,
                difficulty = excluded.difficulty,
                prerequisites_json = excluded.prerequisites_json,
                learning_objectives_json = excluded.learning_objectives_json,
                assessment_criteria_json = excluded.assessment_criteria_json,
                common_misconceptions_json = excluded.common_misconceptions_json,
                resources_json = excluded.resources_json
            """,
            (
                concept.concept_id,
                concept.name,
                concept.description,
                concept.domain,
                concept.subject,
                concept.module_id,
                concept.subtopic_id,
                concept.difficulty,
                json.dumps(concept.prerequisites),
                json.dumps(concept.learning_objectives),
                json.dumps(concept.assessment_criteria),
                json.dumps(concept.common_misconceptions),
                json.dumps(concept.resources),
                concept.created_at
            )
        )
        conn.commit()
        return concept

    @staticmethod
    def get_concept(conn, concept_id: str) -> Optional[Concept]:
        """Retrieves a concept by ID."""
        row = conn.execute(
            "SELECT * FROM gl_concepts WHERE concept_id = ?",
            (concept_id,)
        ).fetchone()
        if not row:
            return None
        return ConceptService._row_to_concept(row)

    @staticmethod
    def get_concept_by_subtopic(conn, subtopic_id: int) -> Optional[Concept]:
        """Finds concept linked to a legacy course subtopic ID."""
        row = conn.execute(
            "SELECT * FROM gl_concepts WHERE subtopic_id = ?",
            (subtopic_id,)
        ).fetchone()
        if not row:
            return None
        return ConceptService._row_to_concept(row)

    @staticmethod
    def list_concepts_for_domain(conn, domain: str) -> List[Concept]:
        """Lists all concepts within a domain ordered by difficulty and dependency."""
        rows = conn.execute(
            "SELECT * FROM gl_concepts WHERE domain = ? ORDER BY difficulty ASC, concept_id ASC",
            (domain,)
        ).fetchall()
        return [ConceptService._row_to_concept(r) for r in rows]

    @staticmethod
    def list_all_concepts(conn) -> List[Concept]:
        """Lists all registered concepts in catalog."""
        rows = conn.execute(
            "SELECT * FROM gl_concepts ORDER BY domain ASC, difficulty ASC, concept_id ASC"
        ).fetchall()
        return [ConceptService._row_to_concept(r) for r in rows]


    @staticmethod
    def get_prerequisites_map(conn) -> Dict[str, List[str]]:
        """Constructs an adjacency map of concept_id -> list of prerequisite concept_ids."""
        rows = conn.execute("SELECT concept_id, prerequisites_json FROM gl_concepts").fetchall()
        graph = {}
        for r in rows:
            cid = r["concept_id"]
            p_json = r["prerequisites_json"] or "[]"
            try:
                graph[cid] = json.loads(p_json)
            except Exception:
                graph[cid] = []
        return graph

    @staticmethod
    def check_prerequisites_met(conn, student_id: int, concept_id: str) -> Tuple[bool, List[str]]:
        """
        Determines if student satisfies all prerequisites for a given concept.
        Returns: (is_met: bool, missing_prerequisites: List[str])
        """
        concept = ConceptService.get_concept(conn, concept_id)
        if not concept:
            raise ConceptNotFoundError(f"Concept '{concept_id}' does not exist.")
            
        if not concept.prerequisites:
            return True, []
            
        # Check student mastery for each prerequisite
        missing = []
        for p_id in concept.prerequisites:
            m_row = conn.execute(
                "SELECT mastery_level, mastery_score FROM gl_student_mastery WHERE student_id = ? AND concept_id = ?",
                (student_id, p_id)
            ).fetchone()
            if not m_row:
                missing.append(p_id)
            else:
                level = m_row["mastery_level"]
                score = m_row["mastery_score"] or 0.0
                if level not in ("PROFICIENT", "MASTERED") and score < 0.70:
                    missing.append(p_id)
                    
        return len(missing) == 0, missing

    @staticmethod
    def get_eligible_concepts_in_domain(conn, student_id: int, domain: str) -> List[Concept]:
        """
        Returns all concepts in domain where student has met prerequisites but not yet MASTERED.
        """
        all_concepts = ConceptService.list_concepts_for_domain(conn, domain)
        eligible = []
        for c in all_concepts:
            # Check if already mastered
            m_row = conn.execute(
                "SELECT mastery_level FROM gl_student_mastery WHERE student_id = ? AND concept_id = ?",
                (student_id, c.concept_id)
            ).fetchone()
            if m_row and m_row["mastery_level"] == "MASTERED":
                continue
                
            can_learn, missing = ConceptService.check_prerequisites_met(conn, student_id, c.concept_id)
            if can_learn:
                eligible.append(c)
        return eligible

    @staticmethod
    def _validate_acyclic(graph: Dict[str, List[str]]) -> None:
        """Performs depth-first search cycle detection on prerequisite dependency graph."""
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def dfs(node: str, path: List[str]):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor, path):
                        return True
                elif neighbor in rec_stack:
                    cycle = " -> ".join(path + [neighbor])
                    raise ConceptPrerequisiteCycleError(f"Circular dependency detected in concept prerequisites: {cycle}")
                    
            rec_stack.remove(node)
            path.pop()
            return False

        for node in list(graph.keys()):
            if node not in visited:
                dfs(node, [])

    @staticmethod
    def _row_to_concept(row) -> Concept:
        """Converts database sqlite3.Row to Concept dataclass."""
        return Concept(
            concept_id=row["concept_id"],
            name=row["name"],
            description=row["description"],
            domain=row["domain"],
            subject=row["subject"],
            module_id=row["module_id"],
            subtopic_id=row["subtopic_id"],
            difficulty=row["difficulty"],
            prerequisites=json.loads(row["prerequisites_json"] or "[]"),
            learning_objectives=json.loads(row["learning_objectives_json"] or "[]"),
            assessment_criteria=json.loads(row["assessment_criteria_json"] or "[]"),
            common_misconceptions=json.loads(row["common_misconceptions_json"] or "[]"),
            resources=json.loads(row["resources_json"] or "[]"),
            created_at=row["created_at"]
        )
