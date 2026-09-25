"""
services/interview_service.py - AI Pre-Selection Interview Domain Service
Fulfills Phase 23 (Monolith Modularization) of INTERNSHIPPORTAL4_LOCAL_AI_AGENT_MASTER_PLAN.md

Encapsulates:
1. Static blueprint question bank assembly across domains.
2. Candidate attempt eligibility checking and cooling period calculation.
3. Interview attempt persistence and answer submission handling.
"""
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

INTERVIEW_BLUEPRINT = [
    ("technical", 2), ("applied", 1), ("communication", 1),
]
INTERVIEW_DEFAULT_DOMAIN = "Python Automation"
INTERVIEW_DOMAIN_LABELS = {
    "AI Agent Development": "AI and agent development",
    "Data Analyst": "data analysis",
    "Full Stack Development": "web development",
    "Python Automation": "Python and automation",
}

INTERVIEW_DOMAIN_BANK = {
    "AI Agent Development": {
        "technical": [
            {"key": "ai_tech_01", "text": "In your own words, what is a large language model, and what does its 'context window' mean for building applications?"},
            {"key": "ai_tech_02", "text": "What is retrieval-augmented generation (RAG), and why might you use it instead of relying only on the model's built-in knowledge?"},
            {"key": "ai_tech_03", "text": "What's the difference between writing a good prompt and fine-tuning a model? When would you reach for each?"},
            {"key": "ai_tech_04", "text": "What are embeddings, and how are they useful when building an app that needs to search documents?"},
            {"key": "ai_tech_05", "text": "What does it mean for an AI agent to 'call a tool' or function, and why is that useful?"},
            {"key": "ai_tech_06", "text": "What is an LLM 'hallucination', and what are one or two practical ways to reduce it?"},
        ],
        "applied": [
            {"key": "ai_app_01", "text": "You're asked to build a support agent that answers questions from a company's PDF manuals. Outline the main steps you would take."},
            {"key": "ai_app_02", "text": "You need an agent that can read a user's email and book meetings on their calendar. How would you break that down?"},
            {"key": "ai_app_03", "text": "An AI feature you built sometimes gives confidently wrong answers. How would you investigate and improve it?"},
            {"key": "ai_app_04", "text": "You want to add a chatbot to a website that only answers questions about the product. How do you keep it on-topic?"},
        ],
        "communication": [
            {"key": "ai_comm_01", "text": "Explain, as you would to a non-technical friend, what an 'API key' is and why it must be kept secret."},
            {"key": "ai_comm_02", "text": "How would you explain to a customer, in plain language, why an AI assistant sometimes gets things wrong?"},
            {"key": "ai_comm_03", "text": "Explain what 'training data' is to someone who has never studied computer science."},
        ],
    },
    "Data Analyst": {
        "technical": [
            {"key": "da_tech_01", "text": "What is the difference between a SQL INNER JOIN and a LEFT JOIN? Give a simple example of when you'd use each."},
            {"key": "da_tech_02", "text": "How would you handle missing or null values in a dataset before analysis, and what trade-offs do your choices involve?"},
            {"key": "da_tech_03", "text": "What does GROUP BY do in SQL? Give an example of a question it helps you answer."},
            {"key": "da_tech_04", "text": "What is the difference between a primary key and a foreign key in a database?"},
            {"key": "da_tech_05", "text": "When would you use a bar chart versus a line chart versus a scatter plot to present data?"},
            {"key": "da_tech_06", "text": "What does it mean to 'clean' a dataset, and what are a few things you typically check for?"},
        ],
        "applied": [
            {"key": "da_app_01", "text": "Given a month of raw sales data, describe how you would find the top-performing products and present that insight to a manager."},
            {"key": "da_app_02", "text": "You receive a messy CSV of survey responses with inconsistent text and blanks. How do you make it analysis-ready?"},
            {"key": "da_app_03", "text": "A manager asks 'why did sales drop last week?' How would you approach answering that with data?"},
            {"key": "da_app_04", "text": "You're asked to build a simple weekly dashboard. What metrics would you include, and why?"},
        ],
        "communication": [
            {"key": "da_comm_01", "text": "Explain what a 'median' is and why it can be more useful than an 'average' in some situations, as if to someone new to data."},
            {"key": "da_comm_02", "text": "Explain the difference between correlation and causation to a manager, using a simple example."},
            {"key": "da_comm_03", "text": "How would you present a surprising finding to a team that expected the opposite result?"},
        ],
    },
    "Full Stack Development": {
        "technical": [
            {"key": "fs_tech_01", "text": "What happens, step by step, when a user types a URL into the browser and presses Enter?"},
            {"key": "fs_tech_02", "text": "What is the difference between client-side and server-side code? Give one example of work best done on each."},
            {"key": "fs_tech_03", "text": "What is the difference between a GET and a POST request, and when would you use each?"},
            {"key": "fs_tech_04", "text": "What is an API, and how does a front-end typically talk to a back-end?"},
            {"key": "fs_tech_05", "text": "What's the difference between a cookie, localStorage, and sessionStorage for keeping a user logged in?"},
            {"key": "fs_tech_06", "text": "What is a database, and why might you choose one over just storing data in files?"},
        ],
        "applied": [
            {"key": "fs_app_01", "text": "You need to build a simple to-do app where tasks persist after refresh. Describe the front-end, back-end, and storage pieces you'd use."},
            {"key": "fs_app_02", "text": "Design a login that keeps a user signed in across page refreshes. What pieces do you need?"},
            {"key": "fs_app_03", "text": "A page loads very slowly. How would you figure out why, and what would you try first?"},
            {"key": "fs_app_04", "text": "You're building a contact form that emails the team. Walk through what happens from submit to delivery."},
        ],
        "communication": [
            {"key": "fs_comm_01", "text": "Explain what an HTTP status code 404 vs 500 means, as you would to a teammate from a non-technical background."},
            {"key": "fs_comm_02", "text": "Explain what an 'API' is to someone who isn't a programmer."},
            {"key": "fs_comm_03", "text": "How would you explain to a client why their website needs both a front-end and a back-end?"},
        ],
    },
    "Python Automation": {
        "technical": [
            {"key": "py_tech_01", "text": "What is the difference between a list and a dictionary in Python, and when would you choose one over the other?"},
            {"key": "py_tech_02", "text": "How would you read a CSV file in Python and process each row? Mention any libraries you'd reach for."},
            {"key": "py_tech_03", "text": "What does try/except do in Python, and why is it important when automating tasks?"},
            {"key": "py_tech_04", "text": "What is a virtual environment, and why is it useful when working on Python projects?"},
            {"key": "py_tech_05", "text": "What is the difference between a list comprehension and a regular for-loop? When would you use each?"},
            {"key": "py_tech_06", "text": "What's the difference between a function and a variable, and why do we put code into functions?"},
        ],
        "applied": [
            {"key": "py_app_01", "text": "You're asked to automate renaming and sorting 500 files into folders by date. Describe your approach."},
            {"key": "py_app_02", "text": "You need to pull a daily report from a website and email it to your team automatically. How would you set that up?"},
            {"key": "py_app_03", "text": "A script you wrote works on your machine but fails on a colleague's. How would you track down why?"},
            {"key": "py_app_04", "text": "You want to fill out the same web form 100 times with data from a spreadsheet. How would you automate it?"},
        ],
        "communication": [
            {"key": "py_comm_01", "text": "Explain what a 'function' is and why we use them, as if teaching someone writing their first script."},
            {"key": "py_comm_02", "text": "Explain why hard-coding a password directly in a script is a bad idea, in plain terms."},
            {"key": "py_comm_03", "text": "How would you explain to a non-technical manager what 'automating a task' actually means?"},
        ],
    },
}


class InterviewService:
    """Pre-selection AI interview domain service."""

    @staticmethod
    def assemble_questions(domain: str, exclude_keys: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Assembles questions from static bank preserving blueprint section balance."""
        exclude = set(exclude_keys or ())
        dom = domain if domain in INTERVIEW_DOMAIN_BANK else INTERVIEW_DEFAULT_DOMAIN
        field = INTERVIEW_DOMAIN_LABELS.get(dom, "this field")
        picked = []
        for section, count in INTERVIEW_BLUEPRINT:
            pool = INTERVIEW_DOMAIN_BANK[dom].get(section, [])
            avail = [q for q in pool if q["key"] not in exclude]
            if len(avail) < count:
                avail = list(pool)
            for q in random.sample(avail, min(count, len(avail))):
                picked.append((section, q))

        out = []
        for i, (section, q) in enumerate(picked, start=1):
            out.append({
                "id": i,
                "type": section,
                "key": q["key"],
                "text": q["text"].replace("{field}", field)
            })
        return out

    @staticmethod
    def check_eligibility(conn, intern_id: int, max_attempts: int = 2, cooling_hours: int = 24) -> Dict[str, Any]:
        """Checks if intern is eligible for a new interview attempt or in cooling period."""
        rows = conn.execute(
            """
            SELECT id, created_at, status 
            FROM preselection_interviews 
            WHERE intern_id = ? 
            ORDER BY id DESC
            """,
            (intern_id,)
        ).fetchall()
        total_attempts = len(rows)

        if total_attempts >= max_attempts:
            return {
                "eligible": False,
                "reason": "Max attempts reached",
                "total_attempts": total_attempts
            }

        if total_attempts > 0:
            last_attempt = rows[0]
            try:
                last_time = datetime.strptime(last_attempt["created_at"], "%Y-%m-%d %H:%M:%S")
                diff_hours = (datetime.now() - last_time).total_seconds() / 3600.0
                if diff_hours < cooling_hours:
                    return {
                        "eligible": False,
                        "reason": f"Cooling period active ({round(cooling_hours - diff_hours, 1)} hours remaining)",
                        "remaining_hours": round(cooling_hours - diff_hours, 1),
                        "total_attempts": total_attempts
                    }
            except Exception:
                pass

        return {
            "eligible": True,
            "total_attempts": total_attempts
        }
