"""
Grounded RAG Tutor with Canonical Curriculum Fallback for Guided Learning 2.0.
Retrieves authoritative curriculum context, prevents curriculum hallucination,
and injects deterministic pedagogical instructions aligned with the active learning action.
"""
from typing import Dict, Any, List, Optional
from services.learning.learning_models import Concept
from services.learning.concept_service import ConceptService

class GroundedRAGTutor:
    @staticmethod
    def retrieve_grounded_context(
        conn,
        concept: Concept,
        student_query: str
    ) -> Dict[str, Any]:
        """
        Retrieves canonical learning material for the concept.
        Tracks retrieval source and ensures zero hallucinated curriculum facts.
        """
        context_items = []
        source = "concept_catalog"

        # 1. Authoritative Concept Criteria
        context_items.append(f"CONCEPT NAME: {concept.name}")
        context_items.append(f"CONCEPT DEFINITION: {concept.description}")

        if concept.learning_objectives:
            obj_str = "; ".join(concept.learning_objectives)
            context_items.append(f"LEARNING OBJECTIVES: {obj_str}")

        if concept.assessment_criteria:
            crit_str = "; ".join(concept.assessment_criteria)
            context_items.append(f"ASSESSMENT CRITERIA: {crit_str}")

        # 2. Associated legacy course subtopic material (if linked)
        if concept.subtopic_id:
            sub = conn.execute(
                "SELECT title, brief, key_takeaways_json, prompt_seed FROM course_subtopics WHERE id = ?",
                (concept.subtopic_id,)
            ).fetchone()
            if sub:
                source = "subtopic_material"
                if sub["brief"]:
                    context_items.append(f"LESSON SUMMARY: {sub['brief']}")
                if sub["prompt_seed"]:
                    context_items.append(f"CANONICAL GUIDELINES: {sub['prompt_seed']}")

        # 3. Common Misconceptions to avoid
        if concept.common_misconceptions:
            misc_notes = []
            for m in concept.common_misconceptions:
                misc_notes.append(f"Clarification: {m.get('name', 'Issue')} - {m.get('description', '')} (Resolution: {m.get('remediation', '')})")
            context_items.append("PEDAGOGICAL NUANCES TO EMPHASIZE:\n" + "\n".join(misc_notes))

        grounded_text = "\n\n".join(context_items)

        return {
            "source": source,
            "grounded_text": grounded_text,
            "retrieval_success": True
        }

    @staticmethod
    def build_tutor_prompt(
        student_name: str,
        concept: Concept,
        action: str,
        grounded_context: str,
        conversation_history: List[str],
        current_input: str,
        target_misconception: Optional[str] = None
    ) -> str:
        """
        Builds the complete grounded system and dialogue prompt for the AI Tutor.
        """
        first_name = (student_name or "Intern").strip().split()[0]

        # Action-specific pedagogical guidance
        action_guidelines = {
            "EXPLAIN": f"Explain the core intuition of {concept.name} to {first_name}. Use clear paragraphs and real-world engineering motivation. Conclude with an active comprehension question.",
            "SIMPLIFY": f"{first_name} is finding this difficult. Strip away complex jargon. Use an everyday analogy first, then explain the concept step-by-step. Keep it concise.",
            "GIVE_EXAMPLE": f"Provide clean, well-commented, idiomatic code illustrating {concept.name}. Walk through each line and ask {first_name} how they would modify it.",
            "ASK_GUIDED_QUESTION": f"Ask {first_name} a scaffolded, thought-provoking question to test understanding of the criteria for {concept.name}.",
            "PRACTICE": f"Give {first_name} an active coding challenge or problem prompt to solve. Do NOT reveal the solution in your answer.",
            "REMEDIATE": f"Address the specific misunderstanding: '{target_misconception}'. Gently point out where common intuition breaks down and guide {first_name} to the correct model.",
            "RETEST": f"Give a fresh problem to verify that {first_name} has overcome the previous confusion.",
            "REVIEW": f"Welcome {first_name} to their spaced repetition review. Ask a quick refresher challenge on {concept.name}.",
            "ADVANCE": f"Congratulate {first_name} on mastering {concept.name}! Introduce the next concept in their learning journey.",
            "ESCALATE_TO_MENTOR": f"Assure {first_name} that engineering mentors are here to help. Explain that a mentor will follow up and provide an encouraging recap."
        }

        directive = action_guidelines.get(action, action_guidelines["ASK_GUIDED_QUESTION"])

        history_formatted = "\n".join(conversation_history[-8:]) if conversation_history else "(Beginning of tutoring session)"

        return f"""<system_identity>
You are the 1-on-1 AI Engineering Mentor for DBERT's Internship Program.
Your student is {first_name}. You are encouraging, rigorous, and completely grounded in the canonical curriculum.
Communicate with clean Markdown, bold terms, and language-tagged code blocks (```python, ```javascript, etc.).
NEVER invent false curriculum facts. Stay anchored to the provided canonical material.
</system_identity>

<canonical_curriculum_grounding>
{grounded_context}
</canonical_curriculum_grounding>

<pedagogical_mission>
CURRENT ACTION: {action}
DIRECTIVE: {directive}
</pedagogical_mission>

<recent_dialogue>
{history_formatted}
</recent_dialogue>

<current_student_message>
{current_input}
</current_student_message>

Respond to {first_name} now following your pedagogical directive:"""
