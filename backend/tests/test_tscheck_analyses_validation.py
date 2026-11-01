"""Criterion: POST /api/analyses rejects non-image with 400; GET /api/analyses/{bad} 404."""

import io


def _auth_headers(client):
    r = client.post(
        "/auth/login",
        json={"email": "operator@terrawatch.ai", "password": "Terra@2026"},
    )
    assert r.status_code == 200, f"login failed: {r.status_code}: {r.text[:200]}"
    token = r.cookies.get("tw_session")
    assert token, "no session cookie returned from login"
    # Server sets the cookie Secure=True; httpx's cookiejar drops it on plain-http
    # re-requests, so forward it explicitly (a real https browser sends it automatically).
    return {"Cookie": f"tw_session={token}"}


def test_create_analysis_rejects_non_image(client):
    headers = _auth_headers(client)
    files = {
        "before": ("before.txt", io.BytesIO(b"not an image"), "text/plain"),
        "after": ("after.txt", io.BytesIO(b"not an image"), "text/plain"),
    }
    data = {
        "region": "tscheck-bad-upload",
        "lat": "10.0",
        "lng": "20.0",
        "before_date": "2024-01-01",
        "after_date": "2024-02-01",
        "scene_area_km2": "50",
        "population_density": "500",
    }
    r = client.post("/analyses", files=files, data=data, headers=headers)
    assert r.status_code == 400, f"expected 400 for non-image upload, got {r.status_code}: {r.text[:300]}"


def test_get_analysis_not_found(client):
    headers = _auth_headers(client)
    r = client.get("/analyses/tscheck-nonexistent-id-00000", headers=headers)
    assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text[:200]}"