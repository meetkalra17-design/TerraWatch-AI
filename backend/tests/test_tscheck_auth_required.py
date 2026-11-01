"""Criterion: Backend API integration - 401 without session, login works, me reflects user."""


def test_me_requires_auth(client):
    r = client.get("/auth/me")
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"


def test_analyses_requires_auth(client):
    r = client.get("/analyses")
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"


def test_login_wrong_password_rejected(client):
    r = client.post("/auth/login", json={"email": "operator@terrawatch.ai", "password": "wrongpass"})
    assert r.status_code in (400, 401), f"expected 4xx, got {r.status_code}: {r.text[:200]}"


def test_login_success_sets_cookie_and_me_works(client):
    r = client.post(
        "/auth/login",
        json={"email": "operator@terrawatch.ai", "password": "Terra@2026"},
    )
    assert r.status_code == 200, f"login failed: {r.status_code}: {r.text[:300]}"
    token = r.cookies.get("tw_session")
    assert token, "no session cookie set"

    # Cookie is set with Secure=True by the server; httpx's cookiejar drops it on
    # plain-http re-requests, so forward it explicitly via the Cookie header
    # (equivalent to what a real https browser session would send automatically).
    me = client.get("/auth/me", headers={"Cookie": f"tw_session={token}"})
    assert me.status_code == 200, f"me failed after login: {me.status_code}: {me.text[:200]}"
    body = me.json()
    assert body.get("email") == "operator@terrawatch.ai", f"unexpected /me body: {body}"