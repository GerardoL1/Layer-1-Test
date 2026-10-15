"""
The API description the app's types are made from, and the response models behind it.

    python -m pytest -q tests/test_openapi.py
"""

import export_openapi
import main
from fastapi.testclient import TestClient

client = TestClient(main.app)


def test_openapi_json_is_up_to_date():
    saved = export_openapi.OUT.read_text(encoding="utf-8")
    assert saved == export_openapi.spec_text(), (
        "server/openapi.json is out of date. Run: python export_openapi.py, then npm run api-types in mobile/"
    )


def test_every_v1_endpoint_describes_its_response():
    for path, ops in main.app.openapi()["paths"].items():
        for method, op in ops.items():
            if op.get("deprecated") or path.endswith("/readings/shortcuts"):  # shortcuts replies in plain text
                continue
            ok = next(code for code in op["responses"] if code.startswith("2"))
            schema = op["responses"][ok].get("content", {}).get("application/json", {}).get("schema", {})
            assert schema not in ({}, {"type": "object"}), f"{method.upper()} {path} has no response model"


def test_a_user_without_nights_still_gets_valid_replies():
    user = "no_nights_yet"
    assert client.patch(f"/api/v1/users/{user}/settings", json={"age": 30}).status_code == 200
    today = client.get(f"/api/v1/users/{user}/today")
    assert today.status_code == 200
    assert today.json()["readiness"] is None and "verdict" not in today.json()  # keys not sent stay out
    trends = client.get(f"/api/v1/users/{user}/trends").json()
    assert trends == {"user_id": user, "nights": 14, "rows": []}
    profile = client.get(f"/api/v1/users/{user}/profile").json()
    assert profile["nights_total"] == 0 and profile["usual_ranges"] == []
