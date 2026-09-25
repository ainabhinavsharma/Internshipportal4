"""
Structured Evaluator for Guided Learning 2.0.
Produces schema-validated evaluation results:
- correctness (0.0 - 1.0)
- partial correctness (bool)
- reasoning quality (0.0 - 1.0)
- concept understanding (0.0 - 1.0)
- detected misconceptions (list)
- evaluator confidence (0.0 - 1.0)
- evidence strength (0.0 - 1.0)
- student feedback & suggested action

Provides a robust deterministic fallback when LLM output is unavailable or invalid.
"""
from dataclasses import dataclass, field, asdict
import json
import re
from typing import List, Dict, Optional, Any, Callable
from services.learning.learning_models import Concept

@dataclass
class EvaluationResult:
    correctness: float  # 0.0 to 1.0
    partial_correctness: bool
    reasoning_quality: float  # 0.0 to 1.0
    concept_understanding: float  # 0.0 to 1.0
    detected_misconceptions: List[str] = field(default_factory=list)
    confidence: float = 0.8  # 0.0 to 1.0
    evidence_strength: float = 0.8  # 0.0 to 1.0
    feedback: str = ""
    suggested_action: str = "PRACTICE"
    is_fallback: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StructuredEvaluator:
    @staticmethod
    def evaluate(
        student_response: str,
        concept: Concept,
        expected_criteria: Optional[List[str]] = None,
        conversation_context: Optional[List[str]] = None,
        llm_caller: Optional[Callable[[str], str]] = None
    ) -> EvaluationResult:
        """
        Evaluates a student response against concept assessment criteria.
        Attempts schema-validated LLM evaluation, falling back gracefully to deterministic heuristics.
        """
        criteria = expected_criteria or concept.assessment_criteria or concept.learning_objectives
        cleaned_response = (student_response or "").strip()

        # If empty or trivial response
        if not cleaned_response:
            return EvaluationResult(
                correctness=0.0,
                partial_correctness=False,
                reasoning_quality=0.0,
                concept_understanding=0.0,
                detected_misconceptions=[],
                confidence=1.0,
                evidence_strength=1.0,
                feedback="Please provide an answer or explanation to demonstrate your understanding.",
                suggested_action="EXPLAIN",
                is_fallback=True
            )

        if llm_caller:
            try:
                prompt = StructuredEvaluator._build_eval_prompt(cleaned_response, concept, criteria, conversation_context)
                raw_output = llm_caller(prompt)
                parsed = StructuredEvaluator._parse_and_validate_json(raw_output)
                if parsed:
                    return parsed
            except Exception:
                # LLM execution failed or returned invalid schema -> proceed to deterministic fallback
                pass

        # Deterministic Fallback Engine
        return StructuredEvaluator._fallback_evaluation(cleaned_response, concept, criteria)

    @staticmethod
    def _build_eval_prompt(
        student_response: str,
        concept: Concept,
        criteria: List[str],
        context: Optional[List[str]]
    ) -> str:
        criteria_list = "\n".join(f"- {c}" for c in criteria)
        misconceptions = "\n".join(
            f"- ID: {m.get('id', 'MISC')}, Name: {m.get('name', '')}, Description: {m.get('description', '')}"
            for m in concept.common_misconceptions
        ) if concept.common_misconceptions else "None specified"
        
        history_str = "\n".join(context[-4:]) if context else "(None)"

        return f"""You are a precise pedagogical evaluation engine. Evaluate the student response against the concept criteria.
Output MUST be a single valid JSON object with NO extra text, markdown ticks, or markdown code blocks.

<concept>
ID: {concept.concept_id}
Name: {concept.name}
Description: {concept.description}
Assessment Criteria:
{criteria_list}
Known Misconceptions:
{misconceptions}
</concept>

<recent_dialogue>
{history_str}
</recent_dialogue>

<student_response>
{student_response}
</student_response>

Return ONLY a valid JSON object matching this exact schema:
{{
  "correctness": <float between 0.0 and 1.0>,
  "partial_correctness": <true/false>,
  "reasoning_quality": <float between 0.0 and 1.0>,
  "concept_understanding": <float between 0.0 and 1.0>,
  "detected_misconceptions": [<list of matching misconception IDs, or empty list>],
  "confidence": <float between 0.0 and 1.0>,
  "evidence_strength": <float between 0.0 and 1.0>,
  "feedback": "<concise constructive feedback to learner>",
  "suggested_action": "<EXPLAIN | SIMPLIFY | GIVE_EXAMPLE | PRACTICE | REMEDIATE | ADVANCE>"
}}
"""

    @staticmethod
    def _parse_and_validate_json(raw_text: str) -> Optional[EvaluationResult]:
        """Extracts and validates JSON schema from LLM text."""
        if not raw_text:
            return None
            
        # Strip potential markdown fences
        cleaned = re.sub(r"^```(json)?\s*", "", raw_text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"```$", "", cleaned.strip(), flags=re.MULTILINE).strip()
        
        # Locate outer JSON object
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
            return None
            
        json_str = cleaned[start_idx:end_idx + 1]
        try:
            data = json.loads(json_str)
        except Exception:
            return None

        # Validate required fields
        required = ["correctness", "reasoning_quality", "concept_understanding"]
        if not all(k in data for k in required):
            return None

        def clamp(val, low=0.0, high=1.0) -> float:
            try:
                return max(low, min(high, float(val)))
            except (ValueError, TypeError):
                return low

        correctness = clamp(data.get("correctness", 0.0))
        reasoning = clamp(data.get("reasoning_quality", 0.0))
        understanding = clamp(data.get("concept_understanding", 0.0))
        confidence = clamp(data.get("confidence", 0.8))
        evidence = clamp(data.get("evidence_strength", 0.8))
        partial = bool(data.get("partial_correctness", correctness >= 0.4))
        
        misc = data.get("detected_misconceptions")
        if not isinstance(misc, list):
            misc = []
        detected_misc = [str(m).strip() for m in misc if str(m).strip()]

        feedback = str(data.get("feedback") or "").strip()
        action = str(data.get("suggested_action") or "PRACTICE").strip().upper()
        if action not in ("EXPLAIN", "SIMPLIFY", "GIVE_EXAMPLE", "PRACTICE", "REMEDIATE", "ADVANCE"):
            action = "PRACTICE" if correctness >= 0.7 else "SIMPLIFY"

        return EvaluationResult(
            correctness=correctness,
            partial_correctness=partial,
            reasoning_quality=reasoning,
            concept_understanding=understanding,
            detected_misconceptions=detected_misc,
            confidence=confidence,
            evidence_strength=evidence,
            feedback=feedback,
            suggested_action=action,
            is_fallback=False
        )

    @staticmethod
    def _fallback_evaluation(
        response: str,
        concept: Concept,
        criteria: List[str]
    ) -> EvaluationResult:
        """
        Deterministic heuristic fallback when LLM is unavailable or outputs malformed data.
        Uses criteria token matching, structural patterns, and misconception triggers.
        """
        resp_lower = response.lower()
        word_tokens = set(re.findall(r"\w+", resp_lower))

        # Check for explicit confusion indicators
        confusion_signals = ["don't understand", "dont understand", "confused", "no idea", "what is this", "idk", "help me"]
        if any(sig in resp_lower for sig in confusion_signals):
            return EvaluationResult(
                correctness=0.1,
                partial_correctness=False,
                reasoning_quality=0.1,
                concept_understanding=0.1,
                detected_misconceptions=[],
                confidence=0.9,
                evidence_strength=0.7,
                feedback="You indicated confusion. Let's break this concept down with a simpler example.",
                suggested_action="SIMPLIFY",
                is_fallback=True
            )

        # Normalized stemming for coding criteria matching
        def stem(w: str) -> str:
            w = w.lower()
            for suffix in ("ing", "ion", "ed", "es", "s"):
                if w.endswith(suffix) and len(w) > len(suffix) + 2:
                    return w[:-len(suffix)]
            return w

        stemmed_tokens = {stem(w) for w in word_tokens}
        stemmed_tokens.update(word_tokens)

        # Include criteria, learning objectives, and misconception remediations for semantic coverage
        all_criteria = list(criteria)
        if concept.learning_objectives:
            all_criteria.extend(concept.learning_objectives)
        for m in concept.common_misconceptions:
            if m.get("remediation"):
                all_criteria.append(m["remediation"])


        matched_criteria_count = 0
        total_criteria = max(1, len(all_criteria))
        for c in all_criteria:
            c_raw = set(re.findall(r"\w+", c.lower())) - {"the", "a", "an", "is", "in", "and", "to", "of", "for", "with", "correct", "valid"}
            c_stemmed = {stem(w) for w in c_raw}
            if (c_raw and len(c_raw & word_tokens) > 0) or (c_stemmed and len(c_stemmed & stemmed_tokens) > 0):
                matched_criteria_count += 1

        coverage = matched_criteria_count / total_criteria

        # Check code block presence (valuable signal for programming concepts)
        has_code = "```" in response or "def " in response or "class " in response or "=" in response or "import " in response

        # Check length & reasoning indicators (e.g., "because", "therefore", "since", "so that", "which causes")
        has_reasoning = any(r_word in resp_lower for r_word in ["because", "therefore", "since", "so that", "returns", "output", "executes", "binds", "assign"])
        
        # Calculate scores
        base_score = 0.40 + (coverage * 0.40)
        if has_code:
            base_score += 0.12
        if has_reasoning:
            base_score += 0.10
        base_score = max(0.1, min(0.98, base_score))


        reasoning_score = 0.8 if has_reasoning else (0.5 if len(word_tokens) > 15 else 0.3)
        understanding_score = base_score

        # Check misconception triggers
        detected_misconceptions = []
        for m in concept.common_misconceptions:
            m_trigger = (m.get("trigger") or m.get("name") or "").lower()
            if m_trigger and m_trigger in resp_lower:
                m_id = m.get("id") or m.get("name") or "MISC"
                detected_misconceptions.append(m_id)

        if detected_misconceptions:
            base_score = min(base_score, 0.5)
            suggested_action = "REMEDIATE"
            feedback = f"Identified a key conceptual nuance to clarify regarding {concept.name}."
        elif base_score >= 0.75:
            suggested_action = "ADVANCE"
            feedback = f"Excellent demonstration of {concept.name}."
        elif base_score >= 0.45:
            suggested_action = "PRACTICE"
            feedback = f"Good grasp of {concept.name}. Let's do another practical challenge."
        else:
            suggested_action = "SIMPLIFY"
            feedback = f"Let's review the core mechanics of {concept.name}."

        return EvaluationResult(
            correctness=round(base_score, 2),
            partial_correctness=base_score >= 0.4,
            reasoning_quality=round(reasoning_score, 2),
            concept_understanding=round(understanding_score, 2),
            detected_misconceptions=detected_misconceptions,
            confidence=0.75,
            evidence_strength=0.70,
            feedback=feedback,
            suggested_action=suggested_action,
            is_fallback=True
        )
