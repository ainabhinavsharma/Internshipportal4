"""
Guided Learning 2.0 Data Models and Database Schema.
Defines tables, indices, and dataclasses for:
- Concepts and Prerequisite Graph
- Student Mastery State (scoped to student_id + concept_id)
- Durable Learning Events (Audit & Replay Ledger)
- Learning Sessions (Reload Tolerance & State Resume)
- Misconception Catalog
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import json
import uuid
from typing import List, Dict, Optional, Any

SCHEMA_SQL = """
-- 1. Concept Hierarchy & Prerequisite Graph
CREATE TABLE IF NOT EXISTS gl_concepts (
    concept_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    domain TEXT NOT NULL,
    subject TEXT NOT NULL,
    module_id INTEGER,
    subtopic_id INTEGER,
    difficulty INTEGER DEFAULT 1,
    prerequisites_json TEXT DEFAULT '[]',
    learning_objectives_json TEXT DEFAULT '[]',
    assessment_criteria_json TEXT DEFAULT '[]',
    common_misconceptions_json TEXT DEFAULT '[]',
    resources_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gl_concepts_domain ON gl_concepts(domain);
CREATE INDEX IF NOT EXISTS idx_gl_concepts_subtopic ON gl_concepts(subtopic_id);

-- 2. Student Mastery State (scoped strictly to student_id + concept_id)
CREATE TABLE IF NOT EXISTS gl_student_mastery (
    student_id INTEGER NOT NULL,
    concept_id TEXT NOT NULL,
    mastery_score REAL DEFAULT 0.0,
    mastery_level TEXT DEFAULT 'NOVICE',
    confidence REAL DEFAULT 0.0,
    learning_velocity REAL DEFAULT 1.0,
    total_attempts INTEGER DEFAULT 0,
    successful_attempts INTEGER DEFAULT 0,
    consecutive_successes INTEGER DEFAULT 0,
    misconceptions_json TEXT DEFAULT '[]',
    last_evidence_json TEXT DEFAULT '{}',
    last_interaction_at TEXT,
    last_review_at TEXT,
    next_review_at TEXT,
    review_interval_days REAL DEFAULT 1.0,
    review_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (student_id, concept_id),
    FOREIGN KEY (concept_id) REFERENCES gl_concepts(concept_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_gl_mastery_student ON gl_student_mastery(student_id);
CREATE INDEX IF NOT EXISTS idx_gl_mastery_review ON gl_student_mastery(student_id, next_review_at);
CREATE INDEX IF NOT EXISTS idx_gl_mastery_level ON gl_student_mastery(student_id, mastery_level);

-- 3. Durable Learning Events Ledger (Audit, Telemetry & Replay)
CREATE TABLE IF NOT EXISTS gl_learning_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_uuid TEXT UNIQUE NOT NULL,
    student_id INTEGER NOT NULL,
    concept_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gl_events_student ON gl_learning_events(student_id);
CREATE INDEX IF NOT EXISTS idx_gl_events_session ON gl_learning_events(session_id);
CREATE INDEX IF NOT EXISTS idx_gl_events_concept ON gl_learning_events(concept_id);
CREATE INDEX IF NOT EXISTS idx_gl_events_type ON gl_learning_events(event_type);

-- 4. Learning Sessions (State Resume, Refresh Resilient & Idempotent)
CREATE TABLE IF NOT EXISTS gl_learning_sessions (
    session_id TEXT PRIMARY KEY,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    subtopic_id INTEGER,
    current_concept_id TEXT,
    current_action TEXT DEFAULT 'EXPLAIN',
    action_state_json TEXT DEFAULT '{}',
    idempotency_key TEXT,
    status TEXT DEFAULT 'active',
    last_heartbeat_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gl_sessions_student ON gl_learning_sessions(student_id, status);
CREATE INDEX IF NOT EXISTS idx_gl_sessions_course ON gl_learning_sessions(student_id, course_id);

-- 5. Diagnostic Misconception Catalog
CREATE TABLE IF NOT EXISTS gl_misconception_catalog (
    misconception_id TEXT PRIMARY KEY,
    concept_id TEXT NOT NULL,
    label TEXT NOT NULL,
    pattern_description TEXT NOT NULL,
    remediation_strategy TEXT NOT NULL,
    example_trigger TEXT,
    FOREIGN KEY (concept_id) REFERENCES gl_concepts(concept_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_gl_misconception_concept ON gl_misconception_catalog(concept_id);
"""

def init_learning_tables(conn) -> None:
    """Idempotently executes table creation and indexes for Guided Learning 2.0."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


@dataclass
class Concept:
    concept_id: str
    name: str
    description: str
    domain: str
    subject: str
    module_id: Optional[int] = None
    subtopic_id: Optional[int] = None
    difficulty: int = 1
    prerequisites: List[str] = field(default_factory=list)
    learning_objectives: List[str] = field(default_factory=list)
    assessment_criteria: List[str] = field(default_factory=list)
    common_misconceptions: List[Dict[str, Any]] = field(default_factory=list)
    resources: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StudentMastery:
    student_id: int
    concept_id: str
    mastery_score: float = 0.0
    mastery_level: str = "NOVICE"  # NOVICE, DEVELOPING, PROFICIENT, MASTERED
    confidence: float = 0.0
    learning_velocity: float = 1.0
    total_attempts: int = 0
    successful_attempts: int = 0
    consecutive_successes: int = 0
    misconceptions: List[Dict[str, Any]] = field(default_factory=list)
    last_evidence: Dict[str, Any] = field(default_factory=dict)
    last_interaction_at: Optional[str] = None
    last_review_at: Optional[str] = None
    next_review_at: Optional[str] = None
    review_interval_days: float = 1.0
    review_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LearningEvent:
    student_id: int
    concept_id: str
    session_id: str
    event_type: str
    payload: Dict[str, Any]
    event_uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LearningSession:
    session_id: str
    student_id: int
    course_id: int
    subtopic_id: Optional[int] = None
    current_concept_id: Optional[str] = None
    current_action: str = "EXPLAIN"
    action_state: Dict[str, Any] = field(default_factory=dict)
    idempotency_key: Optional[str] = None
    status: str = "active"
    last_heartbeat_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
