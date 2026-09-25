import pytest
from app import get_db
from tests.conftest import seed_intern, login_as_intern


def test_tasks_list_unauthenticated_redirects(app_client):
    client, db_path = app_client

    # 1. Unauthenticated browser visitor accessing /tasks
    resp = client.get("/tasks")
    assert resp.status_code == 302
    assert resp.headers.get("Location") == "/#signin"

    # Session cookie should store next target
    with client.session_transaction() as sess:
        assert sess.get("next") == "/tasks"

    # Following the redirect reaches homepage with #signin and flashed prompt
    follow_resp = client.get("/tasks", follow_redirects=True)
    assert follow_resp.status_code == 200
    assert b"Please sign in or sign up to view tasks." in follow_resp.data


def test_tasks_list_unauthenticated_json_returns_401(app_client):
    client, db_path = app_client

    # Accept: application/json returns 401
    resp = client.get("/tasks", headers={"Accept": "application/json"})
    assert resp.status_code == 401
    data = resp.get_json()
    assert data["status"] == "error"
    assert "Authentication required" in data["message"]


def test_task_detail_unauthenticated(app_client):
    client, db_path = app_client

    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO tasks (title, description, task_type, payment_type, coin_reward, submission_type, is_active)
            VALUES ('Sample Task', 'Do something great', 'general', 'coins', 25, 'url', 1)
        """)
        task_id = cur.lastrowid
        conn.commit()

    # Browser GET /tasks/<id> -> 302 to /#signin with next stashed
    resp = client.get(f"/tasks/{task_id}")
    assert resp.status_code == 302
    assert resp.headers.get("Location") == "/#signin"

    with client.session_transaction() as sess:
        assert sess.get("next") == f"/tasks/{task_id}"

    # JSON GET /tasks/<id> -> 401
    json_resp = client.get(f"/tasks/{task_id}", headers={"Accept": "application/json"})
    assert json_resp.status_code == 401
    data = json_resp.get_json()
    assert data["status"] == "error"
    assert "Authentication required" in data["message"]


def test_tasks_authenticated_access(app_client):
    client, db_path = app_client

    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO tasks (title, description, task_type, payment_type, coin_reward, submission_type, is_active)
            VALUES ('Python Micro-Task', 'Write test scripts', 'general', 'coins', 30, 'url', 1)
        """)
        task_id = cur.lastrowid
        conn.commit()

    # Log in as intern
    login_as_intern(client, db_path, email="task_auth_intern@test.com", password="SecurePassword123")

    # Access /tasks -> 200 HTML
    resp = client.get("/tasks")
    assert resp.status_code == 200
    assert b"Open Bounty Tasks" in resp.data
    assert b"Python Micro-Task" in resp.data

    # Access /tasks/<id> -> 200 JSON
    detail_resp = client.get(f"/tasks/{task_id}")
    assert detail_resp.status_code == 200
    data = detail_resp.get_json()
    assert data["status"] == "success"
    assert data["task"]["id"] == task_id
    assert data["task"]["title"] == "Python Micro-Task"


def test_tasks_post_login_redirect_flow(app_client):
    client, db_path = app_client

    seed_intern(db_path, email="return_intern@test.com", password="Password123!")

    # Unauthenticated visitor hits /tasks
    r1 = client.get("/tasks")
    assert r1.status_code == 302

    # Now logs in
    login_resp = client.post("/intern/login", json={
        "email": "return_intern@test.com",
        "password": "Password123!"
    })
    assert login_resp.status_code == 200
    login_data = login_resp.get_json()
    # Should redirect directly to stashed /tasks
    assert login_data.get("redirect") == "/tasks"
