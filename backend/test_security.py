"""Security regression tests. Run from backend/:  APP_ENV=development python -m pytest test_security.py
The heavy RAG dependency is stubbed so the tests need only the light requirements."""
import os
import sys
import types
import tempfile

os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'test.db')}"
os.environ["SEED_DEMO_USERS"] = "true"
os.environ["DEMO_PASSWORD"] = "a-long-demo-password-1"

rag_stub = types.ModuleType("rag.pipeline")
rag_stub.rag_client = types.SimpleNamespace(search=lambda *a, **k: [])
sys.modules["rag"] = types.ModuleType("rag")
sys.modules["rag.pipeline"] = rag_stub

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

DEMO_PW = os.environ["DEMO_PASSWORD"]


def login(client, username, password=DEMO_PW):
    return client.post("/auth/login", json={"username": username, "password": password})


def auth(client, username):
    token = login(client, username).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_everything():
    with TestClient(main.app) as c:
        # no token -> 401 on protected endpoints (previously fell back to the first user)
        for path in ["/children", "/sessions", "/audit-logs"]:
            assert c.get(path).status_code == 401, path
        assert c.get("/sessions/00000000-0000-0000-0000-000000000000").status_code == 401
        assert c.get("/sessions/00000000-0000-0000-0000-000000000000/report").status_code == 401
        assert c.delete("/admin/reset-all-data").status_code == 401

        # forged / garbage tokens rejected
        assert c.get("/children", headers={"Authorization": "Bearer poc-token-admin"}).status_code == 401

        # login needs the correct password; unknown role/email is not a login
        assert login(c, "admin", "wrong-password").status_code == 401
        assert login(c, "admin").status_code == 200
        assert login(c, "nobody").status_code == 401
        assert login(c, "specialist", "").status_code == 401

        # role enforcement: parent cannot hit admin endpoints
        parent = auth(c, "parent")
        assert c.get("/audit-logs", headers=parent).status_code == 403
        assert c.delete("/admin/reset-all-data", headers=parent).status_code == 403
        assert c.get("/audit-logs", headers=auth(c, "admin")).status_code == 200

        # nobody can self-register as admin/specialist
        r = c.post("/auth/register", json={"username": "evil", "password": "long-enough-pass", "role": "admin"})
        assert r.status_code == 403
        r = c.post("/auth/register", json={"username": "okparent", "password": "long-enough-pass", "role": "parent"})
        assert r.status_code == 200
        assert c.post("/auth/register", json={"username": "x", "password": "short", "role": "parent"}).status_code == 422

        # parents only see their own children
        child = {"name": "Test Child", "dob": "2022-01-01", "gender": "male"}
        r = c.post("/children", json=child, headers=parent)
        assert r.status_code == 200, r.text
        child_id = r.json()["id"]
        other = {"Authorization": "Bearer " + login(c, "okparent", "long-enough-pass").json()["access_token"]}
        assert c.get("/children", headers=other).json() == []
        assert len(c.get("/children", headers=parent).json()) == 1
        assert len(c.get("/children", headers=auth(c, "specialist")).json()) == 1
        # another parent cannot open a session on someone else's child
        r = c.post("/sessions", json={"child_id": child_id, "onboarding_specialties": ["speech"]}, headers=other)
        assert r.status_code == 404

        # brute force lockout after 5 failures
        for _ in range(5):
            login(c, "teacher", "bad")
        assert login(c, "teacher").status_code == 429

        # docs hidden outside development are controlled by APP_ENV; security headers present
        assert c.get("/children", headers=parent).headers["x-content-type-options"] == "nosniff"
