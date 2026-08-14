"""Phase 16 验收测试：FastAPI 全量接口。

覆盖：Dashboard / Users / Items / Analysis / Models / Recommendations，
统一响应格式、页面参数校验、未知资源 404、非法算法 400。

运行：python -m pytest backend/tests/test_phase16_api.py -v
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

OK_CODE = 0


def _data(resp) -> dict:
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == OK_CODE
    assert "data" in body
    return body["data"]


# ---- Dashboard ----
def test_dashboard_overview():
    d = _data(client.get("/api/dashboard/overview"))
    for k in ("total_users", "active_users", "buying_users", "gmv_total", "order_count", "aov", "arpu"):
        assert k in d


def test_dashboard_user_trend():
    d = _data(client.get("/api/dashboard/user-trend"))
    assert "dau" in d and "mau" in d and "register_trend" in d


def test_dashboard_gmv_trend():
    d = _data(client.get("/api/dashboard/gmv-trend"))
    assert d["daily_trend"] and d["weekly_trend"] and d["monthly_trend"]


def test_dashboard_behavior_trend():
    d = _data(client.get("/api/dashboard/behavior-trend"))
    assert d["counts"] and d["rates"] and d["by_hour"]


def test_dashboard_funnel():
    d = _data(client.get("/api/dashboard/funnel"))
    assert len(d["stages"]) >= 4 and len(d["steps"]) == len(d["stages"])


def test_dashboard_retention():
    d = _data(client.get("/api/dashboard/retention"))
    assert d["overall"] and d["cohorts"]


# ---- Users ----
def test_users_list_and_pagination():
    d = _data(client.get("/api/users", params={"limit": 5, "offset": 0}))
    assert d["total"] > 0 and len(d["items"]) == 5
    assert set(d["items"][0]) >= {"user_id", "age", "gender", "city"}


def test_users_keyword():
    d = _data(client.get("/api/users", params={"keyword": "U000001"}))
    assert d["total"] >= 1 and d["items"][0]["user_id"] == "U000001"


def test_user_detail_profile_behaviors_orders():
    uid = "U000001"
    detail = _data(client.get(f"/api/users/{uid}"))
    assert detail["user_id"] == uid

    prof = _data(client.get(f"/api/users/{uid}/profile"))
    assert prof["user_id"] == uid and "behavior" in prof and "predictions" in prof

    beh = _data(client.get(f"/api/users/{uid}/behaviors", params={"limit": 5}))
    assert "items" in beh and beh["total"] >= 0

    orders = _data(client.get(f"/api/users/{uid}/orders"))
    assert "total_orders" in orders and "paid_gmv" in orders and "items" in orders

    # 购买/流失预测接口不抛错（可能为 None 表示该用户不在最新快照）
    _data(client.get(f"/api/users/{uid}/prediction"))


def test_user_not_found():
    resp = client.get("/api/users/U_NOT_EXIST")
    assert resp.status_code == 404
    assert resp.json()["code"] == 40400


# ---- Items ----
def test_items_list_and_ranking():
    d = _data(client.get("/api/items", params={"limit": 5}))
    assert d["total"] > 0 and len(d["items"]) == 5
    r = _data(client.get("/api/items/ranking", params={"top_n": 5}))
    assert len(r["items"]) <= 5 and r["categories"] and r["brands"]


def test_item_detail_and_statistics():
    iid = "I000001"
    d = _data(client.get(f"/api/items/{iid}"))
    assert d["item_id"] == iid and "statistics" in d
    s = _data(client.get(f"/api/items/{iid}/statistics"))
    assert s["item_id"] == iid


def test_item_not_found():
    resp = client.get("/api/items/I_NOT_EXIST")
    assert resp.status_code == 404


# ---- Analysis ----
def test_analysis_endpoints():
    for path in (
        "rfm", "lifecycle", "cohort", "path", "channel", "price",
        "association", "segments", "device", "findings", "meta",
    ):
        assert client.get(f"/api/analysis/{path}").status_code == 200, path


def test_analysis_unknown():
    resp = client.get("/api/analysis/not-exist")
    assert resp.status_code == 404


# ---- Models ----
def test_models_purchase_churn_metrics():
    p = _data(client.get("/api/models/purchase"))
    assert p["task"] == "purchase_prediction" and p["metrics"] and p["best_model"]

    c = _data(client.get("/api/models/churn", params={"limit": 5}))
    assert c["task"] == "churn_prediction" and len(c["predictions"]) <= 5

    m = _data(client.get("/api/models/metrics"))
    assert m["purchase"] and m["churn"] and m["recommendation"]["algorithms"]


# ---- Recommendations ----
def test_recommendation_single():
    d = _data(client.get("/api/recommendations/U000001", params={"algorithm": "popular", "top_k": 5}))
    assert d["algorithm"] == "popular" and 0 <= d["count"] <= 5
    if d["items"]:
        assert set(d["items"][0]) >= {"item_id", "score", "reason"}


def test_recommendation_compare_subset():
    d = _data(
        client.get(
            "/api/recommendations/U000001/compare",
            params={"algorithms": "popular,content,hybrid", "top_k": 5},
        )
    )
    assert set(d["results"]) >= {"popular", "content", "hybrid"}
    for alg, r in d["results"].items():
        assert r["count"] <= 5


def test_recommendation_invalid_algorithm():
    resp = client.get("/api/recommendations/U000001", params={"algorithm": "xxx"})
    assert resp.status_code == 400


def test_recommendation_invalid_top_k():
    # top_k=0 由 FastAPI Query(ge=1) 拦截，统一响应 code=42200
    resp = client.get("/api/recommendations/U000001", params={"top_k": 0})
    assert resp.status_code == 422
    assert resp.json()["code"] == 42200


def test_recommendation_metrics():
    d = _data(client.get("/api/recommendations/metrics"))
    assert d["algorithms"] and d["conclusion"]
    for row in d["algorithms"]:
        assert set(row) >= {"algorithm", "ndcg@k", "coverage@k"}


# ---- 统一响应 ----
def test_response_format():
    resp = client.get("/api/dashboard/overview")
    assert set(resp.json()) == {"code", "message", "data"}