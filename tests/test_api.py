from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "database" in data
    assert "schema" in data
    assert "migration" in data


def test_login_page():
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "欢迎回来" in resp.text


def test_dashboard_requires_auth():
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_charts_requires_auth():
    resp = client.get("/charts", follow_redirects=False)
    assert resp.status_code == 303


def test_job_runner_requires_auth():
    resp = client.get("/jobs/run", follow_redirects=False)
    assert resp.status_code == 303


def test_login_success():
    resp = client.post(
        "/login",
        data={"username": "admin", "password": "admin"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_job_runner_page_after_login():
    with TestClient(app) as authed_client:
        authed_client.post(
            "/login",
            data={"username": "admin", "password": "admin"},
            follow_redirects=False,
        )
        resp = authed_client.get("/jobs/run")
    assert resp.status_code == 200
    assert "触发任务" in resp.text
    assert "manual_backfill_range" in resp.text
