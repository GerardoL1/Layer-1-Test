"""
The readiness model and explainer interfaces: the placeholder behind them gives the same scores as before,
its contributions add up, and a different model or explainer drops in without touching the routers.

    python -m pytest -q tests/test_readiness_model.py
"""

import main
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.readiness import explain, model, scoring
from app.readiness.features import FEATURE_COLUMNS, build_features
from app.readiness.model import Contribution, ReadinessResult

client = TestClient(main.app)

ROW = {
    "z_hrv": -1.5,
    "z_rhr": 1.0,
    "z_tst": 0.5,
    "z_eff": float("nan"),
    "z_frag": 0.2,
    "usable_sleep": True,
    "hrv_night_ms": 41.2,
    "rhr_night_bpm": 58.0,
    "tst_min": 410.0,
    "fragmentation_per_hr": 1.1,
}


@pytest.fixture(scope="module")
def demo():
    for person in ("sam", "alex", "jordan"):
        assert client.post(f"/api/v1/demo-users/{person}").status_code == 200


def test_placeholder_model_gives_the_same_score_as_the_formula():
    result = scoring.PlaceholderModel().score(ROW)
    old = scoring.readiness(ROW)
    assert (result.score, result.status, result.z_count, result.placeholder) == (
        old["score"],
        old["status"],
        old["z_count"],
        old["placeholder"],
    )
    for row in ({"usable_sleep": True}, {"tst_min": 150.0, "flag_short_sleep": True}, {}):
        r = scoring.PlaceholderModel().score(row)
        assert r.status == scoring.readiness(row)["status"] and r.score is None and r.contributions == []


def test_contributions_add_up_to_the_score():
    result = scoring.PlaceholderModel().score(ROW)
    assert [c.input for c in result.contributions] == ["hrv", "rhr", "sleep", "fragmentation"]  # efficiency missing
    hrv = result.contributions[0]
    assert hrv.label == "Heart rate variability" and hrv.value == 41.2 and hrv.points < 0
    unclipped = scoring.READINESS_CENTER + sum(c.points for c in result.contributions)
    assert abs(unclipped - result.score) <= 0.6


@pytest.mark.parametrize(
    ("zs", "want"),
    [
        ({"z_hrv": 0.1, "z_rhr": 0.1, "z_tst": 0.1, "z_eff": 0.1, "z_frag": 0.1}, "high"),
        ({"z_hrv": 0.1, "z_tst": 0.1, "z_eff": 0.1}, "medium"),
        ({"z_rhr": 0.1, "z_tst": 0.1}, "low"),
        ({"z_tst": 0.1, "z_eff": 0.1, "z_frag": 0.1}, "sleep_only"),
        ({"usable_sleep": True}, None),
    ],
)
def test_placeholder_confidence(zs, want):
    assert scoring.PlaceholderModel().score(zs).confidence == want


def test_features_come_from_the_last_night_only_and_are_plain_json():
    history = pd.DataFrame([{**ROW, "tst_min": 300.0}, {**ROW, "flag_short_sleep": pd.NA}])
    history["flag_no_hrv"] = [True, False]
    f = build_features(history)
    assert set(f) == set(FEATURE_COLUMNS)
    assert f["tst_min"] == 410.0 and f["z_eff"] is None and f["flag_no_hrv"] is False
    assert f["hr_slot_count"] is None  # not in the history, so missing rather than 0


def test_unknown_model_setting_is_refused(monkeypatch):
    monkeypatch.setenv("READINESS_MODEL", "lightgbm-v1")
    with pytest.raises(ValueError, match="lightgbm-v1"):
        model.get_model()


def test_today_has_the_new_fields_and_trends_stays_light(demo):
    t = client.get("/api/v1/users/demo-alex/today").json()
    r = t["readiness"]
    assert r["model_version"] == "placeholder-1" and r["illness_flag"] is False and r["confidence"] == "high"
    assert {c["input"] for c in r["contributions"]} == {"hrv", "rhr", "sleep", "efficiency", "fragmentation"}
    assert t["advice"] and t["reason"].endswith(t["advice"])  # older apps still read it at the end of reason
    row = client.get("/api/v1/users/demo-alex/trends?nights=14").json()["rows"][-1]["readiness"]
    assert "contributions" not in row and row["model_version"] == "placeholder-1"


def test_a_different_model_drops_in_without_touching_the_routers(demo, monkeypatch):
    class Fake:
        version = "fake-1"
        method = "A test model."

        def score(self, features):
            return ReadinessResult(77, "ready", "medium", [Contribution("hrv", "HRV", 50.0, 9.0)], True, self.version)

    monkeypatch.setattr("app.routers.today.get_model", lambda: Fake())
    monkeypatch.setattr("app.routers.trends.get_model", lambda: Fake())
    t = client.get("/api/v1/users/demo-sam/today").json()
    assert t["readiness"]["score"] == 77 and t["readiness"]["illness_flag"] is True
    assert t["readiness_method"] == "A test model." and t["verdict"] == explain.VERDICT["ready"]
    rows = client.get("/api/v1/users/demo-sam/trends?nights=14").json()["rows"]
    assert {r["readiness"]["model_version"] for r in rows} == {"fake-1"}


def test_template_explainer_only_cites_rows_that_are_not_usual():
    result = ReadinessResult(30, "low", "high")
    metrics = [
        {"key": "hrv", "direction": "worse"},
        {"key": "rhr", "direction": "usual"},
        {"key": "sleep", "direction": "better"},
    ]
    text = explain.TemplateExplainer().today(result, metrics, {"min_nights": 7})
    assert "HRV" in text.reason and "resting heart rate" not in text.reason
    assert text.advice == explain.ADVICE["low"] and text.verdict == explain.VERDICT["low"]
